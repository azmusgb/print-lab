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

    dt_start = _parse_iso(started_at)
    dt_seen = _parse_iso(seen_at)
    if dt_start and dt_seen:
        if dt_start.tzinfo is None:
            dt_start = dt_start.replace(tzinfo=datetime.timezone.utc)
        if dt_seen.tzinfo is None:
            dt_seen = dt_seen.replace(tzinfo=datetime.timezone.utc)
        elapsed_m = max(0.0, round((dt_seen - dt_start).total_seconds() / 60.0, 1))
    else:
        elapsed_m = 0.0

    consumed_g = round(est_g * (progress / 100.0), 1) if progress < 100 else est_g
    is_finished = (state in ("finish", "idle", "success") or progress >= 100)

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
    }


def format_telemetry_text(t: dict) -> str:
    lines = []
    lines.append(f"Experiment: {t['experiment_id']}")
    lines.append(f"Run:        {t['run_id']}" + (f" ({t['build_id']})" if t.get("build_id") else ""))
    lines.append(f"Printer:    {t['printer_state']} ({t['progress']}% complete"
                 + (f", ~{t['minutes_left']:g} min left" if t.get("minutes_left") is not None else "") + ")")
    lines.append("Telemetry:")
    lines.append(f"  Elapsed:     {t['elapsed_minutes']:g} min (started {t['started_at']})")
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

    if failed_at_pct is not None:
        e = record_usage(paths, t["run_id"], failed_at_pct=failed_at_pct,
                         minutes=t["elapsed_minutes"], grams=t["consumed_g"], usage_source="telemetry")
    elif t["is_finished"]:
        e = record_usage(paths, t["run_id"], failed_at_pct=None,
                         minutes=t["elapsed_minutes"], grams=t["estimate_g"], usage_source="telemetry")
    else:  # forced partial
        e = record_usage(paths, t["run_id"], failed_at_pct=None,
                         minutes=t["elapsed_minutes"], grams=t["consumed_g"], usage_source="telemetry")

    return e, t
