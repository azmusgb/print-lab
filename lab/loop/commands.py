"""What the experiment-loop commands do, apart from argument parsing (spec: Commands). Every mutation takes the
record's lock, re-reads it, validates and writes it atomically."""
import re

from lab.loop import ledger
from lab.loop.outcome import comparison_validity, prediction_outcome
from lab.records.project import ProjectPaths, project_settings
from lab.records.schema import load, validate
from lab.records.store import atomic_write_json, now, record_lock

STRENGTHS = ("slightly", "clearly", "a lot")


def all_experiments(paths: ProjectPaths) -> dict[str, dict]:
    return {p.stem: load(p, "experiment") for p in sorted(paths.experiments.glob("E-*.json"))}


def load_experiment(paths: ProjectPaths, eid: str) -> dict:
    p = paths.experiments / f"{eid}.json"
    if not p.exists():
        ids = ", ".join(sorted(x.stem for x in paths.experiments.glob("E-*.json"))) or "none yet"
        raise ValueError(f"{eid} isn't in {paths.name}. Experiments: {ids}")
    return load(p, "experiment")


def load_question(paths: ProjectPaths, qid: str) -> dict:
    p = paths.questions / f"{qid}.json"
    if not p.exists():
        ids = ", ".join(sorted(x.stem for x in paths.questions.glob("Q-*.json"))) or "none yet"
        raise ValueError(f"{qid} isn't in {paths.name}. Questions: {ids}")
    return load(p, "question")


def save_experiment(paths: ProjectPaths, e: dict) -> dict:
    path = paths.experiments / f"{e['id']}.json"
    validate(e, "experiment", path)
    atomic_write_json(path, e)
    return e


def refresh_derived(paths: ProjectPaths, e: dict, exps: dict | None = None) -> dict:
    """Recompute the cached comparison validity and prediction outcome (never authoritative)."""
    exps = dict(exps or all_experiments(paths))
    exps[e["id"]] = e
    s = project_settings(paths)
    e["comparison_validity"] = comparison_validity(e, exps, s["plate_time_tolerance_pct"], s.get("production_plate"))
    e["prediction_outcome"] = prediction_outcome(e, e["comparison_validity"])
    return e


def strip_start(e: dict) -> float | None:
    """The model height where the strip begins: from the build spec, else from 'Z60-72' in the plate's names."""
    spec = e.get("build_spec") or {}
    if spec.get("z"):
        return float(spec["z"][0])
    for b in reversed(e.get("builds") or []):
        for name in ((b.get("plate") or {}).get("objects") or []):
            if m := re.search(r"Z(\d+(?:\.\d+)?)-", name, re.I):
                return float(m.group(1))
    return None


def _variant_names(e: dict) -> str:
    own = [f"{v['id']} ({v['tab']})" if v.get("tab") else v["id"] for v in e["variants"]]
    return ", ".join(own + list(e.get("reference_variants") or []))


def resolve_variant(e: dict, token: str) -> str:
    """A variant by letter (A), tab (4A) or full ID, or a listed reference variant from another experiment."""
    t = token.strip()
    for v in e["variants"]:
        if t in (v["id"], v.get("tab")) or (len(t) == 1 and v["id"].endswith(f"-{t}")):
            return v["id"]
    if t in (e.get("reference_variants") or []):
        return t
    raise ValueError(f"'{t}' isn't a variant of {e['id']}. Use one of: {_variant_names(e)}"
                     + ("" if re.match(r"E-\d+-", t) is None else
                        f". A variant from another experiment must be listed in {e['id']}'s reference_variants."))


def parse_rank(e: dict, rank: str) -> list[list[str]]:
    """'B>A', 'B>A=C', '4B>E-002-A': best first; '=' puts variants in one group (no meaningful difference)."""
    return [[resolve_variant(e, t) for t in group.split("=")] for group in rank.split(">")]


