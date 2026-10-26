"""v62: v61s's staggered tacks made kiss tacks. Each tack is fused into one back and stops KISS mm short of the other.

E-020 (v61s): tacks fused into both backs bonded harder than the 1.25 mm back holds together, so on one tile the
break ran through the back. A kiss tack is joined to the far back only by the squash of its end lines, a weaker
bond than being fused into it, so the pair should break at that face and leave the stubs on the near back.
Tacks alternate sides, so each tile keeps half the stubs.

Args: src out pitch(unused) width height kiss"""
import re, sys, zipfile, numpy as np, trimesh, manifold3d as mf

SRC, OUT, TACK_Z_PITCH, TACK_W, TACK_H = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5])
KISS = float(sys.argv[6])
z = zipfile.ZipFile(SRC); s = z.read('3D/3dmodel.model').decode()

def block(oid): return re.search(rf'(<object id="{oid}"[^>]*>)(.*?)(</object>)', s, re.S)
def mesh(oid):
    blk = block(oid).group(2)
    v = np.array([[float(a) for a in m] for m in re.findall(r'<vertex x="([^"]+)" y="([^"]+)" z="([^"]+)"', blk)])
    f = np.array([[int(a) for a in m] for m in re.findall(r'<triangle v1="(\d+)" v2="(\d+)" v3="(\d+)"', blk)])
    return v, f

v, f = mesh('3')
A = mf.Manifold(mf.Mesh(vert_properties=v.astype(np.float32), tri_verts=f.astype(np.uint32)))
B = 200.0
A = A - mf.Manifold.cube([1.0, 2*B, 2*B]).translate([-0.5, -B, -B])          # empty the gap between the backs

R, AP = 76.2, 76.2*np.cos(np.radians(30))
def inside(y, zz, m):   # point inside the hex (corners at y=±R, flats at z=±AP) shrunk by m
    return abs(zz) <= AP - m and abs(y)*np.cos(np.radians(30)) + abs(zz)*0.5 <= AP - m

# One tack per TACK_H band of height, so every layer prints exactly one tack and the toolpath is the same
# complexity on every layer (v41's tabs, all at the same few heights, left lines across the face). Across the
# width the tacks follow a golden-ratio sequence, which spreads them evenly (about one per 8 x 8 mm) instead
# of stacking them in columns. Kept MARGIN mm inside the outline so no tack sits on the rim, which is solid
# through to the face.
MARGIN, PHI = 4.0, (5 ** 0.5 - 1) / 2
pts = []
for i, zz in enumerate(np.arange(-AP + 2.0 + TACK_H/2, AP - 1.0, TACK_H)):
    w = min(R, (AP - MARGIN - abs(zz) * 0.5) / np.cos(np.radians(30))) - 0.5
    if w <= 0: continue
    y = -w + 2 * w * ((i * PHI) % 1.0)
    if inside(y, zz, MARGIN): pts.append((y, zz))
T = None
L = 0.3 + 1.0 - KISS                       # 0.3 mm into the near back, across the 1.0 mm gap, KISS short of the far back
for i, (y, zz) in enumerate(pts):
    x0 = -0.8 if i % 2 == 0 else 0.8 - L
    c = mf.Manifold.cube([L, TACK_W, TACK_H]).translate([x0, y - TACK_W/2, zz - TACK_H/2])
    T = c if T is None else T + c
A = A + T
out = A.to_mesh()
nv, nf = np.asarray(out.vert_properties)[:, :3], np.asarray(out.tri_verts)
tm = trimesh.Trimesh(nv, nf)
print('tacks', len(pts), 'kiss', KISS, 'end area mm2', round(len(pts)*TACK_W*TACK_H, 1), 'watertight', tm.is_watertight, 'volume', round(tm.volume, 1))

xml = ''.join(f'<vertex x="{a:.5f}" y="{b:.5f}" z="{c:.5f}"/>' for a, b, c in nv)
tri = ''.join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in nf)
body = f'<mesh><vertices>{xml}</vertices><triangles>{tri}</triangles></mesh>'
for oid in ('3', '7', '9'):
    m = block(oid); s = s[:m.start()] + m.group(1) + body + m.group(3) + s[m.end():]
ms = z.read('Metadata/model_settings.config').decode().replace('v60b125', 'v62k')
with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED) as o:
    for n in z.namelist():
        o.writestr(n, s if n == '3D/3dmodel.model' else ms if n == 'Metadata/model_settings.config' else z.read(n))
