from lab.checks import BRIM_MM, MAX_HEIGHT_MM, PLATE_MM
from lab.findings import Finding


def check(m, ctx):
    x, y, z = (float(v) for v in m.extents)
    need_x, need_y = x + 2 * BRIM_MM, y + 2 * BRIM_MM
    if need_x <= PLATE_MM and need_y <= PLATE_MM and z <= MAX_HEIGHT_MM:
        return []
    return [Finding(rule="bed-fit", severity="blocking", where=f"{x:.1f} × {y:.1f} × {z:.1f} mm as placed",
                    why=f"With its {BRIM_MM:g} mm brim it needs {need_x:.0f} × {need_y:.0f} mm, but the X2D plate is "
                        f"{PLATE_MM:g} × {PLATE_MM:g} mm (height up to {MAX_HEIGHT_MM:g} mm).",
                    fix="Turn it on the plate (45° often fits) or print a smaller size.",
                    data={"needs_mm": [round(need_x, 1), round(need_y, 1)], "height_mm": round(z, 1)})]
