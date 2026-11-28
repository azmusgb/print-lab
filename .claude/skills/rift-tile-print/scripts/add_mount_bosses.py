"""Matched 10 in RIFT tile (15.24 mm deep, tear roof) plus two keyhole mounting bosses on vertical ribs.

Tile frame: x is the corner-to-corner axis, y the flat-to-flat axis (vertical when printed standing), z the depth with the
open back at z = 0. The bosses and ribs are built only inside the tile's cavity and stay `CLEAR` below the inner skin, so
nothing prints through the face. Each boss is a house shape: flat top, 50 deg gusset underneath down to its rib. Ribs run along y (vertical in the print, so no bridge) and tie the bosses to the top and
bottom walls. Usage: add_mount_bosses.py <out.stl> [--key-y0 Y --key-w W --embed E]   (a STEP is written beside it)

--key-y0 adds a short key at each rib's top end: from y = Y the rib top climbs at 45 deg (self-supporting) until it meets the
underside of the rim roof wall, then follows it, embedding E mm into that wall, which joins the rib to the upper rim. The key
is --key-w mm wide. Without --key-y0 the ribs stop 1.6 mm short of the roof wall.
"""
import argparse
import math

import trimesh
from build123d import Align, Box, Face, Pos, Solid, Vector, Wire, export_step, export_stl
from lab.design.families import faceted_hex as fh

KX, KZ = 0.921542459, 0.802104461   # the printed 6 in tile's Bambu scale: in plane, thickness axis
CLEAR = 1.6                          # mm of cavity kept between rib/boss tops and the inner skin face
BOSS_X, BOSS_W, BOSS_H = 45.0, 28.0, 16.0   # centre x (both sides), width along x, height along y
RIB_T = 1.8
GUSSET_DEG = 50.0                    # underside of each boss slopes down to its rib at this angle from horizontal (flat undersides print as bridges)
LIP, POCKET = 1.8, 5.0               # keyhole: back lip, then screw-head pocket behind it
HEAD_D, SLOT_W, TRAVEL = 8.5, 4.6, 6.0
PEAK_RISE = 4.0                      # tip 4.0 mm above the circle centre over a 3.75 mm radius step: 46.8 deg from horizontal


def hull(points):
    pts = sorted(set(points))
    def half(seq):
        out = []
        for p in seq:
            while len(out) >= 2 and (out[-1][0] - out[-2][0]) * (p[1] - out[-2][1]) - (out[-1][1] - out[-2][1]) * (p[0] - out[-2][0]) <= 0:
                out.pop()
            out.append(p)
        return out[:-1]
    return half(pts) + half(pts[::-1])


def circle(cx, cy, d, n=72):
    return [(cx + d / 2 * math.cos(2 * math.pi * i / n), cy + d / 2 * math.sin(2 * math.pi * i / n)) for i in range(n)]


def prism(points, z0, z1, dx):
    wire = Wire.make_polygon([Vector(x + dx, y, z0) for x, y in points], close=True)
    return Solid.extrude(Face(wire), Vector(0, 0, z1 - z0))


def keyhole(cx):
    lo, hi = -TRAVEL / 2, TRAVEL / 2
    bore = hull(circle(0, lo, HEAD_D) + circle(0, lo + PEAK_RISE, 1.0))                       # entry bore with a 45 deg roof
    slot = hull(circle(0, lo, SLOT_W) + circle(0, hi, SLOT_W))
    pocket = hull(circle(0, lo, HEAD_D) + circle(0, hi, HEAD_D) + circle(0, hi + PEAK_RISE, 1.0))
    total = LIP + POCKET
    return [prism(bore, -0.01, LIP + 0.01, cx), prism(slot, -0.01, LIP + 0.01, cx), prism(pocket, LIP, total, cx)]


ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--key-y0", type=float, default=None)
ap.add_argument("--key-w", type=float, default=RIB_T)
ap.add_argument("--embed", type=float, default=0.3)
args = ap.parse_args()

