"""Telemetry auto-fill (`lab exp telemetry <eid>`) using Local AI's printer status endpoint."""
import datetime
import json
from pathlib import Path

from lab import sync
from lab.loop.commands import find_run, load_experiment, record_usage
from lab.records.project import ProjectPaths


def _parse_iso(s: str) -> datetime.datetime | None:
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.datetime.fromisoformat(s)
    except Exception:
        return None


def get_run_telemetry(paths: ProjectPaths, eid: str, *, run_id: str | None = None,
                      base: str | None = None, timeout: float = 2.0) -> dict:
    e = load_experiment(paths, eid)
    runs = e.get("print_runs") or []
    if not runs:
        raise ValueError(f"Experiment {eid} has no print runs.")

    if run_id:
        run = next((r for r in runs if r["id"] == run_id), None)
        if not run:
            raise ValueError(f"Print run {run_id} not found in experiment {eid}.")
    else:
        run = runs[-1]

    build = next((b for b in e.get("builds") or [] if b["id"] == run.get("build_id")), None)
    est = (build or {}).get("estimate") or {}
    est_m = float(est.get("minutes") or 0.0)
    est_g = float(est.get("g") or 0.0)

    ws = sync.fetch_workshop_status(base=base, timeout=timeout)
    if not ws or not isinstance(ws, dict) or not ws.get("printer"):
        raise ValueError("Printer telemetry is currently unavailable from Local AI.")

    p = ws["printer"]
    state = p.get("state") or "unknown"
    progress = int(p.get("progress") or 0)
    minutes_left = float(p.get("minutesLeft")) if p.get("minutesLeft") is not None else None
    seen_at = p.get("seenAt")
    started_at = run.get("started_at")

    is_finished = (state in ("finish", "idle", "success") or progress >= 100)
    plog = run.get("printer_log") or {}
    # Only a finish heard without a gap is an end time; a cancel, a stop or a gap before the end report isn't.
    log_end = plog.get("ended_at") if plog.get("final_state") == "FINISH" and not plog.get("end_uncertain") else None
    dt_start = _parse_iso(started_at)
    # Once the print is over, Local AI's seenAt is when it last looked, not when the print ended; only the printer
    # log knows the end.
    dt_seen = _parse_iso(log_end) if log_end else (None if is_finished else _parse_iso(seen_at))
    if dt_start and dt_seen:
        if dt_start.tzinfo is None:
            dt_start = dt_start.replace(tzinfo=datetime.timezone.utc)
        if dt_seen.tzinfo is None:
            dt_seen = dt_seen.replace(tzinfo=datetime.timezone.utc)
        elapsed_m = max(0.0, round((dt_seen - dt_start).total_seconds() / 60.0, 1))
    else:
        elapsed_m = None if is_finished else 0.0

    consumed_g = round(est_g * (progress / 100.0), 1) if progress < 100 else est_g

    return {
        "experiment_id": eid,
        "run_id": run["id"],
        "build_id": run.get("build_id"),
        "printer_state": state,
        "progress": progress,
        "minutes_left": minutes_left,
        "elapsed_minutes": elapsed_m,
        "estimate_minutes": est_m,
        "estimate_g": est_g,
        "consumed_g": consumed_g,
        "started_at": started_at,
        "seen_at": seen_at,
        "is_finished": is_finished,
        "elapsed_source": "printer_log" if log_end else ("seen_at" if elapsed_m is not None else None),
        "log_final_state": plog.get("final_state"),
        "log_last_percent": plog.get("last_percent"),
    }


