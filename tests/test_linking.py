"""lab/loop/linking.py: Bambuddy prints attached to lab print runs by name, and the evidence snapshot when one ends."""
import json
from pathlib import Path

import pytest

from loop_fixtures import make_project, minimal_experiment, minimal_question, started

from lab.loop import ledger
from lab.loop.commands import load_experiment
from lab.loop.linking import link_by_hand, link_entries, unlink
from lab.records.schema import validate

LOG = json.loads((Path(__file__).parent / "fixtures" / "bambuddy_print_log.json").read_text())["items"]


def entry(print_id: int, **changes) -> dict:
    """A recorded print-log entry, renamed to E-023's build unless a name is given."""
    e = next(x for x in LOG if x["id"] == print_id)
    return {**e, "print_name": "hex-tile_E-023_BLD-023-01", **changes}


def no_plan(_archive_id):
    return None


@pytest.fixture
def paths(tmp_path):
    """hex-tile with E-023 printing BLD-023-01 on PR-023-01."""
    e = started(minimal_experiment("E-023", "Q-023"), minutes=50.0, g=20.0)
    return make_project(tmp_path, minimal_question("Q-023", ("E-023",)), [e])


def run(paths, run_id="PR-023-01"):
    return next(r for r in load_experiment(paths, "E-023")["print_runs"] if r["id"] == run_id)


def test_attaches_to_the_open_run(paths):
    events = link_entries(paths, [entry(15, status="printing", completed_at=None, duration_seconds=None)], no_plan)
    assert [(x["action"], x["experiment"], x["run"], x["print"]) for x in events] == [
        ("linked", "E-023", "PR-023-01", 15)]
    b = run(paths)["bambuddy"]
    assert (b["print"], b["archive"], b["linked"], b["status"]) == (15, 15, "auto", "printing")
    assert len(load_experiment(paths, "E-023")["print_runs"]) == 1


def test_creates_a_run_when_none_is_open(paths):
    link_entries(paths, [entry(15)], no_plan)
    events = link_entries(paths, [entry(16, archive_id=15)], no_plan)
    assert [x["action"] for x in events] == ["created", "snapshot"]
    e = load_experiment(paths, "E-023")
    new = e["print_runs"][-1]
    assert new["id"] == "PR-023-02" and events[0]["run"] == "PR-023-02"
    assert (new["build_id"], new["setup"], new["baseline_missing"], new["photos"]) == ("BLD-023-01", None, [], [])
    assert new["started_at"] == "2026-10-21T09:15:03+00:00"
    assert new["bambuddy"]["print"] == 16 and new["bambuddy"]["archive"] == 15


def test_newest_of_two_open_runs_wins_and_says_so(paths):
    from lab.loop.commands import save_experiment
    e = load_experiment(paths, "E-023")
    e["print_runs"].append({**e["print_runs"][0], "id": "PR-023-02", "started_at": "2026-10-25T10:00:00+00:00"})
    save_experiment(paths, e)
    events = link_entries(paths, [entry(15, status="printing", completed_at=None, duration_seconds=None)], no_plan)
    assert events[0]["run"] == "PR-023-02"
    assert "PR-023-01" in events[0]["message"] and "PR-023-02" in events[0]["message"]
    assert "bambuddy" not in run(paths, "PR-023-01")


def test_unknown_experiment_is_skipped_not_raised(paths):
    events = link_entries(paths, [entry(16, print_name="hex-tile_E-024_BLD-024-01"),
                                  entry(15, print_name="hex-tile_E-023_BLD-023-07"),
                                  entry(15, print_name="other-project_E-023_BLD-023-01")], no_plan)
    assert [x["action"] for x in events] == ["skipped"] * 3
    assert all(x["message"] for x in events)
    assert "bambuddy" not in run(paths)


def test_outside_names_are_ignored(paths):
    outside = [x for x in LOG if x["id"] >= 17]
    assert link_entries(paths, outside, no_plan) == []
    assert "bambuddy" not in run(paths)


def test_printing_entry_links_now_snapshots_later(paths):
    live = entry(15, status="completed", failure_reason=None)
    link_entries(paths, [{**live, "status": "printing", "completed_at": None, "duration_seconds": None,
                          "filament_used_grams": None}], no_plan)
    r = run(paths)
    assert r["bambuddy"]["snapshot_at"] is None and r["usage"] is None

    events = link_entries(paths, [live], no_plan)
    assert [x["action"] for x in events] == ["snapshot"]
    r = run(paths)
    b = r["bambuddy"]
    assert b["status"] == "completed" and b["snapshot_at"]
    assert (b["minutes"], b["grams"], b["ended"]) == (20.0, 8.4, "2026-10-20T14:22:11+00:00")
    assert b["failed_at_estimate"] is None
    assert r["usage"] == {"actual_minutes": 20.0, "actual_g": 8.4, "usage_source": "bambuddy",
                          "completion_fraction": None}
    assert load_experiment(paths, "E-023")["status"] == "printing"  # completed: the owner judges it

    before = load_experiment(paths, "E-023")
    assert link_entries(paths, [live], no_plan) == []
    assert load_experiment(paths, "E-023") == before


