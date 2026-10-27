"""`lab page`: page.json for a project, drawn from `page_index.build_index`, plus the spool colours from Bambuddy. The
page itself lives in Local AI (Projects › Print lab), which `lab sync` keeps current; this file is what sync reads the
colours from, so commands that refresh it reuse the saved colours and never wait on the network
(spec: docs/superpowers/specs/2026-10-27-print-lab-one-home-design.md).

Spool colours come from Bambuddy (the household's spool inventory) when it answers: the experiment's filament text is
matched against each spool's colour name. LAB_BAMBUDDY_URL changes the address; "off" skips it. Bambuddy has sign-in
on, so the spool list is asked for with print-lab's own read-only API key, from ~/.config/bambuddy/print-lab-key
(LAB_BAMBUDDY_KEY_FILE changes the file). When Bambuddy doesn't answer or refuses, the colours saved in page.json are
kept. Commands that refresh the page reuse the saved colours, so they never wait on the network.
"""
import json
import os
import re
import urllib.request
from datetime import timezone
from pathlib import Path

from lab import bambuddy
from lab.page_index import build_index

NEUTRAL = "#8698b1"


def bambuddy_colours(url=None, timeout=2.0) -> dict | None:
    """Spool colour name (lower case) → '#rrggbb', from Bambuddy; {} when it's off, None when it doesn't answer or
    refuses (so the caller keeps what it had rather than wiping it)."""
    url = url if url is not None else bambuddy.base_url()
    if not url or url == "off":
        return {}
    key = bambuddy.key()
    req = urllib.request.Request(f"{url}/api/v1/inventory/spools", headers={"X-API-Key": key} if key else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            spools = json.load(r)
    except Exception:
        return None
    out = {}
    for s in spools if isinstance(spools, list) else []:
        name, rgba = (s.get("color_name") or "").strip().lower(), s.get("rgba") or ""
        if name and re.fullmatch(r"[0-9a-fA-F]{6}([0-9a-fA-F]{2})?", rgba):  # never anything else into a style
            out[name] = "#" + rgba[:6]
    return out


def spool_colour(filament: str, colours: dict) -> str:
    text = (filament or "").lower()
    for name in sorted(colours, key=len, reverse=True):  # "light matte terracotta" before "terracotta"
        if name in text and re.fullmatch(r"#[0-9a-fA-F]{6}", colours[name]):
            return colours[name]
    return NEUTRAL


def _utc(s):
    t = bambuddy.parse_time(s)
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if t else None


def outside_prints(log: list[dict], linked: set) -> list[dict]:
    """The 20 newest print-log entries no run in the project is linked to."""
    return [{"print": e["id"], "archive": e.get("archive_id"), "name": e.get("print_name"),
             "status_word": bambuddy.status_word(e.get("status")), "started": _utc(e.get("started_at")),
             "ended": _utc(e.get("completed_at"))}
            for e in log if e.get("id") is not None and e["id"] not in linked][:20]


def write(pdir: Path, colours: dict | None = None, outside: list | None = None) -> Path:
    """page.json (the index and the spool colours); a page.html left from before is removed so it can't mislead."""
    pdir = Path(pdir)
    if colours is None:
        colours = bambuddy_colours()
    if colours is None:  # Bambuddy didn't answer: keep the saved colours
        try:
            colours = json.loads((pdir / "page.json").read_text()).get("colours") or {}
        except (OSError, ValueError):
            colours = {}
    ix = build_index(pdir)
    ix["colours"] = colours
    if outside is None:
        log = bambuddy.print_log()
        if log is not None:
            linked = {r["print"]["id"] for e in ix["experiments"] for r in e["runs"] if r.get("print")}
            outside = outside_prints(log, linked)
    if outside is None:  # Bambuddy didn't answer: keep the saved list
        try:
            outside = json.loads((pdir / "page.json").read_text()).get("outside") or []
        except (OSError, ValueError):
            outside = []
    ix["outside"] = outside
    out = pdir / "page.json"
    out.write_text(json.dumps(ix, indent=1))
    (pdir / "page.html").unlink(missing_ok=True)
    return out


def refresh(pdir: Path) -> None:
    """After a command changed a record: rebuild page.json if there is one, reusing its saved spool colours."""
    pdir = Path(pdir)
    if not (pdir / "page.json").exists():
        return
    try:
        saved = json.loads((pdir / "page.json").read_text())
    except (OSError, ValueError):
        saved = {}
    write(pdir, saved.get("colours") or {}, saved.get("outside") or [])


def page_url() -> str:
    from lab.sync import BASE
    return (os.environ.get("LAB_LOCALAI_URL") or BASE).rstrip("/") + "/#/printLab"


def cmd_page(args) -> int:
    from lab.cli import project_dir
    pdir = project_dir(args.project)
    if not pdir.is_dir():
        raise FileNotFoundError(f"No project {args.project!r} at {pdir}.")
    out = write(pdir)
    print(f"Wrote {out}")
    print(f"Open the print lab: {page_url()}")
    if args.open:
        import webbrowser
        webbrowser.open(page_url())
    return 0


def register(sub) -> None:
    s = sub.add_parser("page", help="refresh page.json and the spool colours; the page itself is in Local AI")
    s.add_argument("--open", action="store_true", help="open the print lab page in Local AI")
    s.set_defaults(fn=cmd_page)
