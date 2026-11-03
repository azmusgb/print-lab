"""`lab pull` reports release:print-lab (amendment A3): the checkout it runs from, queued through mac-watch's outbox."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from lab import pull


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin:/opt/homebrew/bin"})


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "print-lab"
    (r / "lab").mkdir(parents=True)
    (r / "projects").mkdir()
    (r / "lab" / "cli.py").write_text("x = 1\n")
    (r / "projects" / "E-001.json").write_text("{}\n")
    _git(r, "init", "-q")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "init")
    return r


@pytest.fixture
def watch(tmp_path):
    """A stand-in mac-watch that appends its arguments to calls.jsonl, or fails when fail.txt exists."""
    w = tmp_path / "mac-watch.py"
    w.write_text(
        "import json, sys, pathlib\n"
        "d = pathlib.Path(__file__).parent\n"
        "if (d / 'fail.txt').exists():\n"
        "    print('mac-watch: not a Mac agent: print-lab; no release report', file=sys.stderr); sys.exit(1)\n"
        "with open(d / 'calls.jsonl', 'a') as f: f.write(json.dumps(sys.argv[1:]) + '\\n')\n")
    return w


def calls(watch):
    f = watch.parent / "calls.jsonl"
    return [json.loads(line) for line in f.read_text().splitlines()] if f.exists() else []


def report(repo, watch, last, monkeypatch):
    monkeypatch.delenv("LAB_MAC_WATCH", raising=False)
    return pull.report_release(last, watch=watch, repo=repo)


def test_a_new_commit_is_queued_once(repo, watch, monkeypatch, capsys):
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    got = report(repo, watch, None, monkeypatch)
    assert got == {"commit": head, "dirty": False}
    assert calls(watch) == [["--queue-release", "print-lab", head, "0"]]
    assert "Release report queued: print-lab " + head[:7] in capsys.readouterr().out
    assert report(repo, watch, got, monkeypatch) == got  # unchanged checkout: nothing queued
    assert len(calls(watch)) == 1


def test_only_code_changes_make_it_dirty(repo, watch, monkeypatch):
    (repo / "projects" / "E-001.json").write_text('{"verdict": "clean"}\n')
    (repo / "projects" / "runs").mkdir()
    (repo / "projects" / "runs" / "PR-001-01.json").write_text("{}\n")
    assert report(repo, watch, None, monkeypatch)["dirty"] is False
    (repo / "lab" / "cli.py").write_text("x = 2\n")
    got = report(repo, watch, {"commit": "0" * 40, "dirty": False}, monkeypatch)
    assert got["dirty"] is True and calls(watch)[-1][-1] == "1"


def test_a_refused_queue_is_retried_but_printed_once(repo, watch, monkeypatch, capsys):
    (watch.parent / "fail.txt").write_text("")
    first = report(repo, watch, None, monkeypatch)
    assert "not a Mac agent" in first["failed"] and "commit" not in first
    assert "didn't queue the release report" in capsys.readouterr().err
    again = report(repo, watch, first, monkeypatch)
    assert again == first and capsys.readouterr().err == ""
    (watch.parent / "fail.txt").unlink()
    done = report(repo, watch, again, monkeypatch)
    assert set(done) == {"commit", "dirty"} and len(calls(watch)) == 1


def test_no_mac_watch_or_no_checkout_does_nothing(repo, tmp_path, monkeypatch):
    assert report(repo, tmp_path / "missing.py", None, monkeypatch) is None
    plain = tmp_path / "not-git"
    plain.mkdir()
    assert pull.checkout_release(plain) is None


def test_the_default_mac_watch_is_found_under_home(repo, tmp_path, monkeypatch):
    monkeypatch.delenv("LAB_MAC_WATCH", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert pull.report_release(None, repo=repo) is None  # the test HOME has no mac-watch: nothing queued
