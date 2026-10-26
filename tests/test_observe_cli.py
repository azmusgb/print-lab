"""`lab observe` on the terminal: no defaults, owner reports need the TTY confirmation."""
import json

from lab.cli import main
from lab.records import observations as obs
from loop_fixtures import make_project, minimal_experiment, minimal_question, started
from test_pull import _obs_snapshot


def _setup(tmp_path, monkeypatch, snapshot=None):
    monkeypatch.setenv("LAB_HOME", str(tmp_path))
    paths = make_project(tmp_path, minimal_question(), [started(minimal_experiment("E-009"))])
    f = tmp_path / "session.json"
    f.write_text(json.dumps({"snapshots": [snapshot or _obs_snapshot()]}))
    return paths, f


def test_an_owner_report_without_a_terminal_is_refused(tmp_path, monkeypatch, capsys):
    paths, f = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert main(["--project", "hex-tile", "observe", "add", "--file", str(f)]) == 1
    assert "your own words" in capsys.readouterr().err and not obs.all_observations(paths)


def test_an_owner_report_confirmed_at_the_terminal_is_recorded(tmp_path, monkeypatch, capsys):
    paths, f = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "yes")
    assert main(["--project", "hex-tile", "observe", "add", "--file", str(f)]) == 0
    rv = obs.latest(obs.all_observations(paths)[0])
    assert rv["submitted"] == {**rv["submitted"], "actor": "owner", "channel": "cli"}


def test_claude_records_its_reading_as_an_ai_reading(tmp_path, monkeypatch):
    snap = _obs_snapshot()
    snap["source"] = {**snap["source"], "kind": "ai_reading", "attributed_by": "claude session 5e49"}
    paths, f = _setup(tmp_path, monkeypatch, snap)
    assert main(["--project", "hex-tile", "observe", "add", "--file", str(f), "--as", "claude"]) == 0
    assert obs.latest(obs.all_observations(paths)[0])["source"]["kind"] == "ai_reading"


def test_import_is_a_dry_run_unless_applied(tmp_path, monkeypatch, capsys):
    paths, _ = _setup(tmp_path, monkeypatch)
    assert main(["--project", "hex-tile", "observe", "import-verdicts"]) == 0
    assert "dry run" in capsys.readouterr().out
