import pytest

from lab.loop.ledger import auto_stop, owner_stopped, run_usage, spent, streak
from loop_fixtures import minimal_experiment, minimal_question

BUILD = {"id": "BLD-009-01", "ok": True, "estimate": {"minutes": 50.0, "g": 20.0}}


def test_usage_order():
    run = {"id": "PR-009-01", "build_id": "BLD-009-01"}
    assert run_usage(run, BUILD) == (50.0, 20.0)
    assert run_usage({**run, "failed": {"at_fraction": 0.4, "note": None}}, BUILD) == (20.0, 8.0)
    assert run_usage({**run, "usage": {"actual_minutes": 41.0, "actual_g": 11.6, "usage_source": "manual"}}, BUILD) == (41.0, 11.6)


def answered(n, outcome_strength, at, provenance="prospective", failed_run=False):
    """E-0NN answered with B>A at the given strength: 'clearly' -> supported, 'slightly' -> unresolved,
    'refuted' -> A>B."""
    e = minimal_experiment(f"E-0{n:02d}")
    a, b = f"E-0{n:02d}-A", f"E-0{n:02d}-B"
    order = [[a], [b]] if outcome_strength == "refuted" else [[b], [a]]
    e.update(status="answered", provenance=provenance,
             builds=[{**BUILD, "id": f"BLD-0{n:02d}-01"}],
             print_runs=[{"id": f"PR-0{n:02d}-01", "build_id": f"BLD-0{n:02d}-01",
                          **({"failed": {"at_fraction": 0.5, "note": None}} if failed_run else {})}],
             owner_verdict={"kind": "ranking", "order": order, "about_target": True, "by": "owner", "at": at,
                            "strength": "clearly" if outcome_strength == "refuted" else outcome_strength})
    return e


def setup(kinds, **q):
    exps = {}
    for i, k in enumerate(kinds, 1):
        e = answered(i, k, f"2026-10-25T1{i}:00:00+00:00")
        exps[e["id"]] = e
    question = minimal_question(experiments=list(exps))
    question.update(q)
    return question, exps


def test_two_unresolved_stop():
    q, exps = setup(["slightly", "slightly"])
    s = auto_stop(q, exps)
    assert s["code"] == "uninformative_streak" and s["triggered_by"] == ["E-001", "E-002"]


def test_refuted_between_resets():
    q, exps = setup(["slightly", "refuted", "slightly"])
    assert streak(q, exps) == 1 and auto_stop(q, exps) is None


def test_failed_print_does_not_touch_streak_but_uses_budget():
    q, exps = setup(["slightly"])
    e = minimal_experiment("E-002")
    e.update(status="built", builds=[{**BUILD, "id": "BLD-002-01"}],
             print_runs=[{"id": "PR-002-01", "build_id": "BLD-002-01", "failed": {"at_fraction": 0.5, "note": None}}])
    exps["E-002"] = e
    q["experiments"].append("E-002")
    assert streak(q, exps) == 1 and spent(q, exps) == {"minutes": 75.0, "g": 30.0}


def test_migrated_experiments_ignored_by_streak():
    q, exps = setup(["slightly", "slightly"])
    exps["E-001"]["provenance"] = "migrated"
    assert streak(q, exps) == 1


def test_resume_resets_streak():
    q, exps = setup(["slightly", "slightly"],
                    stops=[{"reason": "auto", "auto_code": "uninformative_streak", "at": "2026-10-25T13:00:00+00:00",
                            "resumed_at": "2026-10-25T13:00:00+00:00",
                            "resume": {"added": {"minutes": None, "g": None}, "reason": "new idea"}}])
    assert streak(q, exps) == 0 and auto_stop(q, exps) is None


def test_spent_equal_to_budget_stops():
    q, exps = setup(["clearly", "refuted", "clearly"])  # 3 x 50 min = 150
    q["budget"]["max_minutes"] = 150
    assert auto_stop(q, exps)["code"] == "budget_time_exhausted"
    q["budget"]["max_minutes"] = 150.5
    assert auto_stop(q, exps) is None


def test_added_budget_counts():
    q, exps = setup(["clearly", "refuted", "clearly"])
    q["budget"]["max_minutes"] = 150
    q["stops"] = [{"reason": "auto", "auto_code": "budget_time_exhausted", "at": "t", "resumed_at": "t",
                   "resume": {"added": {"minutes": 60, "g": None}, "reason": "worth it"}}]
    assert auto_stop(q, exps) is None


def test_owner_stopped():
    q = minimal_question()
    assert owner_stopped(q) is None
    q["stops"] = [{"reason": "wrong way", "at": "t", "resumed_at": None, "resume": None}]
    assert owner_stopped(q)["reason"] == "wrong way"
