"""The Stage 1A checks. Each check is check(mesh, ctx) -> list[Finding]; a check that throws is reported, not fatal."""
from dataclasses import dataclass, field

import trimesh

from lab.findings import Finding

LINE_W = {0.4: 0.42, 0.6: 0.62}
PLATE_MM, MAX_HEIGHT_MM, BRIM_MM = 256.0, 256.0, 10.0


@dataclass
class CheckContext:
    nozzle: float
    line_w: float
    settings: dict | None = None
    file_name: str | None = None


def run_checks(m: trimesh.Trimesh, *, nozzle: float, settings: dict | None = None,
               file_name: str | None = None) -> list[Finding]:
    from lab.checks import bed_fit, feature_width, mesh_validity, nozzle_mismatch, overhang_flip, part_gap, wall_speed

    ctx = CheckContext(nozzle=nozzle, line_w=LINE_W.get(nozzle, round(nozzle * 1.05, 2)), settings=settings,
                       file_name=file_name)
    out: list[Finding] = []
    for check in (mesh_validity.check, overhang_flip.check, feature_width.check, bed_fit.check,
                  nozzle_mismatch.check, part_gap.check, wall_speed.check):
        try:
            out += check(m, ctx)
        except Exception as e:  # a broken check must not hide the others
            out.append(Finding(rule=check.__module__.rsplit(".", 1)[-1], severity="info", where="",
                               why=f"This check couldn't run: {e}", fix="Report it; the other checks still ran."))
    return out
