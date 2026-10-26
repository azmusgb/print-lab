"""Spend, the uninformative streak and automatic stops, derived from the experiment records (spec: Budget and
stopping). Nothing here is stored."""
from lab.loop.outcome import comparison_validity, prediction_outcome

UNINFORMATIVE = ("unresolved", "inconclusive")


def run_usage(run: dict, build: dict | None) -> tuple[float, float]:
    """A started print run's cost: telemetry, then manual figures, then estimate x fraction for a failed run, then
    the estimate. A print run exists only once started, so every run listed costs something."""
    u = run.get("usage") or {}
    est = (build or {}).get("estimate") or {}
    m, g = float(est.get("minutes") or 0.0), float(est.get("g") or 0.0)
    if run.get("failed") and run["failed"].get("at_fraction") is not None:
        f = float(run["failed"]["at_fraction"])
        m, g = round(m * f, 2), round(g * f, 2)
    if u.get("usage_source") in ("telemetry", "manual", "printer_log"):  # each figure given replaces its fallback
        if u.get("actual_minutes") is not None:
            m = float(u["actual_minutes"])
        if u.get("actual_g") is not None:
            g = float(u["actual_g"])
    return m, g


def _build_of(exp: dict, run: dict) -> dict | None:
    return next((b for b in exp.get("builds") or [] if b["id"] == run.get("build_id")), None)


def spent(question: dict, exps: dict[str, dict]) -> dict:
    total_m = total_g = 0.0
    for eid in question["experiments"]:
        e = exps.get(eid)
        for run in (e or {}).get("print_runs") or []:
            m, g = run_usage(run, _build_of(e, run))
            total_m, total_g = total_m + m, total_g + g
    return {"minutes": round(total_m, 2), "g": round(total_g, 2)}


def budget(question: dict) -> dict:
    """The question's budget plus everything added on resuming."""
    b = {"minutes": float(question["budget"]["max_minutes"]), "g": float(question["budget"]["max_g"])}
    for s in question["stops"]:
        added = ((s.get("resume") or {}).get("added") or {})
        b["minutes"] += float(added.get("minutes") or 0)
        b["g"] += float(added.get("g") or 0)
    return b


def last_resume(question: dict) -> str | None:
    return max((s["resumed_at"] for s in question["stops"] if s.get("resumed_at")), default=None)


def outcomes(question: dict, exps: dict[str, dict], tolerance_pct: float = 10) -> list[tuple[str, str, str]]:
    """(verdict time, experiment id, outcome) for every answered prospective experiment, oldest first."""
    out = []
    for eid in question["experiments"]:
        e = exps.get(eid)
        v = (e or {}).get("owner_verdict")
        if not e or not v or e.get("provenance") != "prospective":
            continue
        o = prediction_outcome(e, comparison_validity(e, exps, tolerance_pct))
        if o:
            out.append((v.get("at") or "", eid, o))
    return sorted(out)


def streak(question: dict, exps: dict[str, dict], tolerance_pct: float = 10) -> int:
    since = last_resume(question)
    n = 0
    for at, _, o in outcomes(question, exps, tolerance_pct):
        if since and at <= since:
            continue
        n = n + 1 if o in UNINFORMATIVE else 0
    return n


def auto_stop(question: dict, exps: dict[str, dict], tolerance_pct: float = 10) -> dict | None:
    since = last_resume(question)
    recent = [(at, eid, o) for at, eid, o in outcomes(question, exps, tolerance_pct) if not since or at > since]
    if streak(question, exps, tolerance_pct) >= 2:
        return {"code": "uninformative_streak",
                "message": "Two experiments in a row were unresolved or inconclusive.",
                "triggered_by": [eid for _, eid, _ in recent[-2:]]}
    s, b = spent(question, exps), budget(question)
    if s["minutes"] >= b["minutes"]:
        return {"code": "budget_time_exhausted", "message": f"{s['minutes']:g} of {b['minutes']:g} min used.",
                "triggered_by": []}
    if s["g"] >= b["g"]:
        return {"code": "budget_material_exhausted", "message": f"{s['g']:g} of {b['g']:g} g used.",
                "triggered_by": []}
    return None


def owner_stopped(question: dict) -> dict | None:
    return next((s for s in reversed(question["stops"]) if not s.get("resumed_at")), None)
