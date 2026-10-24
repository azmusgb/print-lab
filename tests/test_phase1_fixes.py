"""Findings from the Phase 1 review, each pinned by a test."""
import json

import pytest

from lab.loop.builders import build_experiment, plan_experiment
from lab.loop.commands import record_usage, record_verdict
from lab.loop.guards import check_experiment, start
from lab.loop.ledger import run_usage
from lab.loop.outcome import comparison_validity
from lab.records.schema import load
from loop_fixtures import PLAN, minimal_experiment, started
from test_builders import fake_slicer
from test_guards import built, codes, edit, proj  # noqa: F401


# 1. plate-wide settings can't be varied on one plate; the realized factor is checked in the G-code
@pytest.mark.parametrize("factor,values", [("nozzle_temperature", ["190", "240"]), ("fan_max_speed", ["20", "100"]),
                                           ("objects_on_plate", ["1", "2"])])
def test_plate_wide_factor_with_two_values_on_one_plate_refused(proj, factor, values):
    with pytest.raises(ValueError, match="plate-wide"):
        plan_experiment(proj, "Q-009", **{**PLAN, "factor": factor, "values": values})


def test_plate_wide_factor_with_one_value_and_a_reference_is_fine(proj):
    first = plan_experiment(proj, "Q-009", **{**PLAN, "factor": "nozzle_temperature", "values": ["210"], "expect": ""})
    plan_experiment(proj, "Q-009", **{**PLAN, "factor": "nozzle_temperature", "values": ["220"], "expect": "",
                                      "references": [f"{first}-A"]})


def test_speed_not_realized_blocks(proj, monkeypatch):
    import lab.loop.realized as r
    eid = built(proj)  # 250 vs 80 requested
    monkeypatch.setattr(r, "object_feature_speeds", lambda sliced, feature: {"E-001-A": (147.0, 0.99),
                                                                             "E-001-B": (146.8, 0.99)})
    res = check_experiment(proj, eid)
    assert "factor_not_realized" in codes(res, "blocked")


def test_speed_realized_differently_is_recorded_not_blocked(proj, monkeypatch):
    import lab.loop.realized as r
    eid = built(proj)
    monkeypatch.setattr(r, "object_feature_speeds", lambda sliced, feature: {"E-001-A": (147.0, 0.99),
                                                                             "E-001-B": (80.0, 0.99)})
    res = check_experiment(proj, eid)
    g = next(x for x in res.guards if x.code == "factor_not_realized")
    assert g.ok and "realized differently" in g.message and "147" in g.message
    assert res.realization["status"] == "realized_differently"
    assert res.realization["variants"]["E-001-A"] == {"requested": 250.0, "realized": 147.0, "coverage": 0.99}


# 2. start refuses answered and abandoned experiments
@pytest.mark.parametrize("status", ["answered", "abandoned"])
def test_start_refuses_finished_experiments(proj, status):
    eid = built(proj)
    edit(proj, eid, lambda e: e.update(status=status))
    with pytest.raises(ValueError, match=status):
        start(proj, eid)


# 3. a missing artifact fails the difference guard
def test_missing_artifact_is_a_failure(proj):
    eid = built(proj)
    e = load(proj.experiments / f"{eid}.json", "experiment")
    (proj.root / e["builds"][-1]["artifact"]).unlink()
    res = check_experiment(proj, eid)
    assert res.status in ("rebuild", "blocked") and "undeclared_difference" in codes(res)


# 4. cross-plate comparisons use the build that was printed, and fail closed
def _ref(seconds_by_build):
    ref = minimal_experiment("E-002")
    ref["builds"] = [{"id": bid, "ok": True, "measured": {"layer_time_median_s": s,
                                                          "layer_time_profile": [[0.2 * i, s] for i in range(1, 61)]}}
                     for bid, s in seconds_by_build]
    ref["print_runs"] = [{"id": "PR-002-01", "build_id": "BLD-002-01"}]
    return ref


def _crossing(seconds):
    e = started(minimal_experiment())
    e["builds"][-1]["measured"]["layer_time_profile"] = [[0.2 * i, seconds] for i in range(1, 61)]
    e["reference_variants"] = ["E-002-A"]
    e["anchors"] = [{"id": "E-009-ANCHOR", "compared_to": "E-002-A", "condition": "same", "strength": None,
                     "note": None}]
    return e


def test_reference_uses_the_printed_build():
    ref = _ref([("BLD-002-01", 18.0), ("BLD-002-02", 36.0)])  # only BLD-002-01 was printed
    assert comparison_validity(_crossing(18.0), {"E-002": ref}, 10)["status"] == "valid"


def test_unmeasurable_reference_is_unknown():
    ref = _ref([("BLD-002-01", 18.0)])
    ref["builds"][0]["measured"] = None
    v = comparison_validity(_crossing(18.0), {"E-002": ref}, 10)
    assert v["status"] == "unknown" and v["reasons"][0]["code"] == "reference_unmeasurable"


# 5. separate plates with no anchor are weak
def test_cross_plate_without_anchor_is_unknown():
    ref = _ref([("BLD-002-01", 18.0)])
    e = _crossing(18.0)
    e["anchors"] = []
    v = comparison_validity(e, {"E-002": ref}, 10)
    assert v["status"] == "unknown" and "cross_plate_no_anchor" in [r["code"] for r in v["reasons"]]


def test_plate_factor_crosses_plates_by_design():
    ref = _ref([("BLD-002-01", 18.0)])
    e = _crossing(36.0)
    e["anchors"] = []
    e["factor"] = {"name": "objects_on_plate", "values": [2], "unit": ""}
    v = comparison_validity(e, {"E-002": ref}, 10)
    assert v["status"] == "valid" and [r["code"] for r in v["reasons"]] == ["cross_plate_by_design"]


# 6. manual usage falls back field by field
def test_manual_usage_falls_back_per_field():
    b = {"id": "B", "ok": True, "estimate": {"minutes": 50.0, "g": 20.0}}
    assert run_usage({"usage": {"actual_minutes": 41.0, "actual_g": None, "usage_source": "manual"}}, b) == (41.0, 20.0)
    assert run_usage({"usage": {"actual_minutes": None, "actual_g": 11.0, "usage_source": "manual"}}, b) == (50.0, 11.0)


def test_single_object_plate_speeds_are_read():
    from pathlib import Path
    from lab.loop.realized import object_feature_speeds
    p = Path(__file__).parent / "fixtures" / "hex" / "studio_saved_v58_strip.gcode.3mf"  # E-002's lone strip
    (speed, cover), = object_feature_speeds(p, "Inner wall").values()
    assert speed == 147.0 and cover > 0.95


def test_factor_execution_scopes_recorded_with_evidence():
    from lab.loop.outcome import _factors
    f = _factors()
    assert f["inner_wall_speed"]["execution_scope"] == "per_object_verified"
    assert f["outer_wall_speed"]["execution_scope"] == "per_object_verified"
    assert f["nozzle_temperature"]["execution_scope"] == "per_plate_only"
    assert f["fan_max_speed"]["execution_scope"] == "per_plate_only"
    assert f["slow_down_layer_time"]["execution_scope"] == "unknown"
    for k in ("inner_wall_speed", "nozzle_temperature"):
        assert f[k]["scope_evidence"]["bambu_studio"] == "02.08.02.61"
    assert all("per_object" not in v for v in f.values())


def test_unknown_scope_is_treated_as_plate_wide(proj):
    with pytest.raises(ValueError, match="plate-wide"):
        plan_experiment(proj, "Q-009", **{**PLAN, "factor": "slow_down_layer_time", "values": ["4", "8"]})