def record_verdict(paths: ProjectPaths, eid: str, *, rank, strength, inconclusive, accept, defects, marks, witness,
                   witness_override, anchors, not_about_target, note, replace, runs) -> dict:
    with record_lock(paths.locks, eid, f"lab exp verdict {eid}"):
        e = load_experiment(paths, eid)
        if not e.get("print_runs"):
            raise ValueError(f"{eid} has no print yet; start it first (`lab exp start {eid}`).")
        if e.get("owner_verdict") and not replace:
            raise ValueError(f"{eid} already has a verdict. Use --replace to change it; the old one is kept.")
        run_ids = runs or [e["print_runs"][-1]["id"]]
        for r in run_ids:
            if r not in {x["id"] for x in e["print_runs"]}:
                raise ValueError(f"{r} isn't a print run of {eid}: {', '.join(x['id'] for x in e['print_runs'])}")
        base = {"print_runs": run_ids, "note": note, "by": "owner", "at": now()}
        if inconclusive:
            v = {"kind": "inconclusive", "reason": inconclusive, **base}
        elif accept is not None:
            if e["test_kind"] not in ("scaled_part", "full_part"):
                raise ValueError(f"{eid} is a {e['test_kind']}; the good-enough verdict is for full or scaled parts. "
                                 "Rank the variants instead (--rank).")
            v = {"kind": "acceptance", "good_enough": bool(accept), "blocking_defects": list(defects),
                 "lighting": "installed", **base}
        else:
            if not rank:
                raise ValueError("Give a ranking (--rank 'B>A', or 'A=B' for no meaningful difference), "
                                 "--inconclusive, or --accept.")
            order = parse_rank(e, rank)
            if len(order) > 1 and strength not in STRENGTHS:
                raise ValueError("A difference needs a strength: --strength slightly, clearly or 'a lot'.")
            ctrl = e.get("controls") or {}
            if ctrl.get("witness_required") and not witness:
                raise ValueError(f"{eid} has a witness wall; say how it looks: --witness normal, abnormal or "
                                 "inconclusive.")
            z0 = strip_start(e)
            mk = []
            for m in marks:
                tok, _, mm = m.partition(":")
                mz = float(mm)
                mk.append({"variant": resolve_variant(e, tok), "mark_z_mm": mz,
                           "defect_z_mm": round(z0 + mz, 2) if z0 is not None else None})
            v = {"kind": "ranking", "order": order, "strength": strength if len(order) > 1 else None,
                 "about_target": not not_about_target, "lighting": "diagnostic", "marks": mk,
                 "witness": {"id": "WITNESS-01", "condition": witness, "note": None} if witness else None,
                 "witness_override": witness_override, **base}
        if e.get("owner_verdict"):
            e.setdefault("superseded_verdicts", []).append(e["owner_verdict"])
        e["owner_verdict"] = v
        e["anchors"] = [_anchor(a) for a in anchors] or e.get("anchors", [])
        e["status"] = "answered"
        return save_experiment(paths, refresh_derived(paths, e))


def _anchor(text: str) -> dict:
    """'E-005-ANCHOR=E-002-A:same[:clearly]'"""
    ids, _, rest = text.partition(":")
    aid, _, to = ids.partition("=")
    cond, _, strength = rest.partition(":")
    return {"id": aid, "compared_to": to, "condition": cond, "strength": strength or None, "note": None}


def find_run(paths: ProjectPaths, run_id: str) -> tuple[dict, dict]:
    runs = []
    for e in all_experiments(paths).values():
        for r in e.get("print_runs") or []:
            if r["id"] == run_id:
                return e, r
            runs.append(r["id"])
    raise ValueError(f"{run_id} isn't a print run in {paths.name}. Print runs: {', '.join(runs) or 'none yet'}")


def record_usage(paths: ProjectPaths, run_id: str, *, failed_at_pct, minutes, grams) -> dict:
    if failed_at_pct is not None and not 1 <= failed_at_pct <= 99:
        raise ValueError("--failed-at is how far a failed print got, 1–99 %. For a print that finished, give "
                         "--minutes and --grams.")
    e, _ = find_run(paths, run_id)
    with record_lock(paths.locks, e["id"], f"lab exp usage {run_id}"):
        e = load_experiment(paths, e["id"])
        run = next(r for r in e["print_runs"] if r["id"] == run_id)
        if failed_at_pct is not None:
            run["failed"] = {"at_fraction": round(failed_at_pct / 100, 3), "note": None}
            if e["status"] == "printing":
                e["status"] = "built"  # the next attempt is checked again
        if minutes is not None or grams is not None:
            run["usage"] = {"actual_minutes": float(minutes) if minutes is not None else None,
                            "actual_g": float(grams) if grams is not None else None, "usage_source": "manual",
                            "completion_fraction": run.get("failed", {}).get("at_fraction") if run.get("failed") else None}
        return save_experiment(paths, e)


