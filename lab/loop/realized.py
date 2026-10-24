"""Was the declared factor actually realized in the sliced G-code? (owner's amendment during the Phase 1 review).
Stage 1A.1 checks speed factors per object; 1A.2 replaces this with the full intent -> setting -> toolpath trace."""
import re
import zipfile
from collections import defaultdict
from pathlib import Path

from lab.adapters.bambu import extract_gcode
from lab.loop.diff import _variant_of
from lab.loop.outcome import _factors

# Provisional thresholds, in one place (1A.2 replaces them with distribution analysis).
AS_ASKED_MM_S, AS_ASKED_PCT = 2.0, 3.0
MATERIAL_MM_S, MATERIAL_PCT = 5.0, 10.0


def _labels(sliced: Path) -> dict[str, str]:
    with zipfile.ZipFile(sliced) as z:
        info = z.read("Metadata/slice_info.config").decode()
    return {m.group(1): m.group(2) for m in re.finditer(r'<object identify_id="(\d+)" name="([^"]*)"', info)}


def object_feature_speeds(sliced: Path, feature: str) -> dict[str, tuple[float, float]]:
    """{variant: (dominant speed mm/s, share of that feature's path at it)}, weighted by length; copies combined."""
    names = _labels(sliced)
    lengths: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    feat = None
    # A plate with one object has no per-object markers: everything belongs to it.
    obj = next(iter(names.values())) if len(names) == 1 else None
    feed, x, y = 0, 0.0, 0.0
    for line in extract_gcode(sliced, 1).splitlines():
        if line.startswith("; start printing object, unique label id:"):
            obj = names.get(line.rsplit(":", 1)[1].strip())
        elif line.startswith("; stop printing object"):
            obj = None
        elif line.startswith("; FEATURE:"):
            feat = line[10:].strip()
        elif line.startswith(("G1", "G0")):
            if m := re.search(r"F(\d+(?:\.\d+)?)", line):
                feed = round(float(m.group(1)) / 60)
            mx, my = re.search(r"X(-?[\d.]+)", line), re.search(r"Y(-?[\d.]+)", line)
            nx, ny = (float(mx.group(1)) if mx else x), (float(my.group(1)) if my else y)
            if obj and feat == feature and " E" in line:
                lengths[_variant_of(obj)][feed] += ((nx - x) ** 2 + (ny - y) ** 2) ** 0.5
            x, y = nx, ny
    out = {}
    for vid, by_speed in lengths.items():
        total = sum(by_speed.values())
        speed, length = max(by_speed.items(), key=lambda kv: kv[1])
        out[vid] = (float(speed), round(length / total, 3) if total else 0.0)
    return out


def _material(a: float, b: float) -> bool:
    return abs(a - b) >= max(MATERIAL_MM_S, MATERIAL_PCT / 100 * max(a, b))


def _as_asked(requested: float | None, realized: float) -> bool:
    return requested is None or abs(realized - requested) <= max(AS_ASKED_MM_S, AS_ASKED_PCT / 100 * requested)


def realization(paths, exp: dict, build: dict, others: dict) -> dict | None:
    """None when the factor isn't a G-code-observable speed. Otherwise per variant: requested, realized, coverage,
    and the status realized / realized_differently / not_realized."""
    f = _factors().get(exp["factor"]["name"], {})
    feature = f.get("gcode_feature")
    if f.get("kind") != "setting" or not feature or not build.get("sliced"):
        return None
    key = f["settings_key"]
    requested = {}
    for v in (exp.get("build_spec") or {}).get("variants", []):
        val = v.get("settings_patch", {}).get(key)
        requested[v["id"]] = float(val) if val is not None else None
    speeds = dict(object_feature_speeds(paths.root / build["sliced"], feature))
    own_ids = [v["id"] for v in exp["variants"] if v.get("role", "variant") == "variant"]
    if len(speeds) == 1 and len(own_ids) == 1 and own_ids[0] not in speeds:  # a migrated plate's object name
        speeds = {own_ids[0]: next(iter(speeds.values()))}
    for ref in exp.get("reference_variants") or []:
        rexp = others.get(ref.rsplit("-", 1)[0]) or {}
        run = (rexp.get("print_runs") or [None])[-1]
        rb = next((b for b in rexp.get("builds") or [] if run and b["id"] == run.get("build_id")), None)
        if rb and rb.get("sliced") and (paths.root / rb["sliced"]).exists():
            got = object_feature_speeds(paths.root / rb["sliced"], feature)
            if got:
                speeds[ref] = next(iter(got.values())) if ref not in got else got[ref]
                requested.setdefault(ref, None)
    variants = {vid: {"requested": requested.get(vid), "realized": s, "coverage": c} for vid, (s, c) in speeds.items()}
    ids = list(variants)
    same = [(a, b) for i, a in enumerate(ids) for b in ids[i + 1:]
            if not _material(variants[a]["realized"], variants[b]["realized"])]
    differently = [v for v, x in variants.items() if not _as_asked(x["requested"], x["realized"])]
    status = ("single" if len(ids) < 2 else "not_realized" if same
              else "realized_differently" if differently else "realized")
    return {"feature": feature, "status": status, "variants": variants,
            "same_pairs": [list(p) for p in same], "differently": differently}
