"""Coupons cut from a model, and laying parts out on the X2D plate."""
import manifold3d as mf
import numpy as np
import trimesh

PLATE, BRIM = 256.0, 10.0


def _to_manifold(m: trimesh.Trimesh) -> mf.Manifold:
    return mf.Manifold(mf.Mesh(vert_properties=np.asarray(m.vertices, dtype=np.float32),
                               tri_verts=np.asarray(m.faces, dtype=np.uint32)))


def height_strip(m: trimesh.Trimesh, z0: float, z1: float) -> trimesh.Trimesh:
    """The model between heights z0 and z1, full width, set down on the bed."""
    if not m.is_watertight:
        raise ValueError("The mesh isn't closed, so a coupon can't be cut from it. Fix the model first (mesh-validity).")
    from lab.geometry.mesh import solid_pieces
    if (n := solid_pieces(m)) > 2:
        raise ValueError(f"The model is {n} separate pieces, so a coupon cut from it can't be trusted. Fix the model "
                         "first (mesh-validity).")
    lo, hi = m.bounds
    pad = 1.0
    box = mf.Manifold.cube([hi[0] - lo[0] + 2 * pad, hi[1] - lo[1] + 2 * pad, z1 - z0]).translate(
        [lo[0] - pad, lo[1] - pad, z0])
    cut = (_to_manifold(m) ^ box).to_mesh()
    out = trimesh.Trimesh(np.asarray(cut.vert_properties)[:, :3], np.asarray(cut.tri_verts), process=True)
    out.apply_translation([0, 0, -out.bounds[0][2]])
    return out


def plate_layout(parts: list[tuple[str, trimesh.Trimesh]], gap: float = 15.0) -> list[tuple[str, trimesh.Trimesh, tuple[float, float]]]:
    """Parts in a row along X, centred on the plate; when the row is wider than the plate (full-width strips of a
    big tile), a column along Y instead, front to back in the same order. Each (name, mesh, (x, y)) is the part's
    centre."""
    widths = [float(p.extents[0]) for _, p in parts]
    depths = [float(p.extents[1]) for _, p in parts]
    total = sum(widths) + gap * (len(parts) - 1) + 2 * BRIM
    depth = max(depths) + 2 * BRIM
    if total <= PLATE and depth <= PLATE:
        x = (PLATE - total) / 2 + BRIM
        out = []
        for (name, p), w in zip(parts, widths):
            out.append((name, p, (round(x + w / 2, 3), PLATE / 2)))
            x += w + gap
        return out
    col_w, col_d = max(widths) + 2 * BRIM, sum(depths) + gap * (len(parts) - 1) + 2 * BRIM
    if col_w <= PLATE and col_d <= PLATE:
        y = (PLATE + col_d) / 2 - BRIM  # the first part at the back, like the first of a row on the left
        out = []
        for (name, p), d in zip(parts, depths):
            out.append((name, p, (PLATE / 2, round(y - d / 2, 3))))
            y -= d + gap
        return out
    raise ValueError(f"The parts don't fit: a row needs {total:.0f} × {depth:.0f} mm with brims and a column "
                     f"{col_w:.0f} × {col_d:.0f} mm; the plate is {PLATE:g} × {PLATE:g} mm. Print fewer parts per "
                     "plate.")
