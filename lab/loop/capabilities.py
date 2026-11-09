"""Capability tests: proof, from a real slice, that Bambu Studio honours a mechanism the builders rely on (spec:
Builders 4 and 5). Results are per Bambu Studio version and per factor: a pass authorizes only what it tested."""
import json
import re
from collections import defaultdict
from pathlib import Path

from lab.adapters.bambu import EXPECTED_VERSION, extract_gcode, slice_with_job
from lab.records.store import atomic_write_json, now

ROOT = Path(__file__).resolve().parent.parent.parent
CAP_DIR = ROOT / "capabilities"
REFERENCE = ROOT / "tests" / "fixtures" / "hex"  # the lab's reference specimen: a v58 strip on v55 0.4 settings
TAB_ISOLATION = "CAP-TAB-ISOLATION"


def height_range_capability(factor: str) -> str:
    return f"CAP-BAMBU-HEIGHT-RANGE-{factor}"


def _path(version: str) -> Path:
    return CAP_DIR / f"{version}.json"


def results(version: str = EXPECTED_VERSION) -> dict:
    p = _path(version)
    return json.loads(p.read_text()) if p.exists() else {}


def record(name: str, passed: bool, evidence: dict, version: str = EXPECTED_VERSION) -> dict:
    allr = results(version)
    allr[name] = {"name": name, "passed": bool(passed), "at": now(), "bambu_studio": version, "evidence": evidence}
    CAP_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_json(_path(version), allr)
    return allr[name]


def capability_passed(name: str, version: str = EXPECTED_VERSION) -> bool:
    return bool(results(version).get(name, {}).get("passed"))


def _strip():
    from lab.adapters.threemf import load_object
    from lab.geometry.coupons import height_strip
    return height_strip(load_object(REFERENCE / "hexagon_v58_X2D_0.6nozzle.3mf", "v58_06_6in"), 60, 72)


def per_layer(gcode: str, feature: str) -> dict[float, dict]:
    """Per layer: the feature's dominant speed, the layer's estimated time and its fan level."""
    from lab.analysis.gcode import read_layers
    speeds: dict[float, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    z = 0.0
    feat, feed, x, y = None, 0, 0.0, 0.0
    for line in gcode.splitlines():
        if line.startswith("; Z_HEIGHT:"):
            z = round(float(line.split(":")[1]), 2)
        elif line.startswith("; FEATURE:"):
            feat = line[10:].strip()
        elif line.startswith(("G1", "G0")):
            if m := re.search(r"F(\d+(?:\.\d+)?)", line):
                feed = round(float(m.group(1)) / 60)
            mx, my = re.search(r"X(-?[\d.]+)", line), re.search(r"Y(-?[\d.]+)", line)
            nx, ny = (float(mx.group(1)) if mx else x), (float(my.group(1)) if my else y)
            if feat == feature and " E" in line:
                speeds[z][feed] += ((nx - x) ** 2 + (ny - y) ** 2) ** 0.5
            x, y = nx, ny
    layers = {round(l.z, 2): l for l in read_layers(gcode)}
    return {z: {"speed": max(s.items(), key=lambda kv: kv[1])[0], "time": layers[z].est_time_s if z in layers else None,
                "fan": layers[z].fan_pct if z in layers else None} for z, s in speeds.items()}


def _slice(meshes, work: Path, name: str, height_ranges=None) -> str:
    from lab.adapters.threemf import write_print_3mf
    from lab.geometry.coupons import plate_layout
    art = work / f"{name}.3mf"
    write_print_3mf(REFERENCE / "hexagon_v57_X2D_0.4nozzle.3mf", plate_layout(meshes), art, {"capability": name},
                    height_ranges=height_ranges)
    out, _ = slice_with_job(art, work / "sliced", 1, work / "jobs")
    return extract_gcode(out, 1)


def _height_range(factor: str, work: Path) -> tuple[bool, dict]:
    from lab.loop.outcome import _factors
    f = _factors()[factor]
    low, high = 60, 120  # both under the filament's flow cap, so the slicer can honour them
    g = _slice([("probe", _strip())], work, f"hr-{factor}",
               height_ranges=[[(0.0, 6.0, {f["settings_key"]: str(low)}), (6.0, 12.0, {f["settings_key"]: str(high)})]])
    layers = per_layer(g, f["gcode_feature"])
    below = [v["speed"] for z, v in layers.items() if 1.0 <= z <= 5.8]
    above = [v["speed"] for z, v in layers.items() if 6.4 <= z <= 11.0]
    switch = min((z for z, v in layers.items() if v["speed"] == high), default=None)
    ok = bool(below and above and set(below) == {low} and set(above) == {high} and switch is not None
              and abs(switch - 6.2) <= 0.21)
    return ok, {"asked": [low, high], "boundary_mm": 6.0, "first_layer_at_high": switch,
                "below": sorted(set(below)), "above": sorted(set(above))}


def _tab_isolation(work: Path) -> tuple[bool, dict]:
    from lab.loop.tabs import attach_tab
    strip = _strip()
    plain = per_layer(_slice([("probe", strip)], work, "tab-off"), "Outer wall")
    tabbed = per_layer(_slice([("probe", attach_tab(strip, "1A", work / "jobs"))], work, "tab-on"), "Outer wall")
    judged = [z for z in plain if z >= 2.0 and z in tabbed]
    worst = max((abs(tabbed[z]["time"] - plain[z]["time"]) / plain[z]["time"] * 100 for z in judged
                 if plain[z]["time"]), default=0.0)
    same_speed = all(plain[z]["speed"] == tabbed[z]["speed"] for z in judged)
    same_fan = all(plain[z]["fan"] == tabbed[z]["fan"] for z in judged)
    return bool(judged) and worst <= 2.0 and same_speed and same_fan, {
        "judged_from_mm": 2.0, "layers": len(judged), "worst_time_pct": round(worst, 2), "speeds_identical": same_speed,
        "fan_identical": same_fan}


def run_capability(name: str, work: Path) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    if name == TAB_ISOLATION:
        ok, ev = _tab_isolation(work)
    elif name.startswith("CAP-BAMBU-HEIGHT-RANGE-"):
        ok, ev = _height_range(name.removeprefix("CAP-BAMBU-HEIGHT-RANGE-"), work)
    else:
        raise ValueError(f"No capability test called {name}. Known: {TAB_ISOLATION}, "
                         "CAP-BAMBU-HEIGHT-RANGE-<factor> (inner_wall_speed, outer_wall_speed).")
    return record(name, ok, ev)
