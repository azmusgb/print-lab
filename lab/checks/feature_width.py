from lab.findings import Finding
from lab.geometry.sections import thin_regions


def check(m, ctx):
    one = [z for z, _ in thin_regions(m, ctx.line_w, max_lines=1.0)]
    two = thin_regions(m, ctx.line_w, max_lines=2.0)
    if not one and not two:
        return []
    blocking = bool(one)
    zs = one if blocking else [z for z, _ in two]
    width = ctx.line_w if blocking else 2 * ctx.line_w
    return [Finding(rule="feature-below-line-width", severity="blocking" if blocking else "warning",
                    where=f"{len(zs)} layers between {min(zs):g} and {max(zs):g} mm",
                    why=(f"Parts of this model are thinner than one printed line ({ctx.line_w} mm), so the slicer "
                         "will leave them out or print them as nubs.") if blocking else
                        (f"Parts of this model are narrower than two printed lines ({width:.2f} mm, two lines of "
                         f"{ctx.line_w} mm), so the slicer can only print them as single lines or gap fill, and small "
                         "ones (joins, rib stubs) may come out as nubs."),
                    fix=f"Make them at least {round(ctx.line_w * 2 + 0.06, 2)} mm wide, or check the slice preview "
                        "at those heights that they print as real walls.",
                    data={"layers": len(zs), "z_min": min(zs), "z_max": max(zs)})]
