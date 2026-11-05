"""The project as one read-only projection: what `lab sync` pushes to Local AI, whose print lab page draws it.

Every number comes from the loop's own code (ledger, outcome), so the page can't disagree with `lab question status`.
Records that fail validation are listed under `problems` and left out, never guessed at. Each record also travels as
its original payload with its file's sha256, so a receiver can upsert by ID and refuse an older copy.
"""
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

from lab import bambuddy
from lab.qualification import summary as qualification_summary
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


RUN_BOUND = ("printing", "answered")


def _shown_build(e: dict) -> dict | None:
    """The build the page describes. While a print is on the printer or has been judged, that print's own build: a
    rebuild doesn't change what it was (and if that build is gone, none, rather than another one). Otherwise, as
    after a failed run and a rebuild, the newest good build, which is the one waiting for a check or approval."""
    runs = e.get("print_runs") or []
    if e.get("status") in RUN_BOUND and runs and runs[-1].get("build_id"):
        return next((b for b in e.get("builds") or [] if b["id"] == runs[-1]["build_id"]), None)
    return _last_build(e)


def _variants(e: dict) -> list[dict]:
    b = _shown_build(e) or {}
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


def _running(e: dict) -> dict | None:
    """The print run still on the printer: the last one, while the experiment is printing and it has no usage yet."""
    runs = e.get("print_runs") or []
    r = runs[-1] if runs and e["status"] == "printing" else None
    return r if r and not r.get("usage") and not r.get("failed") else None


def _due_at(e: dict) -> str | None:
    """When the running print should be done: its start plus the build's estimate."""
    r = _running(e)
    est = ((_shown_build(e) or {}).get("estimate") or {}).get("minutes")
    if not r or not r.get("started_at") or not est:
        return None
    return (datetime.fromisoformat(r["started_at"]) + timedelta(minutes=float(est))).isoformat(timespec="seconds")


OBSERVED = ("telemetry", "manual", "printer_log", "bambuddy")


def _source(sources: set[str]) -> str:
    return sources.pop() if len(sources) == 1 else "mixed"


def _usage(e: dict) -> dict | None:
    """What the finished runs used, each total labelled: 'observed' when every run's figure was measured or given,
    'estimate' when it fell back to the slicer's estimate, 'scaled_estimate' for a failed run's estimate times how
    far it got, 'none' for a run whose build is gone (counted as 0), and 'mixed' when the runs differ."""
    running = _running(e)
    runs = [r for r in e.get("print_runs") or [] if r is not running]  # an estimate isn't usage until the print ends
    if not runs:
        return None
    builds = {b["id"]: b for b in e.get("builds") or []}
    m = g = 0.0
    m_src, g_src = set(), set()
    for r in runs:
        rm, rg = ledger.run_usage(r, builds.get(r.get("build_id")))
        m, g = m + rm, g + rg
        u = r.get("usage") or {}
        seen_m = u.get("minutes_source", u.get("usage_source")) in OBSERVED  # a kept figure keeps its own source
        seen_g = u.get("g_source", u.get("usage_source")) in OBSERVED
        fallback = ("none" if r.get("build_id") not in builds else
                    "scaled_estimate" if (r.get("failed") or {}).get("at_fraction") is not None else "estimate")
        m_src.add("observed" if seen_m and u.get("actual_minutes") is not None else fallback)
        g_src.add("observed" if seen_g and u.get("actual_g") is not None else fallback)
    return {"minutes": round(m, 1), "g": round(g, 1), "minutes_source": _source(m_src), "g_source": _source(g_src)}


def _reserved(e: dict) -> dict | None:
    """The running print's estimate: spoken for in the budget, not used yet. The question's `spent` already includes
    it (the ledger counts a started run at its estimate), so `reserved` says how much of `spent` that is."""
    r = _running(e)
    b = next((b for b in e.get("builds") or [] if r and b["id"] == r.get("build_id")), None)
    est = (b or {}).get("estimate") or {}
    return {"minutes": est.get("minutes"), "g": est.get("g")} if r and est else None


def _print(r: dict) -> dict | None:
    """The run's Bambuddy print as the page shows it, or None when it isn't linked. Before the snapshot the print is
    still on the printer, so it reads as Printing."""
    b = r.get("bambuddy")
    if not b:
        return None
    return {"id": b.get("print"), "status_word": bambuddy.status_word(b.get("status") or "printing"),
            "minutes": b.get("minutes"), "grams": b.get("grams"), "failed_at_estimate": b.get("failed_at_estimate"),
            "failure_reason": b.get("failure_reason"), "linked": b.get("linked")}


