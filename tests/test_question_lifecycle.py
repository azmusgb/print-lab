import json

import pytest

from lab.loop.commands import (abandon, new_question, observe, rebuild_question, record_verdict, resume_question,
                               stop_question)
from lab.loop.ledger import auto_stop, owner_stopped, streak
from lab.records.schema import load
from lab.records.store import atomic_write_json
from loop_fixtures import make_project, minimal_experiment, minimal_question, started
from test_commands_verdict import V


@pytest.fixture
def proj(tmp_path):
    return make_project(tmp_path, minimal_question(), [started(minimal_experiment())])


def test_new_question_and_duplicate_refused(proj):
    qid = new_question(proj, "Why does the seam show?", {"minutes": 90, "g": 40})
    q = load(proj.questions / f"{qid}.json", "question")
    assert qid == "Q-010" and q["budget"]["max_minutes"] == 90 and q["budget"]["max_test_minutes"] == 45
    with pytest.raises(ValueError, match="already open"):
        new_question(proj, "why does the seam show?", {"minutes": None, "g": None})


def test_stop_then_resume_keeps_history(proj):
    stop_question(proj, "Q-009", "wrong direction")
    with pytest.raises(ValueError, match="already stopped"):
        stop_question(proj, "Q-009", "again")
    resume_question(proj, "Q-009", {"minutes": 60, "g": None}, "new idea")
    q = load(proj.questions / "Q-009.json", "question")
    assert owner_stopped(q) is None and len(q["stops"]) == 1
    assert q["stops"][0]["reason"] == "wrong direction" and q["stops"][0]["resume"]["added"]["minutes"] == 60


def test_resume_without_a_stop_refused(proj):
    with pytest.raises(ValueError, match="isn't stopped"):
        resume_question(proj, "Q-009", None, "why")


def test_auto_stop_lifted_by_add(proj):
    q = load(proj.questions / "Q-009.json", "question")
    q["budget"]["max_minutes"] = 40  # E-009's run used 40
    atomic_write_json(proj.questions / "Q-009.json", q)
    from lab.loop.commands import all_experiments
    assert auto_stop(q, all_experiments(proj))["code"] == "budget_time_exhausted"
    resume_question(proj, "Q-009", {"minutes": 60, "g": None}, "worth more time")
    q = load(proj.questions / "Q-009.json", "question")
    assert q["stops"][-1]["reason"] == "auto" and q["stops"][-1]["auto_code"] == "budget_time_exhausted"
    assert auto_stop(q, all_experiments(proj)) is None


def test_rebuild_matches_step_by_step_state(proj):
    V(proj, rank="B>A", strength="clearly")
    p = proj.experiments / "E-009.json"
    e = json.loads(p.read_text())
    cached = (e["prediction_outcome"], e["comparison_validity"])
    e["prediction_outcome"] = None
    atomic_write_json(p, e)
    report = rebuild_question(proj, "Q-009")
    assert load(p, "experiment")["prediction_outcome"] == cached[0] and any("E-009" in r for r in report)


def test_rebuild_with_invalid_record_writes_nothing(proj):
    V(proj, rank="B>A", strength="clearly")
    e2 = started(minimal_experiment("E-010"))
    e2["status"] = "wobbly"
    atomic_write_json(proj.experiments / "E-010.json", e2)
    q = load(proj.questions / "Q-009.json", "question")
    q["experiments"].append("E-010")
    atomic_write_json(proj.questions / "Q-009.json", q)
    p = proj.experiments / "E-009.json"
    e = json.loads(p.read_text())
    e["prediction_outcome"] = None
    atomic_write_json(p, e)
    before = p.read_text()
    report = rebuild_question(proj, "Q-009")
    assert any("E-010" in r and "status" in r for r in report) and any("No derived state updated" in r for r in report)
    assert p.read_text() == before


def test_rebuild_reports_orphans_and_unattached(proj):
    (proj.prints).mkdir(parents=True, exist_ok=True)
    (proj.prints / "stray.3mf").write_bytes(b"x")
    e = started(minimal_experiment("E-011"))
    atomic_write_json(proj.experiments / "E-011.json", e)
    report = "\n".join(rebuild_question(proj, "Q-009"))
    assert "stray.3mf" in report and "E-011" in report and "unattached" in report


def test_abandon(proj):
    e = abandon(proj, "E-009", "superseded by E-010")
    assert e["status"] == "abandoned" and e["abandoned_reason"] == "superseded by E-010"


def test_observations_never_change_outcome_or_streak(proj):
    V(proj, rank="B>A", strength="slightly")
    from lab.loop.commands import all_experiments
    q = load(proj.questions / "Q-009.json", "question")
    before = (load(proj.experiments / "E-009.json", "experiment")["prediction_outcome"], streak(q, all_experiments(proj)))
    observe(proj, "E-009", {"type": "band_visibility", "variant": "E-009-B", "assessment": "much lower",
                            "confidence": 0.9})
    e = load(proj.experiments / "E-009.json", "experiment")
    assert e["ai_observations"][-1]["confirmed"] is False
    assert (e["prediction_outcome"], streak(q, all_experiments(proj))) == before
