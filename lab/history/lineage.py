"""Steps between past revisions: what changed, how many factors, and how far the outcome can be trusted."""
from dataclasses import dataclass, field

from lab.history.revisions import Revision

# Settings keys that name or version things rather than change how the part prints.
_IGNORE_PARTS = ("_id", "name", "version", "inherits", "compatible", "different_settings_to_system", "from",
                 "upward_compatible_machine", "default_", "thumbnail")


@dataclass
class Transition:
    from_v: int
    to_v: int
    scad_changes: dict = field(default_factory=dict)
    settings_changes: dict = field(default_factory=dict)
    nozzle_change: bool = False
    factors: int = 0
    grade: str = "F"
    gap: list = field(default_factory=list)


def _diff(a: dict, b: dict, ignore=()) -> dict:
    keys = (set(a) | set(b))
    return {k: [a.get(k), b.get(k)] for k in sorted(keys)
            if not any(p in k for p in ignore) and a.get(k) != b.get(k)}


def _mismatch(r: Revision) -> bool:
    return bool(r.nozzle_in_name and r.nozzle_profile and r.nozzle_in_name != r.nozzle_profile)


def grade(factors: int, unknown: bool) -> str:
    """F: what printed is unknown or contradicts the file; A: 1 factor; B: 2; C: 3-4; D: 5 or more."""
    if unknown:
        return "F"
    return "A" if factors <= 1 else "B" if factors == 2 else "C" if factors <= 4 else "D"


def transitions(revs: list[Revision]) -> list[Transition]:
    revs = sorted(revs, key=lambda r: r.version)
    out = []
    for a, b in zip(revs, revs[1:]):
        scad = _diff(a.scad_params, b.scad_params) if a.scad_params and b.scad_params else {}
        if a.scad_code and b.scad_code and a.scad_code != b.scad_code:
            scad["scad code"] = [a.scad_code, b.scad_code]
        if not (a.scad_params and b.scad_params):  # no source on one side: compare the measured meshes instead
            for size in sorted(set(a.mesh) & set(b.mesh)):
                va, vb = a.mesh[size].get("volume_cm3"), b.mesh[size].get("volume_cm3")
                if va and vb and abs(va - vb) / max(va, vb) > 0.0005:
                    scad[f"model ({size} volume)"] = [va, vb]
        sett = _diff(a.settings or {}, b.settings or {}, _IGNORE_PARTS) if a.settings and b.settings else {}
        nozzle = (a.nozzle_profile or "") != (b.nozzle_profile or "")
        factors = len(scad) + len(sett) + int(nozzle)
        unknown = _mismatch(a) or _mismatch(b) or not ((a.scad_params or a.settings) and (b.scad_params or b.settings))
        out.append(Transition(from_v=a.version, to_v=b.version, scad_changes=scad, settings_changes=sett,
                              nozzle_change=nozzle, factors=factors, grade=grade(factors, unknown),
                              gap=list(range(a.version + 1, b.version))))
    return out
