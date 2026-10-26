import json
from pathlib import Path
from unittest.mock import patch

from lab.cli import main
from lab.status import _rel_time, build_status, format_status_text


def test_rel_time():
    assert _rel_time(None) == "never"
    assert _rel_time("") == "never"
    # ISO string
    assert "ago" in _rel_time("2020-01-01T00:00:00+00:00")


def test_build_status_and_format(tmp_path):
    # Setup mock project structure
    pdir = tmp_path / "projects" / "test-proj"
    pdir.mkdir(parents=True)
    (pdir / "experiments").mkdir()
    (pdir / "questions").mkdir()
    (pdir / "locks").mkdir()
    (pdir / "project.json").write_text(json.dumps({"name": "test-proj", "plate_time_tolerance_pct": 5}))

    with patch("lab.sync.fetch_workshop_status", return_value={"online": True, "printer": {"state": "idle"}}):
        st = build_status(pdir, include_printer=True)
        assert st["project"] == "test-proj"
        assert st["printer"] == {"state": "idle", "progress": None, "minutes_left": None, "seen_at": None, "access": None}

        text = format_status_text(st)
        assert "Project: test-proj" in text
        assert "Question: none yet" in text
        assert "Active Print: none (Printer: idle)" in text
        assert "Needs Attention: none (all caught up)" in text


def test_status_cli(tmp_path, capsys, monkeypatch):
    pdir = tmp_path / "projects" / "myproj"
    pdir.mkdir(parents=True)
    (pdir / "experiments").mkdir()
    (pdir / "questions").mkdir()
    (pdir / "locks").mkdir()
    (pdir / "project.json").write_text(json.dumps({"name": "myproj", "plate_time_tolerance_pct": 5}))

    monkeypatch.setenv("LAB_HOME", str(tmp_path))

    with patch("lab.sync.fetch_workshop_status", return_value=None):
        rc = main(["--project", "myproj", "status", "--no-printer"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Project: myproj" in out
        assert "Active Print: none" in out

        rc = main(["--project", "myproj", "status", "--json", "--no-printer"])
        assert rc == 0
        jout = json.loads(capsys.readouterr().out)
        assert jout["project"] == "myproj"
        assert jout["active_print"] is None
