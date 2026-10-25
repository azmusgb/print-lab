"""The project as one read-only projection: what `lab page` draws and what Stage 1B pushes to Local AI.

Every number comes from the loop's own code (ledger, outcome), so the page can't disagree with `lab question status`.
Records that fail validation are listed under `problems` and left out, never guessed at. Each record also travels as
its original payload with its file's sha256, so a receiver can upsert by ID and refuse an older copy.
"""
import hashlib
import json
from pathlib import Path

from lab.loop import ledger
from lab.loop.outcome import comparison_validity, criteria_finding, prediction_outcome, sweep_finding
from lab.records.project import ProjectPaths, project_settings
from lab.records.schema import load
from lab.records.store import RecordError, now

SCHEMA = "print-lab-index/1"
OPEN = ("planned", "built", "build_failed", "ready", "needs_approval", "approved", "printing")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_all(paths: ProjectPaths, folder: Path, kind: str, records: dict, problems: list) -> dict:
    out = {}
    for f in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        rel = f"{folder.name}/{f.name}"
        try:
            r = load(f, kind)
        except (RecordError, ValueError) as err:
            problems.append({"file": rel, "error": str(err)})
            continue
        out[r["id"]] = r
        records[r["id"]] = {"type": kind, "file": rel, "sha256": _sha(f), "payload": r}
    return out


def _last_build(e: dict) -> dict | None:
    ok = [b for b in e.get("builds") or [] if b.get("ok")]
    return ok[-1] if ok else None


def _variants(e: dict) -> list[dict]:
    b = _last_build(e) or {}
    real = ((b.get("realization") or {}).get("variants")) or {}
    unit = (e.get("factor") or {}).get("unit") or ""
    grades = (e.get("owner_verdict") or {}).get("grades") or {}
    out = []
    for v in e.get("variants") or []:
        if v.get("role", "variant") != "variant":
            continue
        r = real.get(v["id"]) or {}
        requested = r.get("requested", v.get("factor_value"))
        realized = r.get("realized")
        out.append({"id": v["id"], "tab": v.get("tab"), "requested": requested, "realized": realized,
                    "as_asked": None if realized is None else v["id"] not in
                    ((b.get("realization") or {}).get("differently") or []), "unit": unit,
                    "grade": grades.get(v["id"])})
    return out


def _usage(e: dict) -> dict | None:
    runs = e.get("print_runs") or []
    if not runs:
        return None
    builds = {b["id"]: b for b in e.get("builds") or []}
    m = g = 0.0
    for r in runs:
        rm, rg = ledger.run_usage(r, builds.get(r.get("build_id")))
        m, g = m + rm, g + rg
    return {"minutes": round(m, 1), "g": round(g, 1)}


def _photos(e: dict, root: Path) -> list[dict]:
    return [{"run": r["id"], "path": p["path"], "sha256": p.get("sha256") or _sha(root / p["path"]), "source": p.get("source"),
             "captured_at": p.get("captured_at")}
            for r in e.get("print_runs") or [] for p in r.get("photos") or []
            if p.get("path") and (root / p["path"]).is_file()]


def _verdict_command(e: dict) -> str:
    if e.get("criteria"):
        own = [v for v in e.get("variants") or [] if v.get("role", "variant") == "variant"]
        g = ";".join(f"{v.get('tab') or v['id']}=" + ",".join(f"{c['key']}:{c['choices'][0]}" for c in e["criteria"])
                     for v in own)
        return f'uv run lab exp verdict {e["id"]} --grade "{g}"'
    if e.get("test_kind") in ("scaled_part", "full_part"):
        return f'uv run lab exp verdict {e["id"]} --accept yes --note "what you see"'
    if len([v for v in e.get("variants") or [] if v.get("role", "variant") == "variant"]) > 1:
        return f'uv run lab exp verdict {e["id"]} --rank "B>A" --strength clearly'
    return f'uv run lab exp verdict {e["id"]} --rank A --note "what you see"'


def _needs(e: dict) -> dict | None:
    """What the owner has to do next for this experiment, or None. Urgency: lower first."""
    s, eid, b = e["status"], e["id"], _last_build(e) or {}
    if s in ("answered", "abandoned"):
        return None
    check = b.get("check") or {}
    why = "; ".join(g["message"] for g in check.get("guards") or [] if not g["ok"] and g["result"] != "info")
    if s == "printing" and not e.get("owner_verdict"):
        return {"id": eid, "urgency": 0, "action": "Judge the print",
                "why": f"Look at: {e.get('judge_on') or 'the face'}. Photos help.", "command": _verdict_command(e)}
    if s == "approved":
        return {"id": eid, "urgency": 1, "action": "Send it to the printer",
                "why": f"Approved; then record that it started.", "command": f"uv run lab exp start {eid}"}
    if s == "needs_approval":
        return {"id": eid, "urgency": 2, "action": "Approve or drop", "why": why or "over a budget or a full part",
                "command": f'uv run lab exp approve {eid} --reason "..."'}
    if s == "ready":
        return {"id": eid, "urgency": 1, "action": "Send it to the printer", "why": "Ready to print.",
                "command": f"uv run lab exp start {eid}"}
    if check.get("status") == "blocked":
        return {"id": eid, "urgency": 3, "action": "Fix the plan", "why": why, "command": f"uv run lab exp check {eid}"}
    if s in ("built", "planned", "build_failed"):
        nxt = "check" if s == "built" else "build"
        return {"id": eid, "urgency": 3, "action": f"Run the {nxt}", "why": f"It's {s.replace('_', ' ')}.",
                "command": f"uv run lab exp {nxt} {eid}"}
    return None