def _n(x: float) -> str:
    return f"{x:.1f}".rstrip("0").rstrip(".")


def question_status(paths: ProjectPaths, qid: str) -> str:
    q = load_question(paths, qid)
    exps = all_experiments(paths)
    tol = project_settings(paths)["plate_time_tolerance_pct"]
    s, b = ledger.spent(q, exps), ledger.budget(q)
    lines = [f"{q['id']} — {q['question']}", "", "Budget",
             f"  Time       {_n(s['minutes'])} / {_n(b['minutes'])} min",
             f"  Material   {_n(s['g'])} / {_n(b['g'])} g"]
    nxt = next((exps[x] for x in q["experiments"] if x in exps and exps[x]["status"] in
                ("built", "ready", "needs_approval", "approved")), None)
    if nxt and nxt.get("builds") and (est := nxt["builds"][-1].get("estimate")):
        lines.append(f"  After {nxt['id']}  {_n(s['minutes'] + est['minutes'])} min, {_n(s['g'] + est['g'])} g")
    lines += ["", "Experiments"]
    counts = {"informative": 0, "uninformative": 0}
    for eid in q["experiments"]:
        e = exps.get(eid)
        if not e:
            lines.append(f"  {eid}   missing")
            continue
        o = prediction_outcome(e, comparison_validity(e, exps, tol)) if e.get("owner_verdict") else None
        if o and e["provenance"] == "prospective":
            counts["informative" if o in ("supported", "refuted") else "uninformative"] += 1
        lines.append(f"  {eid}   {e['status']:<15} {o or '-':<13} {e['provenance']:<12} {e['question_text'][:60]}")
    lines += ["", "Evidence", f"  {counts['informative']} informative, {counts['uninformative']} uninformative "
                              "(prospective experiments only)", "", "Stop state"]
    if st := ledger.owner_stopped(q):
        lines.append(f"  stopped by you: {st['reason']} (resume with `lab question resume {qid}`)")
    elif st := ledger.auto_stop(q, exps, tol):
        lines.append(f"  stopped automatically: {st['message']}")
    else:
        lines.append("  continue")
    answered = [x for x in q["experiments"] if exps.get(x, {}).get("status") == "answered"]
    plans = [p for p in q.get("plans") or [] if not answered or p.get("after") in (answered[-1], None)]
    lines += ["", "Next"]
    if nxt:
        lines.append(f"  {nxt['id']} is {nxt['status'].replace('_', ' ')}")
    for p in plans:
        lines.append(f"  {p['id']}: if {p['if']}, then {p['next']}")
    if not nxt and not plans:
        lines.append("  plan the next experiment (`lab exp plan`)")
    return "\n".join(lines)


def new_question(paths: ProjectPaths, text: str, budget: dict) -> str:
    from lab.records.store import create_record
    for p in paths.questions.glob("Q-*.json"):
        q = load(p, "question")
        if q["status"] == "active" and q["question"].strip().lower() == text.strip().lower():
            raise ValueError(f"{q['id']} already open with that question.")
    s = project_settings(paths)
    b = dict(s["budget"])
    if budget.get("minutes") is not None:
        b["max_minutes"] = budget["minutes"]
    if budget.get("g") is not None:
        b["max_g"] = budget["g"]

    def make(qid):
        return {"schema": 1, "record_type": "question", "id": qid, "project": paths.name, "question": text,
                "status": "active", "autonomy_level": s["autonomy_level"], "budget": b, "experiments": [],
                "plans": [], "stops": []}
    qid, _ = create_record(paths.locks, paths.questions, "Q", make,
                           validate=lambda r: validate(r, "question", paths.questions / f"{r['id']}.json"))
    return qid


def _save_question(paths: ProjectPaths, q: dict) -> dict:
    path = paths.questions / f"{q['id']}.json"
    atomic_write_json(path, validate(q, "question", path))
    return q


