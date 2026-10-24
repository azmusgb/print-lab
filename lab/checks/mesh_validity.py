from lab.findings import Finding
from lab.geometry.mesh import solid_pieces


def check(m, ctx):
    bodies = solid_pieces(m)
    if m.is_watertight and bodies <= 2:
        return []
    problem = "isn't closed (it has holes)" if not m.is_watertight else f"is {bodies} separate pieces"
    return [Finding(rule="mesh-validity", severity="blocking", where="whole model",
                    why=f"The model {problem}, so its measurements and any coupon cut from it can't be trusted.",
                    fix="Re-export it from OpenSCAD, or repair it in Bambu Studio, and check it again.",
                    data={"watertight": bool(m.is_watertight), "bodies": bodies})]
