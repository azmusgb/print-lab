"""`lab exp send`: open the build the check passed in Bambu Connect, so the printer gets exactly that G-code."""
import json

import pytest

from lab.loop.guards import start
from lab.loop.send import send
from lab.records.schema import load
from test_guards import built, edit, proj  # noqa: F401  (fixture)


def opener(calls):
    return lambda app, path: calls.append((app, path))


def test_send_opens_the_checked_builds_sliced_file_in_bambu_connect(proj):
    eid = built(proj)
    before = (proj.experiments / f"{eid}.json").read_text()
    calls = []
    res = send(proj, eid, opener=opener(calls))
    b = load(proj.experiments / f"{eid}.json", "experiment")["builds"][-1]
    assert calls == [("Bambu Connect", proj.root / b["sliced"])]
    assert str(calls[0][1]).endswith(".gcode.3mf") and calls[0][1].exists()
    assert res == {"experiment": eid, "build": b["id"], "file": str(proj.root / b["sliced"]), "app": "Bambu Connect"}
    assert (proj.experiments / f"{eid}.json").read_text() == before  # sending records nothing


def test_send_refuses_what_start_would_refuse(proj):
    eid = built(proj)
    edit(proj, "Q-009", lambda q: q["stops"].append({"reason": "wrong way", "at": "t", "resumed_at": None,
                                                     "resume": None}), "questions")
    calls = []
    with pytest.raises(ValueError, match="owner_stopped"):
        send(proj, eid, opener=opener(calls))
    assert calls == []


def test_send_names_the_approve_command_when_approval_is_needed(proj):
    eid = built(proj)
    edit(proj, "Q-009", lambda q: q["budget"].update(max_minutes=10), "questions")
    with pytest.raises(ValueError, match=rf"question_time[\s\S]*lab exp approve {eid}"):
        send(proj, eid, opener=opener([]))


def test_send_refuses_while_the_experiment_is_printing(proj):
    eid = built(proj)
    start(proj, eid)
    with pytest.raises(ValueError, match="already printing"):
        send(proj, eid, opener=opener([]))


def test_send_refuses_a_build_whose_sliced_file_is_gone(proj):
    eid = built(proj)
    b = json.loads((proj.experiments / f"{eid}.json").read_text())["builds"][-1]
    (proj.root / b["sliced"]).unlink()
    with pytest.raises(ValueError, match=rf"lab exp build {eid} --replace"):
        send(proj, eid, opener=opener([]))


def test_send_uses_another_app_when_asked(proj):
    eid = built(proj)
    calls = []
    send(proj, eid, app="BambuStudio", opener=opener(calls))
    assert calls[0][0] == "BambuStudio"


def test_cli_dry_run_names_the_file_and_the_next_steps(proj, monkeypatch, capsys):
    from lab import cli
    eid = built(proj)
    monkeypatch.setenv("LAB_HOME", str(proj.root.parent.parent))
    monkeypatch.setenv("LAB_SYNC", "off")
    opened = []
    monkeypatch.setattr("lab.loop.send._open", lambda app, path: opened.append(path))
    assert cli.main(["exp", "send", eid, "--dry-run"]) == 0
    out = capsys.readouterr().out
    b = load(proj.experiments / f"{eid}.json", "experiment")["builds"][-1]
    assert opened == [] and b["sliced"].split("/")[-1] in out
    assert f"uv run lab exp start {eid}" in out and "Don't slice it again" in out
