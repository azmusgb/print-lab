"""`lab sync`: push the project's read-only projection (`build_index`, plus the spool colours `lab page` saved in
page.json) and its new photos to Local AI, so the lab page is on the phone too (spec: docs/superpowers/specs/2026-10-24-print-lab-slim-1b-design.md).

The Mac stays the record: Local AI stores what it's sent and never writes back. Photos go up once each, named by
their sha256. Every attempt is written to <project>/sync.json, which `lab status` shows. Commands that change a record
start a sync in the background (`background`); LAB_SYNC=off turns that off.
"""
import hashlib
import json
import os
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from lab.page_index import build_index
from lab.records.store import atomic_write_json, now

HOME = Path.home() / ".claude" / "localai-chat"
BASE = "https://10.0.0.21"
HUB_URL = "https://home.home.arpa"
LOCALAI_HEADER, HUB_HEADER = "X-LocalAI-Mac-Key", "X-Hub-Mac-Key"


@dataclass(frozen=True)
class Target:
    """One place the lab page lives. Each has its own address, its own trust and its own key header."""
    name: str
    base: str
    header: str
    key: str
    context: ssl.SSLContext | None


def _clean_key(text: str, name: str) -> str:
    """A key is printable ASCII with no whitespace. Anything else (an inner newline, a control character) would make
    http.client raise an error that quotes the key, so it is refused here, by file name and never by content."""
    key = text.strip()
    if key and not all(0x21 <= ord(c) <= 0x7E for c in key):
        raise ValueError(f"The {name} key file has characters a key can't contain.")
    return key


def _key() -> str:
    return _clean_key(Path(os.environ.get("LAB_LOCALAI_KEY_FILE", HOME / "mac.key")).read_text(), "Local AI")


def _context(base: str):
    if not base.startswith("https://"):
        return None
    ca = Path(os.environ.get("LAB_LOCALAI_CA", HOME / "localai-ca.crt"))
    return ssl.create_default_context(cafile=str(ca)) if ca.exists() else ssl.create_default_context()


class RemoteError(Exception):
    """A target couldn't be asked something it had to answer; the text is what to show the owner."""


def localai_base(base: str | None = None) -> str:
    """Local AI's address: the one given, else LAB_LOCALAI_URL, else the default. Telemetry always uses this."""
    return (base or os.environ.get("LAB_LOCALAI_URL") or BASE).rstrip("/")


def localai_target(base: str | None = None) -> Target:
    base = localai_base(base)
    return Target("Local AI", base, LOCALAI_HEADER, _key(), _context(base))


def hub_target() -> Target | None:
    """The Pi Hub, or None when this Mac has no hub key (not set up: not a failure). A set-up hub that can't be
    reached safely raises ValueError: plain http, no saved house CA, or an empty key."""
    key_file = Path(os.environ.get("LAB_HUB_KEY_FILE") or Path.home() / ".config" / "print-lab" / "hub.key")
    if not key_file.exists():
        return None
    base = (os.environ.get("LAB_HUB_URL") or HUB_URL).rstrip("/")
    if not base.startswith("https://"):
        raise ValueError("The Pi Hub address must start with https://")
    ca = Path(os.environ.get("LAB_HUB_CA") or Path.home() / ".config" / "print-lab" / "home-ca.crt")
    if not ca.is_file():
        raise ValueError("Save the house CA first: curl -o ~/.config/print-lab/home-ca.crt "
                         "https://home.home.arpa/home-ca.crt")
    key = _clean_key(key_file.read_text(), "Pi Hub")
    if not key:
        raise ValueError("The Pi Hub key file is empty.")
    try:
        context = ssl.create_default_context(cafile=str(ca))  # only the house CA: never the system store
    except (ssl.SSLError, OSError) as e:
        raise ValueError(f"The house CA file can't be used ({e})") from e
    return Target("Pi Hub", base, HUB_HEADER, key, context)


def targets(base: str | None = None) -> list:
    """Local AI, then the Pi Hub when set up. A target that can't be built is (name, message), not a raise, so the
    caller records it as that target's failure. An explicit base means Local AI at that address only."""
    if base:
        return [localai_target(base)]
    out: list = []
    try:
        out.append(localai_target())
    except (OSError, ValueError) as e:
        out.append(("Local AI", f"No Local AI key ({getattr(e, 'strerror', None) or e})"))
    try:
        hub = hub_target()
    except (OSError, ValueError) as e:
        hub = ("Pi Hub", str(e))
    if hub:
        out.append(hub)
    return out


