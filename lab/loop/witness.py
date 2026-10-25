"""The witness wall: a plain, fixed control piece on a plate (spec: Builders, 2). Any change to its shape makes a
new version; WITNESS-01 never changes."""
import trimesh

WITNESS_VERSION = "WITNESS-01"
LENGTH_MM, LOOPS, MIN_GAP_MM = 40.0, 2, 25.0


def witness_wall(height_mm: float, line_w: float) -> trimesh.Trimesh:
    """40 mm long (along Y), two line widths thick (along X), the strip's height, standing on the bed."""
    w = trimesh.creation.box((LOOPS * line_w, LENGTH_MM, height_mm))
    w.apply_translation([0, 0, height_mm / 2])
    return w
