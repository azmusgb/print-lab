"""Full 10 in RIFT tile (tile frame) plus conformal fins for the 60 deg lean. Usage: make_full_fins.py <out.stl> [--ycap 20] [--t 1.6] [--xs -90,-45,0,45,90] [--gap 0.3] [--tine 1.2] [--pitch 12]
Each fin is a YZ-plane wall from the bed plane up into the tile's cavity. It stops --gap short of the skin underside and of the back plane,
and joins them only through small tines every --pitch mm, so it snaps off (--gap 0 fuses it solid)."""
import argparse, math
import trimesh
from build123d import Align, Box, Pos, Vector, Polygon, extrude, Plane, export_step, export_stl
from lab.design.families import faceted_hex as fh

KX, KZ = 0.921542459, 0.802104461
ap = argparse.ArgumentParser(); ap.add_argument("out"); ap.add_argument("--ycap", type=float, default=20.0)
ap.add_argument("--t", type=float, default=1.6); ap.add_argument("--xs", default="-90,-45,0,45,90")
ap.add_argument("--gap", type=float, default=0.3); ap.add_argument("--tine", type=float, default=1.2); ap.add_argument("--pitch", type=float, default=12.0)
a = ap.parse_args()
p = {"corner_diameter": 254.0, "edge_depth": 9.0 * KZ, "facet_rise": 10.0 * KZ, "skin_axial": 2.4 * KZ, "perimeter_wall": 2.4 * KX,
     "land_width": 17.7 * KX, "land_thickness": 2.4 * KZ, "roof_wall": 2.4 * KZ, "mark": 1.0, "roof_tear": 1.0}
tile = fh.build(p, seed=3)
bb = tile.bounding_box(); depth, y0 = bb.size.Z, bb.min.Y
sa, ca = math.sin(math.radians(60)), math.cos(math.radians(60))
zb = lambda y: (sa * y0 - sa * y) / ca          # tile z where the bed plane crosses at this y (z < 0 behind the back)
cap = Box(bb.size.X + 20, bb.size.Y + 20, depth, align=(Align.CENTER, Align.CENTER, Align.MIN))
cavity = next(s for s in (cap - tile).solids() if s.is_inside(Vector(0, 0, 1.0)))
zlow = zb(a.ycap)
pts = [(y0, 0.0), (a.ycap, zlow), (a.ycap, depth), (y0, depth)]   # (y, z) wedge from the bed up to the cavity top
fins = None
for xf in [float(v) for v in a.xs.split(",")]:
    wedge = extrude(Polygon(*[(y, z) for y, z in pts], align=None), amount=a.t)   # in XY, extruded along Z
    # rotate so the sketch plane is YZ: sketch (u,v)=(y,z), extrude along +x
    w = Plane(origin=(xf - a.t / 2, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0)) * wedge
    fins = w if fins is None else fins + w
tall = bb.size.X + 20
behind_box = lambda top: Pos(0, 0, top) * Box(tall, bb.size.Y + 20, 500, align=(Align.CENTER, Align.CENTER, Align.MAX))
if a.gap > 0:
    cavity_lo = cavity - Pos(0, 0, -a.gap) * tile                         # skin underside lowered by the gap
    body = (fins & behind_box(-a.gap)) + (fins & cavity_lo)
    ys = [y0 + a.pitch / 2 + i * a.pitch for i in range(int((bb.size.Y - a.pitch / 2) // a.pitch) + 1)]
    comb = None
    for y in ys:
        c = Pos(0, y, depth / 2 - 250) * Box(tall, a.tine, 500 + depth, align=(Align.CENTER, Align.CENTER, Align.CENTER))
        comb = c if comb is None else comb + c
    zone = ((fins & behind_box(0)) - (fins & behind_box(-a.gap))) + ((fins & cavity) - (fins & cavity_lo))   # the gap, filled
    out = tile + body + (zone & comb)
else:
    out = tile + (fins & behind_box(0)) + (fins & cavity)
print("valid", out.is_valid, "solids", len(out.solids()), "tile cm3", round(tile.volume / 1000, 1), "fins cm3", round((out.volume - tile.volume) / 1000, 1))
export_stl(out, a.out)
export_step(out, a.out.replace(".stl", ".step"))
m = trimesh.load(a.out); print("watertight", m.is_watertight, "tris", len(m.faces), m.bounds.round(1).tolist())