def _error(body: dict, code: int) -> str:
    """Local AI says {"error"}, the Pi Hub (FastAPI) says {"detail"}."""
    msg = body.get("error") or body.get("detail") if isinstance(body, dict) else None
    return (msg if isinstance(msg, str) else json.dumps(msg) if msg else f"HTTP {code}")[:200]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A keyed request is never re-sent somewhere else: a 3xx is an error, not a hop."""
    def redirect_request(self, *a, **k):
        return None


def _open(req, timeout, context):
    """urlopen for keyed requests: verified TLS context, redirects refused."""
    opener = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPSHandler(context=context))
    return opener.open(req, timeout=timeout)


def _call(target: Target, method, path, timeout, body: bytes | None = None, ctype="application/json"):
    """One request carrying exactly one key header: the target's own. A 3xx comes back as (code, {}) so the caller
    reports `HTTP <code>`."""
    req = urllib.request.Request(
        target.base + path, data=body, method=method,
        headers={target.header: target.key, **({"Content-Type": ctype} if body else {})}
    )
    try:
        with _open(req, timeout, target.context) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        if 300 <= e.code < 400:
            return e.code, {}
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}


def _record(pdir: Path, result: dict) -> dict:
    atomic_write_json(pdir / "sync.json", {**result, "at": now()})
    return result


def _sync_to_target(pdir: Path, target: Target, ix: dict, timeout: float = 10) -> dict:
    project = ix["project"]
    try:
        st, have = _call(target, "GET", f"/api/lab/{project}/photos", timeout)
        if st != 200:
            return {"ok": False, "message": _error(have, st)}
        have = set(have.get("have") or [])
        sent = 0
        for x in ix.get("experiments", []):
            for p in x.get("photos", []):
                if p.get("sha256") and p["sha256"] not in have:
                    photo_file = pdir / p["path"]
                    if not photo_file.exists():
                        return {"ok": False, "message": f"photo file missing: {p['path']}", "photos_sent": sent}
                    st, body = _call(target, "PUT", f"/api/lab/{project}/photos/{p['sha256']}.jpg", timeout,
                                     photo_file.read_bytes(), "image/jpeg")
                    if st != 200:
                        return {"ok": False, "message": _error(body, st), "photos_sent": sent}
                    have.add(p["sha256"])
                    sent += 1
        st, body = _call(target, "POST", f"/api/lab/{project}/sync", timeout, json.dumps(ix).encode())
        if st != 200:
            return {"ok": False, "message": _error(body, st), "photos_sent": sent}
        return {"ok": True, "message": "synced", "photos_sent": sent,
                **{k: body[k] for k in ("upserted", "removed", "unchanged") if k in body}}
    except (OSError, ValueError) as e:
        reason = getattr(e, "reason", None) or e
        return {"ok": False, "message": f"{target.name} didn't answer ({reason})"[:200]}


def _why(e: Exception) -> str:
    return str(getattr(e, "reason", None) or e) or type(e).__name__


def sync(pdir: Path, base: str | None = None, timeout: float = 10) -> dict:
    """Apply what each target has pending, then push the index to each, one result per target. `ok` is true only
    when every target is. One target's failure of any kind never stops the others."""
    pdir = Path(pdir)
    try:
        ts = targets(base)
    except (OSError, ValueError) as e:  # an explicit base whose key is missing
        return _record(pdir, {"ok": False, "message": f"Sync failed ({_why(e)})"[:200], "photos_sent": 0,
                              "targets": {}})
    results: dict[str, dict] = {}
    live: list[Target] = []
    for t in ts:
        if isinstance(t, tuple):
            results[t[0]] = {"ok": False, "message": t[1][:200]}
            continue
        if os.environ.get("LAB_SYNC", "on") != "off":
            from lab.pull import apply_pending
            try:
                applied = apply_pending(pdir, t, timeout)
                if any(r.get("status") == "applied" for r in applied):
                    from lab.page import refresh
                    refresh(pdir)
            except RemoteError as e:
                results[t.name] = {"ok": False, "message": str(e)[:200]}
                continue
            except Exception as e:
                print(f"lab sync: {t.name}: {type(e).__name__}: {e}", file=sys.stderr)
                results[t.name] = {"ok": False, "message": f"{t.name} failed ({_why(e)})"[:200]}
                continue
        live.append(t)

    if live:
        try:
            ix = build_index(pdir)
            try:
                saved = json.loads((pdir / "page.json").read_text())
            except (OSError, ValueError):
                saved = {}
            ix["colours"] = saved.get("colours") or {}
            ix["outside"] = saved.get("outside") or []
            if ix["outside"]:  # Remote skips a push whose fingerprint it has, so the list is part of it
                whole = json.dumps(ix["outside"], sort_keys=True)
                ix["fingerprint"] += ":o" + hashlib.sha256(whole.encode()).hexdigest()[:12]
        except Exception as e:  # nothing to push to anyone
            print(f"lab sync: building the index failed: {type(e).__name__}: {e}", file=sys.stderr)
            for t in live:
                results[t.name] = {"ok": False, "message": f"Sync failed ({_why(e)})"[:200]}
            live = []
        for t in live:
            try:
                results[t.name] = _sync_to_target(pdir, t, ix, timeout)
            except Exception as e:
                print(f"lab sync: {t.name}: {type(e).__name__}: {e}", file=sys.stderr)
                results[t.name] = {"ok": False, "message": f"{t.name} failed ({_why(e)})"[:200]}

    ordered = {(t[0] if isinstance(t, tuple) else t.name): results[t[0] if isinstance(t, tuple) else t.name]
               for t in ts}
    failed = [f"{n}: {r['message']}" for n, r in ordered.items() if not r["ok"]]
    return _record(pdir, {"ok": not failed, "message": "; ".join(failed) or "synced",
                          "photos_sent": sum(r.get("photos_sent", 0) for r in ordered.values()),
                          "targets": ordered})


def status(pdir: Path) -> dict | None:
    try:
        return json.loads((Path(pdir) / "sync.json").read_text())
    except (OSError, ValueError):
        return None


def fetch_workshop_status(base: str | None = None, timeout: float = 2.0) -> dict | None:
    """Fetch live printer/workshop status from Local AI. Returns None on network error or missing key."""
    try:
        st, data = _call(localai_target(base), "GET", "/api/workshop/status", timeout)
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
    for name, t in (r.get("targets") or {}).items():
        print(f"{name}: {t['message']}" + (f" ({t.get('photos_sent', 0)} photos sent)" if t["ok"] else ""))
    if not r.get("targets"):
        print(r["message"])
    return 0 if r["ok"] else 1


def register(sub) -> None:
    s = sub.add_parser("sync", help="push the lab page's data and new photos to Local AI and Pi Hub (read-only there)")
    s.set_defaults(fn=cmd_sync)


if __name__ == "__main__":
    sync(Path(sys.argv[1]))