def _photos(e: dict, root: Path) -> list[dict]:
    return [{"run": r["id"], "path": p["path"], "sha256": p.get("sha256") or _sha(root / p["path"]), "source": p.get("source"),
             "captured_at": p.get("captured_at")}
            for r in e.get("print_runs") or [] for p in r.get("photos") or []
            if p.get("path") and (root / p["path"]).is_file()]


def _verdict_command(e: dict) -> str:
    if e.get("criteria"):
        own = [v for v in e.get("variants") or [] if v.get("role", "variant") == "variant"]
        # Every answer is a list of the choices, which the command refuses: copied unedited it records nothing.
        g = ";".join(f"{v.get('tab') or v['id']}=" + ",".join(f"{c['key']}:{'|'.join(c['choices'])}"
                                                            for c in e["criteria"]) for v in own)
        return f'uv run lab exp verdict {e["id"]} --grade "{g}" --lighting "diagnostic|room"'
    if e.get("test_kind") in ("scaled_part", "full_part"):
        return f'uv run lab exp verdict {e["id"]} --accept "yes|no" --note "what you see"'
    if len([v for v in e.get("variants") or [] if v.get("role", "variant") == "variant"]) > 1:
        return (f'uv run lab exp verdict {e["id"]} --rank "B>A|A>B|A=B" --strength "slightly|clearly|a lot" '
                '--lighting "diagnostic|room"')
    return f'uv run lab exp verdict {e["id"]} --rank A --note "what you see" --lighting "diagnostic|room"'


