import re

from lab.findings import Finding


def _from_line_width(w: str | None) -> str | None:
    try:
        return "0.6" if float(w) >= 0.55 else "0.4"
    except (TypeError, ValueError):
        return None


def check(m, ctx):
    claims: dict[str, str] = {"you said": f"{ctx.nozzle:g}"}
    if ctx.file_name and (hit := re.search(r"(0\.[46])\s*nozzle", ctx.file_name)):
        claims["file name"] = hit.group(1)
    if ctx.settings:
        if nd := ctx.settings.get("nozzle_diameter"):
            claims["printer profile"] = f"{float(nd[0] if isinstance(nd, list) else nd):g}"
        if lw := _from_line_width(ctx.settings.get("outer_wall_line_width")):
            claims["line width"] = lw
    if len(set(claims.values())) <= 1:
        return []
    said = ", ".join(f"{k} {v}" for k, v in claims.items())
    return [Finding(rule="nozzle-mismatch", severity="blocking", where=said,
                    why="The nozzle size isn't the same everywhere, so what prints won't be what was checked.",
                    fix="Pick the nozzle actually on the printer, choose its printer, process and filament presets, "
                        "and name the file to match.", data=claims)]
