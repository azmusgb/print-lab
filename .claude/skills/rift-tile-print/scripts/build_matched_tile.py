import sys, numpy as np, trimesh
from build123d import export_stl
from lab.design.families import faceted_hex as fh
kx, kz = 0.921542459, 0.802104461   # the printed 6 in tile's Bambu scale
p = {"corner_diameter": 254.0, "edge_depth": 9.0 * kz, "facet_rise": 10.0 * kz, "skin_axial": 2.4 * kz, "perimeter_wall": 2.4 * kx,
     "land_width": 17.7 * kx, "land_thickness": 2.4 * kz, "roof_wall": 2.4 * kz, "mark": 1.0, "roof_tear": 1.0}
for q in fh.PARAMS:
    assert q.lo <= p[q.name] <= q.hi, (q.name, p[q.name], q.lo, q.hi)
part = fh.build(p, seed=3)
bb = part.bounding_box()
print("valid", part.is_valid, "solids", len(part.solids()), "size", [round(v, 2) for v in (bb.size.X, bb.size.Y, bb.size.Z)], "min", [round(v, 2) for v in (bb.min.X, bb.min.Y, bb.min.Z)], "vol cm3", round(part.volume / 1000, 2))
export_stl(part, sys.argv[1])
from build123d import export_step
export_step(part, sys.argv[1].replace(".stl", ".step"))
print("brep faces", len(part.faces()), "types", sorted({f.geom_type.name for f in part.faces()}))
m = trimesh.load(sys.argv[1]); n, a = m.face_normals, m.area_faces
print("watertight", m.is_watertight, "tris", len(m.faces))
f = n[:, 2] > 0.02
lean = np.degrees(np.arcsin(np.clip(np.abs(n[f, 1]), 0, 1))); aa = a[f]; o = np.argsort(lean); c = np.cumsum(aa[o]) / aa.sum()
print("lean med", round(float(lean[o][np.searchsorted(c, .5)]), 2), "p90", round(float(lean[o][np.searchsorted(c, .9)]), 2), "max", round(float(lean.max()), 1), "step mm", round(float((0.16 * np.tan(np.radians(lean)) * aa).sum() / aa.sum()), 4))
dn = n[:, 1] < -0.02
print("down area past 45deg mm2", round(float(a[dn & (np.abs(n[:, 1]) > 0.7072)].sum()), 1))