def _clock(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone().strftime("%H:%M")


def _needs(e: dict, at: str, root: Path | None = None) -> dict | None:
    """What the owner has to do next for this experiment, or None. Urgency: lower first. With root, a build waiting
    on the owner is checked against its frozen files first: approving or sending one whose files are gone or changed
    would only be refused."""
    s, eid, b = e["status"], e["id"], _last_build(e) or {}
    if s in ("answered", "abandoned"):
        return None
    # Only a build that records its files: a migrated one without them is lab exp check's to explain.
    if root is not None and (b.get("artifact") or b.get("sliced")) and s in ("needs_approval", "approved", "ready"):
        from lab.loop.verify import build_integrity_problems
        lost = build_integrity_problems(ProjectPaths(root), b)
        if lost:
            return {"id": eid, "urgency": 2, "action": "Restore the build files",
                    "why": "; ".join(lost) + ". If it was built in another checkout, copy the files from there "
                           "(the digests must match); otherwise rebuild.",
                    "command": f"uv run lab exp build {eid} --replace"}
    check = b.get("check") or {}
    why = "; ".join(g["message"] for g in check.get("guards") or [] if not g["ok"] and g["result"] != "info")
    if s == "printing" and not e.get("owner_verdict"):
        look, due = f"look at: {e.get('judge_on') or 'the face'}. Photos help.", _due_at(e)
        early = due and datetime.fromisoformat(at) < datetime.fromisoformat(due)
        why = f"Printing until about {_clock(due)} (estimate). Then {look}" if early else look[0].upper() + look[1:]
        return {"id": eid, "urgency": 0, "action": "Judge the print", "why": why, "due_at": due,
                "command": _verdict_command(e)}
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


def _experiment(e: dict, exps: dict, root: Path, tol: float, production, at: str) -> dict:
    validity = outcome = None
    if e.get("owner_verdict") or e.get("print_runs"):
        validity = comparison_validity(e, exps, tol, production)
        outcome = prediction_outcome(e, validity) if e.get("owner_verdict") else None
    b = _shown_build(e) or {}
    v = e.get("owner_verdict")
    return {
        "id": e["id"], "question": e["question"], "status": e["status"], "provenance": e["provenance"],
        "question_text": e["question_text"], "hypothesis": e.get("hypothesis"), "prediction": e.get("prediction"),
        "why_this_test": e.get("why_this_test"), "test_kind": e.get("test_kind"), "judge_on": e.get("judge_on"),
        "factor": {k: (e.get("factor") or {}).get(k) for k in ("name", "unit", "values")},
        "variants": _variants(e), "reference_variants": e.get("reference_variants") or [],
        "estimate": b.get("estimate"), "layer_time_median_s": (b.get("measured") or {}).get("layer_time_median_s"),
        "usage": _usage(e), "reserved": _reserved(e), "shown_build": b.get("id"), "check": b.get("check"), "outcome": outcome, "validity": validity,
        "verdict": {**{k: v.get(k) for k in ("kind", "order", "strength", "good_enough", "grades", "lighting", "note",
                                             "at")}, "defects": v.get("blocking_defects") or []} if v else None, "criteria": e.get("criteria"),
        "run": (e.get("print_runs") or [{}])[-1].get("id"),
        "approval": e.get("approval"), "abandoned_reason": e.get("abandoned_reason"),
        "filament": (e.get("controlled") or {}).get("filament"),
        "runs": [{"id": r["id"], "started_at": r.get("started_at"), "baseline_missing": r.get("baseline_missing") or [],
                  "print": _print(r), "entered_on_mac": (r.get("usage") or {}).get("usage_source") == "manual"}
                 for r in e.get("print_runs") or []],
        **_finding(e, root), "photos": _photos(e, root), "ai_observations": e.get("ai_observations") or [], "due_at": _due_at(e), "needs": _needs(e, at, root)}


def _finding(e: dict, root: Path) -> dict:
    """Observations win over the verdict for the variants they cover (spec rev 2, 'Which record wins'); the verdict's
    finding is kept, marked legacy, for variants nobody has observed, and a sweep's finding (a prediction-side result)
    is always kept."""
    from lab.records import observations as obs
    recs = obs.for_experiment(ProjectPaths(root), e["id"])
    covered = {obs.latest(r)["subject"].get("variant") for r in recs}
    v = e.get("owner_verdict") or {}
    legacy = None
    if v.get("kind") == "criteria":
        left = {k: g for k, g in (v.get("grades") or {}).items() if k not in covered}
        legacy = criteria_finding({**e, "owner_verdict": {**v, "grades": left}}) if left else None
    sweep = sweep_finding(e)
    observed = obs.finding(recs) if recs else None
    parts = [x for x in (observed, legacy and f"{legacy} (from the old verdict, not re-checked)", sweep) if x]
    source = ("mixed" if observed and legacy else "observations" if observed else
              "legacy_verdict" if legacy or sweep else None)
    return {"finding": " ".join(parts) or None, "finding_source": source,
            "observations": [{"id": r["id"], "rev": obs.latest(r)["rev"], "group": obs.latest(r)["subject"].get("group"),
                              "subject": obs.latest(r)["subject"], "outcomes": obs.latest(r)["outcomes"],
                              "source": obs.latest(r)["source"]["kind"], "light": obs.latest(r)["viewing"]["light"]}
                             for r in recs]}


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
    rm = rg = 0.0
    for e in mine.values():
        r = _reserved(e) or {}
        rm, rg = rm + float(r.get("minutes") or 0), rg + float(r.get("g") or 0)
    return {"id": q["id"], "question": q["question"], "status": q["status"], "budget": b,
            "spent": {"minutes": round(s["minutes"], 1), "g": round(s["g"], 1)},
            "reserved": {"minutes": round(rm, 1), "g": round(rg, 1)},  # the part of `spent` still printing
            "next": {"id": nxt["id"], "minutes": est["minutes"], "g": est["g"]} if est else None,
            "stop": stop, "streak": ledger.streak(q, exps, tol), "evidence": counts,
            "experiments": q["experiments"], "plans": q.get("plans") or [],
            "answered": sum(1 for e in mine.values() if e["status"] == "answered")}


def build_index(pdir: Path, at: str | None = None) -> dict:
    at = at or now()
    paths = ProjectPaths(Path(pdir))
    records, problems = {}, []
    questions = _load_all(paths, paths.questions, "question", records, problems)
    exps = _load_all(paths, paths.experiments, "experiment", records, problems)
    settings = project_settings(paths)
    tol, production = settings["plate_time_tolerance_pct"], settings.get("production_plate")
    experiments = [_experiment(e, exps, paths.root, tol, production, at)
                   for e in sorted(exps.values(), key=lambda e: e["id"], reverse=True)]
    needs = sorted((x["needs"] for x in experiments if x["needs"]), key=lambda n: (n["urgency"], n["id"]))
    needs = [n for n in needs if n["urgency"] < 3 or n["action"] == "Fix the plan"]
    qualification = qualification_summary(paths)
    fingerprint_material = {
        "records": {k: r["sha256"] for k, r in sorted(records.items())},
        "qualification": qualification,
    }
    fingerprint = hashlib.sha256(json.dumps(fingerprint_material, sort_keys=True).encode()).hexdigest()
    return {"schema": SCHEMA, "project": paths.name, "generated_at": at, "fingerprint": fingerprint,
            "questions": [_question(q, exps, tol) for q in sorted(questions.values(), key=lambda q: q["id"], reverse=True)],
            "experiments": experiments, "needs": needs, "qualification": qualification,
            "records": records, "problems": problems}
