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
    shots = []

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
        if self.path == "/components":
            return self._send(200, json.dumps([
                {"name": "carrier:1", "visible": True, "volume_mm3": 1500.0, "size_mm": [31, 29.86, 6]},
                {"name": "knob:1", "visible": True, "volume_mm3": 10.0, "size_mm": [1, 1, 1]},
                {"name": "tilt_knob:1", "visible": False, "volume_mm3": 900.5, "size_mm": [20, 20, 6]},
                {"name": "pivot_bolt:1", "visible": True, "volume_mm3": 294.1, "size_mm": [18.9, 7, 7]},
                {"name": "tilt_gauge:1", "visible": True, "volume_mm3": 2249.7, "size_mm": [60, 30, 1.6]}]).encode())
        if self.path.startswith("/shot"):
            FakeFusion.shots.append(self.path)
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
        "bolt_d": ("4 mm", "printed pivot bolt shank diameter"),  # a design choice, not provisional: read-only
        "gauge_r": ("30 mm", "printed tilt gauge radius"),  # a design choice, not provisional: read-only
    }
    FakeFusion.failed = []
    FakeFusion.sets = []
    FakeFusion.shots = []
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
    assert {d["name"] for d in s["derived"]} == {"board_t", "carrier_x", "stand_x", "bolt_d", "gauge_r"}
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


def test_the_walkthrough_ties_each_part_to_the_sizes_that_shape_it(app):
    _, base = app
    cs = {c["name"]: c for c in json.load(get(base, "/api/components"))}
    assert cs["carrier:1"]["editable"] == ["board_x", "carrier_margin"]  # board_t is measured: fixed, with carrier_x (derived)
    assert {f["name"] for f in cs["carrier:1"]["fixed"]} == {"board_t", "carrier_x"}
    assert cs["carrier:1"]["size_mm"] == [31, 29.86, 6] and cs["carrier:1"]["label"] == "carrier"
    assert cs["tilt_knob:1"]["editable"] == ["knob_d"] and cs["tilt_knob:1"]["visible"] is False
    assert cs["pivot_bolt:1"]["editable"] == [] and [f["name"] for f in cs["pivot_bolt:1"]["fixed"]] == ["bolt_d"]
    assert cs["tilt_gauge:1"]["editable"] == [] and [f["name"] for f in cs["tilt_gauge:1"]["fixed"]] == ["gauge_r"]
    assert cs["knob:1"]["editable"] == [] and cs["knob:1"]["fixed"] == []  # a part with no sizes tied to it says so, no guessing


def test_one_part_alone_is_asked_of_fusion_by_name_and_a_bad_name_is_refused(app):
    _, base = app
    assert get(base, "/api/shot?view=iso&only=tilt_knob%3A1").read() == PNG
    assert "only=tilt_knob%3A1" in FakeFusion.shots[-1]
    assert code(lambda: get(base, "/api/shot?view=iso&only=" + "a%3B%20rm" * 3))[0] == 422
    assert code(lambda: get(base, "/api/shot?view=iso&only=" + "x" * 70))[0] == 422


def test_the_guide_fills_in_current_values_and_checks_the_model(app):
    _, base = app
    g = json.load(get(base, "/api/guide"))
    assert g["live"] is True and [s["id"] for s in g["steps"]][:2] == ["board", "posts"]
    board = g["steps"][0]
    assert {c["name"]: c["expression"] for c in board["confirm"]}["board_x"] == "25 mm"
    assert {c["name"]: c["expression"] for c in board["confirm"]}["hole_dx"] is None  # not in this fake model: "not read", not invented
    clean = next(s for s in g["steps"] if s["id"] == "clean")
    assert clean["auto"] == {"ok": True, "text": "No failed steps in the model."}
    FakeFusion.failed = ["screw_posts: lost a reference"]
    assert next(s for s in json.load(get(base, "/api/guide"))["steps"] if s["id"] == "clean")["auto"]["ok"] is False


def test_the_guide_still_reads_with_fusion_closed(app):
    m, base = app
    m.BRIDGE = "http://127.0.0.1:9"
    g = json.load(get(base, "/api/guide"))
    assert g["live"] is False and len(g["steps"]) >= 6
    assert next(s for s in g["steps"] if s["id"] == "clean")["auto"]["ok"] is None


def test_progress_is_saved_and_only_known_things_can_be_saved(app):
    m, base = app
    post(base, "/api/progress", {"kind": "done", "name": "coupon", "value": True})
    post(base, "/api/progress", {"kind": "confirmed", "name": "board_x", "value": True})
    r = json.load(post(base, "/api/progress", {"kind": "notes", "name": "coupon", "value": "snug on the rail"}))
    assert r == {"done": {"coupon": True}, "confirmed": {"board_x": True}, "notes": {"coupon": "snug on the rail"}}
    assert json.load(get(base, "/api/guide"))["progress"] == r
    assert (m.DATA / "progress.json").is_file()
    r = json.load(post(base, "/api/progress", {"kind": "done", "name": "coupon", "value": False}))
    assert r["done"] == {}
    for body in ({"kind": "done", "name": "nope", "value": True}, {"kind": "confirmed", "name": "knob_d", "value": True},
                 {"kind": "done", "name": "coupon", "value": "yes"}, {"kind": "notes", "name": "coupon", "value": "x" * 2001},
                 {"kind": "other", "name": "coupon", "value": True}):
        assert code(lambda b=body: post(base, "/api/progress", b))[0] == 422


