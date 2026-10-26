from unittest.mock import patch

from lab.cli import main
from lab.watch import format_progress_bar, render_dashboard


def test_format_progress_bar():
    b0 = format_progress_bar(0, width=10)
    assert b0 == "[░░░░░░░░░░] 0%"
    b50 = format_progress_bar(50, width=10)
    assert b50 == "[█████░░░░░] 50%"
    b100 = format_progress_bar(100, width=10)
    assert b100 == "[██████████] 100%"


def test_render_dashboard_no_print():
    st = {
        "project": "demo",
        "active_print": None,
        "printer": {"state": "idle"},
        "question": None,
        "needs": [],
    }
    text, is_finished, ap = render_dashboard(st)
    assert "Print Lab — demo" in text
    assert "Printer:     IDLE" in text
    assert is_finished is False
    assert ap is None


def test_render_dashboard_printing():
    st = {
        "project": "demo",
        "active_print": {
            "experiment_id": "E-001",
            "run_id": "PR-001-01",
            "build_id": "BLD-001-01",
            "estimate": {"minutes": 100.0, "g": 30.0},
            "printer": {
                "state": "printing",
                "progress": 40,
                "minutes_left": 60.0,
                "seen_at": "2026-10-25T10:00:00+00:00",
            },
        },
        "question": {"id": "Q-001", "question": "Test question", "status": "active"},
        "needs": [{"id": "E-001", "action": "Wait for print", "command": "uv run lab status"}],
    }
    text, is_finished, ap = render_dashboard(st)
    assert "State:       PRINTING" in text
    assert "Experiment:  E-001 (PR-001-01)" in text
    assert "Time:        ~60 min remaining" in text
    assert "Material:    ~12 g consumed so far" in text
    assert is_finished is False


def test_render_dashboard_finished():
    st = {
        "project": "demo",
        "active_print": {
            "experiment_id": "E-001",
            "run_id": "PR-001-01",
            "printer": {
                "state": "finish",
                "progress": 100,
            },
        },
    }
    text, is_finished, ap = render_dashboard(st)
    assert is_finished is True


def test_watch_cli_once(capsys):
    with patch("lab.sync.fetch_workshop_status", return_value={"printer": {"state": "idle"}}):
        rc = main(["watch", "--once", "--no-notify"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Print Lab — hex-tile" in out
