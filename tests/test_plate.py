import json

import pytest

from lab.loop.builders import build_experiment
from lab.loop.outcome import comparison_validity, judged_window
from lab.loop.plate import plates_match
from lab.records.schema import load
from lab.records.store import atomic_write_json
from loop_fixtures import minimal_experiment, started
from test_builders import fake_slicer
from test_guards import built, edit, proj  # noqa: F401


def prof(fn):
    return [[round(0.2 * i, 2), fn(0.2 * i)] for i in range(1, 61)]  # a 12 mm strip


def test_plates_match_within_tolerance():
    r = plates_match(prof(lambda z: 20.0), prof(lambda z: 21.0), (0, 12), 10)
    assert r["match"] and r["worst_pct"] == pytest.approx(5.0, abs=0.1)


def test_equal_medians_but_window_mismatch_caught():
    a = prof(lambda z: 20.0)
    b = prof(lambda z: 10.0 if z <= 6 else 30.0)
    from lab.loop.plate import median_layer_time
    assert median_layer_time(a) == pytest.approx(median_layer_time(b), abs=10.1)
    r = plates_match(a, b, (6.5, 12), 10)
    assert not r["match"] and r["worst_pct"] == pytest.approx(50.0, abs=1) and 6.5 <= r["at_z"] <= 12


def test_judged_window_from_a_defect_mark():
    e = started(minimal_experiment())
    e["build_spec"]["z"] = [60, 100]
    e["owner_verdict"] = {"kind": "ranking", "order": [["E-009-B"], ["E-009-A"]], "strength": "clearly",
                          "about_target": True, "by": "owner", "at": "t",
                          "marks": [{"variant": "E-009-A", "mark_z_mm": 25.0, "defect_z_mm": 85.0}]}
    assert judged_window(e) == (15.0, 35.0)


def _two(seconds_a, seconds_b):
    ref = minimal_experiment("E-002")
    ref["builds"] = [{"id": "BLD-002-01", "ok": True, "measured": {"layer_time_profile": prof(seconds_a)}}]
    ref["print_runs"] = [{"id": "PR-002-01", "build_id": "BLD-002-01"}]
    e = started(minimal_experiment())
    e["build_spec"]["judged"] = [66, 72]
    e["builds"][-1]["measured"]["layer_time_profile"] = prof(seconds_b)
    e["reference_variants"] = ["E-002-A"]
    e["anchors"] = [{"id": "E-009-X", "compared_to": "E-002-A", "condition": "same", "strength": None, "note": None}]
    return e, {"E-002": ref}


def test_validity_uses_the_judged_heights():
    e, others = _two(lambda z: 20.0, lambda z: 10.0 if z <= 6 else 30.0)
    v = comparison_validity(e, others, 10)
    assert v["status"] == "confounded" and v["reasons"][0]["code"] == "layer_time_mismatch"
    assert 6 <= v["reasons"][0]["at_z"] <= 12


def test_production_mismatch_flagged(proj):
    eid = built(proj)  # two objects on the plate
    atomic_write_json(proj.project_json, {"production_plate": {"objects": 1}})
    from lab.loop.commands import refresh_derived
    e = refresh_derived(proj, load(proj.experiments / f"{eid}.json", "experiment"))
    assert "production_mismatch" in [r["code"] for r in e["comparison_validity"]["reasons"]]
    assert e["comparison_validity"]["status"] == "valid"   # a warning, not a confound


def test_repeat_build_mirrors_placements(proj):
    eid = built(proj)
    e = load(proj.experiments / f"{eid}.json", "experiment")
    first = e["builds"][-1]["plate"]
    edit(proj, eid, lambda x: x.update(print_runs=[{"id": f"PR-{eid[2:]}-01", "build_id": x["builds"][-1]["id"]}],
                                       status="built"))
    edit(proj, eid, lambda x: x["build_spec"].update(note="repeat"))
    b = build_experiment(proj, eid, replace=True, slicer=fake_slicer)
    assert b["plate"]["objects"] == list(reversed(first["objects"]))
