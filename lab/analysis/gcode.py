"""Per-layer facts from Bambu Studio G-code: height, an estimated layer time, outer-wall speeds, fan and seam.

The time is the sum of move lengths over their feed rates, ignoring acceleration: an estimate for spotting changes
between layers, not a print-time prediction (Bambu Studio's own estimate is the authority)."""
import math
import re
from dataclasses import dataclass, field

_WORD = re.compile(r"([XYZEFS])(-?\d*\.?\d+)")


@dataclass
class LayerInfo:
    index: int
    z: float
    est_time_s: float = 0.0
    outer_wall_speeds_mm_s: list[float] = field(default_factory=list)
    fan_pct: float | None = None
    seam_xy: tuple[float, float] | None = None


def read_layers(gcode: str) -> list[LayerInfo]:
    layers: list[LayerInfo] = []
    x = y = 0.0
    feed = 0.0  # mm/s
    feature = ""
    fan: float | None = None
    for raw in gcode.splitlines():
        line = raw.strip()
        if line.startswith(";"):
            if line.startswith("; CHANGE_LAYER"):
                layers.append(LayerInfo(index=len(layers), z=0.0, fan_pct=fan))
            elif line.startswith("; Z_HEIGHT:") and layers:
                layers[-1].z = float(line.split(":", 1)[1])
            elif line.startswith("; FEATURE:"):
                feature = line.split(":", 1)[1].strip()
            continue
        code = line.split(";", 1)[0].strip()
        if not code:
            continue
        cmd, *_ = code.split()
        words = dict(_WORD.findall(code))
        if cmd == "M106" and "S" in words and not re.search(r"\bP\d", code):  # part fan only (P1/P2/P3 are others)
            fan = round(float(words["S"]) / 255 * 100, 1)
            if layers:
                layers[-1].fan_pct = fan
        if cmd not in ("G0", "G1", "G2", "G3"):
            continue
        if "F" in words:
            feed = float(words["F"]) / 60
        nx, ny = float(words.get("X", x)), float(words.get("Y", y))
        dist = math.hypot(nx - x, ny - y)
        extruding = "E" in words and float(words["E"]) > 0
        if layers:
            cur = layers[-1]
            if feed > 0 and dist > 0:
                cur.est_time_s += dist / feed
            if feature == "Outer wall" and extruding:
                if cur.seam_xy is None:
                    cur.seam_xy = (x, y)
                if round(feed, 1) not in cur.outer_wall_speeds_mm_s:
                    cur.outer_wall_speeds_mm_s.append(round(feed, 1))
        x, y = nx, ny
    return layers


def events_near(layers: list[LayerInfo], z: float, window: float = 5.0) -> dict:
    """Slicer changes within ±window mm of z: outer-wall speed, fan, or a >30 % layer-time jump."""
    near = [l for l in layers if abs(l.z - z) <= window]
    speed_z = [b.z for a, b in zip(near, near[1:]) if a.outer_wall_speeds_mm_s and b.outer_wall_speeds_mm_s
               and max(a.outer_wall_speeds_mm_s) != max(b.outer_wall_speeds_mm_s)]
    fan_z = [b.z for a, b in zip(near, near[1:]) if a.fan_pct != b.fan_pct]
    time_z = [b.z for a, b in zip(near, near[1:]) if a.est_time_s and abs(b.est_time_s - a.est_time_s) / a.est_time_s > 0.3]
    return {"outer_wall_speed_change": bool(speed_z), "speed_change_z": speed_z,
            "fan_change": bool(fan_z), "fan_change_z": fan_z,
            "layer_time_jump": bool(time_z), "layer_time_jump_z": time_z}
