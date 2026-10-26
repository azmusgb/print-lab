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


# ---- review of ad6009f ------------------------------------------------------------------------------------------

def _cases_project(tmp_path, *exps):
    return make_project(tmp_path, minimal_question(), list(exps))


def test_an_unreviewed_case_on_disk_is_shown_at_most_supported(tmp_path):
    from lab.loop.cases import cases_dir, format_cases_list, load_cases
    from lab.records.store import atomic_write_json
    paths = _cases_project(tmp_path, _answered("E-008"))
    atomic_write_json(cases_dir(paths) / "CASE-001.json",
                      {"id": "CASE-001", "title": "t", "factor": "part_gap", "finding": "f", "confidence": "reproduced",
                       "ladder_step": 3, "experiments": ["E-008"], "status": "promoted"})
    c = load_cases(paths)[0]
    assert (c["confidence"], c["ladder_step"], c["reviewed"]) == ("supported", 2, False)
    assert c["recorded_confidence"] == "reproduced"
    assert "●●○○○" in format_cases_list([c])


def test_inconclusive_or_unresolved_verdicts_dont_count():
    from lab.loop.cases import evaluate_confidence
    e = _answered("E-011")
    e["owner_verdict"] = {"kind": "inconclusive", "reason": "print failed", "by": "owner", "at": "t"}
    r = _answered("E-001")
    r["owner_verdict"] = {"kind": "ranking", "order": [["E-001-A"]], "lighting": None, "by": "owner", "at": "t"}
    r["prediction_outcome"] = "unresolved"
    assert evaluate_confidence([e, r]) == ("candidate", 1)


def test_the_pages_verdict_command_asks_for_the_light(tmp_path):
    from lab import page_index
    paths = _cases_project(tmp_path, started(minimal_experiment("E-009")))
    needs = page_index.build_index(paths.root)["needs"]
    assert '--lighting "diagnostic|room"' in needs[0]["command"]


def test_a_ranking_without_a_light_warns(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LAB_HOME", str(tmp_path))
    make_project(tmp_path, minimal_question(), [started(minimal_experiment("E-009"))])
    main(["--project", "hex-tile", "exp", "verdict", "E-009", "--rank", "B>A", "--strength", "clearly"])
    assert "light" in capsys.readouterr().err


def test_checkers_dont_call_a_case_proven():
    import inspect
    from lab.checks import part_gap, wall_speed
    assert "proven" not in inspect.getsource(part_gap) and "proven" not in inspect.getsource(wall_speed)


def test_a_review_goes_stale_when_its_evidence_changes(tmp_path):
    from lab.loop.cases import load_cases, review_case, sync_cases
    from lab.loop.commands import load_experiment, save_experiment
    paths = _cases_project(tmp_path, _answered("E-008"), _answered("E-012"))
    sync_cases(paths)
    review_case(paths, "CASE-001", level="reproduced", reason="both fused")
    e = load_experiment(paths, "E-012")
    e["owner_verdict"]["at"] = "2026-10-27T10:00:00+00:00"  # verdict replaced
    save_experiment(paths, e)
    sync_cases(paths)
    c = next(x for x in load_cases(paths) if x["id"] == "CASE-001")
    assert c["review"]["stale"] is True and c["confidence"] == "supported"


def test_a_case_no_longer_generated_is_marked_orphaned(tmp_path):
    from lab.loop.cases import cases_dir, load_cases, sync_cases
    from lab.records.store import atomic_write_json
    paths = _cases_project(tmp_path, _answered("E-008"))
    atomic_write_json(cases_dir(paths) / "CASE-777.json", {"id": "CASE-777", "title": "old", "factor": "x",
                                                            "finding": "f", "confidence": "supported", "ladder_step": 2})
    sync_cases(paths)
    assert next(c for c in load_cases(paths) if c["id"] == "CASE-777")["orphaned"] is True


def test_a_promoted_case_reviewed_below_reproduced_is_flagged():
    from lab.loop.cases import format_case_detail
    c = {"id": "CASE-001", "title": "t", "factor": "part_gap", "finding": "f", "confidence": "supported",
         "ladder_step": 2, "experiments": [], "status": "promoted",
         "review": {"by": "owner", "level": "supported", "reason": "r", "at": "t"}}
    assert "below" in format_case_detail(c)


def test_check_rule_without_history_has_every_field(tmp_path):
    from lab.loop.cases import check_rule_against_history, sync_cases
    paths = _cases_project(tmp_path, _answered("E-008"))
    sync_cases(paths)
    res = check_rule_against_history(paths, "CASE-001")
    assert res["flagged_count"] == 0 and "coverage_note" in res and res["flagged_versions"] == []


def test_review_regenerates_first_and_checks_the_id(tmp_path):
    from lab.loop.cases import review_case
    paths = _cases_project(tmp_path, _answered("E-008"))
    assert review_case(paths, "CASE-001", level="supported", reason="r")["review"]["level"] == "supported"
    with pytest.raises(ValueError, match="CASE-"):
        review_case(paths, "../evil", level="supported", reason="r")
    with pytest.raises(ValueError, match="Give the case"):
        review_case(paths, None, level="supported", reason="r")


def test_findings_say_when_the_light_wasnt_diagnostic():
    from lab.loop.outcome import criteria_finding
    e = started(minimal_experiment("E-009"))
    e["criteria"] = [{"key": "print", "label": "Printed?", "choices": ["clean", "flawed", "failed"]}]
    e["owner_verdict"] = {"kind": "criteria", "grades": {"E-009-A": {"print": "clean"}}, "lighting": None}
    assert "light not recorded" in criteria_finding(e)


def test_a_sweep_under_an_unknown_light_is_unresolved():
    from lab.loop.outcome import prediction_outcome
    e = started(minimal_experiment("E-009"))
    e["test_kind"], e["expect"] = "speed_sweep", {"bands_from": 80}
    e["variants"] = [{"id": "E-009-A", "factor_value": 40}, {"id": "E-009-B", "factor_value": 80}]
    e["owner_verdict"] = {"kind": "sweep", "grades": {"E-009-A": "clean", "E-009-B": "banded"}, "lighting": None}
    assert prediction_outcome(e, {"status": "valid"}) == "unresolved"
