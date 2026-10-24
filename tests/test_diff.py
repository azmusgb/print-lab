import json

import pytest
import trimesh

from lab.adapters.threemf import write_print_3mf
from lab.loop.builders import build_experiment, plan_experiment
from lab.loop.diff import actual_differences, undeclared
from lab.records.schema import load
from lab.records.store import atomic_write_json
from loop_fixtures import PLAN, project_with_sources
from test_builders import fake_slicer


@pytest.fixture
def proj(tmp_path):
    return project_with_sources(tmp_path)


def _plan(proj, tweak=None, **kw):
    eid = plan_experiment(proj, "Q-009", **{**PLAN, **kw})
    p = proj.experiments / f"{eid}.json"
    e = json.loads(p.read_text())
    if tweak:
        tweak(e)
        atomic_write_json(p, e)
    build_experiment(proj, eid, replace=False, slicer=fake_slicer)
    e = load(p, "experiment")
    return e, e["builds"][-1]


def test_clean_experiment_has_only_the_factor(proj):
    e, b = _plan(proj)
    diffs = actual_differences(proj, e, b)
    assert [(d["where"], d["key"]) for d in diffs] == [("settings", "inner_wall_speed")]
    assert undeclared(diffs, e) == ([], [])


def test_undeclared_setting_found(proj):
    e, b = _plan(proj, lambda e: e["build_spec"]["variants"][1]["settings_patch"].update(outer_wall_speed="60"))
    bad, _ = undeclared(actual_differences(proj, e, b), e)
    assert [(d["where"], d["key"]) for d in bad] == [("settings", "outer_wall_speed")]


def test_declared_dependent_adjustment_allowed(proj):
    def t(e):
        e["build_spec"]["variants"][1]["settings_patch"]["outer_wall_speed"] = "60"
        e["dependent_adjustments"] = {"outer_wall_speed": "80"}
    e, b = _plan(proj, t)
    assert undeclared(actual_differences(proj, e, b), e)[0] == []


def test_undeclared_plate_change_found(proj):
    e, b = _plan(proj, lambda e: e["build_spec"]["variants"][1].update(copies=2))
    bad, _ = undeclared(actual_differences(proj, e, b), e)
    assert ("plate", "copies") in [(d["where"], d["key"]) for d in bad]


def _box_source(proj):
    box = trimesh.creation.box((20, 150, 132))
    write_print_3mf(proj.sources / "hexagon_v57_X2D_0.4nozzle.3mf", [("v58_06_6in", box, (128, 128))],
                    proj.sources / "box.3mf", {})
    return "sources/box.3mf"


def test_undeclared_geometry_change_found(proj):
    src = _box_source(proj)
    e, b = _plan(proj, lambda e: e["build_spec"]["variants"][1].update(source=src))
    bad, _ = undeclared(actual_differences(proj, e, b), e)
    assert ("geometry", "mesh") in [(d["where"], d["key"]) for d in bad]


def test_bundle_factor_records_scope_and_list(proj):
    src = _box_source(proj)
    e, b = _plan(proj, factor="model_version", values=["sources/hexagon_v58_X2D_0.6nozzle.3mf", src], expect="A=B")
    bad, bundle = undeclared(actual_differences(proj, e, b), e)
    assert bad == [] and ("geometry", "mesh") in [(d["where"], d["key"]) for d in bundle]
    assert e["factor_scope"] == "bundle"


def test_cross_plate_reference_compared(proj):
    first, _ = _plan(proj, values=["250"], expect="")
    e, b = _plan(proj, values=["80"], expect="", references=[f"{first['id']}-A"])
    diffs = actual_differences(proj, e, b)
    assert [(d["where"], d["key"]) for d in diffs] == [("settings", "inner_wall_speed")]
