"""Put a tile-frame STL into an existing Bambu project 3MF as a FLAT, face-up print with supports in the open back.

Tile frame (x corner axis, y flat axis, z depth, back at z = 0, face toward +z) is used as is: the back plane sits on the bed.
The tile is rotated ROT deg about Z (15 deg gives the smallest square footprint, about 245 mm) and centred on the plate.
Settings changed from the base project: layer height, supports (tree, from the plate only), brim width. Everything else
(filament, walls, speeds, textured PEI) stays as in the base.

Usage: mesh_to_flat_project_3mf.py <base.3mf> <tile_frame.stl> <out.3mf> [--layer 0.08] [--rot 15] [--tilt 0] [--brim 2] [--bed 256]
--tilt leans the tile back about its corner axis (x): 0 is flat face up, 90 is standing on the flat edge.
"""
import argparse
import json
import math
import re
import zipfile

import numpy as np
import trimesh

ap = argparse.ArgumentParser()
ap.add_argument("base")
ap.add_argument("stl")
ap.add_argument("out")
ap.add_argument("--layer", type=float, default=0.08)
ap.add_argument("--rot", type=float, default=15.0)
ap.add_argument("--tilt", type=float, default=0.0)
ap.add_argument("--brim", type=float, default=2.0)
ap.add_argument("--bed", type=float, default=256.0)
args = ap.parse_args()

m = trimesh.load(args.stl)
v = m.vertices.copy()
cx, cy = (v[:, 0].min() + v[:, 0].max()) / 2, (v[:, 1].min() + v[:, 1].max()) / 2
zmid = (v[:, 2].min() + v[:, 2].max()) / 2
obj = np.stack([v[:, 0] - cx, v[:, 1] - cy, v[:, 2] - zmid], 1)    # centred on the origin, as the base project keeps its object
height = v[:, 2].max() - v[:, 2].min()

th, al = math.radians(args.rot), math.radians(args.tilt)
c, s = math.cos(th), math.sin(th)
ca, sa = math.cos(al), math.sin(al)
# 3MF transform is row-vector form (x' = x*m00 + y*m10 + z*m20 + m30): rotate about Z by `rot`, then about X by `tilt`.
# A tilt of 0 leaves the face up; 90 stands the tile on its flat edge, face toward -Y, tile +y up (tear roof at the top).
rz = np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]])
rxm = np.array([[1, 0, 0], [0, ca, sa], [0, -sa, ca]])
mrow = rz @ rxm
rot_v = obj @ mrow
foot = (rot_v[:, 0].max() - rot_v[:, 0].min(), rot_v[:, 1].max() - rot_v[:, 1].min())
# Flat, the brim runs around the whole footprint; tilted or standing, it only surrounds the narrow contact edge at the bed.
margin = 2 * args.brim if args.tilt == 0 else 0
if max(foot) + margin > args.bed - 1:
    raise SystemExit(f"footprint {foot[0]:.1f} x {foot[1]:.1f} mm plus brim does not fit a {args.bed:.0f} mm plate")
tx, ty, tz = args.bed / 2, args.bed / 2, -rot_v[:, 2].min()
height = rot_v[:, 2].max() - rot_v[:, 2].min()
item_tf = " ".join(f"{val:.9f}" for val in mrow.flatten()) + f" {tx:.6f} {ty:.6f} {tz:.6f}"

vx = "\n".join(f'     <vertex x="{a:.6f}" y="{b:.6f}" z="{d:.6f}"/>' for a, b, d in obj)
tx_ = "\n".join(f'     <triangle v1="{a}" v2="{b}" v3="{d}"/>' for a, b, d in m.faces)
src = zipfile.ZipFile(args.base)
old = src.read("3D/Objects/object_4.model").decode()
new = re.sub(r"<vertices>.*?</vertices>", lambda _: f"<vertices>\n{vx}\n    </vertices>", old, flags=re.S)
new = re.sub(r"<triangles>.*?</triangles>", lambda _: f"<triangles>\n{tx_}\n    </triangles>", new, flags=re.S)

cfg = json.loads(src.read("Metadata/project_settings.config"))
cfg.update({
    "layer_height": f"{args.layer:g}",
    "enable_support": "1",
    "support_type": "tree(auto)",
    "support_on_build_plate_only": "1",
    "brim_type": "outer_only" if args.brim > 0 else "no_brim",
    "brim_width": f"{args.brim:g}",
})
for k, val in (("layer_height", cfg["layer_height"]), ("brim_width", cfg["brim_width"])):
    assert cfg[k] == val

with zipfile.ZipFile(args.out, "w", zipfile.ZIP_DEFLATED) as dst:
    for it in src.infolist():
        data = src.read(it.filename)
        name = it.filename
        if name == "3D/Objects/object_4.model":
            data = new.encode()
        elif name == "3D/3dmodel.model":
            data = re.sub(r'(<item objectid="2"[^>]*?)transform="[^"]*"', lambda mo: f'{mo.group(1)}transform="{item_tf}"', data.decode()).encode()
        elif name.endswith("model_settings.config"):
            txt = re.sub(r'face_count="\d+"', f'face_count="{len(m.faces)}"', data.decode())
            txt = re.sub(r'(<assemble_item object_id="2" instance_id="0" transform=")[^"]*"', lambda mo: f'{mo.group(1)}{item_tf}"', txt)
            data = txt.encode()
        elif name == "Metadata/project_settings.config":
            data = json.dumps(cfg, indent=4).encode()
        dst.writestr(it, data)
print(f"triangles {len(m.faces)}  footprint {foot[0]:.1f} x {foot[1]:.1f} mm at rot {args.rot:g} tilt {args.tilt:g} deg  height {height:.2f} mm  layer {args.layer:g}  brim {args.brim:g}")
print("item transform:", item_tf)
