"""`lab status`: at-a-glance project, question, budget, in-flight print, and sync status."""
import argparse
import datetime
import json
import sys
from pathlib import Path

from lab.page_index import build_index
from lab.records.store import now
from lab import sync


def _parse_iso(s: str) -> datetime.datetime | None:
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.datetime.fromisoformat(s)
    except Exception:
        return None


def _rel_time(dt_or_str: datetime.datetime | str | None) -> str:
    if not dt_or_str:
        return "never"
    dt = dt_or_str if isinstance(dt_or_str, datetime.datetime) else _parse_iso(dt_or_str)
    if not dt:
        return str(dt_or_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    now_dt = datetime.datetime.now(datetime.timezone.utc)
    diff = int((now_dt - dt).total_seconds())
    if diff < 0:
        return "just now"
    if diff < 60:
        return f"{diff}s ago"
    if diff < 3600:
        return f"{diff // 60}m ago"
    if diff < 86400:
        return f"{diff // 3600}h ago"
    return f"{diff // 86400}d ago"


def build_status(pdir: Path, *, include_printer: bool = True) -> dict:
    ix = build_index(pdir)
    sync_st = sync.status(pdir)

    # Active or latest question
    question = ix["questions"][0] if ix.get("questions") else None

    # In-flight experiment / print run
    active_print = None
    printing_exp = next((e for e in ix.get("experiments", []) if e.get("status") == "printing"), None)
    if printing_exp:
        last_run = (printing_exp.get("runs") or [{}])[-1]
        last_build = printing_exp.get("approval", {}).get("build_id")
        active_print = {
            "experiment_id": printing_exp["id"],
            "question_id": printing_exp.get("question"),
            "run_id": last_run.get("id"),
            "started_at": last_run.get("started_at"),
            "build_id": last_build or (printing_exp.get("estimate") and "approved"),
            "estimate": printing_exp.get("estimate"),
        }

    printer_info = None
    if include_printer:
        ws = sync.fetch_workshop_status()
        if ws and isinstance(ws, dict) and ws.get("printer"):
            p = ws["printer"]
            printer_info = {
                "state": p.get("state"),
                "progress": p.get("progress"),
                "minutes_left": p.get("minutesLeft"),
                "seen_at": p.get("seenAt"),
                "access": p.get("access"),
            }

    if active_print and printer_info:
        active_print["printer"] = printer_info

    return {
        "project": ix["project"],
        "at": now(),
        "sync": sync_st,
        "question": question,
        "active_print": active_print,
        "printer": printer_info if not active_print else None,
        "needs": ix.get("needs") or [],
        "problems": ix.get("problems") or [],
    }


def format_status_text(st: dict) -> str:
    lines = []
    lines.append(f"Project: {st['project']}")

    # Sync line
    s = st.get("sync")
    if s:
        mark = "✓" if s.get("ok") else "✗"
        msg = s.get("message") or ("synced" if s.get("ok") else "error")
        ago = _rel_time(s.get("at"))
        lines.append(f"Sync:    {mark} {msg.capitalize()} ({ago})")
    else:
        lines.append("Sync:    never synced")

    lines.append("")

    # Question section
    q = st.get("question")
    if q:
        lines.append(f"Question: {q['id']} — {q['question']}")
        stop = q.get("stop") or {}
        lines.append(f"Status:   {stop.get('text', q.get('status', '-'))}")
        spent, budget = q.get("spent") or {}, q.get("budget") or {}
        sm, bm = spent.get("minutes", 0), budget.get("minutes", 0)
        sg, bg = spent.get("g", 0), budget.get("g", 0)
        pct_m = f" ({int(round(sm / bm * 100))}%)" if bm else ""
        pct_g = f" ({int(round(sg / bg * 100))}%)" if bg else ""
        lines.append(f"Budget:   Time {sm:g} / {bm:g} min{pct_m} · Material {sg:g} / {bg:g} g{pct_g}")
        ev = q.get("evidence") or {}
        lines.append(f"Streak:   {q.get('streak', 0)} uninformative · Evidence: {ev.get('informative', 0)} informative, {ev.get('uninformative', 0)} uninformative")
    else:
        lines.append("Question: none yet")

    lines.append("")

    # Active print section
    ap = st.get("active_print")
    if ap:
        lines.append("Active Print:")
        lines.append(f"  Experiment: {ap['experiment_id']}" + (f" ({ap['run_id']})" if ap.get("run_id") else ""))
        if ap.get("build_id"):
            lines.append(f"  Build:      {ap['build_id']}")
        if ap.get("started_at"):
            lines.append(f"  Started:    {ap['started_at']} ({_rel_time(ap['started_at'])})")
        pr = ap.get("printer")
        if pr:
            state = pr.get("state") or "unknown"
            prog = pr.get("progress")
            prog_s = f"{prog}%" if prog is not None else ""
            left = pr.get("minutes_left")
            left_s = f", ~{left} min remaining" if left is not None else ""
            ago = f" (seen {_rel_time(pr.get('seen_at'))})" if pr.get("seen_at") else ""
            lines.append(f"  Printer:    {state} — {prog_s}{left_s}{ago}")
        est = ap.get("estimate")
        if est:
            lines.append(f"  Estimate:   {est.get('minutes', 0):g} min, {est.get('g', 0):g} g")
    else:
        pr = st.get("printer")
        if pr:
            state = pr.get("state") or "unknown"
            lines.append(f"Active Print: none (Printer: {state})")
        else:
            lines.append("Active Print: none")

    lines.append("")

    # Needs attention section
    needs = st.get("needs") or []
    if needs:
        lines.append("Needs Attention:")
        for n in needs:
            lines.append(f"  • [{n['id']}] {n['action']}")
            if n.get("why"):
                lines.append(f"    Why:     {n['why']}")
            if n.get("command"):
                lines.append(f"    Command: {n['command']}")
    else:
        lines.append("Needs Attention: none (all caught up)")

    # Problems if any
    probs = st.get("problems") or []
    if probs:
        lines.append("")
        lines.append("Problems:")
        for p in probs:
            lines.append(f"  ✗ {p.get('file')}: {p.get('error')}")

    return "\n".join(lines)


def cmd_status(args) -> int:
    from lab.cli import project_dir
    pdir = project_dir(args.project)
    include_printer = not getattr(args, "no_printer", False)
    st = build_status(pdir, include_printer=include_printer)
    if getattr(args, "json", False):
        print(json.dumps(st, indent=2))
    else:
        print(format_status_text(st))
    return 0


def register(sub) -> None:
    s = sub.add_parser("status", help="overview of project, active question, printer, and next actions")
    s.add_argument("--json", action="store_true", help="output JSON")
    s.add_argument("--no-printer", action="store_true", help="skip live printer query")
    s.add_argument("--project", default=argparse.SUPPRESS)
    s.set_defaults(fn=cmd_status)
