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
STOPPED = ("failed", "cancelled")  # the print didn't finish: the next attempt is checked again
NOT_YET_PRINTED = ("built", "ready", "needs_approval", "approved")
REPLACEABLE = (None, "telemetry", "finished_unknown")  # a figure Bambuddy's own measurement is better than


def _iso(s: str | None) -> str | None:
    """Bambuddy's naive-UTC timestamp as the lab writes times: aware UTC, to the second."""
    t = bambuddy.parse_time(s)
    return t.isoformat(timespec="seconds") if t else None


def _mark(print_id: int) -> str:
    return f"bambuddy print #{print_id}"


def _is_mark(reason, print_id: int) -> bool:
    """A revision reason that starts with this print's mark ("bambuddy print #15", maybe with a note after it),
    but not another print's (#150)."""
    mark = _mark(print_id)
    return isinstance(reason, str) and reason.startswith(mark) and not reason[len(mark):][:1].isdigit()


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
    message). Opening a run checks nothing: the print already happened. An experiment not yet printed becomes
    `printing`, so a finished print asks for its verdict (a failed one goes back to `built` in the snapshot);
    answered and abandoned ones stay as they are. The link notes a run it opened and the status it moved, so
    unlinking can undo both."""
    prior = e["status"]
    if prior in NOT_YET_PRINTED:
        e["status"] = "printing"
    link = _link(entry, how) | ({"prior_status": prior} if e["status"] != prior else {})
    open_runs = [r for r in e["print_runs"] if r.get("build_id") == build_id and not r.get("bambuddy")]
    if open_runs:
        run = open_runs[-1]
        run["bambuddy"] = link
        msg = None
        if len(open_runs) > 1:
            msg = (f"{build_id} has {len(open_runs)} runs without a print ({', '.join(r['id'] for r in open_runs)}); "
                   f"{_mark(entry['id'])} went to the newest, {run['id']}.")
        return run, "linked", msg
    run = {"id": next_local_id(e, "print_runs", f"PR-{e['id'][2:]}"), "build_id": build_id,
           "started_at": _iso(entry.get("started_at")) or now(), "setup": None, "baseline_missing": [],
           "usage": None, "failed": None, "photos": [], "bambuddy": link | {"opened_run": True}}
    e["print_runs"].append(run)
    return run, "created", f"{_mark(entry['id'])} had no run on {build_id}; opened {run['id']}."


def _snapshot(e: dict, run: dict, entry: dict, planned: float | None) -> bool:
    """Write the evidence once the print has ended; False when it hasn't, or already was. A usage figure or failure
    the owner (or the printer log) gave is kept, with Bambuddy's beside it in `bambuddy`. planned: the archive's
    planned seconds, for a failed print's estimate."""
    b = run["bambuddy"]
    status = entry.get("status")
    if b.get("snapshot_at") or status not in ENDED:
        return False
    dur, n = entry.get("duration_seconds"), entry["id"]
    est = failed_at_estimate(dur, planned) if status == "failed" else None
    b.update(status=status, started=_iso(entry.get("started_at")), ended=_iso(entry.get("completed_at")),
             minutes=round(dur / 60.0, 1) if dur is not None else None, grams=entry.get("filament_used_grams"),
             failure_reason=entry.get("failure_reason"), failed_at_estimate=est, snapshot_at=now())
    if status == "failed" and run.get("failed") is None:
        run["failed"] = {"at_fraction": est, "note": f"estimate from Bambuddy print #{n}"}
    if status in STOPPED and e["status"] == "printing" and run is e["print_runs"][-1]:
        e["status"] = "built"  # as `lab exp usage --failed-at`; not when a later run is the one printing
    current = run.get("usage")
    if (current or {}).get("usage_source") in REPLACEABLE:
        if current:
            run.setdefault("usage_revisions", []).append({**current, "replaced_at": b["snapshot_at"],
                                                          "reason": _mark(n)})
        keep = current or {}  # a figure Bambuddy doesn't have stays what it was
        usage = {"actual_minutes": b["minutes"] if b["minutes"] is not None else keep.get("actual_minutes"),
                 "actual_g": b["grams"] if b["grams"] is not None else keep.get("actual_g"),
                 "usage_source": "bambuddy",
                 "completion_fraction": (run.get("failed") or {}).get("at_fraction") if status == "failed"
                 else None}
        # A figure kept because Bambuddy has none is still what it was, so it keeps its own source.
        if b["minutes"] is None and keep.get("actual_minutes") is not None:
            usage["minutes_source"] = keep.get("minutes_source", keep.get("usage_source"))
        if b["grams"] is None and keep.get("actual_g") is not None:
            g_src = keep.get("g_source", keep.get("usage_source"))
            # Telemetry grams were the slicer's estimate (apply_telemetry now records none): say so.
            usage["g_source"] = "slicer_estimate" if g_src == "telemetry" else g_src
        run["usage"] = usage
    return True


def _save(paths: ProjectPaths, e: dict, status_before: str, created: bool = False) -> dict:
    """Save, recomputing the derived fields when a run was opened or the status moved, as `lab exp start` does."""
    return save_experiment(paths, refresh_derived(paths, e) if created or e["status"] != status_before else e)


