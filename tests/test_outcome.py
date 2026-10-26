import copy

import pytest

from lab.loop.outcome import comparison_validity, prediction_outcome
from loop_fixtures import minimal_experiment

VALID = {"status": "valid", "reasons": []}


def judged(order, strength, about=True, expect=None, **verdict):
    e = minimal_experiment()
    if expect is not None:
        e["expect"] = expect
    e["owner_verdict"] = {"kind": "ranking", "order": [[f"E-009-{x}" for x in g] for g in order],
                          "strength": strength, "about_target": about, "by": "owner", "at": "2026-10-25T10:00:00+00:00",
                          "lighting": "diagnostic", **verdict}
    return e


@pytest.mark.parametrize("order,strength,about,want", [
    (["B", "A"], "clearly", True, "supported"), (["B", "A"], "a lot", True, "supported"),
    (["B", "A"], "slightly", True, "unresolved"), (["B", "A"], None, True, "unresolved"),
    (["B", "A"], "clearly", None, "unresolved"), (["B", "A"], "clearly", False, "unresolved"),
    (["AB"], None, True, "refuted"), (["A", "B"], "clearly", True, "refuted"), (["A", "B"], "slightly", True, "refuted"),
    (["AB"], None, False, "unresolved")])
def test_outcome_better_than(order, strength, about, want):
    assert prediction_outcome(judged(order, strength, about), VALID) == want


SAME = {"same": ["E-009-A", "E-009-B"]}


@pytest.mark.parametrize("order,strength,about,want", [
    (["AB"], None, True, "supported"), (["AB"], None, None, "unresolved"), (["AB"], None, False, "unresolved"),
    (["B", "A"], "slightly", True, "unresolved"), (["B", "A"], "clearly", True, "refuted"),
    (["A", "B"], "a lot", True, "refuted"), (["A", "B"], "slightly", True, "unresolved")])
def test_outcome_same(order, strength, about, want):
    assert prediction_outcome(judged(order, strength, about, SAME), VALID) == want


def test_inconclusive_verdict_and_no_verdict():
    e = minimal_experiment()
    assert prediction_outcome(e, VALID) is None
    e["owner_verdict"] = {"kind": "inconclusive", "reason": "too dark", "by": "owner", "at": "t"}
    assert prediction_outcome(e, VALID) == "inconclusive"


@pytest.mark.parametrize("cond", ["abnormal", "inconclusive"])
def test_witness_forces_inconclusive_unless_overridden(cond):
    e = judged(["B", "A"], "clearly", witness={"id": "WITNESS-01", "condition": cond, "note": None})
    assert prediction_outcome(e, comparison_validity(e, {}, 10)) == "inconclusive"
    e["owner_verdict"]["witness_override"] = "the witness only has a blob at one end"
    assert prediction_outcome(e, comparison_validity(e, {}, 10)) == "supported"


def test_migrated_supported_becomes_unresolved():
    e = judged(["B", "A"], "clearly")
    e["provenance"] = "migrated"
    assert prediction_outcome(e, VALID) == "unresolved"
    e["provenance"] = "post_hoc"
    assert prediction_outcome(e, VALID) == "unresolved"


@pytest.mark.parametrize("cond,status,code", [("different", "confounded", "anchor_shifted"),
                                              ("inconclusive", "unknown", "anchor_inconclusive")])
def test_anchor_conditions(cond, status, code):
    e = judged(["B", "A"], "clearly")
    e["anchors"] = [{"id": "E-009-ANCHOR", "compared_to": "E-002-A", "condition": cond, "strength": None, "note": None}]
    v = comparison_validity(e, {}, 10)
    assert v["status"] == status and v["reasons"][0]["code"] == code
    assert prediction_outcome(e, v) == "inconclusive"


def _with_profile(e, seconds, eid=None):
    bid = f"BLD-{(eid or e['id'])[2:]}-01"
    e["builds"] = [{"id": bid, "ok": True,
                    "measured": {"layer_time_median_s": seconds,
                                 "layer_time_profile": [[0.2 * i, seconds] for i in range(1, 61)]}}]
    e["print_runs"] = [{"id": f"PR-{(eid or e['id'])[2:]}-01", "build_id": bid}]
    return e


ANCHOR = [{"id": "E-009-ANCHOR", "compared_to": "E-002-A", "condition": "same", "strength": None, "note": None}]


def test_layer_time_mismatch_confounds_cross_plate():
    ref = _with_profile(minimal_experiment("E-002"), 18.4)
    e = _with_profile(judged(["B", "A"], "clearly"), 34.8)
    e["reference_variants"] = ["E-002-A"]
    v = comparison_validity(e, {"E-002": ref}, 10)
    assert v["status"] == "confounded" and "layer_time_mismatch" in [r["code"] for r in v["reasons"]]


def test_layer_time_mismatch_not_a_confound_when_plate_is_the_factor():
    ref = _with_profile(minimal_experiment("E-002"), 18.4)
    e = _with_profile(judged(["B", "A"], "clearly"), 34.8)
    e["reference_variants"] = ["E-002-A"]
    e["factor"] = {"name": "objects_on_plate", "values": [1, 2], "unit": ""}
    assert comparison_validity(e, {"E-002": ref}, 10)["status"] == "valid"


def test_within_tolerance_is_valid():
    ref = _with_profile(minimal_experiment("E-002"), 18.4)
    e = _with_profile(judged(["B", "A"], "clearly"), 19.5)
    e["reference_variants"] = ["E-002-A"]
    e["anchors"] = ANCHOR
    assert comparison_validity(e, {"E-002": ref}, 10)["status"] == "valid"