p = {"corner_diameter": 254.0, "edge_depth": 9.0 * KZ, "facet_rise": 10.0 * KZ, "skin_axial": 2.4 * KZ, "perimeter_wall": 2.4 * KX,
     "land_width": 17.7 * KX, "land_thickness": 2.4 * KZ, "roof_wall": 2.4 * KZ, "mark": 1.0, "roof_tear": 1.0}
for q in fh.PARAMS:
    assert q.lo <= p[q.name] <= q.hi, (q.name, p[q.name], q.lo, q.hi)
tile = fh.build(p, seed=3)
bb = tile.bounding_box()
depth, half_y = bb.size.Z, bb.size.Y / 2

# cavity = the enclosed pocket of (box - tile) that holds a point just inside the back plane at the centre; the other piece is air
cap = Box(bb.size.X + 20, bb.size.Y + 20, depth, align=(Align.CENTER, Align.CENTER, Align.MIN))
cavity = next(s for s in (cap - tile).solids() if s.is_inside(Vector(0, 0, 1.0)))
room = cavity - Pos(0, 0, -CLEAR) * tile          # cavity minus a copy of the tile moved back: leaves CLEAR under the skin

ribs = [Pos(sx * BOSS_X, 0, 0) * Box(RIB_T, 2 * half_y, depth, align=(Align.CENTER, Align.CENTER, Align.MIN)) for sx in (-1, 1)]
drop = (BOSS_W - RIB_T) / 2 * math.tan(math.radians(GUSSET_DEG))
outline = [(-BOSS_W / 2, BOSS_H / 2), (BOSS_W / 2, BOSS_H / 2), (BOSS_W / 2, -BOSS_H / 2), (RIB_T / 2, -BOSS_H / 2 - drop),
           (-RIB_T / 2, -BOSS_H / 2 - drop), (-BOSS_W / 2, -BOSS_H / 2)]
bosses = [prism(outline, 0.0, depth, sx * BOSS_X) for sx in (-1, 1)]
add = room & (ribs[0] + ribs[1] + bosses[0] + bosses[1])
if args.key_y0 is not None:
    body = tile + cavity
    reach = body - Pos(0, 0, args.embed) * tile                      # the cavity plus the lowest `embed` mm of the roof wall
    for sx in (-1, 1):
        probe = room & (Pos(sx * BOSS_X, args.key_y0, 0) * Box(0.2, 0.2, depth, align=(Align.CENTER, Align.CENTER, Align.MIN)))
        z0 = probe.bounding_box().max.Z                              # where the standard rib top is at the key's start
        wedge = Solid.extrude(Face(Wire.make_polygon([Vector(-60, args.key_y0, -1), Vector(-60, args.key_y0 + 15, -1),
                                                      Vector(-60, args.key_y0 + 15, z0 + 15), Vector(-60, args.key_y0, z0)], close=True)),
                              Vector(120, 0, 0))
        strip = Pos(sx * BOSS_X, (args.key_y0 + half_y) / 2, 0) * Box(args.key_w, half_y - args.key_y0 + 1.0, depth, align=(Align.CENTER, Align.CENTER, Align.MIN))
        add = add + (reach & wedge & strip)
out = tile + add

for sx in (-1, 1):
    for cutter in keyhole(sx * BOSS_X):
        out = out - cutter

nsol = len(out.solids())
print("valid", out.is_valid, "solids", nsol, "vol cm3", round(out.volume / 1000, 2), "added cm3", round((out.volume - tile.volume) / 1000, 2),
      "size", [round(v, 2) for v in (out.bounding_box().size.X, out.bounding_box().size.Y, out.bounding_box().size.Z)])
export_stl(out, args.out)
export_step(out, args.out.replace(".stl", ".step"))

# the exported mesh must be watertight
m = trimesh.load(args.out)
print("watertight", m.is_watertight, "tris", len(m.faces))
