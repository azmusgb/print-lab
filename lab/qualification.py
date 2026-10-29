"""Canonical qualification decisions for Print Lab.

The Mac owns this state. Pi Hub may request a decision, but this module re-checks
the experiment against the canonical records before recording anything.

Qualification is project-level metadata stored atomically in project.json:
- history is append-only in meaning (records are never rewritten);
- current_reference changes only for a successful "qualified" decision;
- rejected/continue decisions are retained without altering the current reference.
"""
from __future__ import annotations

import re
from typing import Optional

from lab.loop.commands import all_experiments, load_experiment
from lab.loop.outcome import comparison_validity
from lab.records import observations as obs
from lab.records.project import ProjectPaths, project_settings
from lab.records.store import atomic_write_json, now, read_json, record_lock

SCHEMA = "print-lab-qualification/1"
DECISIONS = ("qualified", "continue", "rejected")
MAX_REASON = 500
QUAL_ID_RE = re.compile(r"^QUAL-(\d{4,})$")


def _project_doc(paths: ProjectPaths) -> dict:
    if not paths.project_json.exists():
        return {}
    got = read_json(paths.project_json)
    if not isinstance(got, dict):
        raise ValueError("project.json must contain an object.")
    return got


def _state_from_doc(doc: dict) -> dict:
    raw = doc.get("qualification")
    if not isinstance(raw, dict):
        return {
            "schema": SCHEMA,
            "current_reference": None,
            "current": None,
            "history": [],
        }
    history = raw.get("history")
    return {
        "schema": SCHEMA,
        "current_reference": raw.get("current_reference") if isinstance(raw.get("current_reference"), str) else None,
        "current": raw.get("current") if isinstance(raw.get("current"), dict) else None,
        "history": [x for x in history if isinstance(x, dict)] if isinstance(history, list) else [],
    }


def summary(paths: ProjectPaths) -> dict:
    """The qualification projection included in page_index and sync fingerprint."""
    return _state_from_doc(_project_doc(paths))


def _next_id(history: list[dict]) -> str:
    nums = []
    for item in history:
        m = QUAL_ID_RE.fullmatch(str(item.get("id") or ""))
        if m:
            nums.append(int(m.group(1)))
    return f"QUAL-{(max(nums) + 1 if nums else 1):04d}"


def _latest_run(e: dict) -> dict | None:
    runs = e.get("print_runs") or []
    return runs[-1] if runs else None


def _build_for_run(e: dict, run: dict | None) -> dict | None:
    if not run or not run.get("build_id"):
        return None
    return next((b for b in e.get("builds") or [] if b.get("id") == run["build_id"]), None)


def _reference_ids(e: dict) -> set[str]:
    out = set()
    for token in e.get("reference_variants") or []:
        if isinstance(token, str) and re.fullmatch(r"E-\d+-[^-]+", token):
            out.add(token.rsplit("-", 1)[0])
    return out


def _blocked_build(build: dict | None) -> bool:
    check = (build or {}).get("check") or {}
    if check.get("status") == "blocked":
        return True
    return any(
        isinstance(g, dict) and not g.get("ok") and g.get("result") == "blocked"
        for g in (check.get("guards") or [])
    )


def gate(paths: ProjectPaths, eid: str, reference_experiment: str, *,
         evidence_reviewed: bool) -> dict:
    """Return the authoritative qualification gate without mutating anything."""
    e = load_experiment(paths, eid)
    exps = all_experiments(paths)
    settings = project_settings(paths)
    run = _latest_run(e)
    build = _build_for_run(e, run)
    verdict = e.get("owner_verdict") or {}
    problems: list[dict] = []

    def problem(code: str, message: str) -> None:
        problems.append({"code": code, "message": message})

    if e.get("status") != "answered":
        problem("not_answered", "The experiment must be answered before it can become a production reference.")

    if e.get("test_kind") not in ("full_part", "scaled_part"):
        problem("not_part", "Only a full-part or scaled-part experiment can become a production reference.")

    if not verdict:
        problem("no_verdict", "Record a verdict first.")
    elif verdict.get("kind") != "acceptance" or verdict.get("good_enough") is not True:
        problem("not_accepted", "The owner verdict must explicitly say this part is good enough.")

    if not run:
        problem("no_run", "The experiment has no print run.")
    elif run.get("failed"):
        problem("failed_run", "The latest print run failed and cannot be qualified.")

    if not build:
        problem("no_build", "The printed build cannot be resolved.")
    elif _blocked_build(build):
        problem("blocked_build", "The printed build has a blocked guard.")

    observations = obs.for_experiment(paths, eid)
    if not observations:
        problem("no_observation", "Record what happened before qualification.")

    if not evidence_reviewed:
        problem("evidence_not_reviewed", "Review the evidence comparison before qualification.")

    if not reference_experiment or reference_experiment == eid:
        problem("bad_reference", "Qualification needs a different reference experiment.")
    elif reference_experiment not in exps:
        problem("reference_missing", f"{reference_experiment} is not an experiment in this project.")
    elif reference_experiment not in _reference_ids(e):
        problem(
            "reference_not_bound",
            f"{reference_experiment} is not one of {eid}'s declared reference experiments.",
        )

    validity = comparison_validity(
        e,
        exps,
        settings["plate_time_tolerance_pct"],
        settings.get("production_plate"),
    )
    if validity.get("status") != "valid":
        problem(
            "comparison_not_valid",
            f"The comparison is {validity.get('status') or 'unknown'}; resolve its validity before qualification.",
        )

    return {
        "ok": not problems,
        "experiment": eid,
        "reference_experiment": reference_experiment,
        "run": run.get("id") if run else None,
        "build": build.get("id") if build else None,
        "validity": validity,
        "observations": len(observations),
        "problems": problems,
    }


