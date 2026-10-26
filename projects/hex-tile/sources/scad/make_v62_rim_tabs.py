"""Build v62 from v60b125: keep the 1.25 mm backs, remove the old continuous ribs/seams,
and reconnect the pair only with small breakaway tabs on the solid back rim.

Design intent
-------------
- Return to the only join topology that actually separated successfully (v39/v40): rim tabs.
- Keep the modern v60b125 body/back geometry and current print orientation.
- Use a 0.4 mm pair gap and 0.6 mm breakaway tabs, matching v40's proven values.
- Keep max tab pitch <= 12 mm, matching v40's fix for the 6-inch pair flexing apart.
- Avoid v41's synchronized tab-height lines by varying the inset of successive tabs inside the
  2 mm rim. On horizontal rim segments this moves adjacent tabs onto different Z bands instead
  of putting a whole row on one layer.

This script edits the same 3MF mesh objects as make_v61_tacks.py. It does not alter slicer settings.

Usage:
    python projects/hex-tile/sources/scad/make_v62_rim_tabs.py \
        projects/hex-tile/sources/hexagon_v60b125_X2D_0.6nozzle.3mf \
        projects/hex-tile/sources/hexagon_v62r_X2D_0.6nozzle.3mf

Optional arguments:
    --gap 0.4       physical gap between the two backs, mm
    --tab 0.6       tab width/height in the Y/Z plane, mm
    --pitch 12      maximum distance between tabs along each rim side, mm
    --overlap 0.3   tab overlap into each back, mm

The generated file still needs the normal Print Lab checks and a real Bambu slice before printing.
"""

from __future__ import annotations

import argparse
import math
import re
import zipfile
from pathlib import Path

import manifold3d as mf
import numpy as np
import trimesh


# 6-inch tile geometry used by v58-v61. In the object mesh, X is across the pair gap and
# Y/Z are the regular-hex plane. These are the same dimensions used by make_v61_tacks.py.
R = 76.2
AP = R * math.cos(math.radians(30.0))
PHI = (5**0.5 - 1.0) / 2.0
OBJECT_IDS = ("3", "7", "9")


def _block(xml: str, oid: str) -> re.Match[str]:
    match = re.search(rf'(<object id="{oid}"[^>]*>)(.*?)(</object>)', xml, re.S)
    if not match:
        raise ValueError(f"3MF is missing expected mesh object {oid}")
    return match


def _mesh(xml: str, oid: str) -> tuple[np.ndarray, np.ndarray]:
    body = _block(xml, oid).group(2)
    vertices = np.array(
        [[float(a) for a in m] for m in re.findall(r'<vertex x="([^"]+)" y="([^"]+)" z="([^"]+)"', body)],
        dtype=np.float32,
    )
    faces = np.array(
        [[int(a) for a in m] for m in re.findall(r'<triangle v1="(\d+)" v2="(\d+)" v3="(\d+)"', body)],
        dtype=np.uint32,
    )
    if not len(vertices) or not len(faces):
        raise ValueError(f"3MF object {oid} has no readable mesh")
    return vertices, faces


def _hex_vertices(inset_mm: float) -> np.ndarray:
    """Regular hex in the Y/Z plane, inset normally from the outer rim by inset_mm."""
    ap = AP - inset_mm
    if ap <= 0:
        raise ValueError("rim inset is larger than the tile")
    r = ap / math.cos(math.radians(30.0))
    return np.array(
        [
            [r, 0.0],
            [r / 2.0, ap],
            [-r / 2.0, ap],
            [-r, 0.0],
            [-r / 2.0, -ap],
            [r / 2.0, -ap],
        ],
        dtype=float,
    )


def _rim_tab_centers(tab_mm: float, pitch_mm: float) -> list[tuple[float, float, float]]:
    """Return (y, z, inset) centers, max pitch <= pitch_mm, staggered within the rim.

    v40 put the tabs on the back rim and proved that the 6-inch pair could separate. v41's
    problem was many tabs sharing the same Z. We retain the rim topology but vary the normal
    inset from ~0.65 to ~1.65 mm. On horizontal rim segments that moves adjacent tab centers
    onto different Z layers while keeping the whole 0.6 mm tab inside the nominal 2 mm rim.
    """
    if tab_mm <= 0 or pitch_mm <= 0:
        raise ValueError("tab and pitch must be positive")
    if tab_mm > 1.0:
        raise ValueError("tab > 1.0 mm is intentionally refused; this is a breakaway join")

    # Keep the entire tab inside the ~2 mm rim: inset + half tab <= 1.95 mm.
    inset_lo = max(0.65, tab_mm / 2.0 + 0.30)
    inset_hi = 1.95 - tab_mm / 2.0
    if inset_hi <= inset_lo:
        raise ValueError("tab is too large to stagger safely inside the rim")

    centers: list[tuple[float, float, float]] = []
    global_index = 0

    # Side length of a regular hex is R. Use ceil so actual spacing never exceeds pitch.
    n_side = max(2, math.ceil(R / pitch_mm))
    for side in range(6):
        for i in range(n_side):
            # Irrational phase + side offset avoids repeating the same few inset/Z values.
            phase = (global_index * PHI + side * 0.17320508075688773) % 1.0
            inset = inset_lo + (inset_hi - inset_lo) * phase
            verts = _hex_vertices(inset)
            p0 = verts[side]
            p1 = verts[(side + 1) % 6]
            t = (i + 0.5) / n_side
            y, z = (1.0 - t) * p0 + t * p1
            centers.append((float(y), float(z), float(inset)))
            global_index += 1

    return centers


