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


def diff_layers(layers_a: list[LayerInfo], layers_b: list[LayerInfo],
                *, near: float | None = None, window: float = 5.0) -> dict:
    time_a = sum(l.est_time_s for l in layers_a)
    time_b = sum(l.est_time_s for l in layers_b)
    span_a = (layers_a[0].z, layers_a[-1].z) if layers_a else (0.0, 0.0)
    span_b = (layers_b[0].z, layers_b[-1].z) if layers_b else (0.0, 0.0)

    map_a = {round(l.z, 2): l for l in layers_a}
    map_b = {round(l.z, 2): l for l in layers_b}
    all_z = sorted(set(map_a.keys()) | set(map_b.keys()))

    if near is not None:
        all_z = [z for z in all_z if abs(z - near) <= window]

    layer_diffs = []
    speed_diffs = []
    time_jumps = []
    fan_diffs = []

    for z in all_z:
        la = map_a.get(z)
        lb = map_b.get(z)
        if la and lb:
            sa = max(la.outer_wall_speeds_mm_s) if la.outer_wall_speeds_mm_s else None
            sb = max(lb.outer_wall_speeds_mm_s) if lb.outer_wall_speeds_mm_s else None
            speed_delta = (sb - sa) if (sa is not None and sb is not None) else None
            t_delta = round(lb.est_time_s - la.est_time_s, 2)
            t_ratio = (lb.est_time_s / la.est_time_s) if la.est_time_s > 0 else 1.0
            fan_delta = round((lb.fan_pct or 0.0) - (la.fan_pct or 0.0), 1)
            seam_dist = None
            if la.seam_xy and lb.seam_xy:
                seam_dist = round(math.hypot(lb.seam_xy[0] - la.seam_xy[0], lb.seam_xy[1] - la.seam_xy[1]), 1)

            entry = {
                "z": z,
                "speed_a": sa,
                "speed_b": sb,
                "speed_delta": speed_delta,
                "time_a": round(la.est_time_s, 2),
                "time_b": round(lb.est_time_s, 2),
                "time_delta": t_delta,
                "fan_a": la.fan_pct,
                "fan_b": lb.fan_pct,
                "fan_delta": fan_delta,
                "seam_dist": seam_dist,
            }
            layer_diffs.append(entry)

            if speed_delta is not None and abs(speed_delta) > 0.1:
                speed_diffs.append(entry)
            if abs(t_ratio - 1.0) > 0.25 and (la.est_time_s > 2.0 or lb.est_time_s > 2.0):
                time_jumps.append(entry)
            if abs(fan_delta) > 1.0:
                fan_diffs.append(entry)
        else:
            layer_diffs.append({
                "z": z,
                "only_in": "A" if la else "B",
                "time": round((la or lb).est_time_s, 2),
            })

    def _group_intervals(entries, key):
        if not entries:
            return []
        intervals = []
        cur_start = entries[0]["z"]
        cur_end = entries[0]["z"]
        cur_val = entries[0].get(key)
        for e in entries[1:]:
            val = e.get(key)
            if val == cur_val and round(e["z"] - cur_end, 2) <= 0.4:
                cur_end = e["z"]
            else:
                intervals.append((cur_start, cur_end, cur_val))
                cur_start = cur_end = e["z"]
                cur_val = val
        intervals.append((cur_start, cur_end, cur_val))
        return intervals

    speed_intervals = _group_intervals(speed_diffs, "speed_delta")

    return {
        "count_a": len(layers_a),
        "count_b": len(layers_b),
        "span_a": span_a,
        "span_b": span_b,
        "time_a": round(time_a, 1),
        "time_b": round(time_b, 1),
        "time_delta": round(time_b - time_a, 1),
        "speed_intervals": speed_intervals,
        "speed_diff_count": len(speed_diffs),
        "time_jump_count": len(time_jumps),
        "fan_diff_count": len(fan_diffs),
        "layers": layer_diffs,
    }


def format_gcode_diff(res: dict, name_a: str = "A", name_b: str = "B", *, show_layers: bool = False, max_rows: int = 30) -> str:
    lines = []
    lines.append("G-code Plate Comparison:")
    ta_min = round(res['time_a'] / 60, 1)
    tb_min = round(res['time_b'] / 60, 1)
    td_min = round(res['time_delta'] / 60, 1)
    lines.append(f"  {name_a}: {res['count_a']} layers, Z {res['span_a'][0]:g}–{res['span_a'][1]:g} mm, est {ta_min:g} min")
    lines.append(f"  {name_b}: {res['count_b']} layers, Z {res['span_b'][0]:g}–{res['span_b'][1]:g} mm, est {tb_min:g} min")
    lines.append(f"  Delta: {'+' if td_min >= 0 else ''}{td_min:g} min ({'+' if res['time_delta'] >= 0 else ''}{res['time_delta']:g} s)")

    lines.append("")
    lines.append("Divergences:")
    if res.get("speed_intervals"):
        lines.append(f"  Outer Wall Speed ({res['speed_diff_count']} layers differ):")
        for z0, z1, d in res["speed_intervals"]:
            d_str = f"{'+' if d >= 0 else ''}{d:g} mm/s"
            lines.append(f"    • Z {z0:g}–{z1:g} mm: delta {d_str}")
    else:
        lines.append("  Outer Wall Speed: identical across all shared layers")

    if res.get("time_jump_count"):
        lines.append(f"  Layer Duration: {res['time_jump_count']} layers have >25% time divergence")

    if res.get("fan_diff_count"):
        lines.append(f"  Part Cooling Fan: {res['fan_diff_count']} layers differ in fan speed")

    if show_layers and res.get("layers"):
        lines.append("")
        lines.append("Layer Detail:")
        lines.append(f"  {'Z (mm)':>7} │ {'Speed A':>9} → {'Speed B':>9} │ {'Time A':>7} → {'Time B':>7} │ {'Fan A':>5} → {'Fan B':>5}")
        lines.append("  " + "─" * 7 + "─┼─" + "─" * 21 + "─┼─" + "─" * 17 + "─┼─" + "─" * 13)
        shown = res["layers"][:max_rows]
        for l in shown:
            if "only_in" in l:
                lines.append(f"  {l['z']:>7.2f} │ (only in plate {l['only_in']})")
                continue
            sa = f"{l['speed_a']:g}" if l['speed_a'] is not None else "-"
            sb = f"{l['speed_b']:g}" if l['speed_b'] is not None else "-"
            fa = f"{l['fan_a']:g}%" if l['fan_a'] is not None else "-"
            fb = f"{l['fan_b']:g}%" if l['fan_b'] is not None else "-"
            lines.append(f"  {l['z']:>7.2f} │ {sa:>9} → {sb:>9} │ {l['time_a']:>6.1f}s → {l['time_b']:>6.1f}s │ {fa:>5} → {fb:>5}")
        if len(res["layers"]) > max_rows:
            lines.append(f"  … ({len(res['layers']) - max_rows} more layers)")

    return "\n".join(lines)