def stop_question(paths: ProjectPaths, qid: str, reason: str) -> dict:
    with record_lock(paths.locks, qid, f"lab question stop {qid}"):
        q = load_question(paths, qid)
        if ledger.owner_stopped(q):
            raise ValueError(f"{qid} is already stopped: {ledger.owner_stopped(q)['reason']}")
        q["stops"].append({"reason": reason, "at": now(), "resumed_at": None, "resume": None, "auto_code": None})
        return _save_question(paths, q)


def resume_question(paths: ProjectPaths, qid: str, add: dict | None, reason: str) -> dict:
    exps = all_experiments(paths)
    tol = project_settings(paths)["plate_time_tolerance_pct"]
    with record_lock(paths.locks, qid, f"lab question resume {qid}"):
        q = load_question(paths, qid)
        resume = {"added": {"minutes": (add or {}).get("minutes"), "g": (add or {}).get("g")}, "reason": reason}
        if st := ledger.owner_stopped(q):
            st.update(resumed_at=now(), resume=resume)
        elif auto := ledger.auto_stop(q, exps, tol):
            t = now()
            q["stops"].append({"reason": "auto", "auto_code": auto["code"], "at": t, "resumed_at": t,
                               "resume": resume})
        else:
            raise ValueError(f"{qid} isn't stopped; nothing to resume.")
        return _save_question(paths, q)


def rebuild_question(paths: ProjectPaths, qid: str) -> list[str]:
    """Validate everything first; any problem means a full report and no writes. Otherwise refresh the cached
    outcomes and validity, and report orphaned print files and unattached experiments."""
    from lab.records.store import RecordError
    problems, exps = [], {}
    try:
        q = load_question(paths, qid)
    except (RecordError, ValueError) as err:
        return [f"{qid}: {err}", "No derived state updated."]
    for p in sorted(paths.experiments.glob("E-*.json")):
        try:
            exps[p.stem] = load(p, "experiment")
        except RecordError as err:
            problems.append(f"{p.stem}: {err}")
    for eid in q["experiments"]:
        if eid not in exps and not any(x.startswith(f"{eid}:") for x in problems):
            problems.append(f"{eid}: listed in {qid} but its file is missing")
    if problems:
        return [f"{qid} rebuild: {len(problems)} problem(s)", *problems, "No derived state updated."]
    report = [f"{qid} rebuild"]
    for eid in q["experiments"]:
        e = exps[eid]
        before = (e.get("prediction_outcome"), e.get("comparison_validity"))
        refresh_derived(paths, e, exps)
        if (e["prediction_outcome"], e["comparison_validity"]) != before:
            save_experiment(paths, e)
            report.append(f"{eid}: outcome {e['prediction_outcome'] or '-'}, comparison "
                          f"{e['comparison_validity']['status']} (updated)")
        else:
            report.append(f"{eid}: unchanged")
    for eid, e in exps.items():
        if e["question"] == qid and eid not in q["experiments"]:
            report.append(f"{eid}: unattached (names {qid} but isn't in its list)")
    used = {b.get("artifact") for e in exps.values() for b in e.get("builds") or []}
    used |= {f"prints/{r['file']}" for e in exps.values() for r in ((e.get("legacy") or {}).get("print_runs") or [])}
    for f in sorted(paths.prints.glob("*.3mf")) if paths.prints.exists() else []:
        if f"prints/{f.name}" not in used:
            report.append(f"orphaned print file: prints/{f.name}")
    return report


def abandon(paths: ProjectPaths, eid: str, reason: str) -> dict:
    with record_lock(paths.locks, eid, f"lab exp abandon {eid}"):
        e = load_experiment(paths, eid)
        e.update(status="abandoned", abandoned_reason=reason)
        return save_experiment(paths, e)


def observe(paths: ProjectPaths, eid: str, observation: dict) -> dict:
    """An AI observation: kept apart from the owner's verdict and never read by outcomes, stops or budgets."""
    with record_lock(paths.locks, eid, f"lab exp observe {eid}"):
        e = load_experiment(paths, eid)
        e.setdefault("ai_observations", []).append({**observation, "confirmed": False, "at": now()})
        return save_experiment(paths, e)
