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


def prediction_outcome(exp: dict, validity: dict) -> str | None:
    """supported / refuted / unresolved / inconclusive, or None with no verdict to judge (or an acceptance verdict,
    which answers 'good enough', not a prediction)."""
    v = exp.get("owner_verdict")
    if not v or v["kind"] == "acceptance":
        return None
    if v["kind"] == "inconclusive" or _witness_spoils(v) or validity.get("status") in ("confounded", "unknown"):
        return "inconclusive"
    expect, order = exp.get("expect") or {}, v["order"]
    strength = STRENGTH_RANK[v.get("strength")]
    if v.get("about_target") is not True:
        out = "unresolved"
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
