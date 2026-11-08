"""Camera-fit page: finish the camera_carrier Fusion model from an iPhone on the home network.

    python tools/camera_fit/server.py            # prints the URL (with its token) to open on the iPhone

The page shows Fusion's own pictures of the model and sliders for its placeholder parameters. This server holds the token,
the allow-list and the ranges, and forwards each change to the PhoneBridge add-in inside Fusion (127.0.0.1:8766). It never
saves the Fusion document. Standard library only; every request needs the token."""
import argparse
import json
import os
import re
import secrets
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
BRIDGE = "http://127.0.0.1:8766"
MAX_BODY = 4096
BRIDGE_TOKEN = ""  # shared with the add-in through data/bridge-token
HARD_MAX_MM = 300.0
_lock = threading.Lock()  # one change at a time; Fusion recomputes after each
_start: dict[str, str] = {}  # parameter -> its expression when this server first saw it, for "Back to start"
PLAIN = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*mm\s*$")
EDITABLE_WORDS = ("placeholder", "provisional", "verify", "check on the real")
READONLY = {"coupon_x", "stand_x", "stand_y"}  # figures taken from a README, not design choices


def bridge(path: str, body: dict | None = None, timeout: int = 25) -> bytes:
    req = urllib.request.Request(BRIDGE + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "X-Bridge-Token": BRIDGE_TOKEN})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def editable(p: dict) -> dict | None:
    """A parameter the page may change: a plain 'N mm' value whose comment says it is still provisional.
    Its range is half to double its first-seen value, capped; anything derived (carrier_x = board_x + ...) stays read-only."""
    m = PLAIN.match(_start.get(p["name"]) or p["expression"] or "")
    if not m or p["name"] in READONLY or not any(w in (p["comment"] or "").lower() for w in EDITABLE_WORDS):
        return None
    base = float(m.group(1))
    return {"name": p["name"], "comment": p["comment"], "start": base,
            "lo": round(max(base * 0.5, 0.2), 2), "hi": round(min(max(base * 2, base + 2), HARD_MAX_MM), 2)}


def state() -> dict:
    params = json.loads(bridge("/params"))
    for p in params:
        _start.setdefault(p["name"], p["expression"])
    out = []
    for p in params:
        e = editable(p)
        if e:
            m = PLAIN.match(p["expression"])
            e["value"] = float(m.group(1)) if m else None
            out.append(e)
    return {"params": out, "derived": [{"name": p["name"], "expression": p["expression"], "value_mm": p["value_mm"]}
                                       for p in params if not editable(p)],
            "status": json.loads(bridge("/status"))}


