"""Put a tile-frame STL into the object of an existing Bambu project 3MF, keeping its settings and placement.

Tile frame (x corner axis, y flat axis, z depth, back at z = 0) maps to the standing print as (x, y, z) -> (-(z - 7.62), -x, y),
the same as build_project_3mf.py. Usage: mesh_to_project_3mf.py <base.3mf> <tile_frame.stl> <out.3mf>
"""
import re
import sys
import zipfile

import numpy as np
import trimesh

base, stl, out = sys.argv[1:4]
m = trimesh.load(stl)
v = m.vertices
obj = np.stack([-(v[:, 2] - 7.62), -v[:, 0], v[:, 1]], 1)
if abs(obj[:, 2].min() + obj[:, 2].max()) > 0.01:
    obj[:, 2] -= (obj[:, 2].min() + obj[:, 2].max()) / 2          # keep the object centred on z = 0 as the base project has it
vx = "\n".join(f'     <vertex x="{a:.6f}" y="{b:.6f}" z="{c:.6f}"/>' for a, b, c in obj)
tx = "\n".join(f'     <triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in m.faces)
src = zipfile.ZipFile(base)
old = src.read("3D/Objects/object_4.model").decode()
new = re.sub(r"<vertices>.*?</vertices>", lambda _: f"<vertices>\n{vx}\n    </vertices>", old, flags=re.S)
new = re.sub(r"<triangles>.*?</triangles>", lambda _: f"<triangles>\n{tx}\n    </triangles>", new, flags=re.S)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
    for it in src.infolist():
        data = src.read(it.filename)
        if it.filename == "3D/Objects/object_4.model":
            data = new.encode()
        elif it.filename.endswith("model_settings.config"):
            data = re.sub(r'face_count="\d+"', f'face_count="{len(m.faces)}"', data.decode()).encode()
        dst.writestr(it, data)
print("triangles", len(m.faces), "object z range", obj[:, 2].min().round(3), obj[:, 2].max().round(3))