def _experiment(e: dict, exps: dict, root: Path, tol: float, production) -> dict:
    validity = outcome = None
    if e.get("owner_verdict") or e.get("print_runs"):
        validity = comparison_validity(e, exps, tol, production)
        outcome = prediction_outcome(e, validity) if e.get("owner_verdict") else None
    b = _last_build(e) or {}
    v = e.get("owner_verdict")
    return {
        "id": e["id"], "question": e["question"], "status": e["status"], "provenance": e["provenance"],
        "question_text": e["question_text"], "hypothesis": e.get("hypothesis"), "prediction": e.get("prediction"),
        "why_this_test": e.get("why_this_test"), "test_kind": e.get("test_kind"), "judge_on": e.get("judge_on"),
        "factor": {k: (e.get("factor") or {}).get(k) for k in ("name", "unit", "values")},
        "variants": _variants(e), "reference_variants": e.get("reference_variants") or [],
        "estimate": b.get("estimate"), "layer_time_median_s": (b.get("measured") or {}).get("layer_time_median_s"),
        "usage": _usage(e), "check": b.get("check"), "outcome": outcome, "validity": validity,
        "verdict": {k: v.get(k) for k in ("kind", "order", "strength", "good_enough", "grades", "lighting", "note", "at")}
        if v else None, "criteria": e.get("criteria"),
        "run": (e.get("print_runs") or [{}])[-1].get("id"),
        "approval": e.get("approval"), "abandoned_reason": e.get("abandoned_reason"),
        "filament": (e.get("controlled") or {}).get("filament"),
        "runs": [{"id": r["id"], "started_at": r.get("started_at"), "baseline_missing": r.get("baseline_missing") or []}
                 for r in e.get("print_runs") or []],
        "finding": criteria_finding(e) or sweep_finding(e), "photos": _photos(e, root), "ai_observations": e.get("ai_observations") or [], "needs": _needs(e)}


def _question(q: dict, exps: dict, tol: float) -> dict:
    mine = {i: exps[i] for i in q["experiments"] if i in exps}
    s, b = ledger.spent(q, exps), ledger.budget(q)
    nxt = next((e for e in mine.values() if e["status"] in ("built", "ready", "needs_approval", "approved")), None)
    est = (_last_build(nxt) or {}).get("estimate") if nxt else None
    if st := ledger.owner_stopped(q):
        stop = {"kind": "owner", "text": f"stopped by you: {st['reason']}"}
    elif st := ledger.auto_stop(q, exps, tol):
        stop = {"kind": "auto", "text": f"stopped automatically: {st['message']}"}
    else:
        stop = {"kind": None, "text": "continue"}
    counts = {"informative": 0, "uninformative": 0}
    for e in mine.values():
        if e.get("owner_verdict") and e["provenance"] == "prospective":
            o = prediction_outcome(e, comparison_validity(e, exps, tol))
            counts["informative" if o in ("supported", "refuted") else "uninformative"] += 1
    return {"id": q["id"], "question": q["question"], "status": q["status"], "budget": b,
            "spent": {"minutes": round(s["minutes"], 1), "g": round(s["g"], 1)},
            "next": {"id": nxt["id"], "minutes": est["minutes"], "g": est["g"]} if est else None,
            "stop": stop, "streak": ledger.streak(q, exps, tol), "evidence": counts,
            "experiments": q["experiments"], "plans": q.get("plans") or [],
            "answered": sum(1 for e in mine.values() if e["status"] == "answered")}


def build_index(pdir: Path) -> dict:
    paths = ProjectPaths(Path(pdir))
    records, problems = {}, []
    questions = _load_all(paths, paths.questions, "question", records, problems)
    exps = _load_all(paths, paths.experiments, "experiment", records, problems)
    settings = project_settings(paths)
    tol, production = settings["plate_time_tolerance_pct"], settings.get("production_plate")
    experiments = [_experiment(e, exps, paths.root, tol, production)
                   for e in sorted(exps.values(), key=lambda e: e["id"], reverse=True)]
    needs = sorted((x["needs"] for x in experiments if x["needs"]), key=lambda n: (n["urgency"], n["id"]))
    needs = [n for n in needs if n["urgency"] < 3 or n["action"] == "Fix the plan"]
    fingerprint = hashlib.sha256(json.dumps({k: r["sha256"] for k, r in sorted(records.items())}).encode()).hexdigest()
    return {"schema": SCHEMA, "project": paths.name, "generated_at": now(), "fingerprint": fingerprint,
            "questions": [_question(q, exps, tol) for q in sorted(questions.values(), key=lambda q: q["id"], reverse=True)],
            "experiments": experiments, "needs": needs, "records": records, "problems": problems}
