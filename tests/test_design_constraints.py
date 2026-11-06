"""Design constraints: each hex-tile constraint passes on Rift v6 (except the top-wall warning, which v6 really breaks
under the base settings) and fails on a design that breaks it."""
from pathlib import Path

import pytest

from lab.adapters.bambu import read_settings
from lab.design import constraints as C
from lab.design.families import faceted_hex as fh
from lab.design.family import resolve

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / "projects/hex-tile"
SETTINGS = read_settings(PROJECT / "sources/RIFT_6IN_marked_pair.3mf")


def _one(cid: str) -> list[dict]:
    return [c for c in C.load(PROJECT) if c["id"] == cid]


def _check(cid: str, params: dict, part=None, settings=SETTINGS) -> C.Result:
    (result,) = C.check(_one(cid), fh, params, part, settings)
    return result


@pytest.fixture(scope="module")
def v6():
    p = resolve(fh.PARAMS)
    return p, fh.build(p)


def test_the_file_is_well_formed():
    cs = C.load(PROJECT)
    assert len({c["id"] for c in cs}) == len(cs)
    for c in cs:
        assert c["severity"] in ("block", "warn") and c["reason"] and c["source"]
        assert c["check"] in ("min", "max", "infill_bands", "mark_clearance")


@pytest.mark.parametrize("cid,param,bad", [
    ("skin-gap", "edge_depth", 6.0),
    ("skin-two-lines", "skin_axial", 0.6),
    ("wall-two-lines", "perimeter_wall", 0.6),
    ("land-two-lines", "land_thickness", 0.6),
    ("roof-two-lines", "roof_wall", 0.6),
])
def test_parameter_limits(cid, param, bad):
    good = resolve(fh.PARAMS)
    assert _check(cid, good).ok
    # Raw values on purpose: the family's ranges would refuse some of these before a constraint saw them.
    failed = _check(cid, {**good, param: bad})
    assert not failed.ok and failed.severity == "block" and failed.value == bad


def test_infill_behind_face_allows_v6s_roof_junction(v6):
    p, part = v6
    result = _check("no-infill-behind-face", p, part)
    assert result.ok
    assert result.value < 3.0  # the 2.2–2.4 mm band where the roof plate meets the skin


def test_infill_behind_face_catches_a_roof_thick_enough_to_be_solid_again():
    p = resolve(fh.PARAMS, {"roof_wall": 6})
    result = _check("no-infill-behind-face", p, fh.build(p))
    assert not result.ok and result.value > 5


def test_infill_check_needs_the_settings(v6):
    p, part = v6
    result = _check("no-infill-behind-face", p, part, settings=None)
    assert not result.ok and "needs the base settings" in result.message


def test_geometry_checks_wait_for_a_part():
    assert C.check(_one("no-infill-behind-face"), fh, resolve(fh.PARAMS), None, SETTINGS) == []


def test_top_wall_warns_under_the_base_shells_and_passes_with_more():
    p = resolve(fh.PARAMS)
    base = _check("top-wall-all-shells", p)
    assert not base.ok and base.severity == "warn" and base.limit == pytest.approx(1.6)
    assert _check("top-wall-all-shells", p, settings={**SETTINGS, "bottom_shell_layers": "7"}).ok


def test_mark_stays_on_the_land():
    assert _check("mark-on-land", resolve(fh.PARAMS)).ok
    assert _check("mark-on-land", resolve(fh.PARAMS, {"land_width": 15})).ok
    narrow = _check("mark-on-land", resolve(fh.PARAMS, {"land_width": 14}))
    assert not narrow.ok and narrow.value < 1.0
    assert C.check(_one("mark-on-land"), fh, resolve(fh.PARAMS, {"mark": 0}), None, SETTINGS) == []


def test_other_families_constraints_are_skipped():
    other = [{**_one("skin-gap")[0], "family": "some_other_family"}]
    assert C.check(other, fh, resolve(fh.PARAMS)) == []


def test_an_unknown_name_in_a_limit_fails_with_a_reason():
    bad = [{**_one("skin-gap")[0], "min": "skin_axial + lip_width"}]
    (result,) = C.check(bad, fh, resolve(fh.PARAMS))
    assert not result.ok and "lip_width" in result.message


@pytest.mark.parametrize("expr", ["__import__('os')", "skin_axial ** 2", "max(1, 2)", "skin_axial.real"])
def test_expressions_are_arithmetic_only(expr):
    with pytest.raises((ValueError, KeyError)):
        C.evaluate_expression(expr, {"skin_axial": 2.4})


def test_expressions_read_like_fusion():
    assert C.evaluate_expression("skin_axial + 1.6 mm", {"skin_axial": 2.4}) == pytest.approx(4.0)
    assert C.evaluate_expression("(a + b) * c / 2", {"a": 1, "b": 3, "c": 0.5}) == pytest.approx(1.0)
