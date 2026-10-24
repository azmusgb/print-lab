"""Reading meshes out of Bambu 3MF projects and writing the lab's print files."""
import json
import xml.etree.ElementTree as ET
from xml.sax.saxutils import quoteattr
import zipfile
from pathlib import Path

import numpy as np
import trimesh

from lab.adapters.bambu import list_objects
from lab.jobs import sha256

NS = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
P_PATH = "{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}path"
MAIN = "3D/3dmodel.model"


def _matrix(text: str | None) -> np.ndarray:
    """A 3MF transform (12 numbers, row-vector convention) as a 4x4 matrix for column vectors."""
    if not text:
        return np.eye(4)
    v = [float(x) for x in text.split()]
    m = np.eye(4)
    m[:3, :3] = np.array(v[:9]).reshape(3, 3).T
    m[:3, 3] = v[9:12]
    return m


class _Models:
    """The objects of every model part in a 3MF. Bambu Studio keeps each mesh in its own part
    (3D/Objects/object_N.model), referenced from the main model's components with p:path."""

    def __init__(self, z: zipfile.ZipFile):
        self.z, self.parts = z, {}

    def objects(self, part: str) -> dict:
        if part not in self.parts:
            root = ET.fromstring(self.z.read(part))
            self.parts[part] = {o.get("id"): o for o in root.iter(f"{{{NS['m']}}}object")}
        return self.parts[part]


def _object_mesh(models: _Models, part: str, oid: str, transform: np.ndarray) -> list[trimesh.Trimesh]:
    obj = models.objects(part).get(oid)
    if obj is None:
        raise ValueError(f"The 3MF refers to object {oid} in {part}, but it isn't there; the file is damaged.")
    mesh = obj.find("m:mesh", NS)
    if mesh is not None:
        verts = np.array([[float(v.get(a)) for a in "xyz"] for v in mesh.find("m:vertices", NS)])
        faces = np.array([[int(t.get(a)) for a in ("v1", "v2", "v3")] for t in mesh.find("m:triangles", NS)])
        m = trimesh.Trimesh(verts, faces, process=True)
        m.apply_transform(transform)
        return [m]
    out = []
    comps = obj.find("m:components", NS)
    for c in (comps if comps is not None else []):
        sub = c.get(P_PATH, "").lstrip("/") or part
        out += _object_mesh(models, sub, c.get("objectid"), transform @ _matrix(c.get("transform")))
    return out


def load_object(path_3mf: Path, name_contains: str) -> trimesh.Trimesh:
    """The one object whose name contains name_contains, rotated as it sits on its plate, on the bed (min z = 0) and
    centred at x = y = 0. Several objects with the same name are copies, so the first is used."""
    infos = list_objects(path_3mf)
    hits = [o for o in infos if name_contains in o.name]
    if not hits or len({o.name for o in hits}) > 1:
        names = ", ".join(sorted({o.name for o in infos}))
        raise ValueError(f"{len({o.name for o in hits})} objects match '{name_contains}' in {path_3mf.name}. "
                         f"Pick one of: {names}")
    with zipfile.ZipFile(path_3mf) as z:
        root = ET.fromstring(z.read(MAIN))
        item = next((i for i in root.iter(f"{{{NS['m']}}}item") if i.get("objectid") == hits[0].id), None)
        if item is None:
            raise ValueError(f"'{hits[0].name}' is in {path_3mf.name} but not on the build plate. Put it on a plate in "
                             "Bambu Studio and save again.")
        placement = _matrix(item.get("transform"))
        placement[:3, 3] = 0  # keep how it is turned on the plate, not where
        m = trimesh.util.concatenate(_object_mesh(_Models(z), MAIN, hits[0].id, placement))
    lo, hi = m.bounds
    m.apply_translation([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]])
    return m


_CT = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
 <Default Extension="png" ContentType="image/png"/>
 <Default Extension="gcode" ContentType="text/x.gcode"/>
</Types>
"""
_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>
"""


def write_print_3mf(base_3mf: Path, meshes: list[tuple[str, trimesh.Trimesh, tuple[float, float]]], out: Path,
                    meta: dict) -> str:
    """A print file on plate 1: the base project's settings, the given named meshes at (x, y) on the bed, and
    Metadata/print_lab.json = meta. Returns the file's SHA-256."""
    with zipfile.ZipFile(base_3mf) as z:
        settings = z.read("Metadata/project_settings.config")
    objs, items, ms_objs, insts = [], [], [], []
    for i, (name, mesh, (x, y)) in enumerate(meshes):
        m = mesh.copy()
        lo, hi = m.bounds
        m.apply_translation([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]])
        oid = str(i + 1)
        vs = "".join(f'<vertex x="{a:.6f}" y="{b:.6f}" z="{c:.6f}"/>' for a, b, c in m.vertices)
        ts = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in m.faces)
        objs.append(f'<object id="{oid}" type="model"><mesh><vertices>{vs}</vertices><triangles>{ts}</triangles>'
                    f'</mesh></object>')
        items.append(f'<item objectid="{oid}" transform="1 0 0 0 1 0 0 0 1 {x:.5f} {y:.5f} 0" printable="1"/>')
        q = quoteattr(name)
        ms_objs.append(f'<object id="{oid}"><metadata key="name" value={q}/><metadata key="extruder" value="1"/>'
                       f'<part id="{oid}" subtype="normal_part"><metadata key="name" value={q}/></part></object>')
        insts.append(f'<model_instance><metadata key="object_id" value="{oid}"/>'
                     f'<metadata key="instance_id" value="0"/></model_instance>')
    model = ('<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" '
             'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
             'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021">'
             '<metadata name="Application">BambuStudio-02.08.02.61</metadata>'
             '<metadata name="BambuStudio:3mfVersion">1</metadata>'
             f'<resources>{"".join(objs)}</resources><build>{"".join(items)}</build></model>')
    model_settings = ('<?xml version="1.0" encoding="UTF-8"?>\n<config>' + "".join(ms_objs) +
                      '<plate><metadata key="plater_id" value="1"/>' + "".join(insts) + '</plate></config>')
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CT)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("3D/3dmodel.model", model)
        z.writestr("Metadata/project_settings.config", settings)
        z.writestr("Metadata/model_settings.config", model_settings)
        z.writestr("Metadata/print_lab.json", json.dumps(meta, indent=2))
    return sha256(out)