def _validate_payload(payload: dict) -> tuple[str, str, str, str, str, bool]:
    if not isinstance(payload, dict):
        raise ValueError("Qualification payload must be an object.")

    decision = payload.get("decision")
    if decision not in DECISIONS:
        raise ValueError("decision must be qualified, continue, or rejected.")

    reason = payload.get("reason")
    reason = reason.strip() if isinstance(reason, str) else ""
    if not reason:
        raise ValueError("A qualification decision needs a reason.")
    if len(reason) > MAX_REASON:
        raise ValueError(f"Keep the qualification reason to {MAX_REASON} characters.")

    reference = payload.get("reference_experiment")
    if not isinstance(reference, str) or not re.fullmatch(r"E-\d{3,}", reference):
        raise ValueError("reference_experiment must look like E-019.")

    run_seen = payload.get("run_seen")
    if not isinstance(run_seen, str) or not re.fullmatch(r"PR-\d{3,}-\d{2,}", run_seen):
        raise ValueError("run_seen must look like PR-023-01.")

    build_seen = payload.get("build_seen")
    if not isinstance(build_seen, str) or not re.fullmatch(r"BLD-\d{3,}-\d{2,}", build_seen):
        raise ValueError("build_seen must look like BLD-023-01.")

    evidence_reviewed = payload.get("evidence_reviewed")
    if evidence_reviewed is not True:
        raise ValueError("evidence_reviewed must be true.")

    return decision, reason, reference, run_seen, build_seen, evidence_reviewed


def apply_request(paths: ProjectPaths, eid: str, payload: dict, *,
                  request_id: Optional[str] = None) -> dict:
    """Apply one Pi/phone qualification decision under canonical record locks."""
    decision, reason, reference, run_seen, build_seen, evidence_reviewed = _validate_payload(payload)

    with record_lock(paths.locks, eid, f"lab qualify {eid}"):
        e = load_experiment(paths, eid)
        run = _latest_run(e)
        build = _build_for_run(e, run)

        current_run = run.get("id") if run else None
        current_build = build.get("id") if build else None
        if current_run != run_seen or current_build != build_seen:
            raise ValueError(
                f"{eid} changed since the evidence was reviewed "
                f"(run {current_run or 'none'}, build {current_build or 'none'}); reload and review it again."
            )

        gate_result = gate(paths, eid, reference, evidence_reviewed=evidence_reviewed)
        if decision == "qualified" and not gate_result["ok"]:
            raise ValueError(
                "Cannot qualify: " + "; ".join(p["message"] for p in gate_result["problems"])
            )

        if reference not in all_experiments(paths) or reference == eid:
            raise ValueError("The reviewed reference experiment is no longer available.")
        if reference not in _reference_ids(e):
            raise ValueError(f"{reference} is no longer a declared reference of {eid}.")

        with record_lock(paths.locks, "qualification", f"lab qualify {eid}"):
            doc = _project_doc(paths)
            state = _state_from_doc(doc)
            history = list(state["history"])
            previous = state.get("current_reference") or reference

            rec = {
                "schema": SCHEMA,
                "id": _next_id(history),
                "experiment": eid,
                "decision": decision,
                "reason": reason,
                "reference_experiment": reference,
                "previous_reference": previous,
                "run": run_seen,
                "build": build_seen,
                "evidence_reviewed": True,
                "validity": gate_result.get("validity"),
                "at": now(),
                "by": "owner",
                "request_id": request_id,
            }
            history.append(rec)

            next_state = {
                "schema": SCHEMA,
                "current_reference": state.get("current_reference"),
                "current": state.get("current"),
                "history": history,
            }
            if decision == "qualified":
                next_state["current_reference"] = eid
                next_state["current"] = rec

            doc["qualification"] = next_state
            atomic_write_json(paths.project_json, doc)
            return rec


def message(record: dict) -> str:
    decision = record.get("decision")
    eid = record.get("experiment")
    if decision == "qualified":
        return f"{eid} qualified as the production reference."
    if decision == "rejected":
        return f"{eid} rejected for qualification."
    return f"{eid} kept in testing."
