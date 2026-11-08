"""The settings Quick Print exposes, each allow-listed and range-checked here, because Bambu Studio silently accepts
bad values (a bogus infill pattern, 0.01 mm layers). Ranges come from the A19 P0 probe on Studio 02.09.01.70."""
from dataclasses import dataclass

LAYER_HEIGHT = (0.08, 0.28)  # the profile's min/max layer height
WALLS = (1, 6)
SHELL_LAYERS = (1, 10)
INFILL_PCT = (0, 99)  # 100% is refused by Studio with a sparse pattern
INFILL_PATTERNS = ("grid", "gyroid", "honeycomb", "cubic", "line")
BRIM_TYPES = {"none": "no_brim", "outer": "outer_only"}
BRIM_WIDTH = (1.0, 20.0)


@dataclass
class QuickSettings:
    """None means: keep the base project's value."""
    layer_height: float | None = None
    walls: int | None = None
    top_layers: int | None = None
    bottom_layers: int | None = None
    infill_pct: int | None = None
    infill_pattern: str | None = None
    supports: bool | None = None
    brim: str | None = None
    brim_width: float | None = None

    def asdict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


def _in(name, v, lo, hi):
    if not lo <= v <= hi:
        raise ValueError(f"{name} {v:g} is outside {lo:g} to {hi:g}")


def settings_patch(s: QuickSettings) -> dict:
    """The Studio keys to override. Raises ValueError for anything outside the allowed values."""
    p: dict = {}
    if s.layer_height is not None:
        _in("layer height", s.layer_height, *LAYER_HEIGHT)
        p["layer_height"] = f"{s.layer_height:g}"
    if s.walls is not None:
        _in("walls", s.walls, *WALLS)
        p["wall_loops"] = str(int(s.walls))
    if s.top_layers is not None:
        _in("top layers", s.top_layers, *SHELL_LAYERS)
        p["top_shell_layers"] = str(int(s.top_layers))
        p["top_shell_thickness"] = "0"  # the profile's 1 mm thickness would force at least 5 layers
    if s.bottom_layers is not None:
        _in("bottom layers", s.bottom_layers, *SHELL_LAYERS)
        p["bottom_shell_layers"] = str(int(s.bottom_layers))
    if s.infill_pct is not None:
        _in("infill", s.infill_pct, *INFILL_PCT)
        p["sparse_infill_density"] = f"{int(s.infill_pct)}%"
    if s.infill_pattern is not None:
        if s.infill_pattern not in INFILL_PATTERNS:
            raise ValueError(f"infill pattern {s.infill_pattern!r} is not one of {', '.join(INFILL_PATTERNS)}")
        p["sparse_infill_pattern"] = s.infill_pattern
    if s.supports is not None:
        p["enable_support"] = "1" if s.supports else "0"
    if s.brim is not None:
        if s.brim not in BRIM_TYPES:
            raise ValueError(f"brim {s.brim!r} is not one of {', '.join(BRIM_TYPES)}")
        p["brim_type"] = BRIM_TYPES[s.brim]
        if s.brim == "outer":
            w = 5.0 if s.brim_width is None else s.brim_width
            _in("brim width", w, *BRIM_WIDTH)
            p["brim_width"] = f"{w:g}"
    elif s.brim_width is not None:
        raise ValueError("brim width needs brim 'outer'")
    return p
