from lab.findings import Finding
from lab.geometry.facets import facet_switches, front_facets


def check(m, ctx):
    sw = facet_switches(front_facets(m))
    if not sw:
        return []
    heights = ", ".join(f"{s.z_mm:g} mm ({s.side})" for s in sw)
    return [Finding(rule="overhang-flip-on-A", severity="warning", where=f"front faces at {heights}",
                    why="Below these heights the front facets lean out (a mild overhang); above they lean back. The "
                        "two print with a different surface, which can show as a change in texture across the face.",
                    fix="Lean the part back far enough that every front facet faces up, and test it on an orientation "
                        "coupon first.",
                    data={"switches": [s.__dict__ for s in sw]})]
