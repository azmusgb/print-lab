"""Leaning a tile back and scoring lean angles for an appearance part."""
from dataclasses import dataclass

import numpy as np
import trimesh

from lab.geometry.facets import front_facets

# Appearance profile weights from the spec (contact damage and time count in full in Stage 1A: no supports, no slice).
WEIGHTS = {"a_surface": 40, "consistency": 20, "stability": 15, "contact": 10, "bed": 5, "time": 5, "height": 5}


@dataclass
class OrientationScore:
    angle: float
    a_surface: float
    stability: float
    height_mm: float
    score: float


def lean(m: trimesh.Trimesh, angle_deg: float, axis: str) -> trimesh.Trimesh:
    """Rotate about the bed-level long axis ('x' or 'y') so the -thin-axis face tilts up by angle_deg; back on the bed."""
    out = m.copy()
    vec = [1, 0, 0] if axis == "x" else [0, 1, 0]
    sign = -1 if axis == "x" else 1
    out.apply_transform(trimesh.transformations.rotation_matrix(np.radians(sign * angle_deg), vec))
    out.apply_translation([0, 0, -out.bounds[0][2]])
    return out


def _a_surface(original: trimesh.Trimesh, leaned: trimesh.Trimesh, side: str) -> float:
    """Lowest front-facet elevation after leaning, mapped to 0 (−10° or worse) … 1 (+5° or better). The front
    facets are picked on the unleaned part: leaning would otherwise make inner faces look like front facets."""
    idx = [f.index for f in front_facets(original) if f.side == side and f.area_mm2 > 1]
    if not idx:
        return 0.0
    lowest = float(np.degrees(np.arcsin(np.clip(leaned.face_normals[idx, 2], -1, 1))).min())
    return float(np.clip((lowest + 10) / 15, 0, 1))


def score_orientations(m: trimesh.Trimesh, angles: list[float], profile: str = "appearance") -> list[OrientationScore]:
    if profile != "appearance":
        raise ValueError(f"Only the appearance profile is scored in Stage 1A, not '{profile}'.")
    thin = int(np.argmin(m.extents[:2]))
    long_axis = "y" if thin == 0 else "x"
    side = "-" + "xy"[thin]
    base_h = m.extents[2]
    out = []
    for a in angles:
        lm = lean(m, a, long_axis)
        a_surf = _a_surface(m, lm, side)
        com_z = lm.center_mass[2] if lm.is_watertight else lm.triangles_center[:, 2].mean()
        stability = float(np.clip(lm.extents[thin] / max(com_z, 1e-6) * 4, 0, 1))
        height_term = float(np.clip(1 - (lm.extents[2] - base_h) / base_h, 0, 1)) if a else 1.0
        score = (WEIGHTS["a_surface"] * a_surf + WEIGHTS["consistency"] * a_surf + WEIGHTS["stability"] * stability
                 + WEIGHTS["contact"] + WEIGHTS["bed"] * stability + WEIGHTS["time"] + WEIGHTS["height"] * height_term)
        out.append(OrientationScore(angle=a, a_surface=round(a_surf, 3), stability=round(stability, 3),
                                    height_mm=round(float(lm.extents[2]), 1), score=round(score, 1)))
    return out
