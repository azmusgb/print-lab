"""Cut a vertical test strip from the matched 10 in RIFT tile (15.24 mm deep, tear roof): the full flat-to-flat height, WIDTH mm wide.

Tile frame: x corner axis, y flat axis (vertical when standing), z depth, open back at z = 0. The strip is the tile cut to
|x - X0| <= WIDTH / 2. The cut would leave the cavity open at both sides, so each side gets a SIDE_T wall (taken from the
cavity-filled body), which keeps the strip a closed channel like the real rim. Usage: make_strip_coupon.py <out.stl> [--width 50.8] [--x0 0]
A STEP is written beside the STL.
"""
import argparse

import trimesh
from build123d import Align, Box, Pos, Vector, export_step, export_stl
from lab.design.families import faceted_hex as fh

KX, KZ = 0.921542459, 0.802104461   # the printed 6 in tile's Bambu scale: in plane, thickness axis
SIDE_T = 2.4 * KX                    # the tile's own perimeter wall

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--width", type=float, default=50.8)
ap.add_argument("--x0", type=float, default=0.0)
args = ap.parse_args()
if args.width <= 2 * SIDE_T + 1:
    raise SystemExit("strip too narrow for its side walls")

p = {"corner_diameter": 254.0, "edge_depth": 9.0 * KZ, "facet_rise": 10.0 * KZ, "skin_axial": 2.4 * KZ, "perimeter_wall": 2.4 * KX,
     "land_width": 17.7 * KX, "land_thickness": 2.4 * KZ, "roof_wall": 2.4 * KZ, "mark": 1.0, "roof_tear": 1.0}
for q in fh.PARAMS:
    assert q.lo <= p[q.name] <= q.hi, (q.name, p[q.name], q.lo, q.hi)
tile = fh.build(p, seed=3)
bb = tile.bounding_box()
depth, half_y = bb.size.Z, bb.size.Y / 2

cap = Box(bb.size.X + 20, bb.size.Y + 20, depth, align=(Align.CENTER, Align.CENTER, Align.MIN))
cavity = next(s for s in (cap - tile).solids() if s.is_inside(Vector(0, 0, 1.0)))
body = tile + cavity                                                  # the tile with its cavity filled

lo, hi = args.x0 - args.width / 2, args.x0 + args.width / 2
walls = [Pos((a + b) / 2, 0, 0) * Box(b - a, bb.size.Y + 20, depth, align=(Align.CENTER, Align.CENTER, Align.MIN))
         for a, b in ((lo, lo + SIDE_T), (hi - SIDE_T, hi))]
strip_box = Pos(args.x0, 0, 0) * Box(args.width, bb.size.Y + 20, depth, align=(Align.CENTER, Align.CENTER, Align.MIN))
out = (tile + (body & walls[0]) + (body & walls[1])) & strip_box

print("valid", out.is_valid, "solids", len(out.solids()), "vol cm3", round(out.volume / 1000, 2),
      "size", [round(v, 2) for v in (out.bounding_box().size.X, out.bounding_box().size.Y, out.bounding_box().size.Z)])
export_stl(out, args.out)
export_step(out, args.out.replace(".stl", ".step"))
m = trimesh.load(args.out)
print("watertight", m.is_watertight, "tris", len(m.faces))
