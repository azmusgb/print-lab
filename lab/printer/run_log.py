"""`lab exp log`: record what the printer reports during a print run, then summarise it on the run.

Unknown stays unknown: an end time is recorded only when the printer was heard reporting the finish without a gap,
and usage is written only from such an end. A stop, a cancel or a reconnect after the print ended never becomes a
completion time."""
import datetime
import json

from lab.loop.commands import load_experiment, save_experiment
from lab.printer.log import LayerLog, StateMerger, summarize
from lab.printer.mqtt import END_STATES
from lab.records.project import ProjectPaths
from lab.records.store import record_lock

MAX_GAP_S = 120  # a longer silence before the end report means the end time isn't known


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _ts(s: str | None) -> datetime.datetime | None:
    if not s:
        return None
    t = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)


def _printer_start(raw: str | None, first_seen: str | None) -> str | None:
    """The printer's own start (epoch seconds in `gcode_start_time`), if it is plausible: before we first heard
    the printer and within a day of it."""
    try:
        t = datetime.datetime.fromtimestamp(int(raw), datetime.timezone.utc)
    except (TypeError, ValueError, OSError):
        return None
    seen = _ts(first_seen)
    if seen and datetime.timedelta(0) <= seen - t <= datetime.timedelta(days=1):
        return t.isoformat(timespec="seconds")
    return None


def log_run(paths: ProjectPaths, eid: str, *, env: dict, listen, heights: dict[int, float],
            run_id: str | None = None) -> dict:
    """Listen until the printer reports an end state (or Ctrl-C), writing telemetry/<RUN>.jsonl, then store the
    summary in the run's `printer_log`. Usage is recorded from the printer's times only for a print heard finishing
    without a gap; a replaced value is kept in `usage_revisions`."""
    e = load_experiment(paths, eid)
    runs = e.get("print_runs") or []
    run = next((r for r in runs if r["id"] == run_id), None) if run_id else (runs[-1] if runs else None)
    if run is None:
        raise ValueError(f"{eid} has no print run{' ' + run_id if run_id else ''} to log; run `lab exp start` first.")
    if run.get("printer_log"):
        raise ValueError(f"{run['id']} already has a printer log ({run['printer_log'].get('path')}).")
    rel = f"telemetry/{run['id']}.jsonl"
    out_path = paths.root / rel
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("")  # a fresh log for this run, never appended to an earlier attempt
    merger, log, lines = StateMerger(), LayerLog(), []
    seen = {"first": None, "running": False, "late": False, "end": None, "end_uncertain": False, "state": None,
            "last_report": None, "last_running": None, "last_percent": None, "gcode_start": None, "job": None,
            "job_changed": False}

    def on_report(rep: dict) -> None:
        now = _now()
        seen["first"] = seen["first"] or now
        p = rep.get("print") or {}
        if p.get("gcode_start_time"):
            seen["gcode_start"] = p["gcode_start_time"]
        job = p.get("subtask_name") or p.get("gcode_file")
        if job:
            if seen["job"] and job != seen["job"]:
                seen["job_changed"] = True  # another print started: nothing after this belongs to our run
                return
            seen["job"] = job
        state = merger.update(rep)
        gs = state.get("gcode_state")
        if not seen["running"] and gs in END_STATES:
            seen["late"] = True  # the print was already over before we heard it running
            return
        if gs in ("RUNNING", "PREPARE"):
            seen["running"] = True
            seen["last_running"] = now
            if state.get("mc_percent") is not None:
                seen["last_percent"] = state.get("mc_percent")
        seen["state"] = gs
        line = log.offer(state, t=now)
        if line:
            lines.append(line)
            with out_path.open("a") as f:
                f.write(json.dumps(line) + "\n")
        if seen["running"] and gs in END_STATES and not seen["end"]:
            gap = (_ts(now) - _ts(seen["last_report"])).total_seconds() if seen["last_report"] else 0
            if gap > MAX_GAP_S:  # e.g. reconnected after the print ended: the end lies somewhere in the gap
                seen["end"], seen["end_uncertain"] = seen["last_running"], True
            else:
                seen["end"] = now
        seen["last_report"] = now

    stopped = False
    try:
        listen(env, on_report, should_stop=lambda: seen["end"] is not None or seen["late"] or seen["job_changed"])
    except KeyboardInterrupt:
        stopped = True
    if seen["late"] and not lines:
        out_path.unlink(missing_ok=True)
        raise ValueError(f"The printer says the print is already over ({merger.state.get('gcode_state')}); "
                         "nothing was logged. Start `lab exp log` while the run is printing.")
    if seen["job_changed"] and not seen["end"]:
        final = "job_changed"
    elif stopped and not seen["end"]:
        final = "stopped"
    else:
        final = seen["state"]
    summary = {"path": rel, "first_seen": seen["first"], "printer_start": _printer_start(seen["gcode_start"], seen["first"]),
               "last_running": seen["last_running"], "ended_at": seen["end"], "job": seen["job"],
               "end_uncertain": seen["end_uncertain"], "final_state": final, "last_percent": seen["last_percent"],
               "lines": len(lines), "events": summarize(lines, heights)}
    with record_lock(paths.locks, eid, f"lab exp log {eid}"):
        e = load_experiment(paths, eid)
        target = next(r for r in e["print_runs"] if r["id"] == run["id"])
        target["printer_log"] = summary
        _record_logged_usage(target, summary)
        return save_experiment(paths, e)


