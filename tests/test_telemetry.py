import json
from unittest.mock import patch

import pytest

from lab.cli import main
from lab.loop.telemetry import apply_telemetry, format_telemetry_text, get_run_telemetry
from loop_fixtures import make_project, minimal_experiment, minimal_question, started


def test_get_run_telemetry(tmp_path):
    e = started(minimal_experiment("E-009"), minutes=60.0, g=20.0)
    # Start time is 09:00:00
    e["print_runs"][0]["started_at"] = "2026-10-25T09:00:00+00:00"
    paths = make_project(tmp_path, minimal_question(), [e])

    mock_ws = {
        "online": True,
        "printer": {
            "state": "printing",
            "progress": 25,
            "minutesLeft": 45,
            "seenAt": "2026-10-25T09:15:00+00:00",
            "access": "ok",
        }
    }

    with patch("lab.sync.fetch_workshop_status", return_value=mock_ws):
        t = get_run_telemetry(paths, "E-009")
        assert t["experiment_id"] == "E-009"
        assert t["run_id"] == "PR-009-01"
        assert t["printer_state"] == "printing"
        assert t["progress"] == 25
        assert t["minutes_left"] == 45.0
        assert t["elapsed_minutes"] == 15.0
        assert t["estimate_minutes"] == 60.0
        assert t["estimate_g"] == 20.0
        assert t["consumed_g"] == 5.0
        assert t["is_finished"] is False

        text = format_telemetry_text(t)
        assert "Printer:    printing (25% complete, ~45 min left)" in text
        assert "Elapsed:     15 min" in text
        assert "Consumed ~:  5 g" in text


def test_apply_telemetry_guards_and_force(tmp_path):
    e = started(minimal_experiment("E-009"), minutes=60.0, g=20.0)
    e["print_runs"][0]["started_at"] = "2026-10-25T09:00:00+00:00"
    paths = make_project(tmp_path, minimal_question(), [e])

    mock_ws = {
        "online": True,
        "printer": {
            "state": "printing",
            "progress": 25,
            "minutesLeft": 45,
            "seenAt": "2026-10-25T09:15:00+00:00",
        }
    }

    with patch("lab.sync.fetch_workshop_status", return_value=mock_ws):
        # In-progress without force or failed-at should raise ValueError
        with pytest.raises(ValueError, match="still printing"):
            apply_telemetry(paths, "E-009")

        # In-progress with --force should succeed
        exp, t = apply_telemetry(paths, "E-009", force=True)
        run = exp["print_runs"][0]
        assert run["usage"]["usage_source"] == "telemetry"
        assert run["usage"]["actual_minutes"] == 15.0
        assert run["usage"]["actual_g"] is None  # estimate x progress isn't a measurement


def test_a_finished_print_without_a_printer_log_has_no_elapsed_time(tmp_path):
    """Local AI's seenAt is when it last looked, not when the print ended (E-021 got 118 min for an 87 min run)."""
    e = started(minimal_experiment("E-009"), minutes=60.0, g=20.0)
    e["print_runs"][0]["started_at"] = "2026-10-25T09:00:00+00:00"
    paths = make_project(tmp_path, minimal_question(), [e])
    mock_ws = {"online": True, "printer": {"state": "idle", "progress": 100, "minutesLeft": 0,
                                           "seenAt": "2026-10-25T13:00:00+00:00"}}
    with patch("lab.sync.fetch_workshop_status", return_value=mock_ws):
        t = get_run_telemetry(paths, "E-009")
        assert t["is_finished"] is True and t["elapsed_minutes"] is None
        assert "Elapsed:     unknown" in format_telemetry_text(t)
        with pytest.raises(ValueError, match="lab exp usage PR-009-01 --minutes"):
            apply_telemetry(paths, "E-009")


def test_a_finished_print_uses_the_printer_logs_end_time(tmp_path):
    e = started(minimal_experiment("E-009"), minutes=60.0, g=20.0)
    e["print_runs"][0]["started_at"] = "2026-10-25T09:00:00+00:00"
    e["print_runs"][0]["printer_log"] = {"path": "telemetry/PR-009-01.jsonl", "first_seen": "2026-10-25T09:00:30+00:00",
                                         "ended_at": "2026-10-25T09:51:00+00:00", "final_state": "FINISH",
                                         "events": []}
    paths = make_project(tmp_path, minimal_question(), [e])
    mock_ws = {"online": True, "printer": {"state": "idle", "progress": 100, "minutesLeft": 0,
                                           "seenAt": "2026-10-25T13:00:00+00:00"}}
    with patch("lab.sync.fetch_workshop_status", return_value=mock_ws):
        exp, t = apply_telemetry(paths, "E-009")
        run = exp["print_runs"][0]
        assert t["elapsed_minutes"] == 51.0
        assert run["usage"] == {"actual_minutes": 51.0, "actual_g": None, "usage_source": "printer_log",
                                "completion_fraction": None}


def test_apply_telemetry_failed_at(tmp_path):
    e = started(minimal_experiment("E-009"), minutes=60.0, g=20.0)
    e["print_runs"][0]["started_at"] = "2026-10-25T09:00:00+00:00"
    paths = make_project(tmp_path, minimal_question(), [e])

    mock_ws = {
        "online": True,
        "printer": {
            "state": "printing",
            "progress": 30,
            "minutesLeft": 40,
            "seenAt": "2026-10-25T09:20:00+00:00",
        }
    }

    with patch("lab.sync.fetch_workshop_status", return_value=mock_ws):
        exp, t = apply_telemetry(paths, "E-009", failed_at_pct=30)
        run = exp["print_runs"][0]
        assert run["failed"]["at_fraction"] == 0.3
        assert run["usage"]["usage_source"] == "telemetry"
        assert run["usage"]["actual_minutes"] == 20.0  # Local AI saw it still printing: a live reading
        assert run["usage"]["actual_g"] is None


def test_telemetry_cli(tmp_path, capsys, monkeypatch):
    e = started(minimal_experiment("E-009"), minutes=60.0, g=20.0)
    paths = make_project(tmp_path, minimal_question(), [e])
    monkeypatch.setenv("LAB_HOME", str(tmp_path))

    mock_ws = {
        "online": True,
        "printer": {
            "state": "finish",
            "progress": 100,
            "minutesLeft": 0,
            "seenAt": "2026-10-25T10:00:00+00:00",
        }
    }

    with patch("lab.sync.fetch_workshop_status", return_value=mock_ws):
        rc = main(["--project", "hex-tile", "exp", "telemetry", "E-009"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Experiment: E-009" in out

        rc = main(["--project", "hex-tile", "exp", "telemetry", "E-009", "--json"])
        assert rc == 0
        jout = json.loads(capsys.readouterr().out)
        assert jout["experiment_id"] == "E-009"
        assert jout["is_finished"] is True

        rc = main(["--project", "hex-tile", "exp", "telemetry", "E-009", "--apply"])
        assert rc != 0
        assert "lab exp usage PR-009-01 --minutes" in capsys.readouterr().err


def test_the_ledger_counts_printer_log_minutes_and_falls_back_for_an_unknown_end():
    from lab.loop.ledger import run_usage
    build = {"estimate": {"minutes": 60.0, "g": 20.0}}
    logged = {"usage": {"actual_minutes": 51.0, "actual_g": None, "usage_source": "printer_log"}}
    unknown = {"usage": {"actual_minutes": None, "actual_g": None, "usage_source": "finished_unknown"}}
    assert run_usage(logged, build) == (51.0, 20.0)
    assert run_usage(unknown, build) == (60.0, 20.0)
