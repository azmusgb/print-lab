"""Build v62r from v60b125: retain the current tile/back geometry but replace the
continuous ribs/seams with v40-style breakaway tabs on the solid back rim.

The placement is deliberately layer-aware.  v40 proved the rim-tab topology could
hold a 6-inch pair and still separate; v41 showed that many tabs beginning or ending
on the same Z layer can print a visible line across the face.  v62r therefore keeps
v40's 0.4 mm gap, 0.6 mm tabs, and <=12 mm nominal pitch, while phasing the slanted
sides and staggering the horizontal-side insets so the default 0.2 mm-layer layout
has no more than two tab start/stop events on any one layer.

Usage:
    uv run python projects/hex-tile/sources/scad/make_v62_rim_tabs.py \
      projects/hex-tile/sources/hexagon_v60b125_X2D_0.6nozzle.3mf \
      projects/hex-tile/sources/hexagon_v62r_X2D_0.6nozzle.3mf

The generated file still requires the normal Print Lab geometry checks and an exact
Bambu Studio slice before physical printing.
"""

from __future__ import annotations

import argparse
import math
import re
import zipfile
from collections import Counter
from pathlib import Path

import manifold3d as mf
import numpy as np
import trimesh


R = 76.2
AP = R * math.cos(math.radians(30.0))
OBJECT_IDS = ("3", "7", "9")
RIM_MM = 2.0

# Offsets are in fractions of one nominal tab slot, not absolute side length.
# Opposite slanted sides are intentionally out of phase so their tab starts/ends
# do not occur on the same print layers.
SIDE_SLOT_PHASE = {0: 0.00, 2: 0.18, 3: 0.33, 5: -0.17}


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
    """Regular-hex back-rim path in the Y/Z plane, inset normally by inset_mm."""
    ap = AP - inset_mm
    if ap <= 0:
        raise ValueError("rim inset is larger than the tile")
    radius = ap / math.cos(math.radians(30.0))
    return np.array(
        [
            [radius, 0.0],
            [radius / 2.0, ap],
            [-radius / 2.0, ap],
            [-radius, 0.0],
            [-radius / 2.0, -ap],
            [radius / 2.0, -ap],
        ],
        dtype=float,
    )


def _event_layer(z_mm: float, layer_height_mm: float) -> int:
    return int(math.floor(z_mm / layer_height_mm + 0.5))


def _event_counts(
    centers: list[tuple[float, float, float, int, int]],
    tab_mm: float,
    layer_height_mm: float,
) -> Counter[int]:
    counts: Counter[int] = Counter()
    half = tab_mm / 2.0
    for _y, z, _inset, _side, _slot in centers:
        counts[_event_layer(z - half, layer_height_mm)] += 1
        counts[_event_layer(z + half, layer_height_mm)] += 1
    return counts


def _rim_tab_centers(
    tab_mm: float,
    pitch_mm: float,
    layer_height_mm: float = 0.2,
) -> list[tuple[float, float, float, int, int]]:
    """Return (y, z, inset, side, slot) for the v62r rim tabs.

    There are seven tabs per side at the default 12 mm maximum pitch.  Slanted
    sides use a small along-side phase shift to break the upper/lower mirror
    symmetry.  Horizontal top/bottom sides cannot change Z by moving along the
    side, so their tabs use distinct safe rim insets spread over roughly six
    print layers.  The resulting default layout is rejected if more than two
    tab starts/ends fall on one layer.
    """
    if tab_mm <= 0 or pitch_mm <= 0 or layer_height_mm <= 0:
        raise ValueError("tab, pitch, and layer height must be positive")
    if tab_mm > 1.0:
        raise ValueError("tab > 1.0 mm is intentionally refused; this is a breakaway join")

    n_side = max(2, math.ceil(R / pitch_mm))

    # A square tab on a horizontal rim side extends tab/2 in the normal (Z)
    # direction.  Keep 0.10 mm extra clearance at the outer edge and stay inside
    # the nominal 2.0 mm solid rim at the inner edge.
    safe_lo = tab_mm / 2.0 + 0.10
    safe_hi = RIM_MM - tab_mm / 2.0
    if safe_hi <= safe_lo:
        raise ValueError("tab is too large for the 2 mm rim")

    # Offset the two horizontal sides by 0.10 mm relative to each other.  With
    # seven 0.6 mm tabs this spreads each row across multiple 0.2 mm layers,
    # instead of seven tabs appearing/disappearing together as in v41.
    top_hi = max(safe_lo, safe_hi - 0.10)
    bottom_lo = min(safe_hi, safe_lo + 0.10)
    top_insets = np.linspace(safe_lo, top_hi, n_side)
    bottom_insets = np.linspace(bottom_lo, safe_hi, n_side)

    centers: list[tuple[float, float, float, int, int]] = []
    for side in range(6):
        for slot in range(n_side):
            if side == 1:  # top horizontal rim
                inset = float(top_insets[slot])
                t = (slot + 0.5) / n_side
            elif side == 4:  # bottom horizontal rim
                inset = float(bottom_insets[slot])
                t = (slot + 0.5) / n_side
            else:
                inset = 1.0
                phase = SIDE_SLOT_PHASE[side]
                t = (slot + 0.5 + phase) / n_side
                if not 0.0 < t < 1.0:
                    raise ValueError("slanted-side phase moved a tab outside its rim side")

            verts = _hex_vertices(inset)
            p0 = verts[side]
            p1 = verts[(side + 1) % 6]
            y, z = (1.0 - t) * p0 + t * p1
            centers.append((float(y), float(z), inset, side, slot))

    events = _event_counts(centers, tab_mm, layer_height_mm)
    max_events = max(events.values(), default=0)
    if max_events > 2:
        raise ValueError(
            f"tab layout creates {max_events} start/stop events on one {layer_height_mm:.2f} mm layer; "
            "refusing a v41-like synchronized layer event"
        )

    return centers


