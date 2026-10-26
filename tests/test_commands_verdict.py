import json

import pytest

from lab.loop.commands import question_status, record_usage, record_verdict
from lab.records.schema import load
from loop_fixtures import make_project, minimal_experiment, minimal_question, started


@pytest.fixture
def proj(tmp_path):
    q = minimal_question()
    q["plans"] = [{"id": "P-001", "after": "E-009", "if": "B clearly smoother", "next": "try 60 mm/s"}]
    return make_project(tmp_path, q, [started(minimal_experiment())])


def V(proj, eid="E-009", **kw):
    args = dict(rank=None, strength=None, inconclusive=None, accept=None, defects=[], marks=[], witness=None,
                witness_override=None, anchors=[], not_about_target=False, note=None, replace=False, runs=None,
                lighting="diagnostic")  # judged under the diagnostic light unless a test says otherwise
    args.update(kw)
    return record_verdict(proj, eid, **args)


def test_verdict_supported_and_status_answered(proj):
    e = V(proj, rank="B>A", strength="clearly")
    assert e["status"] == "answered" and e["prediction_outcome"] == "supported"
    assert e["owner_verdict"]["order"] == [["E-009-B"], ["E-009-A"]] and e["owner_verdict"]["print_runs"] == ["PR-009-01"]
    assert load(proj.experiments / "E-009.json", "experiment")["prediction_outcome"] == "supported"


def test_tabs_and_full_ids_accepted(proj):
    assert V(proj, rank="9B>E-009-A", strength="clearly")["owner_verdict"]["order"] == [["E-009-B"], ["E-009-A"]]


def test_no_difference_group(proj):
    e = V(proj, rank="A=B")
    assert e["owner_verdict"]["order"] == [["E-009-A", "E-009-B"]] and e["prediction_outcome"] == "refuted"


def test_verdict_before_start_refused(tmp_path):
    p = make_project(tmp_path, minimal_question(), [minimal_experiment()])
    with pytest.raises(ValueError, match="start it first"):
        V(p, rank="B>A", strength="clearly")


def test_unknown_variant_lists_valid(proj):
    with pytest.raises(ValueError, match=r"E-009-A \(9A\), E-009-B \(9B\)"):
        V(proj, rank="B>C", strength="clearly")


def test_unknown_experiment_lists_valid_ids(proj):
    with pytest.raises(ValueError, match=r"E-077 isn't in hex-tile. Experiments: E-009"):
        V(proj, eid="E-077", rank="B>A", strength="clearly")


def test_reference_variant_needs_listing(proj):
    with pytest.raises(ValueError, match="E-002-A"):
        V(proj, rank="B>E-002-A", strength="clearly")


def test_strength_required_for_a_difference(proj):
    with pytest.raises(ValueError, match="strength"):
        V(proj, rank="B>A")


def test_second_verdict_needs_replace_and_keeps_old(proj):
    V(proj, rank="B>A", strength="clearly")
    with pytest.raises(ValueError, match="--replace"):
        V(proj, rank="A=B")
    e = V(proj, rank="A=B", replace=True)
    assert e["superseded_verdicts"][0]["order"] == [["E-009-B"], ["E-009-A"]]


def test_mark_stored_in_model_height(proj):
    e = V(proj, rank="B>A", strength="clearly", marks=["A:6"])
    assert e["owner_verdict"]["marks"] == [{"variant": "E-009-A", "mark_z_mm": 6.0, "defect_z_mm": 66.0}]


def test_witness_required_but_missing(tmp_path):
    e = started(minimal_experiment())
    e["controls"] = {"witness_required": True, "anchor": None}
    p = make_project(tmp_path, minimal_question(), [e])
    with pytest.raises(ValueError, match="witness"):
        V(p, rank="B>A", strength="clearly")
    assert V(p, rank="B>A", strength="clearly", witness="abnormal")["prediction_outcome"] == "inconclusive"


def test_not_about_target(proj):
    assert V(proj, rank="B>A", strength="clearly", not_about_target=True)["prediction_outcome"] == "unresolved"


def test_inconclusive_and_acceptance_rules(proj):
    assert V(proj, inconclusive="photo too dark")["prediction_outcome"] == "inconclusive"
    with pytest.raises(ValueError, match="full or scaled"):
        V(proj, accept=True, replace=True)


@pytest.mark.parametrize("pct", [0, 100, 140])
def test_failed_at_out_of_range(proj, pct):
    with pytest.raises(ValueError, match="1–99"):
        record_usage(proj, "PR-009-01", failed_at_pct=pct, minutes=None, grams=None)


def test_failed_run_returns_to_built(proj):
    e = record_usage(proj, "PR-009-01", failed_at_pct=40, minutes=None, grams=None)
    assert e["print_runs"][0]["failed"]["at_fraction"] == 0.4 and e["status"] == "built"


def test_manual_usage(proj):
    e = record_usage(proj, "PR-009-01", failed_at_pct=None, minutes=41, grams=11.6)
    assert e["print_runs"][0]["usage"] == {"actual_minutes": 41.0, "actual_g": 11.6, "usage_source": "manual",
                                          "completion_fraction": None}


def test_unknown_run_lists_runs(proj):
    with pytest.raises(ValueError, match="PR-009-01"):
        record_usage(proj, "PR-999", failed_at_pct=40, minutes=None, grams=None)


def test_status_shows_spend_outcome_and_next_plan(proj):
    V(proj, rank="B>A", strength="clearly")
    text = question_status(proj, "Q-009")
    assert "40 / 180 min" in text and "12 / 100 g" in text
    assert "E-009" in text and "supported" in text and "P-001" in text and "continue" in text
