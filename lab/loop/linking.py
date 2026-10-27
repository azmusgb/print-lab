"""Bambuddy prints linked to lab print runs (spec: one print, print-lab). A print named like
`hex-tile_E-023_BLD-023-01` attaches to that build's newest run without a link, or opens a run when there is none; a
print sent without telling the lab is still caught. When the print ends, the run keeps a small evidence snapshot of
it under `bambuddy`, each fact marked with its print, so the evidence outlives an archive purge in Bambuddy."""
from collections.abc import Callable

from lab import bambuddy
from lab.loop.commands import all_experiments, find_run, load_experiment, refresh_derived, save_experiment
from lab.records.project import ProjectPaths
from lab.records.store import next_local_id, now, record_lock

ENDED = ("completed", "failed", "cancelled")
REPLACEABLE = (None, "telemetry", "finished_unknown")  # a figure Bambuddy's own measurement is better than


def _iso(s: str | None) -> str | None:
    """Bambuddy's naive-UTC timestamp as the lab writes times: aware UTC, to the second."""
    t = bambuddy.parse_time(s)
    return t.isoformat(timespec="seconds") if t else None


def _mark(print_id: int) -> str:
    return f"bambuddy print #{print_id}"


def failed_at_estimate(duration_s, planned_s) -> float | None:
    """How far a failed print got: its time over the archive's planned time, clamped 0-1. Only an estimate (a slow
    first layer reads as less progress); None when either time is missing."""
    if duration_s is None or not planned_s:
        return None
    return round(min(max(float(duration_s) / float(planned_s), 0.0), 1.0), 3)


def _link(entry: dict, how: str) -> dict:
    return {"print": entry["id"], "archive": entry.get("archive_id"), "linked": how, "at": now(),
            "status": entry.get("status"), "started": _iso(entry.get("started_at")), "ended": None, "minutes": None,
            "grams": None, "failure_reason": None, "failed_at_estimate": None, "snapshot_at": None}


def _attach(e: dict, build_id: str, entry: dict, how: str) -> tuple[dict, str, str | None]:
    """Link `entry` to the build's newest run without a link, or open a run for it: (run, "linked" | "created",
    message). Opening a run checks nothing and leaves the experiment's status alone: the print already happened."""
    open_runs = [r for r in e["print_runs"] if r.get("build_id") == build_id and not r.get("bambuddy")]
    if open_runs:
        run = open_runs[-1]
        run["bambuddy"] = _link(entry, how)
        msg = None
        if len(open_runs) > 1:
            msg = (f"{build_id} has {len(open_runs)} runs without a print ({', '.join(r['id'] for r in open_runs)}); "
                   f"{_mark(entry['id'])} went to the newest, {run['id']}.")
        return run, "linked", msg
    run = {"id": next_local_id(e, "print_runs", f"PR-{e['id'][2:]}"), "build_id": build_id,
           "started_at": _iso(entry.get("started_at")) or now(), "setup": None, "baseline_missing": [],
           "usage": None, "failed": None, "photos": [], "bambuddy": _link(entry, how)}
    e["print_runs"].append(run)
    return run, "created", f"{_mark(entry['id'])} had no run on {build_id}; opened {run['id']}."


def _snapshot(e: dict, run: dict, entry: dict, planned_seconds: Callable[[int], float | None]) -> bool:
    """Write the evidence once the print has ended; False when it hasn't, or already was. A usage figure the owner
    (or the printer log) gave is kept, with Bambuddy's beside it in `bambuddy`."""
    b = run["bambuddy"]
    status = entry.get("status")
    if b.get("snapshot_at") or status not in ENDED:
        return False
    dur, n = entry.get("duration_seconds"), entry["id"]
    est = failed_at_estimate(dur, planned_seconds(entry.get("archive_id"))) if status == "failed" else None
    b.update(status=status, started=_iso(entry.get("started_at")), ended=_iso(entry.get("completed_at")),
             minutes=round(dur / 60.0, 1) if dur is not None else None, grams=entry.get("filament_used_grams"),
             failure_reason=entry.get("failure_reason"), failed_at_estimate=est, snapshot_at=now())
    if status == "failed" and run.get("failed") is None:
        run["failed"] = {"at_fraction": est, "note": f"estimate from Bambuddy print #{n}"}
        if e["status"] == "printing":
            e["status"] = "built"  # as `lab exp usage --failed-at`: the next attempt is checked again
    current = run.get("usage")
    if (current or {}).get("usage_source") in REPLACEABLE:
        if current:
            run.setdefault("usage_revisions", []).append({**current, "replaced_at": b["snapshot_at"],
                                                          "reason": _mark(n)})
        run["usage"] = {"actual_minutes": b["minutes"], "actual_g": b["grams"], "usage_source": "bambuddy",
                        "completion_fraction": (run.get("failed") or {}).get("at_fraction") if status == "failed"
                        else None}
    return True