def test_owner_usage_is_kept(paths):
    from lab.loop.commands import record_usage
    record_usage(paths, "PR-023-01", minutes=50, grams=None, usage_source="manual")
    link_entries(paths, [entry(15, status="completed", failure_reason=None)], no_plan)
    r = run(paths)
    assert r["usage"]["actual_minutes"] == 50 and r["usage"]["usage_source"] == "manual"
    assert r["bambuddy"]["minutes"] == 20.0


def test_telemetry_usage_is_replaced_and_kept_as_a_revision(paths):
    from lab.loop.commands import record_usage
    record_usage(paths, "PR-023-01", minutes=31, grams=None, usage_source="telemetry")
    link_entries(paths, [entry(15, status="completed", failure_reason=None)], no_plan)
    r = run(paths)
    assert r["usage"]["usage_source"] == "bambuddy" and r["usage"]["actual_minutes"] == 20.0
    assert r["usage_revisions"][-1]["actual_minutes"] == 31


def test_failed_sets_estimate_and_returns_to_built(paths):
    asked = []

    def plan(archive_id):
        asked.append(archive_id)
        return 3000.0
    link_entries(paths, [entry(15, archive_id=7)], plan)
    assert asked == [7]
    e = load_experiment(paths, "E-023")
    r = e["print_runs"][0]
    assert r["failed"] == {"at_fraction": 0.4, "note": "estimate from Bambuddy print #15"}
    assert r["bambuddy"]["failed_at_estimate"] == 0.4
    assert r["bambuddy"]["failure_reason"] == "Spaghetti detected"
    assert r["usage"]["completion_fraction"] == 0.4
    assert e["status"] == "built"


def test_estimate_clamps_and_tolerates_missing_plan(tmp_path):
    def project(name):
        e = started(minimal_experiment("E-023", "Q-023"))
        return make_project(tmp_path / name, minimal_question("Q-023", ("E-023",)), [e])
    p = project("over")
    link_entries(p, [entry(15, duration_seconds=4000)], lambda _: 3000.0)
    assert run(p)["failed"]["at_fraction"] == 1.0
    p = project("missing")
    link_entries(p, [entry(15)], no_plan)
    r = run(p)
    assert r["bambuddy"]["failed_at_estimate"] is None and r["failed"]["at_fraction"] is None
    p = project("no-duration")
    link_entries(p, [entry(15, duration_seconds=None)], lambda _: 3000.0)
    assert run(p)["bambuddy"]["failed_at_estimate"] is None


def test_cancelled_returns_to_built_but_is_not_a_failure(paths):
    link_entries(paths, [entry(15, status="cancelled", failure_reason=None)], no_plan)
    r = run(paths)
    assert r["bambuddy"]["status"] == "cancelled" and r["bambuddy"]["snapshot_at"]
    assert r["bambuddy"]["minutes"] == 20.0 and r["usage"]["usage_source"] == "bambuddy"
    assert r["failed"] is None and load_experiment(paths, "E-023")["status"] == "built"


def test_started_at_is_utc(paths):
    link_entries(paths, [entry(15)], no_plan)
    link_entries(paths, [entry(16)], no_plan)
    r = run(paths, "PR-023-02")
    assert r["started_at"] == "2026-10-21T09:15:03+00:00"
    assert r["bambuddy"]["started"] == "2026-10-21T09:15:03+00:00"
    assert r["bambuddy"]["ended"] == "2026-10-21T10:01:40+00:00"


def test_bambuddy_minutes_count_as_observed(paths):
    link_entries(paths, [entry(15, status="completed", failure_reason=None)], no_plan)
    e = load_experiment(paths, "E-023")
    assert ledger.run_usage(e["print_runs"][0], e["builds"][0]) == (20.0, 8.4)


