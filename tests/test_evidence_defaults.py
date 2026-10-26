"""Missing evidence stays missing (blueprint R-03, R-05, R-09; findings F-02 to F-05, F-12)."""
import json

import pytest

from lab.cli import main
from lab.loop.commands import load_experiment, record_verdict
from loop_fixtures import make_project, minimal_experiment, minimal_question, started


def _verdict_args(**over):
    base = dict(rank="B>A", strength="clearly", inconclusive=None, accept=None, defects=[], marks=[], witness=None,
                witness_override=None, anchors=[], not_about_target=False, note=None, replace=False, runs=None)
    return {**base, **over}


def test_a_verdict_given_without_its_light_records_the_light_as_unknown(tmp_path):
    paths = make_project(tmp_path, minimal_question(), [started(minimal_experiment("E-009"))])
    record_verdict(paths, "E-009", **_verdict_args())
    assert load_experiment(paths, "E-009")["owner_verdict"]["lighting"] is None


def test_the_cli_has_no_default_light(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LAB_HOME", str(tmp_path))
    make_project(tmp_path, minimal_question(), [started(minimal_experiment("E-009"))])
    assert main(["--project", "hex-tile", "exp", "verdict", "E-009", "--rank", "B>A", "--strength", "clearly"]) == 0
    e = json.loads((tmp_path / "projects" / "hex-tile" / "experiments" / "E-009.json").read_text())
    assert e["owner_verdict"]["lighting"] is None


def test_an_unknown_light_can_neither_support_nor_refute_a_prediction():
    from lab.loop.outcome import prediction_outcome
    e = started(minimal_experiment("E-009"))
    e["owner_verdict"] = {"kind": "ranking", "order": [["E-009-B"], ["E-009-A"]], "strength": "clearly",
                          "about_target": True, "lighting": None, "marks": [], "by": "owner"}
    assert prediction_outcome(e, {"status": "valid"}) == "unresolved"
    e["owner_verdict"]["lighting"] = "diagnostic"
    assert prediction_outcome(e, {"status": "valid"}) == "supported"


def test_a_phone_verdict_without_its_light_records_it_as_unknown():
    from lab import pull
    assert pull.verdict_lighting({"rank": "B>A"}) is None
    assert pull.verdict_lighting({"lighting": "room"}) == "room"


# ---- cases ------------------------------------------------------------------------------------------------------

def _answered(eid, kind="height_strip", lighting="diagnostic"):
    e = started(minimal_experiment(eid))
    e["test_kind"], e["status"] = kind, "answered"
    e["owner_verdict"] = {"kind": "acceptance", "good_enough": True, "lighting": lighting, "by": "owner",
                          "at": "2026-10-25T10:00:00+00:00"}
    return e


def test_counting_answered_experiments_never_lifts_a_case_past_supported():
    from lab.loop.cases import evaluate_confidence
    exps = [_answered("E-008"), _answered("E-011"), _answered("E-014", kind="full_part")]
    assert evaluate_confidence(exps) == ("supported", 2)


def test_only_an_owner_review_sets_a_higher_level_and_regeneration_keeps_it(tmp_path):
    from lab.loop.cases import load_cases, review_case, sync_cases
    paths = make_project(tmp_path, minimal_question(), [_answered("E-008"), _answered("E-012")])
    sync_cases(paths)
    review_case(paths, "CASE-001", level="reproduced", reason="E-008 and E-012 both fused (owner)")
    sync_cases(paths)
    c = next(x for x in load_cases(paths) if x["id"] == "CASE-001")
    assert c["confidence"] == "reproduced" and c["review"]["reason"].startswith("E-008")


def test_promotion_needs_an_owner_review_and_an_existing_checker(tmp_path):
    from lab.loop.cases import promote_case_to_rule, review_case, sync_cases
    paths = make_project(tmp_path, minimal_question(), [_answered("E-008"), _answered("E-012")])
    sync_cases(paths)
    with pytest.raises(ValueError, match="review"):
        promote_case_to_rule(paths, "CASE-001", reason="looks right")
    review_case(paths, "CASE-001", level="reproduced", reason="owner")
    res = promote_case_to_rule(paths, "CASE-001", reason="owner endorses the 1.0 mm gap rule")
    assert res["status"] == "promoted" and res["rule_file"] == "lab/checks/part_gap.py"


def test_a_rule_check_reports_coverage_not_precision(tmp_path):
    from lab.loop.cases import check_rule_against_history, sync_cases
    paths = make_project(tmp_path, minimal_question(), [_answered("E-008")])
    sync_cases(paths)
    (paths.root / "history").mkdir(parents=True, exist_ok=True)
    (paths.root / "history" / "revisions.json").write_text(json.dumps([{"version": 41}, {"version": 46}]))
    res = check_rule_against_history(paths, "CASE-001")
    assert "precision_note" not in res
    assert "not a measured precision" in res["coverage_note"]


def test_a_promotion_made_before_reviews_were_required_is_flagged():
    from lab.loop.cases import format_case_detail, format_cases_list
    c = {"id": "CASE-001", "title": "t", "factor": "part_gap", "finding": "f", "confidence": "reproduced", "ladder_step": 3,
         "experiments": ["E-008"], "status": "promoted", "rule_proposal": None}
    assert "not reviewed" in format_cases_list([c])
    assert "not reviewed" in format_case_detail(c)
