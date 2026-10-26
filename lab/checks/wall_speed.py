"""Rule from CASE-002: inner-to-outer wall speed ratio must not exceed 2.0x.

Large differentials starve outer wall flow on directional changes, causing visible banding.
"""
from lab.findings import Finding


def check(m, ctx):
    if not ctx.settings:
        return []

    inner = ctx.settings.get("inner_wall_speed")
    outer = ctx.settings.get("outer_wall_speed")
    if not inner or not outer:
        return []

    try:
        inner_v = float(inner[0] if isinstance(inner, list) else inner)
        outer_v = float(outer[0] if isinstance(outer, list) else outer)
    except (ValueError, TypeError):
        return []

    if outer_v <= 0:
        return []

    ratio = round(inner_v / outer_v, 1)
    if ratio > 2.0:
        rec_inner = round(outer_v * 1.8)
        return [Finding(
            rule="wall-speed-ratio",
            severity="warning",
            where=f"inner wall {inner_v:g} mm/s vs outer wall {outer_v:g} mm/s (ratio {ratio:g}x)",
            why=f"Inner wall is {ratio:g}x faster than outer wall (>2.0x threshold, proven by CASE-002). "
                "Large acceleration jumps starve outer wall flow when geometry narrows, producing visible bands.",
            fix=f"Lower inner wall speed to {rec_inner:g} mm/s or increase outer wall speed to keep ratio <= 2.0x.",
            data={"inner_speed": inner_v, "outer_speed": outer_v, "ratio": ratio},
        )]
    return []
