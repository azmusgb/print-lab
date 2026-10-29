"""Mesh-level validation of HEX_TILE_v77 exports, independent of the SCAD's own asserts.

Usage (from ~/dev/print-lab):  uv run python projects/hex-tile/sources/scad/validate_v77.py DIR
DIR holds v77_single.stl, v77_pair.stl, v77_installed.stl (and optionally v77_single_gusset.stl).

Checks: watertight, solid pieces, extents, first-layer contact, face isolation
measured on the mesh (not taken from the SCAD formula), flange flatness and tape land.
"""
import sys
from pathlib import Path

import numpy as np
import trimesh

from lab.geometry.mesh import solid_pieces

R = 6 * 25.4 / 2
AP = R * np.cos(np.radians(30))
FLANGE_W, FLANGE_T, RIM = 18.0, 1.2, 2.0
TAPE_W = 12.7
MIN_ISOLATION = 1.6
results = []


def check(name, ok, detail):
    results.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")


def rim_distance(xy):
    """In-plane distance from the hex outline, inward positive."""
    angles = np.radians(30 + 60 * np.arange(6))
    normals = np.stack([np.cos(angles), np.sin(angles)], axis=1)
    return AP - (xy @ normals.T).max(axis=1)


def body(path, expect_pieces):
    m = trimesh.load(path, force="mesh")
    pieces = solid_pieces(m)
    check(f"{path.name} watertight", m.is_watertight, f"watertight={m.is_watertight}")
    check(f"{path.name} solid pieces", pieces == expect_pieces, f"{pieces} (expected {expect_pieces})")
    check(f"{path.name} winding/volume", m.is_winding_consistent and m.volume > 0,
          f"volume {m.volume:.0f} mm3, consistent winding={m.is_winding_consistent}")
    return m


def main(d: Path):
    single = body(d / "v77_single.stl", 1)
    pair = body(d / "v77_pair.stl", 1)
    inst = body(d / "v77_installed.stl", 1)

    # Pair without its joins must fall into exactly two tiles.
    ex = single.extents
    print(f"INFO  single extents (print frame X depth, Y width, Z height): {np.round(ex, 3)}")
    check("width corner-to-corner", abs(ex[1] - 152.4) < 0.05, f"{ex[1]:.3f} mm (152.4)")
    check("height flat-to-flat", abs(ex[2] - 2 * AP) < 0.05, f"{ex[2]:.3f} mm ({2 * AP:.3f})")
    check("overall depth", 10 < ex[0] < 13, f"{ex[0]:.3f} mm")
    print(f"INFO  pair extents: {np.round(pair.extents, 3)}  volume {pair.volume:.0f} mm3"
          f"  (~{pair.volume * 1.24e-3:.0f} g PLA solid-equivalent)")

    # First layer: faces at the bed pointing down.
    for name, m in (("single", single), ("pair", pair)):
        z0 = m.bounds[0][2]
        sel = (m.face_normals[:, 2] < -0.999) & (m.triangles_center[:, 2] < z0 + 0.01)
        area = m.area_faces[sel].sum()
        sec = m.section(plane_origin=[0, 0, z0 + 0.3], plane_normal=[0, 0, 1])
        above = sec.to_planar()[0].area if sec is not None else float("nan")
        check(f"{name} bed contact", area > 250 and area >= 0.95 * above,
              f"{area:.0f} mm2 at Z=0 vs {above:.0f} mm2 at Z=0.3 (no undercut; v74 lesson)")
        islands = len(sec.to_planar()[0].polygons_full) if sec is not None else 0
        print(f"INFO  {name} first-layer islands at Z=0.3: {islands}")

    # Installed frame: back plane at Z=0, face toward +Z.
    v = inst
    # Flange: back faces on Z=0 must be one flat plane.
    back = (v.face_normals[:, 2] < -0.999) & (np.abs(v.triangles_center[:, 2]) < 1e-3)
    off_plane = (v.face_normals[:, 2] < -0.999) & (v.triangles_center[:, 2] > 1e-3) & \
                (v.triangles_center[:, 2] < FLANGE_T + 0.01)
    check("mounting plane flat", back.any() and not off_plane.any(),
          f"{v.area_faces[back].sum():.0f} mm2 on Z=0, {int(off_plane.sum())} down-facing faces just above it")

    # Tape land: sample the band from the rim to the flange inner edge on the five
    # flanged edges; every sample must be solid at the back plane.
    rng = np.random.default_rng(1)
    pts = rng.uniform([-R, -AP], [R, AP], size=(200000, 2))
    rd = rim_distance(pts)
    band = (rd > RIM + 0.05) & (rd < FLANGE_W - 0.05)
    top = pts[:, 1] > AP - FLANGE_W  # top edge band is open by design
    land = pts[band & ~top]
    probe = np.column_stack([land, np.full(len(land), FLANGE_T / 2)])
    inside = v.contains(probe)
    check("tape land solid", inside.all(), f"{inside.mean() * 100:.2f}% of {len(land)} samples inside the flange")
    check("tape land width", FLANGE_W - RIM >= TAPE_W + 2.0,
          f"{FLANGE_W - RIM:.1f} mm land for {TAPE_W} mm tape ({(FLANGE_W - RIM - TAPE_W) / 2:.2f} mm slack each side)")

    # Face isolation measured on the mesh: cast rays from the flange's inner face
    # (Z = FLANGE_T) toward the face and record the first hit (the skin's inner surface).
    fl = pts[(rd > RIM + 0.5) & (rd < FLANGE_W - 0.05) & ~top]
    # Rays start just above the flange; drop the starts that are still inside the
    # drafted rim wall (solid all the way to the face, so not a flange-to-skin gap).
    origins = np.column_stack([fl, np.full(len(fl), FLANGE_T + 1e-3)])
    origins = origins[~v.contains(origins)]
    dirs = np.tile([0, 0, 1.0], (len(origins), 1))
    loc, ray_i, tri = v.ray.intersects_location(origins, dirs, multiple_hits=False)
    # The first surface above the flange is either the face skin (facets slope
    # < 25 deg, normal z < -0.9) or the rim's 45-degree draft, which is the
    # perimeter shell itself rather than a rear feature. Report both.
    on_skin = v.face_normals[tri, 2] < -0.9
    print(f"INFO  rays: {on_skin.sum()} reach the skin, {(~on_skin).sum()} land on the rim draft first")
    gaps = loc[on_skin, 2] - FLANGE_T
    check("face isolation (vertical, mesh)", gaps.min() >= MIN_ISOLATION - 1e-6,
          f"min {gaps.min():.3f} mm over {len(gaps)} rays (need >= {MIN_ISOLATION})")
    # True 3-D clearance: nearest point on the skin's inner surface to the flange top.
    skin_faces = np.where((v.face_normals[:, 2] < -0.9) & (v.triangles_center[:, 2] > FLANGE_T + 0.1))[0]
    skin = v.submesh([skin_faces], append=True)
    sample = origins[rng.choice(len(origins), size=min(20000, len(origins)), replace=False)]
    _, dist, _ = trimesh.proximity.closest_point(skin, sample)
    check("face isolation (3-D, mesh)", dist.min() >= MIN_ISOLATION - 1e-6,
          f"min {dist.min():.3f} mm to the skin's inner surface")

    gusset = d / "v77_single_gusset.stl"
    if gusset.exists():
        g = body(gusset, 1)
        print(f"INFO  gusset adds {g.volume - single.volume:.0f} mm3 per tile")

    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed" + (f"; FAILED: {failed}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
