"""The hex tiles are modelled lying flat (face +Z, top edge +Y) and printed standing up, face toward the printer's -Y:
model +Y becomes up and model +Z becomes -Y, the same turn as the SCAD sources' upright() module."""
import numpy as np
import trimesh


def upright(m: trimesh.Trimesh) -> trimesh.Trimesh:
    """A copy turned upright, centred in x and y, on the bed (min z = 0)."""
    m = m.copy()
    m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    lo, hi = m.bounds
    m.apply_translation([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]])
    return m