def format_telemetry_text(t: dict) -> str:
    lines = []
    lines.append(f"Experiment: {t['experiment_id']}")
    lines.append(f"Run:        {t['run_id']}" + (f" ({t['build_id']})" if t.get("build_id") else ""))
    lines.append(f"Printer:    {t['printer_state']} ({t['progress']}% complete"
                 + (f", ~{t['minutes_left']:g} min left" if t.get("minutes_left") is not None else "") + ")")
    lines.append("Telemetry:")
    el = "unknown" if t["elapsed_minutes"] is None else f"{t['elapsed_minutes']:g} min"
    lines.append(f"  Elapsed:     {el} (started {t['started_at']})")
    if t.get("minutes_left") is not None:
        lines.append(f"  Remaining:   {t['minutes_left']:g} min")
    lines.append(f"  Estimate:    {t['estimate_minutes']:g} min, {t['estimate_g']:g} g")
    lines.append(f"  Consumed ~:  {t['consumed_g']:g} g (at {t['progress']}%)")
    if t.get("is_finished"):
        lines.append("  Status:      Print complete")
    return "\n".join(lines)


def apply_telemetry(paths: ProjectPaths, eid: str, *, run_id: str | None = None,
                    failed_at_pct: float | None = None, force: bool = False,
                    base: str | None = None) -> tuple[dict, dict]:
    t = get_run_telemetry(paths, eid, run_id=run_id, base=base)
    if not t["is_finished"] and failed_at_pct is None and not force:
        raise ValueError(f"Run {t['run_id']} is still printing ({t['progress']}%, ~{t['minutes_left']:g} min left). "
                         "Wait for the print to finish, or pass --force to record partial elapsed time, "
                         "or --failed-at <pct> to record failure.")

    if t["log_final_state"] == "FAILED" and failed_at_pct is None:
        pct = t["log_last_percent"]
        raise ValueError(f"The printer log says {t['run_id']} failed or was cancelled"
                         + (f" at {pct}%" if pct is not None else "") + ". Record it as a failure: "
                         f"`lab exp usage {t['run_id']} --failed-at {pct if pct is not None else '<pct>'}`.")
    if failed_at_pct is not None:
        # Minutes only from a live reading (Local AI saw it still printing) or the printer log's end; never from a
        # later look at an idle or failed printer. Grams are never the estimate times progress.
        live = t["printer_state"] in ("printing", "running")
        minutes = t["elapsed_minutes"] if (live or t["elapsed_source"] == "printer_log") else None
        e = record_usage(paths, t["run_id"], failed_at_pct=failed_at_pct, minutes=minutes, grams=None,
                         usage_source="telemetry")
    elif t["is_finished"]:
        if t["elapsed_minutes"] is None:
            raise ValueError(f"{t['run_id']} has finished, but its end time isn't known: Local AI's last-seen time "
                             "isn't when the print ended. Take the time from the printer's history (Bambuddy or "
                             f"Bambu Handy) and run `lab exp usage {t['run_id']} --minutes N`, or run "
                             "`lab exp log` on the next print.")
        # The printer doesn't report grams, and the slicer's estimate isn't a measurement.
        e = record_usage(paths, t["run_id"], failed_at_pct=None, minutes=t["elapsed_minutes"], grams=None,
                         usage_source=t["elapsed_source"])
    else:  # forced partial: elapsed so far, no grams
        e = record_usage(paths, t["run_id"], failed_at_pct=None,
                         minutes=t["elapsed_minutes"], grams=None, usage_source="telemetry")

    return e, t


def mark_finished_unknown(paths: ProjectPaths, eid: str, run_id: str) -> dict:
    """The print ended but nobody knows when: mark the run so the finish isn't reported again, and leave its cost to
    the estimate until the owner gives the printer's time."""
    from lab.loop.commands import save_experiment
    from lab.records.store import record_lock
    with record_lock(paths.locks, eid, f"lab pull: {run_id} finished"):
        e = load_experiment(paths, eid)
        run = next(r for r in e["print_runs"] if r["id"] == run_id)
        run["usage"] = {"actual_minutes": None, "actual_g": None, "usage_source": "finished_unknown",
                        "completion_fraction": None}
        return save_experiment(paths, e)
