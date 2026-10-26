"""What a verdict means for the prediction, and whether the comparison was sound (spec: Prediction outcome, Test
builders and the plate). Pure functions of the records."""
import json
from functools import lru_cache
from pathlib import Path

STRENGTH_RANK = {None: 0, "slightly": 1, "clearly": 2, "a lot": 3}
FACTORS = Path(__file__).resolve().parent.parent / "factors.json"


@lru_cache
def _factors() -> dict:
    return json.loads(FACTORS.read_text()) if FACTORS.exists() else {"objects_on_plate": {"kind": "plate"}}


def factor_kind(exp: dict) -> str | None:
    return (_factors().get((exp.get("factor") or {}).get("name")) or {}).get("kind")


def _place(order: list[list[str]], vid: str) -> int:
    for i, group in enumerate(order):
        if vid in group:
            return i
    raise ValueError(f"{vid} isn't in the ranking {order}")


def _witness_spoils(v: dict) -> bool:
    w = v.get("witness")
    return bool(w and w.get("condition") in ("abnormal", "inconclusive") and not v.get("witness_override"))


def _sweep_strips(exp: dict) -> list[tuple[float, str | None]]:
    """(speed, grade) per strip, slowest first."""
    grades = (exp.get("owner_verdict") or {}).get("grades") or {}
    own = [v for v in exp.get("variants") or [] if v.get("role", "variant") == "variant"]
    return sorted((float(v["factor_value"]), grades.get(v["id"])) for v in own)


def _sweep_outcome(exp: dict, v: dict) -> str:
    """'bands>=X': supported when every strip at or over X is banded and every one under it clean."""
    if v.get("lighting") not in (None, "diagnostic"):
        return "unresolved"
    x = float(exp["expect"]["bands_from"])
    strips = _sweep_strips(exp)
    if any((s >= x and g == "clean") or (s < x and g == "banded") for s, g in strips):
        out = "refuted"
    elif all((g == "banded") if s >= x else (g == "clean") for s, g in strips):
        out = "supported"
    else:
        out = "unresolved"
    return out if exp.get("provenance") == "prospective" or out == "unresolved" else "unresolved"


CRITERIA_WORDS = {"print": {"clean": "printed clean", "flawed": "printed flawed", "failed": "failed to print"},
                  "apart": {"yes": "came apart", "hard": "came apart with force", "no": "didn't come apart"}}


def criteria_finding(exp: dict) -> str | None:
    """'12A: printed clean, didn't come apart. 12B: …', from the owner's per-strip criteria grades."""
    v = exp.get("owner_verdict") or {}
    if v.get("kind") != "criteria":
        return None
    crit, grades = exp.get("criteria") or [], v.get("grades") or {}
    out = []
    for var in exp.get("variants") or []:
        g = grades.get(var["id"])
        if g is None:
            continue
        words = [CRITERIA_WORDS.get(c["key"], {}).get(g.get(c["key"])) or f"{c['label'].rstrip('?')} {g.get(c['key'])}"
                 for c in crit if g.get(c["key"]) is not None]
        out.append(f"{var.get('tab') or var['id']}: {', '.join(words)}.")
    return " ".join(out) or None


def sweep_finding(exp: dict) -> str | None:
    """'clean up to 60, faint at 80, bands from 100 mm/s', from the owner's grades."""
    if exp.get("test_kind") != "speed_sweep":
        return None
    strips = _sweep_strips(exp)
    if not strips or any(g is None for _, g in strips):
        return None
    n = lambda s: f"{s:g}"
    parts = []
    clean = [s for s, g in strips if g == "clean"]
    faint = [s for s, g in strips if g == "faint"]
    banded = [s for s, g in strips if g == "banded"]
    if clean:
        parts.append(f"clean up to {n(max(clean))}")
    if faint:
        parts.append("faint at " + ", ".join(n(s) for s in faint))
    if banded:
        parts.append(f"bands from {n(min(banded))}")
    unit = (exp.get("factor") or {}).get("unit") or ""
    return ", ".join(parts) + (f" {unit}" if unit else "")


def prediction_outcome(exp: dict, validity: dict) -> str | None:
    """supported / refuted / unresolved / inconclusive, or None with no verdict to judge (or an acceptance verdict,
    which answers 'good enough', not a prediction)."""
    v = exp.get("owner_verdict")
    if not v or v["kind"] in ("acceptance", "criteria"):
        return None  # a criteria verdict is a finding (criteria_finding), not a test of a prediction
    if v["kind"] == "sweep" and not (exp.get("expect") or {}).get("bands_from"):
        return None  # a sweep without a prediction is a finding (sweep_finding), not a test of one
    if v["kind"] == "inconclusive" or _witness_spoils(v) or validity.get("status") in ("confounded", "unknown"):
        return "inconclusive"
    if v["kind"] == "sweep":
        return _sweep_outcome(exp, v)
    expect, order = exp.get("expect") or {}, v["order"]
    strength = STRENGTH_RANK[v.get("strength")]
    if v.get("about_target") is not True or v.get("lighting") not in (None, "diagnostic"):
        out = "unresolved"  # off target, or not judged under the diagnostic light
    elif "better" in expect:
        b, a = _place(order, expect["better"]), _place(order, expect["than"])
        if b < a:
            out = "supported" if strength >= STRENGTH_RANK[expect.get("min_strength", "clearly")] else "unresolved"
        else:
            out = "refuted"
    elif "same" in expect:
        places = {_place(order, x) for x in expect["same"]}
        out = "supported" if len(places) == 1 else ("unresolved" if strength <= 1 else "refuted")
    else:
        out = "unresolved"
    if exp.get("provenance") != "prospective" and out in ("supported", "refuted"):
        out = "unresolved"
    return out


