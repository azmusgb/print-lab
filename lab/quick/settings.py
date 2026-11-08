"""The settings Quick Print offers. Each key was shown by a real slice to change the output (A19 P0 report); Studio
accepts out-of-range values silently, so every range and name here is enforced by the lab, not left to the slicer."""
from dataclasses import dataclass

INFILL_PATTERNS = ("grid", "gyroid")  # the two P0 sliced; anything else is refused, never passed through
BRIMS = ("no_brim", "outer_only")


class QuickSettingError(ValueError):
    """A setting the lab doesn't offer, or a value outside its checked range."""


@dataclass(frozen=True)
class Spec:
    key: str
    label: str
    kind: str  # int | float | bool | choice
    lo: float | None = None
    hi: float | None = None
    choices: tuple = ()


SPECS = {s.key: s for s in (
    Spec("layer_height", "Layer height (mm)", "float", 0.08, 0.28),  # the profile's own min/max; Studio accepts 0.01
    Spec("wall_loops", "Walls", "int", 1, 6),
    Spec("top_shell_layers", "Top layers", "int", 2, 10),
    Spec("bottom_shell_layers", "Bottom layers", "int", 2, 10),
    Spec("sparse_infill_density", "Infill (%)", "int", 0, 90),  # 100 % is refused by Studio with grid, 150 % always
    Spec("sparse_infill_pattern", "Infill pattern", "choice", choices=INFILL_PATTERNS),
    Spec("enable_support", "Supports", "bool"),
    Spec("brim_type", "Brim", "choice", choices=BRIMS),
    Spec("brim_width", "Brim width (mm)", "float", 1, 10),
)}


def _number(spec: Spec, value, whole: bool):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise QuickSettingError(f"{spec.label}: expected a number, got {value!r}")
    try:
        n = float(value)
    except ValueError:
        raise QuickSettingError(f"{spec.label}: expected a number, got {value!r}") from None
    if n != n or not spec.lo <= n <= spec.hi:  # NaN fails both
        raise QuickSettingError(f"{spec.label}: {n:g} is outside {spec.lo:g} to {spec.hi:g}")
    if whole and n != int(n):
        raise QuickSettingError(f"{spec.label}: expected a whole number, got {value!r}")
    return int(n) if whole else n


def to_patch(settings: dict) -> dict:
    """User settings -> the slicer's keys and string values. Raises QuickSettingError on any unknown key or bad value."""
    unknown = sorted(set(settings or {}) - set(SPECS))
    if unknown:
        raise QuickSettingError(f"Not offered: {', '.join(unknown)}")
    patch: dict = {}
    for key, value in (settings or {}).items():
        spec = SPECS[key]
        if spec.kind == "int":
            patch[key] = str(_number(spec, value, True))
        elif spec.kind == "float":
            patch[key] = f"{_number(spec, value, False):g}"
        elif spec.kind == "bool":
            if not isinstance(value, bool):
                raise QuickSettingError(f"{spec.label}: expected on or off, got {value!r}")
            patch[key] = "1" if value else "0"
        else:
            if value not in spec.choices:
                raise QuickSettingError(f"{spec.label}: {value!r} isn't one of {', '.join(spec.choices)}")
            patch[key] = value
    if "top_shell_layers" in patch:
        patch["top_shell_thickness"] = "0"  # otherwise the profile's thickness silently wins (P0: 3 layers changed nothing)
    if patch.get("brim_type") == "outer_only" and "brim_width" not in patch:
        patch["brim_width"] = "5"
    if patch.get("brim_type") == "no_brim":
        patch.pop("brim_width", None)
    if patch.get("sparse_infill_density") == "100":
        raise QuickSettingError("Infill (%): 100 isn't offered")
    return patch