def test_hand_link_and_unlink(paths):
    from lab.loop.commands import record_usage
    renamed = entry(25, print_name="HEX_TILE_v74_textured", archive_id=19)
    r = link_by_hand(paths, "E-023", "BLD-023-01", renamed, 25200.0)
    assert r["id"] == "PR-023-01"
    assert (r["bambuddy"]["linked"], r["bambuddy"]["print"], r["bambuddy"]["archive"]) == ("hand", 25, 19)
    assert r["usage"]["usage_source"] == "bambuddy" and r["bambuddy"]["snapshot_at"]
    with pytest.raises(ValueError, match="already linked"):
        link_by_hand(paths, "E-023", "BLD-023-01", renamed, None)
    with pytest.raises(ValueError, match="BLD-023-09"):
        link_by_hand(paths, "E-023", "BLD-023-09", entry(15), None)

    r = unlink(paths, "PR-023-01")
    assert "bambuddy" not in r and r["usage"] is None
    assert "bambuddy" not in run(paths)

    # a failed print linked, then the owner's own minutes: unlinking takes only what Bambuddy gave
    link_entries(paths, [entry(15)], lambda _: 3000.0)
    record_usage(paths, "PR-023-01", minutes=50, grams=None, usage_source="manual")
    r = unlink(paths, "PR-023-01")
    assert r["failed"] is None and r["usage"]["usage_source"] == "manual" and "bambuddy" not in r
    with pytest.raises(ValueError, match="isn't linked"):
        unlink(paths, "PR-023-01")


def test_unlink_restores_the_replaced_usage(paths):
    from lab.loop.commands import record_usage
    record_usage(paths, "PR-023-01", minutes=31, grams=None, usage_source="telemetry")
    link_entries(paths, [entry(15, status="completed", failure_reason=None)], no_plan)
    r = unlink(paths, "PR-023-01")
    assert r["usage"]["usage_source"] == "telemetry" and r["usage"]["actual_minutes"] == 31
    assert not r.get("usage_revisions")


def test_a_linked_run_validates(paths):
    link_entries(paths, [entry(15)], lambda _: 3000.0)
    e = load_experiment(paths, "E-023")
    validate(e, "experiment", "E-023.json")
    e["print_runs"][0]["bambuddy"] = "25"
    with pytest.raises(Exception):
        validate(e, "experiment", "E-023.json")


def built_project(tmp_path, status="built"):
    """hex-tile with E-023 built (BLD-023-01) and never started."""
    e = started(minimal_experiment("E-023", "Q-023"))
    e["print_runs"], e["status"] = [], status
    return make_project(tmp_path, minimal_question("Q-023", ("E-023",)), [e])


def test_created_run_for_a_live_print_makes_it_printing(tmp_path):
    p = built_project(tmp_path)
    events = link_entries(p, [entry(15, status="printing", completed_at=None, duration_seconds=None)], no_plan)
    assert [x["action"] for x in events] == ["created"]
    assert load_experiment(p, "E-023")["status"] == "printing"


def test_created_run_for_a_finished_print_asks_for_the_verdict(tmp_path):
    from lab import page_index
    p = built_project(tmp_path, "approved")
    link_entries(p, [entry(15, status="completed", failure_reason=None)], no_plan)
    e = load_experiment(p, "E-023")
    assert e["status"] == "printing"
    assert page_index._needs(e, "2026-10-27T12:00:00+00:00")["action"] == "Judge the print"


def test_created_run_for_a_failed_print_ends_built(tmp_path):
    p = built_project(tmp_path, "ready")
    link_entries(p, [entry(15)], lambda _: 3000.0)
    e = load_experiment(p, "E-023")
    assert e["status"] == "built" and e["print_runs"][0]["failed"]["at_fraction"] == 0.4


def test_answered_experiment_status_is_unchanged(tmp_path):
    p = built_project(tmp_path, "answered")
    link_entries(p, [entry(15, status="completed", failure_reason=None)], no_plan)
    e = load_experiment(p, "E-023")
    assert e["status"] == "answered" and e["print_runs"][0]["bambuddy"]["print"] == 15


def test_owner_failure_first_still_ends_built(paths):
    from lab.loop.commands import record_usage
    record_usage(paths, "PR-023-01", failed_at_pct=30)  # the owner's failure: built
    link_entries(paths, [entry(15)], lambda _: 3000.0)  # links (printing), then the failed snapshot
    e = load_experiment(paths, "E-023")
    assert e["status"] == "built"
    assert e["print_runs"][0]["failed"] == {"at_fraction": 0.3, "note": None}
    assert e["print_runs"][0]["bambuddy"]["failed_at_estimate"] == 0.4


