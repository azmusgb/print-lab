"""`lab watch`: live interactive terminal dashboard and progress monitor for active prints."""
import argparse
import sys
import time
from pathlib import Path

from lab.pull import notify_desktop
from lab.status import _rel_time, build_status


def format_progress_bar(pct: float, width: int = 28) -> str:
    clamped = max(0.0, min(100.0, float(pct)))
    filled = int(round(width * (clamped / 100.0)))
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {int(clamped)}%"


def render_dashboard(st: dict) -> tuple[str, bool, dict | None]:
    lines = []
    lines.append("╔════════════════════════════════════════════════════════════════════════╗")
    lines.append(f"║ Print Lab — {st['project']:<58} ║")
    lines.append("╚════════════════════════════════════════════════════════════════════════╝")

    ap = st.get("active_print")
    is_finished = False

    if ap:
        pr = ap.get("printer") or {}
        state = pr.get("state") or "unknown"
        prog = pr.get("progress") or 0
        left = pr.get("minutes_left")
        left_s = f"{left:g} min" if left is not None else "calculating..."
        ago = f"seen {_rel_time(pr.get('seen_at'))}" if pr.get("seen_at") else ""
        is_finished = (state in ("finish", "idle", "success") or prog >= 100)

        lines.append(f"State:       {state.upper()}  ({ago})")
        lines.append(f"Progress:    {format_progress_bar(prog)}")
        lines.append("")
        lines.append(f"Experiment:  {ap['experiment_id']}" + (f" ({ap['run_id']})" if ap.get("run_id") else ""))
        if ap.get("build_id"):
            lines.append(f"Build:       {ap['build_id']}")
        if ap.get("started_at"):
            lines.append(f"Started:     {ap['started_at']} ({_rel_time(ap['started_at'])})")

        est = ap.get("estimate") or {}
        est_m = est.get("minutes", 0)
        est_g = est.get("g", 0)
        consumed_g = round(est_g * (prog / 100.0), 1) if prog < 100 else est_g

        lines.append(f"Time:        ~{left_s} remaining (estimate: {est_m:g} min)")
        lines.append(f"Material:    ~{consumed_g:g} g consumed so far (estimate: {est_g:g} g)")
    else:
        pr = st.get("printer")
        if pr:
            state = pr.get("state") or "unknown"
            lines.append(f"Printer:     {state.upper()} (no active experiment print)")
        else:
            lines.append("Printer:     OFFLINE / UNREACHABLE")
        lines.append("Active:      none")

    lines.append("")
    lines.append("─" * 72)

    # Active Question & Budget
    q = st.get("question")
    if q:
        lines.append(f"Question:    {q['id']} — {q['question'][:55]}")
        stop = q.get("stop") or {}
        lines.append(f"Status:      {stop.get('text', q.get('status', '-'))}")
        spent, budget = q.get("spent") or {}, q.get("budget") or {}
        sm, bm = spent.get("minutes", 0), budget.get("minutes", 0)
        sg, bg = spent.get("g", 0), budget.get("g", 0)
        lines.append(f"Budget:      Time {sm:g} / {bm:g} min · Material {sg:g} / {bg:g} g")
    else:
        lines.append("Question:    none")

    # Next Action
    needs = st.get("needs") or []
    lines.append("")
    if needs:
        n = needs[0]
        lines.append(f"Next Action: [{n['id']}] {n['action']}")
        if n.get("command"):
            lines.append(f"Command:     {n['command']}")
    else:
        lines.append("Next Action: all caught up")

    return "\n".join(lines), is_finished, ap


def watch_loop(pdir: Path, interval: float = 5.0, once: bool = False, notify: bool = True) -> int:
    try:
        while True:
            st = build_status(pdir, include_printer=True)
            text, is_finished, ap = render_dashboard(st)

            if once:
                print(text)
                return 0

            # Clear screen and draw dashboard
            sys.stdout.write("\033[H\033[J")
            sys.stdout.write(text + "\n\n(Auto-refreshing every " + f"{interval:g}s; press Ctrl+C to exit)\n")
            sys.stdout.flush()

            if is_finished and ap:
                print("\n" + "═" * 72)
                print(f"✓ PRINT FINISHED: {ap['experiment_id']} ({ap.get('run_id', '')})")
                print("═" * 72)
                if notify:
                    notify_desktop(f"Print {ap.get('run_id')} ({ap['experiment_id']}) finished!", "Print Lab")
                return 0

            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n\nWatch ended.")
        return 0


def cmd_watch(args) -> int:
    from lab.cli import project_dir
    pdir = project_dir(args.project)
    return watch_loop(pdir, interval=args.interval, once=args.once, notify=not args.no_notify)


def register(sub) -> None:
    s = sub.add_parser("watch", help="live interactive terminal dashboard and progress monitor")
    s.add_argument("--interval", type=float, default=5.0, help="refresh interval in seconds (default: 5.0)")
    s.add_argument("--once", action="store_true", help="print dashboard once and exit")
    s.add_argument("--no-notify", action="store_true", help="do not trigger macOS notification on finish")
    s.add_argument("--project", default=argparse.SUPPRESS)
    s.set_defaults(fn=cmd_watch)
