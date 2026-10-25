import json
import zipfile

import pytest

from lab.loop import capabilities
from lab.loop.builders import build_experiment, plan_experiment
from lab.records.schema import load
from loop_fixtures import PLAN, project_with_sources
from test_builders import fake_slicer


@pytest.fixture
def proj(tmp_path, monkeypatch):
    monkeypatch.setattr(capabilities, "CAP_DIR", tmp_path / "capabilities")
    return project_with_sources(tmp_path)


def test_capabilities_are_factor_specific(proj):
    capabilities.record("CAP-BAMBU-HEIGHT-RANGE-inner_wall_speed", True, {"how": "test"})
    assert capabilities.capability_passed("CAP-BAMBU-HEIGHT-RANGE-inner_wall_speed")
    assert not capabilities.capability_passed("CAP-BAMBU-HEIGHT-RANGE-outer_wall_speed")
    assert capabilities.height_range_capability("inner_wall_speed") == "CAP-BAMBU-HEIGHT-RANGE-inner_wall_speed"


def test_tabs_refused_before_capability(proj):
    eid = plan_experiment(proj, "Q-009", **PLAN, tabs=True)
    with pytest.raises(ValueError, match="CAP-TAB-ISOLATION"):
        build_experiment(proj, eid, replace=False, slicer=fake_slicer)


def test_stepped_falls_back_to_separate_strips(proj):
    eid = plan_experiment(proj, "Q-009", **{**PLAN, "values": ["120", "80"]}, stepped=True)
    e = load(proj.experiments / f"{eid}.json", "experiment")
    assert not e["build_spec"].get("stepped")
    assert any("separate strips" in n for n in e["build_spec"]["notes"])


def test_stepped_with_capability_makes_twin_reversed(proj):
    capabilities.record("CAP-BAMBU-HEIGHT-RANGE-inner_wall_speed", True, {"how": "test"})
    eid = plan_experiment(proj, "Q-009", **{**PLAN, "values": ["120", "80"], "expect": "B>A:clearly"}, stepped=True)
    e = load(proj.experiments / f"{eid}.json", "experiment")
    assert e["build_spec"]["stepped"]["bands"] == [[0.0, 6.0, "120"], [6.0, 12.0, "80"]]
    b = build_experiment(proj, eid, replace=False, slicer=fake_slicer)
    assert b["plate"]["objects"] == ["STEP-1", "STEP-2"]
    with zipfile.ZipFile(proj.root / b["artifact"]) as z:
        xml = z.read("Metadata/layer_config_ranges.xml").decode()
    first, second = xml.split('<object id="2">')
    assert first.index('>120<') < first.index('>80<') and second.index('>80<') < second.index('>120<')


def test_stepped_only_for_verified_per_object_factors(proj):
    with pytest.raises(ValueError, match="stepped"):
        plan_experiment(proj, "Q-009", **{**PLAN, "factor": "nozzle_temperature", "values": ["210"]}, stepped=True)


@pytest.mark.slow
def test_tab_size_and_eight_layer_limit(tmp_path):
    from lab.loop.tabs import id_tab
    t = id_tab("5A", tmp_path / "jobs")
    assert t.extents[2] == pytest.approx(1.6, abs=0.01) and t.extents[0] == pytest.approx(10, abs=0.01)
    assert t.bounds[1][1] == pytest.approx(9.0, abs=0.01)  # 6 mm tab + 3 mm bridge


@pytest.mark.slow
def test_tabs_do_not_count_as_a_geometry_difference(proj):
    from lab.loop.diff import actual_differences, undeclared
    capabilities.record(capabilities.TAB_ISOLATION, True, {"how": "test"})
    eid = plan_experiment(proj, "Q-009", **PLAN)
    b = build_experiment(proj, eid, replace=False, slicer=fake_slicer)
    e = load(proj.experiments / f"{eid}.json", "experiment")
    assert e["build_spec"]["tabs"] is True
    assert undeclared(actual_differences(proj, e, b), e) == ([], [])



def test_tab_text_is_not_a_geometry_finding(tmp_path):
    """The '7' of a '7A' tab is thinner than a line (E-007): a label at bed level, not part of the judged strip."""
    import trimesh
    from lab.checks import run_checks
    from lab.loop.guards import blocking_geometry
    from lab.loop.tabs import attach_tab
    strip = attach_tab(trimesh.creation.box([10, 40, 20]).apply_translation([0, 0, 10]), "7A", tmp_path)
    findings = run_checks(strip, nozzle=0.4)
    assert any(f.rule == "feature-below-line-width" for f in findings)  # the check does see the text
    assert blocking_geometry(findings, tabbed=True) == []
    assert blocking_geometry(findings, tabbed=False)


def test_the_tab_joins_a_strip_whose_end_leans_in_at_the_bed(tmp_path):
    """E-009: a strip cut from the tile's upper face is shorter at bed level than at its top; the tab must reach it."""
    import numpy as np
    import trimesh
    from lab.loop.tabs import attach_tab
    # a slab 40 mm long at the top, 30 mm at the bed: the -Y end leans in by 5 mm
    v = np.array([[-5, -15, 0], [5, -15, 0], [5, 15, 0], [-5, 15, 0],
                  [-5, -20, 12], [5, -20, 12], [5, 20, 12], [-5, 20, 12]], float)
    strip = trimesh.convex.convex_hull(v)
    joined = attach_tab(strip, "40", tmp_path)
    assert len(joined.split(only_watertight=False)) == 1
