"""Version-ID tabs: a small raised label joined to a strip's end at bed level, so a photo says which variant it is
(spec: Builders 5). Used only once CAP-TAB-ISOLATION has passed for this Bambu Studio version."""
import tempfile
from pathlib import Path

import numpy as np
import trimesh

SCAD = Path(__file__).resolve().parent.parent / "scad" / "id_tab.scad"
TAB_HEIGHT_MM = 1.6


def id_tab(text: str, jobs_dir: Path) -> trimesh.Trimesh:
    from lab.adapters.openscad import render
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "tab.stl"
        render(SCAD, out, {"label": text}, jobs_dir)
        return trimesh.load(out, force="mesh")


def attach_tab(strip: trimesh.Trimesh, text: str, jobs_dir: Path) -> trimesh.Trimesh:
    """The strip with its tab joined at the -Y end: the bridge reaches 1.5 mm into the strip's first layers."""
    from lab.geometry.coupons import _to_manifold
    import manifold3d as mf
    tab = id_tab(text, jobs_dir)
    lo, hi = strip.bounds
    (tx0, ty0, tz0), (tx1, ty1, _) = tab.bounds
    cx = (lo[0] + hi[0]) / 2
    # the strip's end at bed level, under the tab (a cut from a leaning face is shorter there than at its top)
    sec = strip.section([0, 0, lo[2] + 0.3], [0, 0, 1])
    end = lo[1]
    if sec is not None:
        pts = sec.vertices[np.abs(sec.vertices[:, 0] - cx) <= (tx1 - tx0) / 2]
        end = float(pts[:, 1].min()) if len(pts) else float(sec.vertices[:, 1].min())
    # centre the tab on the strip's end; its bridge tip reaches 1.5 mm past that end into the strip, at bed level
    tab.apply_translation([cx - (tx0 + tx1) / 2, end + 1.5 - ty1, lo[2] - tz0])
    u = (_to_manifold(strip) + _to_manifold(tab)).to_mesh()
    return trimesh.Trimesh(u.vert_properties[:, :3], u.tri_verts, process=True)
