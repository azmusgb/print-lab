from lab.findings import Finding
from lab.geometry.mesh import solid_pieces


def _alike(m) -> bool:
    """Two solid pieces of the same size and volume: a pair (or two copies), not a part with a stray body."""
    parts = [p for p in m.split(only_watertight=False) if p.volume > 0]
    if len(parts) != 2:
        return False
    (a, b) = parts
    return abs(a.volume - b.volume) <= 0.05 * max(a.volume, b.volume) and \
        all(abs(x - y) <= 1.0 for x, y in zip(sorted(a.extents), sorted(b.extents)))


def check(m, ctx):
    bodies = solid_pieces(m)
    if m.is_watertight and bodies == 2 and not _alike(m):
        return [Finding(rule="mesh-validity", severity="warning", where="whole model",
                        why="The model is 2 separate pieces that don't match, so it isn't a pair; one is probably a "
                            "stray body.",
                        fix="If it should be one part, join the pieces in the model and export it again.",
                        data={"watertight": True, "bodies": 2})]
    if m.is_watertight and bodies <= 2:
        return []
    problem = "isn't closed (it has holes)" if not m.is_watertight else f"is {bodies} separate pieces"
    return [Finding(rule="mesh-validity", severity="blocking", where="whole model",
                    why=f"The model {problem}, so its measurements and any coupon cut from it can't be trusted.",
                    fix="Re-export it from OpenSCAD, or repair it in Bambu Studio, and check it again.",
                    data={"watertight": bool(m.is_watertight), "bodies": bodies})]
