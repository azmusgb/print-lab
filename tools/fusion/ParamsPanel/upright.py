"""Turn an STL exported from Fusion into its upright print orientation, in place.

Fusion exports in model coordinates. The hex tiles are modelled lying flat (face +Z,
top edge +Y) and printed standing up, face toward the printer's -Y: model +Y becomes
up and model +Z becomes -Y, the same turn as the SCAD sources' upright() module.
The result sits on the bed (min Z = 0) and is centred in X and Y.

Run by the Parameters Panel add-in: uv run python -I upright.py FILE.stl
"""

import sys
from pathlib import Path

import numpy as np
import trimesh


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print('usage: upright.py FILE.stl', file=sys.stderr)
        return 2
    path = Path(argv[0])
    if not path.is_file():
        print(f'no such file: {path}', file=sys.stderr)
        return 2
    mesh = trimesh.load(path, force='mesh')
    if mesh.is_empty:
        print(f'no geometry in {path}', file=sys.stderr)
        return 1
    mesh.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    lo, hi = mesh.bounds
    mesh.apply_translation([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]])
    mesh.export(path)
    print(' x '.join(f'{v:.2f}' for v in mesh.extents))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
