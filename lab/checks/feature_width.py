from lab.findings import Finding
from lab.geometry.sections import thin_regions

ENGRAVING_MM = 1.0  # slivers reaching no further than this from solid material are a shallow cut into a surface


def check(m, ctx):
    # A sub-line sliver on one or two layers is a facet edge crossing a layer plane, not a feature: ignore it.
    one = thin_regions(m, ctx.line_w, max_lines=1.0, with_reach=True)
    one = one if len(one) >= 3 else []
    two = thin_regions(m, ctx.line_w, max_lines=2.0, with_reach=True)
    out: list[Finding] = []
    # Lettering or marks cut into a face leave slivers only as deep as the cut. Where every sub-line sliver is that
    # shallow, report the cut once as a note, and leave out the two-line slivers it makes at the same heights.
    if one and all(r <= ENGRAVING_MM for _, _, r in one):
        lo, hi = min(z for z, _, _ in one), max(z for z, _, _ in one)
        out.append(Finding(rule="engraving", severity="info",
                           where=f"marks between {lo:g} and {hi:g} mm",
                           why=("Lettering or marks cut into a surface (up to "
                                f"{max(r for _, _, r in one):g} mm deep) leave slivers narrower than one printed line "
                                "at their edges. The slicer drops or merges them; the cut itself still prints."),
                           fix="Check in the slice preview at those heights that the marks still read.",
                           data={"layers": len(one), "z_min": lo, "z_max": hi}))
        # The marks also leave two-line slivers up to a couple of mm beyond the sub-line ones, at their top and bottom.
        two = [t for t in two if not (lo - 2 <= t[0] <= hi + 2 and t[2] <= ENGRAVING_MM)]
        one = []
    zs1 = [z for z, _, _ in one]
    if not zs1 and not two:
        return out
    blocking = bool(zs1)
    zs = zs1 if blocking else [z for z, _, _ in two]
    width = ctx.line_w if blocking else 2 * ctx.line_w
    return out + [Finding(rule="feature-below-line-width", severity="blocking" if blocking else "warning",
                    where=f"{len(zs)} layers between {min(zs):g} and {max(zs):g} mm",
                    why=(f"Parts of this model are thinner than one printed line ({ctx.line_w} mm), so the slicer "
                         "will leave them out or print them as nubs.") if blocking else
                        (f"Parts of this model are narrower than two printed lines ({width:.2f} mm, two lines of "
                         f"{ctx.line_w} mm), so the slicer can only print them as single lines or gap fill, and small "
                         "ones (joins, rib stubs) may come out as nubs."),
                    fix=f"Make them at least {round(ctx.line_w * 2 + 0.06, 2)} mm wide, or check the slice preview "
                        "at those heights that they print as real walls.",
                    data={"layers": len(zs), "z_min": min(zs), "z_max": max(zs)})]