def build_v62(
    src: Path,
    out: Path,
    *,
    gap_mm: float = 0.4,
    tab_mm: float = 0.6,
    pitch_mm: float = 12.0,
    overlap_mm: float = 0.3,
    layer_height_mm: float = 0.2,
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

        # This clean slab removes every old v58/v60 rib or seam that crosses the
        # pair mid-plane.  The only geometry added back across that plane is the
        # explicit rim-tab set below.
        bound = 200.0
        gap_cut = mf.Manifold.cube([gap_mm, 2 * bound, 2 * bound]).translate(
            [-gap_mm / 2.0, -bound, -bound]
        )
        pair = pair - gap_cut

        centers = _rim_tab_centers(tab_mm, pitch_mm, layer_height_mm)
        bridge_x = gap_mm + 2.0 * overlap_mm
        tabs: mf.Manifold | None = None
        for y, z, _inset, _side, _slot in centers:
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
            raise RuntimeError("generated v62r mesh is not watertight")

        xml_vertices = "".join(f'<vertex x="{a:.5f}" y="{b:.5f}" z="{c:.5f}"/>' for a, b, c in nv)
        xml_faces = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in nf)
        mesh_body = f"<mesh><vertices>{xml_vertices}</vertices><triangles>{xml_faces}</triangles></mesh>"

        # v61 used the same source object as the canonical pair mesh and replaced
        # these linked mesh objects together.  Preserve that established 3MF
        # structure so the Bambu project metadata/placements remain unchanged.
        for oid in OBJECT_IDS:
            match = _block(model_xml, oid)
            model_xml = (
                model_xml[: match.start()]
                + match.group(1)
                + mesh_body
                + match.group(3)
                + model_xml[match.end() :]
            )

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

    events = _event_counts(centers, tab_mm, layer_height_mm)
    n_side = len(centers) // 6
    z_values = np.array([z for _y, z, _inset, _side, _slot in centers])
    return {
        "tabs": len(centers),
        "tabs_per_side": n_side,
        "gap_mm": gap_mm,
        "tab_mm": tab_mm,
        "pitch_max_mm": R / n_side,
        "contact_per_tile_mm2": len(centers) * tab_mm * tab_mm,
        "tab_z_min_mm": float(z_values.min()),
        "tab_z_max_mm": float(z_values.max()),
        "max_tab_events_per_layer": max(events.values(), default=0),
        "layer_height_mm": layer_height_mm,
        "watertight": True,
        "volume_mm3": float(abs(tri.volume)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build v62r: v60b125 body with layer-staggered v40 rim tabs")
    parser.add_argument("src", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--gap", type=float, default=0.4)
    parser.add_argument("--tab", type=float, default=0.6)
    parser.add_argument("--pitch", type=float, default=12.0)
    parser.add_argument("--overlap", type=float, default=0.3)
    parser.add_argument("--layer-height", type=float, default=0.2)
    args = parser.parse_args()

    stats = build_v62(
        args.src,
        args.out,
        gap_mm=args.gap,
        tab_mm=args.tab,
        pitch_mm=args.pitch,
        overlap_mm=args.overlap,
        layer_height_mm=args.layer_height,
    )
    print(
        "v62r",
        f"tabs={stats['tabs']} ({stats['tabs_per_side']}/side)",
        f"gap={stats['gap_mm']:.2f}mm",
        f"tab={stats['tab_mm']:.2f}mm",
        f"actual_pitch<={stats['pitch_max_mm']:.2f}mm",
        f"contact/tile={stats['contact_per_tile_mm2']:.1f}mm2",
        f"max_events/layer={stats['max_tab_events_per_layer']}",
        f"watertight={stats['watertight']}",
        f"volume={stats['volume_mm3']:.1f}mm3",
    )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
