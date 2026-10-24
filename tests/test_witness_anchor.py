import json
import shutil

import pytest

from lab.loop.builders import build_experiment, plan_experiment
from lab.loop.diff import actual_differences, undeclared
from lab.loop.witness import WITNESS_VERSION, witness_wall
from lab.records.schema import load
from lab.records.store import atomic_write_json
from loop_fixtures import PLAN, project_with_sources
from test_builders import fake_slicer


@pytest.fixture
def proj(tmp_path):
    return project_with_sources(tmp_path)


def test_witness_geometry_and_version():
    w = witness_wall(12.0, 0.42)
    assert WITNESS_VERSION == "WITNESS-01"
    assert tuple(round(x, 2) for x in w.extents) == (0.84, 40.0, 12.0) and w.is_watertight


def _printed(proj, **kw):
    eid = plan_experiment(proj, "Q-009", **{**PLAN, **kw})
    build_experiment(proj, eid, replace=False, slicer=fake_slicer)
    p = proj.experiments / f"{eid}.json"
    e = json.loads(p.read_text())
    e["print_runs"] = [{"id": f"PR-{eid[2:]}-01", "build_id": e["builds"][-1]["id"]}]
    e["status"] = "printing"
    atomic_write_json(p, e)
    return eid


def test_witness_default_on_cross_plate_off_same_plate(proj):
    same = load(proj.experiments / f"{plan_experiment(proj, 'Q-009', **PLAN)}.json", "experiment")
    assert same["controls"]["witness_required"] is False and same["build_spec"]["witness"] is False
    first = _printed(proj, values=["250"], expect="")
    cross = load(proj.experiments / f"{plan_experiment(proj, 'Q-009', **{**PLAN, 'values': ['80'], 'expect': '', 'references': [f'{first}-A']})}.json", "experiment")
    assert cross["controls"]["witness_required"] is True and cross["build_spec"]["witness"] is True
    assert {"id": "WITNESS-01", "tab": None, "role": "control"} in cross["variants"]


def test_witness_placed_at_least_25_mm_away(proj):
    first = _printed(proj, values=["250"], expect="")
    eid = plan_experiment(proj, "Q-009", **{**PLAN, "values": ["80"], "expect": "", "references": [f"{first}-A"]})
    b = build_experiment(proj, eid, replace=False, slicer=fake_slicer)
    objs = dict(zip(b["plate"]["objects"], b["plate"]["placements"]))
    assert "WITNESS-01" in objs
    from lab.adapters.threemf import load_object
    from lab.geometry.coupons import height_strip
    half = height_strip(load_object(proj.sources / "hexagon_v58_X2D_0.6nozzle.3mf", "v58_06_6in"), 60, 72).extents[0] / 2
    gap = objs["WITNESS-01"][0] - 0.42 - (objs[f"{eid}-A"][0] + half)
    assert gap == pytest.approx(25, abs=0.01)


def test_witness_spacing_refusal(proj):
    first = _printed(proj, values=["250"], expect="")
    eid = plan_experiment(proj, "Q-009", **{**PLAN, "values": ["80"], "expect": "", "references": [f"{first}-A"]})
    p = proj.experiments / f"{eid}.json"
    e = json.loads(p.read_text())
    e["build_spec"]["variants"][0]["copies"] = 6  # six strips fit; the witness doesn't
    atomic_write_json(p, e)
    with pytest.raises(ValueError, match="witness"):
        build_experiment(proj, eid, replace=False, slicer=fake_slicer)


def test_anchor_reuses_original_inputs_and_placement(proj):
    first = _printed(proj)
    orig = load(proj.experiments / f"{first}.json", "experiment")["builds"][-1]["plate"]
    eid = plan_experiment(proj, "Q-009", **{**PLAN, "values": ["120"], "expect": "", "anchor": f"{first}-A"})
    e = load(proj.experiments / f"{eid}.json", "experiment")
    assert {"id": f"{eid}-ANCHOR", "tab": None, "role": "anchor", "same_as": f"{first}-A"} in e["variants"]
    b = build_experiment(proj, eid, replace=False, slicer=fake_slicer)
    place = dict(zip(b["plate"]["objects"], b["plate"]["placements"]))
    assert place[f"{eid}-ANCHOR"] == dict(zip(orig["objects"], orig["placements"]))[f"{first}-A"]
    diffs = actual_differences(proj, load(proj.experiments / f"{eid}.json", "experiment"), b)
    assert not [d for d in diffs if "ANCHOR" in d["a"] + d["b"]]


def test_anchor_that_differs_from_its_original_blocks(proj):
    first = _printed(proj)
    eid = plan_experiment(proj, "Q-009", **{**PLAN, "values": ["120"], "expect": "", "anchor": f"{first}-A"})
    p = proj.experiments / f"{eid}.json"
    e = json.loads(p.read_text())
    e["build_spec"]["anchor"]["settings_patch"] = {"inner_wall_speed": "200"}
    atomic_write_json(p, e)
    b = build_experiment(proj, eid, replace=False, slicer=fake_slicer)
    bad, _ = undeclared(actual_differences(proj, load(p, "experiment"), b), load(p, "experiment"))
    assert any("ANCHOR" in d["a"] + d["b"] for d in bad)


def test_anchor_with_changed_inputs_refused(proj):
    first = _printed(proj)
    eid = plan_experiment(proj, "Q-009", **{**PLAN, "values": ["120"], "expect": "", "anchor": f"{first}-A"})
    shutil.copy2(proj.sources / "hexagon_v57_X2D_0.4nozzle.3mf", proj.sources / "hexagon_v58_X2D_0.6nozzle.3mf")
    with pytest.raises(ValueError, match="anchor"):
        build_experiment(proj, eid, replace=False, slicer=fake_slicer)


def test_builder_code_change_with_identical_output_is_not_stale(proj, monkeypatch):
    from lab.loop import builders
    from lab.loop.guards import check_experiment
    eid = plan_experiment(proj, "Q-009", **PLAN)
    build_experiment(proj, eid, replace=False, slicer=fake_slicer)
    monkeypatch.setattr(builders, "builder_fingerprint", lambda: "new-code")
    g = next(x for x in check_experiment(proj, eid).guards if x.code == "stale_build")
    assert g.ok and "identical" in g.message


def test_builder_code_change_with_different_output_is_stale(proj, monkeypatch):
    from lab.loop import builders
    from lab.loop.guards import check_experiment
    eid = plan_experiment(proj, "Q-009", **PLAN)
    build_experiment(proj, eid, replace=False, slicer=fake_slicer)
    monkeypatch.setattr(builders, "builder_fingerprint", lambda: "new-code")
    real = builders._lay_out
    monkeypatch.setattr(builders, "_lay_out", lambda *a: [(n, m, (x + 1, y)) for n, m, (x, y) in real(*a)])
    g = next(x for x in check_experiment(proj, eid).guards if x.code == "stale_build")
    assert not g.ok
