"""Loading a model and its basic facts, in print orientation (Z up, bed at min Z)."""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh


@dataclass
class MeshFacts:
    extents: tuple
    volume_cm3: float
    area_cm2: float
    watertight: bool
    bodies: int
    bed_contact_mm2: float
    com_z: float


def load_mesh(path: Path, object: str | None = None) -> trimesh.Trimesh:
    path = Path(path)
    if path.suffix.lower() == ".3mf":
        from lab.adapters.threemf import load_object
        return load_object(path, object or "")
    m = trimesh.load(path, force="mesh")
    m.apply_translation([0, 0, -m.bounds[0][2]])
    return m


def solid_pieces(m: trimesh.Trimesh) -> int:
    """Separate solid pieces: closed shells enclosing material. Inner shells of sealed voids (negative volume, e.g.
    a closed back) are part of the piece around them, not pieces of their own."""
    parts = m.split(only_watertight=False)
    return sum(1 for p in parts if not p.is_watertight or p.volume > 0)


def mesh_facts(m: trimesh.Trimesh) -> MeshFacts:
    bottom = m.area_faces[(m.face_normals[:, 2] < -0.999) & (m.triangles_center[:, 2] < m.bounds[0][2] + 0.01)].sum()
    com_z = float(m.center_mass[2]) if m.is_watertight else float(m.triangles_center[:, 2].mean())
    return MeshFacts(extents=tuple(round(float(x), 3) for x in m.extents),
                     volume_cm3=round(float(abs(m.volume)) / 1000, 3) if m.is_watertight else float("nan"),
                     area_cm2=round(float(m.area) / 100, 3), watertight=bool(m.is_watertight),
                     bodies=solid_pieces(m), bed_contact_mm2=round(float(bottom), 2),
                     com_z=round(com_z, 2))
