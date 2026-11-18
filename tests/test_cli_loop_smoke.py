"""Wiring smoke test for lab/cli_loop.py: every loop subcommand parses and dispatches to its own cmd_* function.

Wiring only. No command body runs, so nothing touches the printer, the network or any project file.
"""
import argparse

import pytest

from lab import cli, cli_loop

# Every leaf command cli_loop.register() adds, by its path on the command line, and the function it must run.
# Spelled out by hand on purpose: a renamed or re-pointed command should fail here, not silently follow the code.
EXPECTED = {
    ("migrate",): "cmd_migrate",
    ("question",): "cmd_question",
    ("photos",): "cmd_photos",
    ("capability",): "cmd_capability",
    ("setup",): "cmd_setup",
    ("case",): "cmd_case",
    ("exp", "plan"): "cmd_exp_plan",
    ("exp", "build"): "cmd_exp_build",
    ("exp", "check"): "cmd_exp_check",
    ("exp", "start"): "cmd_exp_start",
    ("exp", "approve"): "cmd_exp_approve",
    ("exp", "criteria"): "cmd_exp_criteria",
    ("exp", "send"): "cmd_exp_send",
    ("exp", "stage"): "cmd_exp_stage",
    ("exp", "abandon"): "cmd_exp_abandon",
    ("exp", "observe"): "cmd_exp_observe",
    ("exp", "verdict"): "cmd_exp_verdict",
    ("exp", "usage"): "cmd_exp_usage",
    ("exp", "link"): "cmd_exp_link",
    ("exp", "measured"): "cmd_exp_measured",
    ("exp", "unlink"): "cmd_exp_unlink",
    ("exp", "verify"): "cmd_exp_verify",
    ("exp", "telemetry"): "cmd_exp_telemetry",
    ("exp", "log"): "cmd_exp_log",
    ("exp", "tag"): "cmd_exp_tag",
}

# Commands whose minimal argv cannot be derived from the parser alone (none today); path -> full argv after the path.
HAND_WRITTEN_ARGV: dict[tuple[str, ...], list[str]] = {}


def _fresh_parser():
    p = argparse.ArgumentParser(prog="lab")
    sub = p.add_subparsers(dest="cmd", required=True)
    cli_loop.register(sub)
    return p, sub


def _subparsers_action(parser):
    acts = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    return acts[0] if acts else None


def _leaves(parser, path=()):
    """Yield (path, leaf parser) for every command with no sub-commands of its own."""
    action = _subparsers_action(parser)
    if action is None:
        yield path, parser
        return
    for name, child in action.choices.items():
        yield from _leaves(child, path + (name,))


def _value(action):
    if action.choices:
        return str(next(iter(action.choices)))
    return "1" if action.type in (int, float) else "x"


def _minimal_argv(parser):
    """The smallest argv that satisfies the parser: required positionals, then required options."""
    argv = []
    for a in parser._actions:
        if isinstance(a, (argparse._HelpAction, argparse._SubParsersAction)):
            continue
        if not a.option_strings:
            if a.nargs in (None, "+") or isinstance(a.nargs, int):
                argv += [_value(a)] * (a.nargs if isinstance(a.nargs, int) else 1)
        elif a.required:
            argv += [a.option_strings[0], _value(a)]
    return argv


def _parse(parser, path, leaf):
    argv = list(path) + HAND_WRITTEN_ARGV.get(path, _minimal_argv(leaf))
    return parser.parse_args(argv)


def test_every_loop_command_is_listed():
    parser, _ = _fresh_parser()
    assert {path for path, _leaf in _leaves(parser)} == set(EXPECTED)


@pytest.mark.parametrize("path", sorted(EXPECTED))
def test_loop_command_parses_and_dispatches_to_its_own_function(path):
    parser, _ = _fresh_parser()
    leaf = dict(_leaves(parser))[path]
    args = _parse(parser, path, leaf)
    assert callable(args.fn)
    assert args.fn is getattr(cli_loop, EXPECTED[path])


