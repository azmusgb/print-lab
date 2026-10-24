"""The visible front of a tile-like part: its facets, how each faces in the print orientation, and the heights
where the front switches between facing down (mild overhang) and facing up (stepping in)."""
from dataclasses import dataclass

import numpy as np
import trimesh

BAND = 0.5  # degrees either side of vertical counted as neither down nor up


@dataclass
class Facet:
    normal: tuple
    area_mm2: float
    z_min: float
    z_max: float
    centroid_z: float
    elevation_deg: float
    side: str
    index: int = -1


@dataclass
class Switch:
    side: str
    z_mm: float
    down_area_mm2: float
    up_area_mm2: float


def front_facets(m: trimesh.Trimesh, max_tilt_deg: float = 25.0) -> list[Facet]:
    """Faces whose normal is within max_tilt_deg of ± the thinnest horizontal axis. Exactly flat faces (backs, pads,
    ribs, within 0.3° of the axis) are not front facets: a low-poly front is made of tilted facets."""
    axis = int(np.argmin(m.extents[:2]))
    name = "xy"[axis]
    out = []
    for sign in (1, -1):
        d = np.zeros(3)
        d[axis] = sign
        cos = m.face_normals @ d
        keep = (cos >= np.cos(np.radians(max_tilt_deg))) & (cos < np.cos(np.radians(0.3)))
        for i in np.nonzero(keep)[0]:
            n = m.face_normals[i]
            zs = m.triangles[i][:, 2]
            out.append(Facet(normal=tuple(map(float, n)), area_mm2=float(m.area_faces[i]), z_min=float(zs.min()),
                             z_max=float(zs.max()), centroid_z=float(zs.mean()),
                             elevation_deg=float(np.degrees(np.arcsin(np.clip(n[2], -1, 1)))),
                             side=("+" if sign > 0 else "-") + name, index=int(i)))
    return out


def facet_switches(facets: list[Facet], step: float = 0.5) -> list[Switch]:
    """Per side, the heights where the area-weighted facing of the front changes from down to up or back."""
    out = []
    for side in sorted({f.side for f in facets}):
        fs = [f for f in facets if f.side == side]
        down = sum(f.area_mm2 for f in fs if f.elevation_deg < -BAND)
        up = sum(f.area_mm2 for f in fs if f.elevation_deg > BAND)
        top = max(f.z_max for f in fs)
        last_sign, last_z = 0, None
        z = step / 2
        while z < top:
            w = [(f.area_mm2, f.elevation_deg) for f in fs if f.z_min <= z <= f.z_max]
            if w:
                mean = sum(a * e for a, e in w) / sum(a for a, _ in w)
                sign = -1 if mean < -BAND else (1 if mean > BAND else 0)
                if sign and last_sign and sign != last_sign:
                    out.append(Switch(side, round((last_z + z) / 2, 2), round(down, 1), round(up, 1)))
                if sign:
                    last_sign, last_z = sign, z
            z += step
    return out
