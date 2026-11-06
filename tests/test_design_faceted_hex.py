"""faceted_hex rebuilds Fusion's "Rift simplified v6": the same solid at its parameters, and the same response to each
parameter that Fusion showed when they were changed one at a time (5 Nov 2026)."""
from pathlib import Path

import numpy as np
import pytest
import trimesh
from build123d import export_stl

from lab.adapters.threemf import load_object
from lab.design.families import FAMILIES, faceted_hex as fh
from lab.design.family import design_id, read_params, resolve

ROOT = Path(__file__).resolve().parent.parent
V6 = ROOT / "projects/hex-tile/sources/Rift_simplified_v5_save5.3mf"
V6_PARAMS = ROOT / "projects/hex-tile/sources/Rift_simplified_v5_save5.params.json"

# Fusion's body volume (mm³) with one parameter changed from v6's values, measured in Fusion on 5 Nov 2026.
FUSION_FLEX = {("roof_wall", 1.6): 63930.3, ("roof_wall", 3.2): 64652.0, ("corner_diameter", 180): 74309.6,
               ("corner_diameter", 152.4): 55991.6, ("edge_depth", 8): 62908.7, ("facet_rise", 12): 64442.7,
               ("skin_axial", 2): 57782.5, ("perimeter_wall", 2): 63326.0, ("land_width", 15): 62464.4}


@pytest.fixture(scope="module")
def v6_part():
    return fh.build(resolve(fh.PARAMS, read_params(V6_PARAMS, only=fh.PARAMS)))


def test_registered_by_name():
    assert FAMILIES["faceted_hex"] is fh


def test_v6_is_one_valid_solid_with_the_sealed_roof(v6_part):
    assert v6_part.is_valid
    assert len(v6_part.solids()) == 1
    assert len(v6_part.shells()) == 2  # the tile, and the sealed hollow above the roof plate


def test_v6_matches_the_registered_source(v6_part, tmp_path):
    source = load_object(V6, "Rift_simplified_v5_save5")
    assert abs(v6_part.volume - source.volume) / source.volume < 0.001
    stl = tmp_path / "v6.stl"
    export_stl(v6_part, str(stl), tolerance=0.005, angular_tolerance=0.1)
    built = trimesh.load(stl)
    # The source stands upright and ours lies in the tile's frame; the sizes must agree whichever axis carries them.
    assert np.allclose(sorted(built.extents), sorted(source.extents), atol=0.05)


@pytest.mark.parametrize("change,fusion_mm3", FUSION_FLEX.items(), ids=lambda c: f"{c[0]}={c[1]}" if isinstance(c, tuple) else "")
def test_each_parameter_moves_the_part_as_fusion_does(change, fusion_mm3):
    name, value = change
    part = fh.build(resolve(fh.PARAMS, {name: value}))
    assert part.is_valid and len(part.shells()) == 2
    assert abs(part.volume - fusion_mm3) / fusion_mm3 < 0.001


def test_the_mark_is_cut_into_the_land(v6_part):
    plain = fh.build(resolve(fh.PARAMS, {"mark": 0}))
    assert 50 < plain.volume - v6_part.volume < 70  # about 100 mm² of letters, 0.6 mm deep


def test_build_is_deterministic(v6_part):
    again = fh.build(resolve(fh.PARAMS, read_params(V6_PARAMS, only=fh.PARAMS)))
    assert abs(again.volume - v6_part.volume) < 0.001


def test_only_seed_zero_until_make():
    with pytest.raises(NotImplementedError):
        fh.build(resolve(fh.PARAMS), seed=1)


def test_resolve_refuses_unknown_names_and_out_of_range_values():
    with pytest.raises(ValueError, match="unknown"):
        resolve(fh.PARAMS, {"edge_dpeth": 9})
    with pytest.raises(ValueError, match="outside"):
        resolve(fh.PARAMS, {"skin_axial": 0.4})


def test_read_params_takes_fusions_shape_and_drops_what_the_family_lacks(tmp_path):
    values = read_params(V6_PARAMS, only=fh.PARAMS)
    assert values["roof_wall"] == 2.4 and values["corner_diameter"] == 165.4
    plain = tmp_path / "p.json"
    plain.write_text('{"edge_depth": 8, "colour": 3}')
    assert read_params(plain, only=fh.PARAMS) == {"edge_depth": 8.0}


def test_design_id_is_stable_and_tells_designs_apart():
    p = resolve(fh.PARAMS)
    assert design_id(fh.NAME, fh.VERSION, p, 0) == design_id(fh.NAME, fh.VERSION, dict(reversed(list(p.items()))), 0)
    assert design_id(fh.NAME, fh.VERSION, p, 0) != design_id(fh.NAME, fh.VERSION, {**p, "edge_depth": 8.0}, 0)
    assert design_id(fh.NAME, fh.VERSION, p, 0) != design_id(fh.NAME, fh.VERSION + 1, p, 0)