def test_every_cmd_function_is_wired_to_a_command():
    wired = set(EXPECTED.values())
    defined = {n for n in vars(cli_loop) if n.startswith("cmd_") and callable(getattr(cli_loop, n))}
    assert defined == wired


def test_no_loop_command_name_is_registered_twice():
    parser, _ = _fresh_parser()
    paths = [path for path, _leaf in _leaves(parser)]
    assert len(paths) == len(set(paths)) == len(EXPECTED)
    # argparse (3.11+) already refuses a duplicate name at registration; registering again on the same
    # parent must raise, which proves the guard this test relies on is live.
    _, sub = _fresh_parser()
    with pytest.raises(argparse.ArgumentError):
        cli_loop.register(sub)


def test_loop_commands_do_not_collide_with_the_rest_of_lab_cli(monkeypatch):
    """cli.main builds the whole parser, loop commands included; a name clash makes argparse raise here."""
    seen = {}

    def capture(self, args=None, namespace=None):
        seen["parser"] = self
        raise SystemExit(0)

    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", capture)
    with pytest.raises(SystemExit):
        cli.main(["migrate"])
    top = _subparsers_action(seen["parser"]).choices
    loop_top = {path[0] for path in EXPECTED}
    assert loop_top <= set(top)
    # the loop's top-level names must resolve to the loop's own parsers, not another module's
    fresh, _ = _fresh_parser()
    for name in loop_top:
        assert top[name].get_default("fn") is _subparsers_action(fresh).choices[name].get_default("fn")


def test_register_has_no_side_effects(monkeypatch, tmp_path):
    """register() only builds parsers. LAB_HOME points at an empty tmp dir and network/subprocess calls are
    made to fail, so any file, printer or network access would show up as an error or a new file."""
    import socket
    import subprocess

    def boom(*a, **k):
        raise AssertionError("register() must not touch the network or run a process")

    monkeypatch.setenv("LAB_HOME", str(tmp_path))
    monkeypatch.setattr(socket, "create_connection", boom)
    monkeypatch.setattr(socket.socket, "connect", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)
    _fresh_parser()
    assert list(tmp_path.iterdir()) == []


def _project_parser(default="hex-tile"):
    """The parser shape lab.cli.main builds: a top-level --project, then the loop subcommands."""
    p = argparse.ArgumentParser(prog="lab")
    p.add_argument("--project", default=default)
    sub = p.add_subparsers(dest="cmd", required=True)
    cli_loop.register(sub)
    return p


@pytest.mark.parametrize("path", sorted(EXPECTED))
def test_top_level_project_survives_the_subcommand(path):
    parser = _project_parser()
    leaf = dict(_leaves(parser))[path]
    argv = list(path) + _minimal_argv(leaf)
    assert parser.parse_args(["--project", "other"] + argv).project == "other"
    assert parser.parse_args(argv).project == "hex-tile"
    if any("--project" in a.option_strings for a in leaf._actions):
        assert parser.parse_args(argv + ["--project", "mine"]).project == "mine"
        assert parser.parse_args(["--project", "other"] + argv + ["--project", "mine"]).project == "mine"


def test_main_honours_top_level_project_and_lab_project(monkeypatch):
    seen = []
    monkeypatch.setattr(cli_loop, "cmd_question", lambda args: seen.append(args.project) or 0)
    monkeypatch.setattr(cli, "REFRESHES_PAGE", ())
    monkeypatch.delenv("LAB_PROJECT", raising=False)
    assert cli.main(["--project", "other", "question", "status", "Q-001"]) == 0
    monkeypatch.setenv("LAB_PROJECT", "fromenv")
    assert cli.main(["question", "status", "Q-001"]) == 0
    assert cli.main(["question", "status", "Q-001", "--project", "mine"]) == 0
    assert seen == ["other", "fromenv", "mine"]