def _record_logged_usage(run: dict, log: dict) -> None:
    """Minutes from the printer's start (or `lab exp start`) to a finish heard without a gap. Never grams: the
    printer doesn't report them, and the slicer estimate isn't a measurement."""
    if log["final_state"] != "FINISH" or log["end_uncertain"] or not log["ended_at"]:
        return
    current = run.get("usage")
    if current and current.get("usage_source") not in (None, "finished_unknown"):
        return  # an owner or earlier figure stands; the log is in printer_log for comparison
    start = _ts(log.get("printer_start") or run.get("started_at"))
    if not start:
        return
    minutes = round((_ts(log["ended_at"]) - start).total_seconds() / 60.0, 1)
    if current:
        run.setdefault("usage_revisions", []).append(
            {**current, "replaced_at": log["ended_at"], "reason": "printer log heard the finish"})
    run["usage"] = {"actual_minutes": minutes, "actual_g": None, "usage_source": "printer_log",
                    "completion_fraction": None}


def report_text(run: dict, marks: list[dict] | None = None) -> str:
    from lab.printer.log import match_marks
    log = run.get("printer_log") or {}
    end = log.get("ended_at") or "unknown"
    if log.get("end_uncertain"):
        end += " (last report while running; the real end is later and unknown)"
    out = [f"{run['id']}: {log.get('lines', 0)} lines, final state {log.get('final_state')}, "
           f"first seen {log.get('first_seen')}, ended {end}"]
    ev = log.get("events") or []
    out.append("Fan and air-duct events:" if ev else "No fan or air-duct changes logged.")
    for x in ev:
        z = f"{x['z_mm']:g} mm" if x.get("z_mm") is not None else "height unknown"
        out.append(f"  layer {x['layer']} ({z}): {x['field']} {x['from']} → {x['to']}")
    if ev:
        out.append("Events carry the layer the printer reported at that moment; a fan change can land one layer "
                   "(about 0.2 mm) off.")
    for m in match_marks(marks or [], ev):
        z = m.get("defect_z_mm") if m.get("defect_z_mm") is not None else m.get("mark_z_mm")
        where = f"{z:g} mm" if z is not None else "height unknown"
        near = ", ".join(f"{x['field']} at {x['z_mm']:g} mm" for x in m["events"]) or "nothing logged nearby"
        out.append(f"Mark at {where} ({m['variant']}): {near}. A match is a lead to test, not a cause.")
    return "\n".join(out)
