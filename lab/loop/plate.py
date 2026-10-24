"""The plate as part of the experiment: what is on it, where, and the layer times it produced (spec: Test builders
and the plate)."""
import statistics
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from lab.analysis.gcode import read_layers

NS = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}


def layer_time_profile(gcode: str) -> list[list[float]]:
    """[[z, seconds], ...] per layer, from the G-code's own moves."""
    return [[round(l.z, 3), round(l.est_time_s, 2)] for l in read_layers(gcode)]


def median_layer_time(profile: list[list[float]], z_range: tuple[float, float] | None = None) -> float | None:
    ts = [t for z, t in profile if z_range is None or z_range[0] <= z <= z_range[1]]
    return round(statistics.median(ts), 2) if ts else None


def plate_of(path_3mf: Path) -> dict:
    """{"objects": [names], "placements": [[x, y], ...]} for a print file's build plate, in build order."""
    from lab.adapters.bambu import list_objects
    names = {o.id: o.name for o in list_objects(path_3mf)}
    with zipfile.ZipFile(path_3mf) as z:
        root = ET.fromstring(z.read("3D/3dmodel.model"))
    objects, placements = [], []
    for item in root.iter(f"{{{NS['m']}}}item"):
        t = [float(v) for v in (item.get("transform") or "1 0 0 0 1 0 0 0 1 0 0 0").split()]
        objects.append(names.get(item.get("objectid"), item.get("objectid")))
        placements.append([round(t[9], 2), round(t[10], 2)])
    return {"objects": objects, "placements": placements}