def build_v62(
    src: Path,
    out: Path,
    *,
    gap_mm: float = 0.4,
    tab_mm: float = 0.6,
    pitch_mm: float = 12.0,
    overlap_mm: float = 0.3,
) -> dict:
    if gap_mm <= 0 or overlap_mm <= 0:
        raise ValueError("gap and overlap must be positive")
    if gap_mm > 1.0:
        raise ValueError("gap > 1.0 mm is outside this v40-derived design")

    with zipfile.ZipFile(src) as zin:
        names = zin.namelist()
        if "3D/3dmodel.model" not in names:
            raise ValueError("not a supported Bambu 3MF: 3D/3dmodel.model is missing")
        model_xml = zin.read("3D/3dmodel.model").decode()
        vertices, faces = _mesh(model_xml, "3")

        pair = mf.Manifold(mf.Mesh(vert_properties=vertices, tri_verts=faces))

        # Sever all old v58/v60 ribs and seams with a clean center slab. Unlike v61, which
        # used a 1.0 mm gap for interior tack posts, v62 restores v40's proven 0.4 mm gap.
        B = 200.0
        gap_cut = mf.Manifold.cube([gap_mm, 2 * B, 2 * B]).translate([-gap_mm / 2.0, -B, -B])
        pair = pair - gap_cut

        centers = _rim_tab_centers(tab_mm, pitch_mm)
        bridge_x = gap_mm + 2.0 * overlap_mm
        tabs: mf.Manifold | None = None
        for y, z, _inset in centers:
            tab = mf.Manifold.cube([bridge_x, tab_mm, tab_mm]).translate(
                [-bridge_x / 2.0, y - tab_mm / 2.0, z - tab_mm / 2.0]
            )
            tabs = tab if tabs is None else tabs + tab
        if tabs is None:
            raise RuntimeError("no rim tabs were generated")

        pair = pair + tabs
        mesh_out = pair.to_mesh()
        nv = np.asarray(mesh_out.vert_properties)[:, :3]
        nf = np.asarray(mesh_out.tri_verts)
        tri = trimesh.Trimesh(nv, nf, process=False)
        if not tri.is_watertight:
            raise RuntimeError("generated v62 mesh is not watertight")

        xml_vertices = "".join(f'<vertex x="{a:.5f}" y="{b:.5f}" z="{c:.5f}"/>' for a, b, c in nv)
        xml_faces = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in nf)
        mesh_body = f"<mesh><vertices>{xml_vertices}</vertices><triangles>{xml_faces}</triangles></mesh>"

        for oid in OBJECT_IDS:
            match = _block(model_xml, oid)
            model_xml = model_xml[: match.start()] + match.group(1) + mesh_body + match.group(3) + model_xml[match.end() :]

        settings = None
        if "Metadata/model_settings.config" in names:
            settings = zin.read("Metadata/model_settings.config").decode()
            settings = settings.replace("v60b125", "v62r").replace("v61s", "v62r")

        out.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for name in names:
                if name == "3D/3dmodel.model":
                    payload = model_xml
                elif name == "Metadata/model_settings.config" and settings is not None:
                    payload = settings
                else:
                    payload = zin.read(name)
                zout.writestr(name, payload)

    z_values = np.array([z for _y, z, _inset in centers])
    return {
        "tabs": len(centers),
        "tabs_per_side": len(centers) // 6,
        "gap_mm": gap_mm,
        "tab_mm": tab_mm,
        "pitch_max_mm": R / (len(centers) // 6),
        "contact_per_tile_mm2": len(centers) * tab_mm * tab_mm,
        "tab_z_min_mm": float(z_values.min()),
        "tab_z_max_mm": float(z_values.max()),
        "watertight": True,
        "volume_mm3": float(tri.volume),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build v62: v60b125 body with staggered v40-style rim tabs")
    parser.add_argument("src", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--gap", type=float, default=0.4)
    parser.add_argument("--tab", type=float, default=0.6)
    parser.add_argument("--pitch", type=float, default=12.0)
    parser.add_argument("--overlap", type=float, default=0.3)
    args = parser.parse_args()

    stats = build_v62(args.src, args.out, gap_mm=args.gap, tab_mm=args.tab, pitch_mm=args.pitch, overlap_mm=args.overlap)
    print(
        "v62r",
        f"tabs={stats['tabs']} ({stats['tabs_per_side']}/side)",
        f"gap={stats['gap_mm']:.2f}mm",
        f"tab={stats['tab_mm']:.2f}mm",
        f"actual_pitch<={stats['pitch_max_mm']:.2f}mm",
        f"contact/tile={stats['contact_per_tile_mm2']:.1f}mm2",
        f"watertight={stats['watertight']}",
        f"volume={stats['volume_mm3']:.1f}mm3",
    )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
