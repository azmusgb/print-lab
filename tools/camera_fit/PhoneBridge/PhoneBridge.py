"""PhoneBridge (Fusion add-in): lets the Mac-hosted camera-fit page read and edit the active design's user parameters.

It listens on 127.0.0.1 only (port 38117); the page's server on the Mac is the one thing that talks to it, and it adds the
token, the allow-list and the ranges. Every Fusion call runs on Fusion's main thread through a custom event, as the API
requires. It reads parameters, takes a viewport picture and changes ONE user parameter's expression per request, as one
undoable command; it never saves, closes or exports anything."""
import json
import os
import queue
import re
import secrets
import tempfile
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import adsk.core
import adsk.fusion

PORT = 38117
TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "bridge-token")
HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
PLAIN = re.compile(r"^\d+(?:\.\d+)? mm$")
EVENT_ID = "PhoneBridgeCall"
VIEWS = {
    "iso": adsk.core.ViewOrientations.IsoTopRightViewOrientation,
    "front": adsk.core.ViewOrientations.FrontViewOrientation,
    "top": adsk.core.ViewOrientations.TopViewOrientation,
    "right": adsk.core.ViewOrientations.RightViewOrientation,
    "back": adsk.core.ViewOrientations.BackViewOrientation,
}

_app = None
_server = None
_event = None
_handler = None
_calls: "queue.Queue[dict]" = queue.Queue()


def _design():
    d = adsk.fusion.Design.cast(_app.activeProduct)
    if d is None:
        raise RuntimeError("The active document is not a design.")
    return d


def _params():
    d = _design()
    out = []
    for p in d.userParameters:
        out.append({"name": p.name, "expression": p.expression, "value_mm": round(p.value * 10, 4) if p.unit == "mm" else None,
                    "unit": p.unit, "comment": p.comment})
    return out


def _health(d):
    bad = []
    for i in range(d.timeline.count):
        it = d.timeline.item(i)
        if it.healthState != adsk.fusion.FeatureHealthStates.HealthyFeatureHealthState:
            bad.append(f"{it.name}: {it.errorOrWarningMessage}")
    return bad


def _status():
    d = _design()
    vol = 0.0
    for b in d.rootComponent.bRepBodies:
        if b.isVisible and b.isSolid:
            vol += b.volume
    for o in d.rootComponent.allOccurrences:
        for b in o.bRepBodies:
            if b.isVisible and b.isSolid:
                vol += b.volume
    return {"document": _app.activeDocument.name, "unsaved": _app.activeDocument.isModified, "failed": _health(d),
            "volume_mm3": round(vol * 1000, 1), "busy": _app.userInterface.activeCommand not in ("", "SelectCommand")}


def _set(name, expression):
    d = _design()
    p = d.userParameters.itemByName(name)
    if p is None:
        raise ValueError("no such parameter")
    before = p.expression
    if not p.expression == expression:
        p.expression = expression
    return {"name": name, "before": before, "after": p.expression, "failed": _health(d)}


def _shot(view, w, h):
    vp = _app.activeViewport
    vp.viewOrientation = VIEWS[view]
    vp.fit()
    path = os.path.join(tempfile.gettempdir(), f"phonebridge-{os.getpid()}.png")
    if not vp.saveAsImageFile(path, w, h):
        raise RuntimeError("Fusion couldn't save the view.")
    with open(path, "rb") as f:
        data = f.read()
    os.unlink(path)
    return data


class _Main(adsk.core.CustomEventHandler):
    """Runs on the main thread: takes one queued call, does it, hands back the result."""

    def notify(self, args):
        try:
            call = _calls.get_nowait()
        except queue.Empty:
            return
        try:
            if call["op"] == "params":
                call["result"] = _params()
            elif call["op"] == "status":
                call["result"] = _status()
            elif call["op"] == "set":
                call["result"] = _set(call["name"], call["expression"])
            elif call["op"] == "shot":
                call["result"] = _shot(call["view"], call["w"], call["h"])
        except Exception as e:  # reported to the caller, never swallowed
            call["error"] = f"{type(e).__name__}: {e}"
        finally:
            call["done"].set()


def _ask(**call):
    call["done"] = threading.Event()
    _calls.put(call)
    _app.fireCustomEvent(EVENT_ID, "")
    if not call["done"].wait(20):
        raise TimeoutError("Fusion didn't answer in 20 s (is a command open?).")
    if "error" in call:
        raise RuntimeError(call["error"])
    return call["result"]


class _Http(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send(self, code, body, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj).encode())

    def _allowed(self) -> bool:
        """Only the page's server: right Host (no DNS rebinding), no Origin (a browser page always sends one on a
        cross-site POST), and the shared secret the server keeps in data/bridge-token."""
        if self.headers.get("Host") not in HOSTS or self.headers.get("Origin") is not None:
            return False
        try:
            with open(TOKEN_FILE) as f:
                want = f.read().strip()
        except OSError:
            return False
        return bool(want) and secrets.compare_digest(self.headers.get("X-Bridge-Token", ""), want)

    def do_GET(self):
        if not self._allowed():
            return self._json(403, {"error": "not allowed"})
        from urllib.parse import parse_qs, urlparse
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path == "/params":
                return self._json(200, _ask(op="params"))
            if u.path == "/status":
                return self._json(200, _ask(op="status"))
            if u.path == "/shot":
                view = (q.get("view") or ["iso"])[0]
                if view not in VIEWS:
                    return self._json(422, {"error": "unknown view"})
                w = max(200, min(int((q.get("w") or ["800"])[0]), 1600))
                h = max(200, min(int((q.get("h") or ["600"])[0]), 1600))
                return self._send(200, _ask(op="shot", view=view, w=w, h=h), "image/png")
        except (RuntimeError, TimeoutError, ValueError) as e:
            return self._json(502, {"error": str(e)})
        self._json(404, {"error": "not found"})

    def do_POST(self):
        if not self._allowed():
            return self._json(403, {"error": "not allowed"})
        if self.path != "/set":
            return self._json(404, {"error": "not found"})
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            return self._json(415, {"error": "send application/json"})
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if not 0 < n < 4096:
                raise ValueError("bad length")
            body = json.loads(self.rfile.read(n))
            name, expr = body["name"], body["expression"]
            if not isinstance(name, str) or not isinstance(expr, str) or not PLAIN.match(expr):
                raise ValueError("the expression must be a plain number of mm, like 24.5 mm")
            return self._json(200, _ask(op="set", name=name, expression=expr))
        except (KeyError, ValueError, TypeError) as e:
            return self._json(422, {"error": str(e)})
        except (RuntimeError, TimeoutError) as e:
            return self._json(502, {"error": str(e)})


def run(context):
    global _app, _server, _event, _handler
    _app = adsk.core.Application.get()
    ui = _app.userInterface
    try:
        _event = _app.registerCustomEvent(EVENT_ID)
        _handler = _Main()
        _event.add(_handler)
        _server = ThreadingHTTPServer(("127.0.0.1", PORT), _Http)
        threading.Thread(target=_server.serve_forever, daemon=True, name="phonebridge").start()
    except Exception:
        ui.messageBox("PhoneBridge failed to start:\n" + traceback.format_exc())


def stop(context):
    global _server
    try:
        if _server:
            _server.shutdown()
            _server.server_close()
            _server = None
        if _event and _handler:
            _event.remove(_handler)
        _app.unregisterCustomEvent(EVENT_ID)
    except Exception:
        _app.userInterface.messageBox("PhoneBridge failed to stop:\n" + traceback.format_exc())
