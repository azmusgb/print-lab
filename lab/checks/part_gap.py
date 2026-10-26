from itertools import combinations

from lab.findings import Finding
from lab.geometry.sections import _layer_polygons


def check(m, ctx):
    """Separate parts closer than one printed line (or <= 0.75 mm for 0.6 nozzle, per CASE-001):
    the slicer can't keep that gap open, so they fuse (v58's two tiles, 0.1 mm apart, printed as one block)."""
    min_gap = 1.0 if ctx.nozzle >= 0.6 else ctx.line_w
    gaps = []
    for z, poly in list(_layer_polygons(m, 2.0)):
        parts = list(getattr(poly, "geoms", [poly])) if not poly.is_empty else []
        d = [a.distance(b) for a, b in combinations(parts, 2)]
        d = [x for x in d if 0 < x < min_gap]
        if d:
            gaps.append((z, min(d)))
    if not gaps:
        return []
    zs, narrowest = [z for z, _ in gaps], min(g for _, g in gaps)
    wide = 1.0 if ctx.nozzle >= 0.6 else round(ctx.line_w + 0.08, 1)
    rule_note = " (from CASE-001, a lesson under review: gaps <= 0.75 mm fused on the 0.6-nozzle variant)" if ctx.nozzle >= 0.6 else ""
    return [Finding(rule="parts-too-close", severity="warning",
                    where=f"gap {narrowest:.1f} mm between separate parts, Z {min(zs):g}–{max(zs):g} mm",
                    why=f"A gap narrower than {wide} mm{rule_note} can't stay open, so the parts fuse along it.",
                    fix=f"If they should come apart, open the gap to at least {wide} mm; if they should be one part, "
                        "join them in the model.",
                    data={"gap_mm": round(narrowest, 3), "z_min": min(zs), "z_max": max(zs)})]