def test_a_fusion_that_is_not_running_is_said_plainly(app):
    m, base = app
    m.BRIDGE = "http://127.0.0.1:9"
    status, body = code(lambda: get(base, "/api/state"))
    assert status == 502 and "Fusion isn't answering" in body["error"]


def test_an_oversized_or_malformed_body_is_refused(app):
    _, base = app
    assert code(lambda: post(base, "/api/set", {"name": "knob_d", "value": 1, "pad": "x" * 5000}))[0] == 413
    assert code(lambda: post(base, "/api/set", ["knob_d"]))[0] == 422


# --- the add-in's own gate (adsk stubbed: the HTTP handler never touches Fusion before it has checked the request) ---

@pytest.fixture
def addin(tmp_path, monkeypatch):
    import sys
    import types
    stub = types.ModuleType("adsk")
    stub.core = types.SimpleNamespace(ViewOrientations=types.SimpleNamespace(**{k: 0 for k in (
        "IsoTopRightViewOrientation", "FrontViewOrientation", "TopViewOrientation", "RightViewOrientation", "BackViewOrientation")}),
        CustomEventHandler=object)
    stub.fusion = types.SimpleNamespace()
    monkeypatch.setitem(sys.modules, "adsk", stub)
    monkeypatch.setitem(sys.modules, "adsk.core", stub.core)
    monkeypatch.setitem(sys.modules, "adsk.fusion", stub.fusion)
    path = SERVER.parent / "PhoneBridge" / "PhoneBridge.py"
    spec = importlib.util.spec_from_file_location("phonebridge_under_test", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    (tmp_path / "bridge-token").write_text("secret-bridge")
    m.TOKEN_FILE = str(tmp_path / "bridge-token")
    asked = []
    m._ask = lambda **kw: asked.append(kw) or (PNG if kw["op"] == "shot" else {"ok": True})
    srv = ThreadingHTTPServer(("127.0.0.1", 0), m._Http)
    port = srv.server_address[1]
    m.HOSTS = {f"127.0.0.1:{port}"}
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield port, asked
    srv.shutdown()


def raw(port, method, path, body=None, headers=None):
    h = {"Content-Type": "application/json", "X-Bridge-Token": "secret-bridge", **(headers or {})}
    h = {k: v for k, v in h.items() if v is not None}
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body, headers=h, method=method)
    try:
        return urllib.request.urlopen(req).status
    except urllib.error.HTTPError as e:
        return e.code


GOOD = json.dumps({"name": "knob_d", "expression": "21 mm"}).encode()


def test_the_add_in_takes_the_right_request_from_the_server(addin):
    port, asked = addin
    assert raw(port, "POST", "/set", GOOD) == 200
    assert asked == [{"op": "set", "name": "knob_d", "expression": "21 mm"}]


@pytest.mark.parametrize("headers", [{"X-Bridge-Token": None}, {"X-Bridge-Token": "wrong"}, {"Origin": "http://evil.example"},
                                     {"Host": "evil.example"}])
def test_the_add_in_refuses_a_browser_page_a_missing_token_and_a_rebound_host(addin, headers):
    port, asked = addin
    assert raw(port, "POST", "/set", GOOD, headers) == 403
    assert raw(port, "GET", "/params", None, headers) == 403
    assert asked == []


def test_the_add_in_wants_json_and_a_plain_mm_expression(addin):
    port, asked = addin
    assert raw(port, "POST", "/set", GOOD, {"Content-Type": "text/plain"}) == 415
    for bad in ("21", "21 mm + board_x", "board_x", "-3 mm", "21mm; x"):
        assert raw(port, "POST", "/set", json.dumps({"name": "knob_d", "expression": bad}).encode()) == 422
    assert asked == []


def test_a_cross_site_form_post_with_a_text_body_cannot_reach_fusion(addin):
    port, asked = addin
    assert raw(port, "POST", "/set", GOOD, {"Content-Type": "text/plain", "X-Bridge-Token": None, "Origin": "null"}) == 403
    assert asked == []


def test_the_add_in_checks_a_component_name_and_needs_the_token_for_the_walkthrough(addin):
    port, asked = addin
    assert raw(port, "GET", "/components", None, {"X-Bridge-Token": None}) == 403
    assert raw(port, "GET", "/shot?view=iso&only=a%3Bb") == 422
    assert raw(port, "GET", "/shot?view=iso&only=carrier%3A1") == 200
    assert asked[-1]["only"] == "carrier:1"