def link_entries(paths: ProjectPaths, entries: list[dict],
                 planned_seconds: Callable[[int], float | None]) -> list[dict]:
    """Link each print-log entry to its run and snapshot the ones that have ended; what changed, as events
    {"action": "linked" | "created" | "snapshot" | "skipped", "experiment", "run", "print", "message"}. Names outside
    the lab are passed over silently; a lab name for an experiment or build this project hasn't got is "skipped".
    planned_seconds(archive_id) is the archive's planned time, asked only for a failed print still to be
    snapshotted, and never while a record is locked (it may wait on the network)."""
    linked = {r["bambuddy"]["print"]: (e["id"], bool(r["bambuddy"].get("snapshot_at")))
              for e in all_experiments(paths).values() for r in e.get("print_runs") or []
              if (r.get("bambuddy") or {}).get("print") is not None}
    events = []

    def event(action, eid, run, entry, message=None):
        events.append({"action": action, "experiment": eid, "run": run["id"] if run else None, "print": entry["id"],
                       "message": message})

    for entry in entries:
        if entry.get("id") is None:
            continue
        eid, done = linked.get(entry["id"], (None, False))
        wants_plan = entry.get("status") == "failed" and not done
        if eid:  # linked before, by name or by hand: only its snapshot can be due
            if done:
                continue
            planned = planned_seconds(entry.get("archive_id")) if wants_plan else None
            with record_lock(paths.locks, eid, f"lab pull: {_mark(entry['id'])}"):
                e = load_experiment(paths, eid)
                before = e["status"]
                run = next((r for r in e["print_runs"] if (r.get("bambuddy") or {}).get("print") == entry["id"]),
                           None)
                if run and _snapshot(e, run, entry, planned):
                    _save(paths, e, before)
                    linked[entry["id"]] = (eid, True)
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
        planned = None
        if wants_plan and any(b["id"] == bid for b in load_experiment(paths, eid).get("builds") or []):
            planned = planned_seconds(entry.get("archive_id"))  # a lab print only; checked again under the lock
        with record_lock(paths.locks, eid, f"lab pull: {_mark(entry['id'])}"):
            e = load_experiment(paths, eid)
            if any((r.get("bambuddy") or {}).get("print") == entry["id"] for r in e["print_runs"]):
                continue  # another pull linked it since the view above was read
            if not any(b["id"] == bid for b in e.get("builds") or []):
                event("skipped", eid, None, entry, f"{entry['print_name']}: {eid} has no {bid}; treated as "
                                                   "outside the lab.")
                continue
            before = e["status"]
            run, action, msg = _attach(e, bid, entry, "auto")
            ended = _snapshot(e, run, entry, planned)
            _save(paths, e, before, action == "created")
        linked[entry["id"]] = (eid, ended)
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
                                 f"Unlink it first: `lab exp unlink {r['id']}`.")
    with record_lock(paths.locks, exp_id, f"lab exp link {exp_id} {build_id}"):
        e = load_experiment(paths, exp_id)
        for r in e["print_runs"]:
            if (r.get("bambuddy") or {}).get("print") == print_entry["id"]:
                raise ValueError(f"{_mark(print_entry['id'])} is already linked to {e['id']} {r['id']}. "
                                 f"Unlink it first: `lab exp unlink {r['id']}`.")
        builds = [b["id"] for b in e.get("builds") or []]
        if build_id not in builds:
            raise ValueError(f"{exp_id} has no {build_id}. Builds: {', '.join(builds) or 'none yet'}")
        before = e["status"]
        run, action, _ = _attach(e, build_id, print_entry, "hand")
        _snapshot(e, run, print_entry, planned)
        _save(paths, e, before, action == "created")
    return run


def _is_open(run: dict) -> bool:
    """A run still waiting for its end: no usage, no failure and no ended print linked."""
    return not run.get("usage") and not run.get("failed") and not (run.get("bambuddy") or {}).get("snapshot_at")


def unlink(paths: ProjectPaths, run_id: str) -> dict:
    """`lab exp unlink`: drop the run's link and the facts taken from that print (usage and failure whose source is
    it), putting back any usage the snapshot replaced. The owner's own figures stay. A run the link opened goes too
    when nothing of the owner's is on it (else the ledger would charge it the estimate), and a status the link
    moved goes back while the experiment is still printing with no other run open. The run."""
    e, run = find_run(paths, run_id)
    if not run.get("bambuddy"):
        raise ValueError(f"{run_id} isn't linked to a Bambuddy print.")
    with record_lock(paths.locks, e["id"], f"lab exp unlink {run_id}"):
        e = load_experiment(paths, e["id"])
        run = next((r for r in e["print_runs"] if r["id"] == run_id), None)
        if not run or not run.get("bambuddy"):  # unlinked meanwhile (a run the link opened is gone)
            raise ValueError(f"{run_id} isn't linked to a Bambuddy print.")
        before = e["status"]
        link = run.pop("bambuddy")
        n = link["print"]
        if (run.get("failed") or {}).get("note") == f"estimate from Bambuddy print #{n}":
            run["failed"] = None
        if (run.get("usage") or {}).get("usage_source") == "bambuddy":
            revs = run.get("usage_revisions") or []
            if revs and _is_mark(revs[-1].get("reason"), n):
                prior = revs.pop()
                run["usage"] = {k: v for k, v in prior.items() if k not in ("replaced_at", "reason")}
                if not revs:
                    run.pop("usage_revisions")
            else:
                run["usage"] = None
        if link.get("opened_run") and not run.get("usage") and not run.get("failed") and not run.get("photos"):
            e["print_runs"].remove(run)
        if (link.get("prior_status") and e["status"] == "printing"
                and not any(_is_open(r) for r in e["print_runs"] if r is not run)):
            e["status"] = link["prior_status"]
        _save(paths, e, before, run not in e["print_runs"])
    return run
