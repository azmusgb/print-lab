"""v61: v60b125 (1.25 mm backs) with the full-height ribs and edge seams replaced by small tack posts."""
import re, sys, zipfile, numpy as np, trimesh, manifold3d as mf

SRC, OUT, TACK_Z_PITCH, TACK_W, TACK_H = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5])
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

pts = []
for y in (-25.63, -9.63, 6.37, 22.37):                                      # the old rib lines
    for zz in np.arange(-AP + 2.0, AP - 1.0, TACK_Z_PITCH):
        if inside(y, zz, 2.0): pts.append((y, zz))
per = []                                                                      # round the outline, 2.5 mm in
corners = [(R*np.cos(np.radians(a)), R*np.sin(np.radians(a))) for a in range(0, 360, 60)]
for i in range(6):
    (y0, z0), (y1, z1) = corners[i], corners[(i+1) % 6]
    n = int(np.ceil(np.hypot(y1-y0, z1-z0) / TACK_Z_PITCH))
    for k in range(n):
        t = (k + 0.5) / n; y, zz = y0 + t*(y1-y0), z0 + t*(z1-z0)
        sc = (R - 2.5/np.cos(np.radians(30))) / R; y, zz = y*sc, zz*sc
        if zz > -AP + 2.0: per.append((y, zz))
pts += per
T = None
for y, zz in pts:
    c = mf.Manifold.cube([1.6, TACK_W, TACK_H]).translate([-0.8, y - TACK_W/2, zz - TACK_H/2])
    T = c if T is None else T + c
A = A + T
out = A.to_mesh()
nv, nf = np.asarray(out.vert_properties)[:, :3], np.asarray(out.tri_verts)
tm = trimesh.Trimesh(nv, nf)
print('tacks', len(pts), 'contact per side mm2', round(len(pts)*TACK_W*TACK_H, 1), 'watertight', tm.is_watertight, 'volume', round(tm.volume, 1))

xml = ''.join(f'<vertex x="{a:.5f}" y="{b:.5f}" z="{c:.5f}"/>' for a, b, c in nv)
tri = ''.join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in nf)
body = f'<mesh><vertices>{xml}</vertices><triangles>{tri}</triangles></mesh>'
for oid in ('3', '7', '9'):
    m = block(oid); s = s[:m.start()] + m.group(1) + body + m.group(3) + s[m.end():]
ms = z.read('Metadata/model_settings.config').decode().replace('v60b125', 'v61t')
with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED) as o:
    for n in z.namelist():
        o.writestr(n, s if n == '3D/3dmodel.model' else ms if n == 'Metadata/model_settings.config' else z.read(n))
