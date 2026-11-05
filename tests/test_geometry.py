import numpy as np
import trimesh
from shapely.geometry import Polygon

from lab.adapters.threemf import load_object
from lab.geometry.facets import facet_switches, front_facets
from lab.geometry.mesh import load_mesh, mesh_facts
from lab.geometry.sections import layer_outlines, outline_jumps, thin_regions


def bent_wall() -> trimesh.Trimesh:
    """A 20 mm wall whose front leans out 5° for the lower 10 mm (facing down) and back 5° above (facing up)."""
    d = 10 * np.tan(np.radians(5))
    prof = Polygon([(0, 0), (-d, 10), (0, 20), (3, 20), (3, 0)])  # (x, z)
    m = trimesh.creation.extrude_polygon(prof, 20)  # extruded along local z
    m.apply_transform(trimesh.transformations.rotation_matrix(np.radians(90), [1, 0, 0]))
    m.apply_translation([0, 0, -m.bounds[0][2]])
    return m


def test_mesh_facts_v53(hex_dir):
    f = mesh_facts(load_mesh(hex_dir / "hex_pair_v53_6in.stl"))
    assert f.watertight and f.bodies == 1
    assert abs(f.extents[2] - 132.0) < 0.5


def test_front_facets_both_sides_v53(hex_dir):
    facets = front_facets(load_mesh(hex_dir / "hex_pair_v53_6in.stl"))
    sides = {f.side for f in facets}
    assert len(sides) == 2 and sides in ({"+x", "-x"}, {"+y", "-y"})
    for s in sides:
        assert sum(f.side == s for f in facets) >= 10


def test_facet_switch_on_both_faces_v53(hex_dir):
    """Measured: both faces of the 132 mm pair switch from facing down to facing up at 89.75 mm (68 % up)."""
    sw = facet_switches(front_facets(load_mesh(hex_dir / "hex_pair_v53_6in.stl")))
    assert len({s.side for s in sw}) == 2
    assert all(0.3 * 132 <= s.z_mm <= 0.8 * 132 for s in sw)


def test_synthetic_switch():
    sw = facet_switches(front_facets(bent_wall()))
    assert len(sw) == 1 and abs(sw[0].z_mm - 10) <= 0.5


def test_outline_jump_v53_mid(hex_dir):
    jumps = outline_jumps(layer_outlines(load_mesh(hex_dir / "hex_pair_v53_6in.stl")))
    assert any(60 <= z <= 72 for z, _ in jumps)


def test_no_outline_jumps_v57_between_ends(hex_dir):
    """v57 keeps every layer the same shape; only the first and last few mm (seam ends, pry slot) change."""
    m = load_object(hex_dir / "hexagon_v57_X2D_0.4nozzle.3mf", "6in")
    top = m.bounds[1][2]
    assert [z for z, _ in outline_jumps(layer_outlines(m)) if 5 < z < top - 5] == []


def test_thin_regions_v57(hex_dir):
    m = load_object(hex_dir / "hexagon_v57_X2D_0.4nozzle.3mf", "6in")
    thin = thin_regions(m, 0.42)
    layers = [l for l in layer_outlines(m) if l.z > 1]
    assert len([z for z, _ in thin if z > 1]) >= 0.5 * len(layers)


def test_thin_regions_v57_not_below_one_line(hex_dir):
    """v57's ribs and back are 0.45 mm: under two 0.42 lines, but not under one."""
    m = load_object(hex_dir / "hexagon_v57_X2D_0.4nozzle.3mf", "6in")
    assert [z for z, _ in thin_regions(m, 0.42, max_lines=1.0) if 1 < z < m.bounds[1][2] - 1] == []


def test_thin_regions_clean_box():
    assert thin_regions(trimesh.creation.box((10, 10, 10)).apply_translation([0, 0, 5]), 0.42) == []


def test_zero_area_faces_dont_open_an_stl(tmp_path):
    """RIFT's STLs carry back-to-back zero-area triangles on the back plane, sharing edges with real faces: the solid
    read as open and in pieces until load_mesh dropped them (as Bambu Studio does)."""
    from lab.geometry.mesh import load_mesh, solid_pieces
    box = trimesh.creation.box((10, 10, 10))
    a, b, c = box.vertices[box.faces[0]]
    v = np.vstack([box.vertices, [a, b, (a + b) / 2]])
    n = len(box.vertices)
    sliver = [[n, n + 1, n + 2], [n, n + 2, n + 1]]  # zero area, both windings, on one of the box's edges
    f = tmp_path / "littered.stl"
    trimesh.Trimesh(v, np.vstack([box.faces, sliver]), process=False).export(f)
    assert not trimesh.load(f, force="mesh").is_watertight
    m = load_mesh(f)
    assert m.is_watertight and solid_pieces(m) == 1 and abs(m.volume - 1000) < 1e-6