def link_entries(paths: ProjectPaths, entries: list[dict],
                 planned_seconds: Callable[[int], float | None]) -> list[dict]:
    """Link each print-log entry to its run and snapshot the ones that have ended; what changed, as events
    {"action": "linked" | "created" | "snapshot" | "skipped", "experiment", "run", "print", "message"}. Names outside
    the lab are passed over silently; a lab name for an experiment or build this project hasn't got is "skipped".
    planned_seconds(archive_id) is the archive's planned time, asked only for a failed print."""
    linked = {r["bambuddy"]["print"]: e["id"] for e in all_experiments(paths).values()
              for r in e.get("print_runs") or [] if (r.get("bambuddy") or {}).get("print") is not None}
    events = []

    def event(action, eid, run, entry, message=None):
        events.append({"action": action, "experiment": eid, "run": run["id"] if run else None, "print": entry["id"],
                       "message": message})

    for entry in entries:
        if entry.get("id") is None:
            continue
        if entry["id"] in linked:  # linked before, by name or by hand: only its snapshot can be due
            eid = linked[entry["id"]]
            with record_lock(paths.locks, eid, f"lab pull: {_mark(entry['id'])}"):
                e = load_experiment(paths, eid)
                run = next((r for r in e["print_runs"] if (r.get("bambuddy") or {}).get("print") == entry["id"]),
                           None)
                if run and _snapshot(e, run, entry, planned_seconds):
                    save_experiment(paths, e)
                    event("snapshot", eid, run, entry)
            continue
        name = bambuddy.parse_lab_name(entry.get("print_name"))
        if not name:
            continue
        eid, bid = name["exp"], name["build"]
        if name["project"] != paths.name or not (paths.experiments / f"{eid}.json").exists():
            event("skipped", None, None, entry, f"{entry['print_name']} names no experiment in {paths.name}; "
                                                "treated as outside the lab.")
            continue
        with record_lock(paths.locks, eid, f"lab pull: {_mark(entry['id'])}"):
            e = load_experiment(paths, eid)
            if not any(b["id"] == bid for b in e.get("builds") or []):
                event("skipped", eid, None, entry, f"{entry['print_name']}: {eid} has no {bid}; treated as "
                                                   "outside the lab.")
                continue
            run, action, msg = _attach(e, bid, entry, "auto")
            ended = _snapshot(e, run, entry, planned_seconds)
            save_experiment(paths, refresh_derived(paths, e) if action == "created" else e)
        linked[entry["id"]] = eid
        event(action, eid, run, entry, msg)
        if ended:
            event("snapshot", eid, run, entry)
    return events


def link_by_hand(paths: ProjectPaths, exp_id: str, build_id: str, print_entry: dict, planned: float | None) -> dict:
    """`lab exp link`: attach any print (renamed, or sent from outside the lab) to a build's run, as a name match
    would, and snapshot it if it has ended. The linked run."""
    for e in all_experiments(paths).values():
        for r in e.get("print_runs") or []:
            if (r.get("bambuddy") or {}).get("print") == print_entry["id"]:
                raise ValueError(f"{_mark(print_entry['id'])} is already linked to {e['id']} {r['id']}. "
                                 f"Unlink it first: `lab exp unlink {e['id']} {r['id']}`.")
    with record_lock(paths.locks, exp_id, f"lab exp link {exp_id} {build_id}"):
        e = load_experiment(paths, exp_id)
        builds = [b["id"] for b in e.get("builds") or []]
        if build_id not in builds:
            raise ValueError(f"{exp_id} has no {build_id}. Builds: {', '.join(builds) or 'none yet'}")
        run, action, _ = _attach(e, build_id, print_entry, "hand")
        _snapshot(e, run, print_entry, lambda _: planned)
        save_experiment(paths, refresh_derived(paths, e) if action == "created" else e)
    return run


def unlink(paths: ProjectPaths, run_id: str) -> dict:
    """`lab exp unlink`: drop the run's link and the facts taken from that print (usage and failure whose source is
    it), putting back any usage the snapshot replaced. The owner's own figures stay. The run."""
    e, run = find_run(paths, run_id)
    if not run.get("bambuddy"):
        raise ValueError(f"{run_id} isn't linked to a Bambuddy print.")
    with record_lock(paths.locks, e["id"], f"lab exp unlink {run_id}"):
        e = load_experiment(paths, e["id"])
        run = next(r for r in e["print_runs"] if r["id"] == run_id)
        n = run.pop("bambuddy")["print"]
        if (run.get("failed") or {}).get("note") == f"estimate from Bambuddy print #{n}":
            run["failed"] = None
        if (run.get("usage") or {}).get("usage_source") == "bambuddy":
            revs = run.get("usage_revisions") or []
            if revs and revs[-1].get("reason") == _mark(n):
                prior = revs.pop()
                run["usage"] = {k: v for k, v in prior.items() if k not in ("replaced_at", "reason")}
                if not revs:
                    run.pop("usage_revisions")
            else:
                run["usage"] = None
        save_experiment(paths, e)
    return run
