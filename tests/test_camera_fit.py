"""The camera-fit page's server, against a fake PhoneBridge (Fusion itself isn't needed)."""
import importlib.util
import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parents[1] / "tools" / "camera_fit" / "server.py"
PNG = b"\x89PNG\r\n\x1a\nfake"


def _load():
    spec = importlib.util.spec_from_file_location("camera_fit_server", SERVER)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class FakeFusion(BaseHTTPRequestHandler):
    params = {}
    failed = []
    sets = []

    def log_message(self, format, *args):
        pass

    def _send(self, code, body, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/params":
            return self._send(200, json.dumps([{"name": k, "expression": v[0], "value_mm": None, "unit": "mm", "comment": v[1]}
                                               for k, v in self.params.items()]).encode())
        if self.path == "/status":
            return self._send(200, json.dumps({"document": "camera_carrier v5", "unsaved": False, "failed": self.failed,
                                               "volume_mm3": 1234.5, "busy": False}).encode())
        if self.path.startswith("/shot"):
            return self._send(200, PNG, "image/png")
        self._send(404, b"{}")

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeFusion.sets.append(body)
        before = self.params[body["name"]][0]
        self.params[body["name"]] = (body["expression"], self.params[body["name"]][1])
        self._send(200, json.dumps({"name": body["name"], "before": before, "after": body["expression"], "failed": self.failed}).encode())


@pytest.fixture
def app(tmp_path):
    m = _load()
    FakeFusion.params = {
        "board_x": ("25 mm", "PCB size along x (UC-685 drawing, provisional)"),
        "board_t": ("1.6 mm", "PCB thickness"),  # measured, not provisional: read-only
        "carrier_margin": ("3 mm", "carrier margin around the board (placeholder)"),
        "carrier_x": ("board_x + 2 * carrier_margin", "carrier plate x"),  # derived: read-only
        "stand_x": ("84 mm", "stand base x (README figure)"),
        "knob_d": ("20 mm", "tilt knob diameter (placeholder)"),
    }
    FakeFusion.failed = []
    FakeFusion.sets = []
    fusion = ThreadingHTTPServer(("127.0.0.1", 0), FakeFusion)
    threading.Thread(target=fusion.serve_forever, daemon=True).start()
    m.BRIDGE = f"http://127.0.0.1:{fusion.server_address[1]}"
    m.DATA = tmp_path
    m._start.clear()
    m.Handler.token = "tok123"
    srv = ThreadingHTTPServer(("127.0.0.1", 0), m.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield m, f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    fusion.shutdown()


def get(base, path, token="tok123"):
    return urllib.request.urlopen(f"{base}{path}{'&' if '?' in path else '?'}t={token}")


def post(base, path, body, token="tok123"):
    req = urllib.request.Request(f"{base}{path}?t={token}", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req)


def code(fn):
    try:
        fn()
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())
    raise AssertionError("expected an HTTP error")


def test_no_token_or_a_wrong_token_gets_nothing(app):
    _, base = app
    assert code(lambda: urllib.request.urlopen(f"{base}/api/state"))[0] == 401
    assert code(lambda: get(base, "/api/state", token="nope"))[0] == 401
    assert code(lambda: post(base, "/api/set", {"name": "board_x", "value": 24}, token="nope"))[0] == 401
    assert FakeFusion.sets == []


def test_only_provisional_plain_values_are_editable(app):
    _, base = app
    s = json.load(get(base, "/api/state"))
    assert [p["name"] for p in s["params"]] == ["board_x", "carrier_margin", "knob_d"]
    assert {d["name"] for d in s["derived"]} == {"board_t", "carrier_x", "stand_x"}
    assert s["params"][0]["lo"] == 12.5 and s["params"][0]["hi"] == 50.0
    assert s["status"]["document"] == "camera_carrier v5"


def test_a_change_goes_to_fusion_as_a_plain_mm_expression_and_is_logged(app):
    m, base = app
    r = json.load(post(base, "/api/set", {"name": "board_x", "value": 24.456}))
    assert FakeFusion.sets == [{"name": "board_x", "expression": "24.46 mm"}]
    assert r["before"] == "25 mm" and r["after"] == "24.46 mm"
    assert json.loads((m.DATA / "changes.log").read_text().splitlines()[0])["name"] == "board_x"


@pytest.mark.parametrize("name,value", [("board_x", 5), ("board_x", 999), ("board_x", "24"), ("board_x", True), ("board_x", None),
                                        ("board_t", 1.5), ("carrier_x", 30), ("stand_x", 80), ("nope", 1)])
def test_out_of_range_derived_measured_and_unknown_are_refused_before_fusion(app, name, value):
    _, base = app
    assert code(lambda: post(base, "/api/set", {"name": name, "value": value}))[0] == 422
    assert FakeFusion.sets == []


def test_back_to_start_restores_the_first_seen_value_even_after_changes(app):
    _, base = app
    get(base, "/api/state")
    post(base, "/api/set", {"name": "knob_d", "value": 22})
    post(base, "/api/set", {"name": "knob_d", "value": 18})
    post(base, "/api/reset", {"name": "knob_d"})
    assert FakeFusion.sets[-1] == {"name": "knob_d", "expression": "20.0 mm"}
    assert FakeFusion.params["knob_d"][0] == "20.0 mm"


def test_the_range_stays_anchored_to_the_start_after_a_change(app):
    _, base = app
    get(base, "/api/state")
    post(base, "/api/set", {"name": "knob_d", "value": 30})
    p = next(p for p in json.load(get(base, "/api/state"))["params"] if p["name"] == "knob_d")
    assert (p["start"], p["lo"], p["hi"], p["value"]) == (20.0, 10.0, 40.0, 30.0)


def test_failed_steps_from_fusion_are_passed_on(app):
    _, base = app
    FakeFusion.failed = ["screw_posts: the sketch lost a reference"]
    assert json.load(post(base, "/api/set", {"name": "knob_d", "value": 21}))["failed"] == FakeFusion.failed
    assert json.load(get(base, "/api/state"))["status"]["failed"] == FakeFusion.failed


def test_the_picture_and_the_page_are_served_and_a_bad_view_is_refused(app):
    _, base = app
    assert get(base, "/api/shot?view=top&w=400&h=300").read() == PNG
    assert code(lambda: get(base, "/api/shot?view=underneath"))[0] == 422
    assert b"Camera carrier fit" in get(base, "/").read()


def test_a_fusion_that_is_not_running_is_said_plainly(app):
    m, base = app
    m.BRIDGE = "http://127.0.0.1:9"
    status, body = code(lambda: get(base, "/api/state"))
    assert status == 502 and "Fusion isn't answering" in body["error"]


def test_an_oversized_or_malformed_body_is_refused(app):
    _, base = app
    assert code(lambda: post(base, "/api/set", {"name": "knob_d", "value": 1, "pad": "x" * 5000}))[0] == 413
    assert code(lambda: post(base, "/api/set", ["knob_d"]))[0] == 422
