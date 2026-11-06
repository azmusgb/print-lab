import numpy as np
import pytest
import trimesh

from lab.geometry.coupons import height_strip, plate_layout
from lab.geometry.facets import front_facets
from lab.geometry.mesh import load_mesh
from lab.geometry.orientation import lean, score_orientations


@pytest.fixture
def v53(hex_dir):
    return load_mesh(hex_dir / "hex_pair_v53_6in.stl")


def test_strip_closed_and_height(v53):
    s = height_strip(v53, 60, 100)
    assert s.is_watertight and abs(s.extents[2] - 40) < 0.05 and abs(s.bounds[0][2]) < 1e-6


def test_strip_refuses_open_mesh():
    b = trimesh.creation.box((20, 4, 30))
    b.update_faces(np.arange(len(b.faces)) != 0)
    with pytest.raises(ValueError, match="isn't closed"):
        height_strip(b, 0, 10)


def test_lean_15_all_facets_up(v53):
    leaned = lean(v53, 15, "y")
    up = [f for f in front_facets(leaned) if f.side == "-x" and f.area_mm2 > 1]
    assert up and min(f.elevation_deg for f in up) >= 5
    assert abs(leaned.bounds[0][2]) < 1e-6


def test_scores_prefer_lean(v53):
    scores = score_orientations(v53, [0, 10, 15, 20])
    assert [s.angle for s in scores] == [0, 10, 15, 20]
    assert min(scores, key=lambda s: s.a_surface).angle == 0
    assert scores[2].a_surface == 1.0


def test_plate_layout_two_strips_fit(v53):
    s = height_strip(v53, 60, 100)
    placed = plate_layout([("v56", s), ("v58", s.copy())])
    ys = [p[2][0] for p in placed]
    assert len(placed) == 2 and all(0 < y < 256 for y in ys) and ys[0] != ys[1]


def test_plate_layout_stacks_strips_too_wide_for_a_row():
    wide = trimesh.creation.box((165.4, 19, 30))  # full-width strips of the 6" faceted_hex
    placed = plate_layout([("a", wide), ("b", wide.copy())])
    (xa, ya), (xb, yb) = placed[0][2], placed[1][2]
    assert xa == xb == 128 and ya - yb == pytest.approx(19 + 15) and ya > yb
    assert all(10 <= y - 9.5 and y + 9.5 <= 246 for y in (ya, yb))


def test_plate_layout_overflow_message():
    big = trimesh.creation.box((150, 120, 20))
    with pytest.raises(ValueError, match="don't fit"):
        plate_layout([("a", big), ("b", big.copy())])