def _latest_build(exp: dict) -> dict | None:
    return next((b for b in reversed(exp.get("builds") or []) if b.get("ok") and b.get("measured")), None)


def printed_build(exp: dict) -> dict | None:
    """The build the experiment's latest print run used (what was really on the printer)."""
    run = (exp.get("print_runs") or [None])[-1]
    return next((b for b in exp.get("builds") or [] if run and b["id"] == run.get("build_id")), None)


def judged_window(exp: dict) -> tuple[float, float] | None:
    """The heights being judged, in the strip's own heights: around a marked defect (±10 mm), else the strip
    without its 6 mm margins, when known; None means the whole strip."""
    spec = exp.get("build_spec") or {}
    marks = [m["defect_z_mm"] for m in ((exp.get("owner_verdict") or {}).get("marks") or [])
             if m.get("defect_z_mm") is not None]
    if marks and spec.get("z"):
        z0, z1 = spec["z"]
        lo, hi = max(min(marks) - 10, z0), min(max(marks) + 10, z1)
        return (lo - z0, hi - z0)
    if spec.get("judged"):
        z0, z1 = spec["z"]
        j0, j1 = spec["judged"]
        return (j0 - z0, j1 - z0)
    return None



def comparison_validity(exp: dict, others: dict[str, dict], tolerance_pct: float,
                        production: dict | None = None) -> dict:
    """valid / confounded / unknown, with a coded reason for each problem."""
    reasons = []
    v = exp.get("owner_verdict") or {}
    w = v.get("witness")
    if w and not v.get("witness_override"):
        if w["condition"] == "abnormal":
            reasons.append({"code": "witness_abnormal", "status": "confounded"})
        elif w["condition"] == "inconclusive":
            reasons.append({"code": "witness_inconclusive", "status": "unknown"})
    for a in exp.get("anchors") or []:
        if a["condition"] == "different":
            reasons.append({"code": "anchor_shifted", "status": "confounded", "anchor": a["id"]})
        elif a["condition"] == "inconclusive":
            reasons.append({"code": "anchor_inconclusive", "status": "unknown", "anchor": a["id"]})
    mine = printed_build(exp) or _latest_build(exp)
    refs = exp.get("reference_variants") or []
    plate_factor = factor_kind(exp) == "plate"
    if refs and plate_factor:
        reasons.append({"code": "cross_plate_by_design", "status": "valid"})
    elif refs and not any(a["condition"] == "same" for a in exp.get("anchors") or []):
        reasons.append({"code": "cross_plate_no_anchor", "status": "unknown",
                        "note": "separate plates without a shared anchor are a weak comparison"})
    if not plate_factor and mine and mine.get("measured"):
        window = judged_window(exp)
        for ref in refs:
            other = others.get(ref.rsplit("-", 1)[0])
            theirs = printed_build(other) if other else None
            if not theirs:
                reasons.append({"code": "reference_not_printed", "status": "unknown", "variant": ref})
                continue
            from lab.loop.plate import plates_match
            pa = (mine["measured"] or {}).get("layer_time_profile")
            pb = (theirs.get("measured") or {}).get("layer_time_profile")
            r = plates_match(pa, pb, window, tolerance_pct) if pa and pb else {"match": None}
            if r["match"] is None:
                reasons.append({"code": "reference_unmeasurable", "status": "unknown", "variant": ref})
            elif not r["match"]:
                reasons.append({"code": "layer_time_mismatch", "status": "confounded", "variant": ref,
                                "this_s": r["a_s"], "other_s": r["b_s"], "worst_pct": r["worst_pct"],
                                "at_z": r["at_z"]})
    if production and production.get("objects") and mine and mine.get("plate"):
        n = len(mine["plate"].get("objects") or [])
        if n and n != production["objects"]:
            reasons.append({"code": "production_mismatch", "status": "valid", "test_objects": n,
                            "production_objects": production["objects"],
                            "note": "the test plate's layer time may not match production's"})
    status = ("confounded" if any(r["status"] == "confounded" for r in reasons)
              else "unknown" if any(r["status"] == "unknown" for r in reasons) else "valid")
    return {"status": status, "reasons": [{k: x for k, x in r.items() if k != "status"} for r in reasons]}
