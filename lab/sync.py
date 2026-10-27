"""`lab sync`: push the project's read-only projection (`build_index`, plus the spool colours `lab page` saved in
page.json) and its new photos to Local AI, so the lab page is on the phone too (spec: docs/superpowers/specs/2026-10-24-print-lab-slim-1b-design.md).

The Mac stays the record: Local AI stores what it's sent and never writes back. Photos go up once each, named by
their sha256. Every attempt is written to <project>/sync.json, which `lab status` shows. Commands that change a record
start a sync in the background (`background`); LAB_SYNC=off turns that off.
"""
import json
import os
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from lab.page_index import build_index
from lab.records.store import atomic_write_json, now

HOME = Path.home() / ".claude" / "localai-chat"
BASE = "https://10.0.0.21"


def _key() -> str:
    return Path(os.environ.get("LAB_LOCALAI_KEY_FILE", HOME / "mac.key")).read_text().strip()


def _context(base: str):
    if not base.startswith("https://"):
        return None
    ca = Path(os.environ.get("LAB_LOCALAI_CA", HOME / "localai-ca.crt"))
    return ssl.create_default_context(cafile=str(ca)) if ca.exists() else ssl.create_default_context()


def _call(base, method, path, key, timeout, body: bytes | None = None, ctype="application/json"):
    req = urllib.request.Request(base + path, data=body, method=method,
                                 headers={"X-LocalAI-Mac-Key": key, **({"Content-Type": ctype} if body else {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_context(base)) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}


def _record(pdir: Path, result: dict) -> dict:
    atomic_write_json(pdir / "sync.json", {**result, "at": now()})
    return result


def sync(pdir: Path, base: str | None = None, timeout: float = 10) -> dict:
    pdir = Path(pdir)
    base = (base or os.environ.get("LAB_LOCALAI_URL") or BASE).rstrip("/")
    try:
        key = _key()
        if os.environ.get("LAB_SYNC", "on") != "off":
            from lab.pull import apply_pending
            applied = apply_pending(pdir, base, key, timeout)
            if any(r.get("status") == "applied" for r in applied):
                from lab.page import refresh
                refresh(pdir)
        ix = build_index(pdir)
        try:
            ix["colours"] = json.loads((pdir / "page.json").read_text()).get("colours") or {}
        except (OSError, ValueError):
            ix["colours"] = {}
        project = ix["project"]
        _, have = _call(base, "GET", f"/api/lab/{project}/photos", key, timeout)
        have = set(have.get("have") or [])
        sent = 0
        for x in ix["experiments"]:
            for p in x["photos"]:
                if p.get("sha256") and p["sha256"] not in have:
                    st, body = _call(base, "PUT", f"/api/lab/{project}/photos/{p['sha256']}.jpg", key, timeout,
                                     (pdir / p["path"]).read_bytes(), "image/jpeg")
                    if st != 200:
                        return _record(pdir, {"ok": False, "message": body.get("error") or f"photo upload: HTTP {st}"})
                    have.add(p["sha256"])
                    sent += 1
        st, body = _call(base, "POST", f"/api/lab/{project}/sync", key, timeout, json.dumps(ix).encode())
        if st != 200:
            return _record(pdir, {"ok": False, "message": body.get("error") or f"HTTP {st}", "photos_sent": sent})
        return _record(pdir, {"ok": True, "message": "synced", "photos_sent": sent,
                              **{k: body[k] for k in ("upserted", "removed", "unchanged") if k in body}})
    except (OSError, ValueError) as e:  # no key, no network, a TLS problem
        reason = getattr(e, "reason", None) or e
        return _record(pdir, {"ok": False, "message": f"Local AI didn't answer ({reason})"[:200]})


def status(pdir: Path) -> dict | None:
    try:
        return json.loads((Path(pdir) / "sync.json").read_text())
    except (OSError, ValueError):
        return None


def fetch_workshop_status(base: str | None = None, timeout: float = 2.0) -> dict | None:
    """Fetch live printer/workshop status from Local AI. Returns None on network error or missing key."""
    base = (base or os.environ.get("LAB_LOCALAI_URL") or BASE).rstrip("/")
    try:
        key = _key()
        st, data = _call(base, "GET", "/api/workshop/status", key, timeout)
        if st == 200 and isinstance(data, dict):
            return data
    except Exception:
        pass
    return None


def background(pdir: Path) -> None:
    """Start a sync that outlives the command and never slows or fails it."""
    if os.environ.get("LAB_SYNC", "on") == "off":
        return
    subprocess.Popen([sys.executable, "-m", "lab.sync", str(pdir)], start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)


def cmd_sync(args) -> int:
    from lab.cli import project_dir
    r = sync(project_dir(args.project))
    print(f"Local AI: {r['message']}" + (f" ({r.get('photos_sent', 0)} photos sent)" if r["ok"] else ""))
    return 0 if r["ok"] else 1


def register(sub) -> None:
    s = sub.add_parser("sync", help="push the lab page's data and new photos to Local AI (read-only there)")
    s.set_defaults(fn=cmd_sync)


if __name__ == "__main__":
    sync(Path(sys.argv[1]))
