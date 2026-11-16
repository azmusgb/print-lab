import sys, zipfile, re, json
from build123d import Axis, Pos
from lab.design.families import faceted_hex as fh

out, base, six = sys.argv[1], sys.argv[2], sys.argv[3]
kx, kz = 0.921542459, 0.802104461   # the printed 6 in tile's Bambu scale
p = {"corner_diameter": 254.0, "edge_depth": 9.0 * kz, "facet_rise": 10.0 * kz, "skin_axial": 2.4 * kz, "perimeter_wall": 2.4 * kx,
     "land_width": 17.7 * kx, "land_thickness": 2.4 * kz, "roof_wall": 2.4 * kz, "mark": 1.0, "roof_tear": 1.0}
for q in fh.PARAMS:
    assert q.lo <= p[q.name] <= q.hi, (q.name, p[q.name])
part = fh.build(p, seed=3)                                  # not flipped: the tear roof stays at the top end
part = part.rotate(Axis.X, 90).rotate(Axis.Z, -90)         # stands on its flat edge, depth along X, face towards -x
c = part.bounding_box().center()
part = Pos(-c.X, -c.Y, -c.Z) * part
bb = part.bounding_box()
print("valid", part.is_valid, "solids", len(part.solids()), "vol cm3", round(part.volume / 1000, 2),
      "size", round(bb.size.X, 2), round(bb.size.Y, 2), round(bb.size.Z, 2))
verts, tris = part.tessellate(0.01)
key, wv, wt = {}, [], []
for v in verts:
    k = (round(v.X, 4), round(v.Y, 4), round(v.Z, 4))
    if k not in key:
        key[k] = len(wv); wv.append(v)
    wt.append(key[k])
tris = [(wt[a], wt[b], wt[c_]) for a, b, c_ in tris if len({wt[a], wt[b], wt[c_]}) == 3]
vx = "\n".join(f'     <vertex x="{v.X:.6f}" y="{v.Y:.6f}" z="{v.Z:.6f}"/>' for v in wv)
tx = "\n".join(f'     <triangle v1="{a}" v2="{b}" v3="{c_}"/>' for a, b, c_ in tris)
src = zipfile.ZipFile(base)
old = src.read("3D/Objects/object_4.model").decode()
new = re.sub(r"<vertices>.*?</vertices>", lambda m: f"<vertices>\n{vx}\n    </vertices>", old, flags=re.S)
new = re.sub(r"<triangles>.*?</triangles>", lambda m: f"<triangles>\n{tx}\n    </triangles>", new, flags=re.S)

# settings: the smooth profile as printed, with slot 2's filament values taken from the printed 6 in project (Kexcelled matte)
ps = json.loads(src.read("Metadata/project_settings.config"))
s6 = json.loads(zipfile.ZipFile(six).read("Metadata/project_settings.config"))
FIL = ("filament_", "nozzle_temperature", "hot_plate_temp", "cool_plate_temp", "eng_plate_temp", "textured_plate_temp",
       "fan_", "close_fan", "full_fan", "overhang_fan", "slow_down", "additional_cooling", "pressure_advance",
       "enable_pressure_advance", "temperature_vitrification", "reduce_fan", "required_nozzle", "supertack")
changed = []
for k, v in ps.items():
    if k.startswith(FIL) and isinstance(v, list) and isinstance(s6.get(k), list) and len(v) > 1 and len(s6[k]) > 1 \
            and k not in ("filament_colour", "filament_ids", "filament_map", "filament_map_mode"):
        if v[0] != s6[k][1]:
            changed.append(k)
        v[0] = s6[k][1]
json.dump(ps, open(f"{out}/project_settings.json", "w"), indent=4)
with zipfile.ZipFile(f"{out}/RIFT_10IN_15mm_seed3_tear_016_smooth.3mf", "w", zipfile.ZIP_DEFLATED) as dst:
    for it in src.infolist():
        data = src.read(it.filename)
        if it.filename == "3D/Objects/object_4.model":
            data = new.encode()
        elif it.filename.endswith("model_settings.config"):
            data = re.sub(r'face_count="\d+"', f'face_count="{len(tris)}"', data.decode()).encode()
        elif it.filename == "Metadata/project_settings.config":
            data = json.dumps(ps, indent=4).encode()
        dst.writestr(it, data)
print("tris", len(tris), "filament keys set from the 6in project:", len(changed))
print("filament ids", ps["filament_settings_id"][:2], "nozzle temp", ps["nozzle_temperature"][:2], "layer", ps["layer_height"], "infill", ps["sparse_infill_density"], "owall", ps["outer_wall_speed"][:1], ps["outer_wall_acceleration"][:1])
