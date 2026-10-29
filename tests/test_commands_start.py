import json

import pytest

from lab import runs
from lab.loop.guards import run_check, start
from lab.loop.setup_log import append_event
from lab.records.schema import load
from lab.records.store import atomic_write_json
from test_guards import built, edit, proj  # noqa: F401  (fixture)


def test_start_snapshots_setup_and_warns_baseline(proj):
    eid = built(proj)
    append_event(proj, "nozzle_changed", {"diameter_mm": 0.4})
    e, warnings = start(proj, eid)
    run = e["print_runs"][-1]
    assert run["id"] == f"PR-{eid[2:]}-01" and run["build_id"] == f"BLD-{eid[2:]}-01"
    assert run["setup"]["nozzle_changed"]["fields"] == {"diameter_mm": 0.4}
    assert run["baseline_missing"] == ["filament_dried", "vibration_calibration"] and warnings
    assert all("Canonical RUN record was not created" not in w for w in warnings)
    assert e["status"] == "printing"

    canonical = runs.for_source_run(proj, run["id"])
    assert canonical is not None
    assert canonical["id"] == f"RUN-{eid[2:]}-01"
    assert canonical["build_id"] == run["build_id"]
    assert canonical["status"] == "printing"
    assert canonical["started_at"] == run["started_at"]
    assert canonical["source_run"] == run["id"]
    assert set(canonical["artifacts"]) == {"model", "process", "filament", "slice"}
    assert runs.artifact_problems(proj, canonical) == []


def test_start_twice_writes_nothing(proj):
    eid = built(proj)
    start(proj, eid)
    before = (proj.experiments / f"{eid}.json").read_text()
    run_before = runs.latest_for_experiment(proj, eid)
    e, warnings = start(proj, eid)
    assert "already" in warnings[0] and (proj.experiments / f"{eid}.json").read_text() == before
    assert runs.latest_for_experiment(proj, eid) == run_before


def test_start_rechecks_live_state(proj):
    eid = built(proj)
    assert run_check(proj, eid).status == "ready"
    other = built(proj)
    start(proj, other)  # uses 33.9 of the budget
    edit(proj, "Q-009", lambda q: q["budget"].update(max_minutes=60), "questions")
    with pytest.raises(ValueError, match="question_time"):
        start(proj, eid)


def test_failed_run_returns_to_built_and_third_attempt_needs_approval(proj):
    from lab.loop.commands import record_usage
    eid = built(proj)
    for _ in range(2):
        e, _ = start(proj, eid)
        record_usage(proj, e["print_runs"][-1]["id"], failed_at_pct=10, minutes=None, grams=None)
        assert load(proj.experiments / f"{eid}.json", "experiment")["status"] == "built"
    with pytest.raises(ValueError, match="retry_limit"):
        start(proj, eid)