def change(name: str, value) -> dict:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
        raise ValueError("value must be a number")
    cur = {p["name"]: p for p in json.loads(bridge("/params"))}
    for p in cur.values():
        _start.setdefault(p["name"], p["expression"])
    e = editable(cur[name]) if name in cur else None
    if not e:
        raise ValueError("that parameter can't be changed from here")
    if not e["lo"] <= value <= e["hi"]:
        raise ValueError(f"{name} must be between {e['lo']} and {e['hi']} mm")
    with _lock:
        out = json.loads(bridge("/set", {"name": name, "expression": f"{round(float(value), 2)} mm"}))
    DATA.mkdir(exist_ok=True)
    with open(DATA / "changes.log", "a") as f:
        f.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **out}) + "\n")
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "camera-fit"
    token = ""

    def log_message(self, format, *args):
        pass  # no URLs in logs: they carry the token

    def _send(self, code, body: bytes, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj).encode())

    def _authed(self) -> bool:
        q = parse_qs(urlparse(self.path).query)
        supplied = (q.get("t") or [""])[0] or self.headers.get("X-Token", "")
        return secrets.compare_digest(supplied, self.token)

    def _bridge_error(self, e: Exception):
        if isinstance(e, urllib.error.HTTPError):
            try:
                return self._json(HTTPStatus.BAD_GATEWAY, json.loads(e.read()))
            except ValueError:
                pass
        self._json(HTTPStatus.BAD_GATEWAY, {"error": "Fusion isn't answering. Is camera_carrier open and the PhoneBridge add-in running?"})

    def do_GET(self):
        u = urlparse(self.path)
        if not self._authed():
            return self._json(HTTPStatus.UNAUTHORIZED, {"error": "Open the link printed by the server; it carries the token."})
        if u.path == "/":
            return self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        try:
            if u.path == "/api/state":
                return self._json(200, state())
            if u.path == "/api/shot":
                q = parse_qs(u.query)
                view = (q.get("view") or ["iso"])[0]
                if view not in ("iso", "front", "top", "right", "back"):
                    return self._json(422, {"error": "unknown view"})
                w = max(200, min(int((q.get("w") or ["800"])[0]), 1600))
                h = max(200, min(int((q.get("h") or ["600"])[0]), 1600))
                return self._send(200, bridge(f"/shot?view={view}&w={w}&h={h}", timeout=30), "image/png")
        except ValueError:
            return self._json(422, {"error": "bad size"})
        except (urllib.error.URLError, OSError) as e:
            return self._bridge_error(e)
        self._json(404, {"error": "not found"})

    def do_POST(self):
        if not self._authed():
            return self._json(HTTPStatus.UNAUTHORIZED, {"error": "bad token"})
        path = urlparse(self.path).path
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if not 0 < n <= MAX_BODY:
                return self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "bad length"})
            body = json.loads(self.rfile.read(n))
            if not isinstance(body, dict) or not isinstance(body.get("name"), str):
                raise ValueError("send {name, value}")
            if path == "/api/set":
                return self._json(200, change(body["name"], body.get("value")))
            if path == "/api/reset":
                p = {q["name"]: q for q in json.loads(bridge("/params"))}.get(body["name"])
                if not p or not editable(p) or body["name"] not in _start:
                    raise ValueError("nothing to go back to")
                m = PLAIN.match(_start[body["name"]])
                if not m:
                    raise ValueError("nothing to go back to")
                return self._json(200, change(body["name"], float(m.group(1))))
        except (ValueError, KeyError, TypeError) as e:
            return self._json(422, {"error": str(e)})
        except (urllib.error.URLError, OSError) as e:
            return self._bridge_error(e)
        self._json(404, {"error": "not found"})


def addresses() -> list[str]:
    out = []
    for iface in ("en0", "en1"):
        r = subprocess.run(["ipconfig", "getifaddr", iface], capture_output=True, text=True)
        if r.stdout.strip():
            out.append(r.stdout.strip())
    return out or [socket.gethostbyname(socket.gethostname())]


def main() -> None:
    global BRIDGE, BRIDGE_TOKEN
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="0.0.0.0", help="0.0.0.0 reaches the iPhone on the home network; 127.0.0.1 for the Mac only")
    ap.add_argument("--bridge", default=BRIDGE, help="the PhoneBridge add-in's address (tests point it at a fake)")
    a = ap.parse_args()
    BRIDGE = a.bridge
    DATA.mkdir(exist_ok=True)
    tokfile = DATA / "token"
    if not tokfile.is_file():
        tokfile.write_text(secrets.token_urlsafe(16))
        os.chmod(tokfile, 0o600)
    Handler.token = tokfile.read_text().strip()
    bt = DATA / "bridge-token"
    if not bt.is_file():
        bt.write_text(secrets.token_urlsafe(24))
        os.chmod(bt, 0o600)
    BRIDGE_TOKEN = bt.read_text().strip()
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    for ip in addresses() if a.host == "0.0.0.0" else [a.host]:
        print(f"open on the iPhone:  http://{ip}:{a.port}/?t={Handler.token}")
    print("Ctrl+C to stop. Changes are logged to", DATA / "changes.log")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
