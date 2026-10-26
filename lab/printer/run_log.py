"""`lab exp log`: record what the printer reports during a print run, then summarise it on the run."""
import datetime
import json

from lab.loop.commands import load_experiment, save_experiment
from lab.printer.log import LayerLog, StateMerger, summarize
from lab.printer.mqtt import END_STATES
from lab.records.project import ProjectPaths
from lab.records.store import record_lock


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def log_run(paths: ProjectPaths, eid: str, *, env: dict, listen, heights: dict[int, float],
            run_id: str | None = None) -> dict:
    """Listen until the printer reports an end state, writing telemetry/<RUN>.jsonl, then store the summary in the
    run's `printer_log`. Usage is left alone: the owner records it, or `lab exp telemetry --apply` reads the end time
    from this log."""
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
    merger, log, lines = StateMerger(), LayerLog(), []
    seen = {"first": None, "running": False, "end": None, "state": None}

    def on_report(rep: dict) -> None:
        now = _now()
        seen["first"] = seen["first"] or now
        state = merger.update(rep)
        gs = state.get("gcode_state")
        seen["state"] = gs
        if gs in ("RUNNING", "PREPARE"):
            seen["running"] = True
        line = log.offer(state, t=now)
        if line:
            lines.append(line)
            with out_path.open("a") as f:
                f.write(json.dumps(line) + "\n")
        if seen["running"] and gs in END_STATES and not seen["end"]:
            seen["end"] = now

    listen(env, on_report, should_stop=lambda: seen["end"] is not None)
    summary = {"path": rel, "first_seen": seen["first"], "ended_at": seen["end"], "final_state": seen["state"],
               "lines": len(lines), "events": summarize(lines, heights)}
    with record_lock(paths.locks, eid, f"lab exp log {eid}"):
        e = load_experiment(paths, eid)
        target = next(r for r in e["print_runs"] if r["id"] == run["id"])
        target["printer_log"] = summary
        return save_experiment(paths, e)


def report_text(run: dict, marks: list[dict] | None = None) -> str:
    from lab.printer.log import match_marks
    log = run.get("printer_log") or {}
    out = [f"{run['id']}: {log.get('lines', 0)} lines, final state {log.get('final_state')}, "
           f"first seen {log.get('first_seen')}, ended {log.get('ended_at')}"]
    ev = log.get("events") or []
    out.append("Fan and air-duct events:" if ev else "No fan or air-duct changes logged.")
    for x in ev:
        z = f"{x['z_mm']:g} mm" if x.get("z_mm") is not None else "height unknown"
        out.append(f"  layer {x['layer']} ({z}): {x['field']} {x['from']} → {x['to']}")
    for m in match_marks(marks or [], ev):
        z = m.get("defect_z_mm") if m.get("defect_z_mm") is not None else m.get("mark_z_mm")
        near = ", ".join(f"{x['field']} at {x['z_mm']:g} mm" for x in m["events"]) or "nothing logged nearby"
        out.append(f"Mark at {z:g} mm ({m['variant']}): {near}. A match is a lead to test, not a cause.")
    return "\n".join(out)