def test_unlink_removes_the_run_it_opened_and_restores_the_status(tmp_path):
    p = built_project(tmp_path, "approved")
    link_entries(p, [entry(15, status="printing", completed_at=None, duration_seconds=None)], no_plan)
    assert load_experiment(p, "E-023")["status"] == "printing"
    unlink(p, "PR-023-01")
    e = load_experiment(p, "E-023")
    assert e["print_runs"] == [] and e["status"] == "approved"
    assert ledger.spent(minimal_question("Q-023", ("E-023",)), {"E-023": e}) == {"minutes": 0.0, "g": 0.0}


def test_unlink_keeps_an_opened_run_with_the_owners_facts(tmp_path):
    from lab.loop.commands import save_experiment
    p = built_project(tmp_path)
    link_entries(p, [entry(15, status="printing", completed_at=None, duration_seconds=None)], no_plan)
    e = load_experiment(p, "E-023")
    e["print_runs"][0]["photos"] = ["photos/PR-023-01.jpg"]
    save_experiment(p, e)
    r = unlink(p, "PR-023-01")
    e = load_experiment(p, "E-023")
    assert [x["id"] for x in e["print_runs"]] == ["PR-023-01"] and "bambuddy" not in r
    assert e["status"] == "built"  # the status the link moved goes back: no other run is open


def test_unlink_rechecks_the_link_under_the_lock(paths, monkeypatch):
    from lab.loop import linking
    link_entries(paths, [entry(15, status="printing", completed_at=None, duration_seconds=None)], no_plan)
    stale = linking.find_run(paths, "PR-023-01")
    unlink(paths, "PR-023-01")
    monkeypatch.setattr(linking, "find_run", lambda *_: stale)  # read before another unlink got there
    with pytest.raises(ValueError, match="isn't linked"):
        unlink(paths, "PR-023-01")


def test_planned_time_is_asked_outside_the_lock(paths):
    from lab.records.store import record_lock

    def plan(_archive_id):
        with record_lock(paths.locks, "E-023", "probe", timeout_s=0.2):
            return 3000.0
    link_entries(paths, [entry(15)], plan)
    assert run(paths)["failed"]["at_fraction"] == 0.4


def test_status_change_refreshes_derived_fields(tmp_path, monkeypatch):
    from lab.loop import linking
    p = built_project(tmp_path)
    link_entries(p, [entry(15, status="printing", completed_at=None, duration_seconds=None)], no_plan)
    calls = []
    monkeypatch.setattr(linking, "refresh_derived", lambda paths, e: calls.append(e["status"]) or e)
    link_entries(p, [entry(15)], lambda _: 3000.0)  # failed: printing -> built
    assert calls == ["built"]


def test_already_printing_with_an_open_run_stays_printing(paths):
    link_entries(paths, [entry(15, status="printing", completed_at=None, duration_seconds=None)], no_plan)
    e = load_experiment(paths, "E-023")
    assert e["status"] == "printing" and "prior_status" not in e["print_runs"][0]["bambuddy"]


def test_needs_approval_moves_to_printing(tmp_path):
    p = built_project(tmp_path, "needs_approval")
    link_entries(p, [entry(15, status="printing", completed_at=None, duration_seconds=None)], no_plan)
    assert load_experiment(p, "E-023")["status"] == "printing"


def test_abandoned_experiment_status_is_unchanged(tmp_path):
    p = built_project(tmp_path, "abandoned")
    link_entries(p, [entry(15)], lambda _: 3000.0)
    assert load_experiment(p, "E-023")["status"] == "abandoned"


def test_fixture_durations_agree_with_timestamps():
    from datetime import datetime
    for x in LOG:
        if x["completed_at"]:
            span = datetime.fromisoformat(x["completed_at"]) - datetime.fromisoformat(x["started_at"])
            assert abs(span.total_seconds() - x["duration_seconds"]) < 1, x["id"]


def test_double_unlink_of_an_opened_run_says_not_linked(tmp_path, monkeypatch):
    from lab.loop import linking
    p = built_project(tmp_path, "approved")
    link_entries(p, [entry(15, status="printing", completed_at=None, duration_seconds=None)], no_plan)
    stale = linking.find_run(p, "PR-023-01")
    unlink(p, "PR-023-01")  # deletes the run it opened
    monkeypatch.setattr(linking, "find_run", lambda *_: stale)
    with pytest.raises(ValueError, match="isn't linked"):
        unlink(p, "PR-023-01")


def test_a_failed_print_outside_the_lab_never_asks_for_the_planned_time(paths):
    asked = []
    link_entries(paths, [entry(15, print_name="benchy"), entry(15, print_name="hex-tile_E-999_BLD-999-01")],
                 lambda a: asked.append(a))
    assert asked == []
