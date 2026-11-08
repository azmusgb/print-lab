"""A19 P3b: the Quick Print worker, against a fake hub that follows the P3a wire contract and a fake slicer."""
import hashlib
import json
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from lab.jobs import LabToolError, failed_job
from lab.quick import slice_child, worker
from lab.quick.worker import Hub, Lock, Refused, run_once, subprocess_slice
from lab.sync import Target

MODEL = b"solid x\nendsolid x\n"
MODEL_SHA = hashlib.sha256(MODEL).hexdigest()
ART = bytes(range(256)) * 3  # 768 bytes


class FakeHub:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self.bodies: dict[str, list] = {}
        self.job = {"id": "q1", "attempt": "a1", "generation": 1, "lease_seconds": 90, "heartbeat_every": 15,
                    "timeout_s": 30, "max_artifact_bytes": 209715200,
                    "model": {"name": "m.stl", "ext": "stl", "sha256": MODEL_SHA, "bytes": len(MODEL)},
                    "transform": None, "settings": {"wall_loops": 3}, "request_hash": "h"}
        self.no_job = False
        self.model_bytes = MODEL
        self.hb_refuse_after: int | None = None  # 409 from this heartbeat number on
        self.hb_cancel_after: int | None = None  # cancel:true from this heartbeat number on
        self.cancel_on_second_slicing_beat = False
        self.hb_fail = False                      # heartbeats answer 500
        self.complete_status = 200
        self.complete_reason = "terminal"
        self.offset_skew: int | None = None       # answer the first chunk with a 409 "offset" at this offset
        self.received = bytearray()
        self.hb_phases: list[str] = []
        self.lock = threading.Lock()

    def start(self):
        hub = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, obj=None, raw=None, headers=None):
                body = raw if raw is not None else json.dumps(obj or {}).encode()
                self.send_response(code)
                self.send_header("Content-Length", str(len(body)))
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)

            def _body(self):
                return self.rfile.read(int(self.headers.get("Content-Length") or 0))

            def handle_any(self):
                u = urlparse(self.path)
                q = {k: v[0] for k, v in parse_qs(u.query).items()}
                path = u.path
                if self.headers.get("X-Hub-Mac-Key") != "k":
                    return self._send(401, {"detail": "bad key"})
                body = self._body()
                with hub.lock:
                    hub.calls.append((self.command, path))
                    assert path.startswith("/api/lab/quick/worker"), path
                    if path.endswith("/claim"):
                        return self._send(200, {"job": None, "why": "nothing queued"} if hub.no_job else {"job": hub.job})
                    if path.endswith("/model"):
                        assert q["generation"] == "1"
                        return self._send(200, raw=hub.model_bytes, headers={"X-Sha256": MODEL_SHA})
                    if path.endswith("/heartbeat"):
                        b = json.loads(body)
                        hub.hb_phases.append(b["phase"])
                        n = len(hub.hb_phases)
                        if hub.hb_fail:
                            return self._send(500, {"detail": "boom"})
                        if hub.hb_refuse_after and n >= hub.hb_refuse_after:
                            return self._send(409, {"detail": "refused", "reason": "canceled"})
                        return self._send(200, {"ok": True, "lease_seconds": 90,
                                                "cancel": bool(hub.hb_cancel_after and n >= hub.hb_cancel_after)
                                                or (hub.cancel_on_second_slicing_beat and hub.hb_phases.count("slicing") >= 2)})
                    if path.endswith("/artifact"):
                        off, size = int(q["offset"]), int(self.headers["X-Size"])
                        hub.bodies.setdefault("chunks", []).append((off, len(body)))
                        if hub.offset_skew is not None:
                            skew, hub.offset_skew = hub.offset_skew, None
                            hub.received = hub.received[:skew]
                            return self._send(409, {"detail": "offset", "reason": "offset", "offset": skew})
                        if off != len(hub.received):
                            return self._send(409, {"reason": "offset", "offset": len(hub.received)})
                        hub.received += body
                        if len(hub.received) >= size:
                            assert hashlib.sha256(hub.received).hexdigest() == self.headers["X-Sha256"]
                            return self._send(200, {"done": True, "sha256": self.headers["X-Sha256"], "bytes": size})
                        return self._send(200, {"done": False, "offset": len(hub.received)})
                    if path.endswith("/complete"):
                        hub.bodies.setdefault("complete", []).append(json.loads(body))
                        if hub.complete_status != 200:
                            return self._send(hub.complete_status, {"detail": "no", "reason": hub.complete_reason})
                        return self._send(200, {"ok": True, "state": "sliced"})
                self._send(404, {"detail": "unknown"})

            do_GET = do_POST = do_PUT = handle_any

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.target = Target("Pi Hub", f"http://127.0.0.1:{self.srv.server_port}", "X-Hub-Mac-Key", "k", None)
        return self

    def stop(self):
        self.srv.shutdown()


@pytest.fixture
def fake():
    h = FakeHub().start()
    yield h
    h.stop()


@pytest.fixture
def base(tmp_path):
    p = tmp_path / "base.3mf"
    p.write_bytes(b"x")
    return p


WORKER = {"id": "mac-test", "os": "darwin", "studio_version": "02.09.01.70", "presets": ["p"]}


def good_slicer(spec, stop, timeout, work):
    out = Path(spec["out_dir"])
    out.mkdir(parents=True, exist_ok=True)
    art = out / "a.gcode.3mf"
    art.write_bytes(ART)
    return {"ok": True, "slice": {"sliced": str(art), "sliced_sha256": hashlib.sha256(ART).hexdigest(), "minutes": 10.0,
                                  "grams": 3.5, "layers": 30, "studio_version": "02.09.01.70", "start_block_lines": 404,
                                  "base_sha256": "b", "project_sha256": "p", "model_sha256": spec["model_sha256"],
                                  "settings": spec["settings"]}}


def go(fake, base, tmp_path, slicer=good_slicer, **kw):
    return run_once(Hub(fake.target), worker=WORKER, base=base, scratch=tmp_path / "scratch", slicer=slicer,
                    heartbeat_every=kw.pop("heartbeat_every", 0.05), log=lambda *_: None, **kw)


def test_idle_claim_is_the_contact_and_does_nothing_else(fake, base, tmp_path):
    fake.no_job = True
    r = go(fake, base, tmp_path)
    assert r.status == "idle" and r.detail == "nothing queued" and fake.calls == [("POST", "/api/lab/quick/worker/claim")]


def test_good_slice_is_uploaded_in_chunks_and_completed(fake, base, tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "CHUNK", 300)
    r = go(fake, base, tmp_path)
    assert r.status == "sliced" and bytes(fake.received) == ART
    assert fake.bodies["chunks"] == [(0, 300), (300, 300), (600, 168)]
    c = fake.bodies["complete"][0]
    assert c["outcome"] == "sliced" and c["generation"] == 1
    assert c["artifact"] == {"sha256": hashlib.sha256(ART).hexdigest(), "bytes": len(ART)}
    assert c["result"]["minutes"] == 10.0 and c["result"]["model_sha256"] == MODEL_SHA
    assert fake.hb_phases[0] == "preparing" and "slicing" in fake.hb_phases and "uploading" in fake.hb_phases
    assert not (tmp_path / "scratch" / "q1" / "a1").exists()


def test_wrong_offset_continues_from_the_hubs_offset(fake, base, tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "CHUNK", 400)
    fake.offset_skew = 0
    fake.received = bytearray(b"")
    r = go(fake, base, tmp_path)
    assert r.status == "sliced" and bytes(fake.received) == ART


def test_cancel_from_a_heartbeat_stops_the_slice_and_posts_nothing(fake, base, tmp_path):
    fake.hb_cancel_after = 99
    fake.cancel_on_second_slicing_beat = True  # a beat from the thread, mid-slice
    seen = {}

    def slow(spec, stop, timeout, work):
        seen["stopped"] = stop.wait(5)
        return {"stopped": True}
    r = go(fake, base, tmp_path, slicer=slow)
    assert r.status == "refused" and r.detail == "canceled" and seen["stopped"]
    assert "complete" not in fake.bodies and "chunks" not in fake.bodies
    assert not (tmp_path / "scratch" / "q1" / "a1").exists()


def test_refusal_on_the_first_heartbeat_means_nothing_starts(fake, base, tmp_path):
    fake.hb_refuse_after = 1
    r = go(fake, base, tmp_path, slicer=lambda *a: pytest.fail("must not slice"))
    assert r.status == "refused" and not any(p.endswith("/model") for _, p in fake.calls)
    assert "complete" not in fake.bodies


def test_refused_completion_is_clean(fake, base, tmp_path):
    fake.complete_status, fake.complete_reason = 409, "superseded"
    r = go(fake, base, tmp_path)
    assert r.status == "refused" and r.detail == "superseded"
    assert not (tmp_path / "scratch" / "q1" / "a1").exists()


def test_heartbeat_loss_stops_work_and_posts_nothing(fake, base, tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "MISSED_BEATS", 2)
    fake.hb_fail = True

    def slow(spec, stop, timeout, work):
        return {"stopped": True} if stop.wait(5) else {"ok": False, "outcome": "failed", "cause": "slice_failed"}
    r = go(fake, base, tmp_path, slicer=slow, heartbeat_every=0.01)
    assert r.status == "refused" and r.detail == "heartbeat_lost" and "complete" not in fake.bodies


def test_model_changed_in_transit_is_a_failure_not_a_slice(fake, base, tmp_path):
    fake.model_bytes = b"other"
    r = go(fake, base, tmp_path, slicer=lambda *a: pytest.fail("must not slice"))
    assert r.status == "failed" and fake.bodies["complete"][0]["outcome"] == "failed"


def test_no_base_preset_fails_with_a_reason(fake, tmp_path):
    r = go(fake, tmp_path / "missing.3mf", tmp_path, slicer=lambda *a: pytest.fail("must not slice"))
    assert r.status == "failed" and "base preset" in fake.bodies["complete"][0]["message"]


def test_slicer_failures_are_posted_with_their_cause(fake, base, tmp_path):
    r = go(fake, base, tmp_path, slicer=lambda *a: {"ok": False, "outcome": "needs_attention",
                                                     "cause": "start_sequence", "message": "no start"})
    assert r.status == "needs_attention"
    c = fake.bodies["complete"][0]
    assert c["outcome"] == "needs_attention" and c["cause"] == "start_sequence" and "artifact" not in c


def test_artifact_changed_after_slicing_is_not_sent(fake, base, tmp_path):
    def bad(spec, stop, timeout, work):
        res = good_slicer(spec, stop, timeout, work)
        res["slice"]["sliced_sha256"] = "0" * 64
        return res
    r = go(fake, base, tmp_path, slicer=bad)
    assert r.status == "failed" and "chunks" not in fake.bodies
    assert fake.bodies["complete"][0]["cause"] == "output_invalid"


def test_upload_after_cancel_is_refused_before_sending(fake, tmp_path):
    p = tmp_path / "a"
    p.write_bytes(ART)
    ev = threading.Event()
    ev.set()
    with pytest.raises(Refused):
        Hub(fake.target).upload_artifact(fake.job, p, "x", ev)
    assert "chunks" not in fake.bodies


def test_hub_down_or_bad_key(tmp_path):
    t = Target("Pi Hub", "http://127.0.0.1:9", "X-Hub-Mac-Key", "k", None)
    assert run_once(Hub(t, timeout=1), worker=WORKER).status == "hub_error"
    h = FakeHub().start()
    try:
        bad = Target("Pi Hub", h.target.base, "X-Hub-Mac-Key", "wrong", None)
        assert run_once(Hub(bad), worker=WORKER).status == "hub_error"
    finally:
        h.stop()


# ---- the lock and the child process ----------------------------------------------------------------------------

def test_one_worker_per_mac(tmp_path):
    with Lock(tmp_path / "w.lock"):
        with pytest.raises(BlockingIOError):
            Lock(tmp_path / "w.lock").__enter__()
    with Lock(tmp_path / "w.lock"):
        pass


def test_a_killed_worker_releases_the_lock(tmp_path):
    code = ("import sys,time;from lab.quick.worker import Lock;l=Lock(sys.argv[1]);l.__enter__();"
            "print('held',flush=True);time.sleep(60)")
    p = subprocess.Popen([sys.executable, "-c", code, str(tmp_path / "w.lock")], stdout=subprocess.PIPE, text=True)
    assert p.stdout.readline().strip() == "held"
    with pytest.raises(BlockingIOError):
        Lock(tmp_path / "w.lock").__enter__()
    p.send_signal(signal.SIGKILL)
    p.wait()
    with Lock(tmp_path / "w.lock"):
        pass


def test_subprocess_slice_stop_kills_the_child(tmp_path):
    ev = threading.Event()
    threading.Timer(0.5, ev.set).start()
    t0 = time.monotonic()
    r = subprocess_slice({}, ev, 30, tmp_path, cmd=[sys.executable, "-c", "import time;time.sleep(60)"])
    assert r == {"stopped": True} and time.monotonic() - t0 < 5


def test_subprocess_slice_timeout_and_silent_death(tmp_path):
    r = subprocess_slice({}, threading.Event(), 0.5, tmp_path, cmd=[sys.executable, "-c", "import time;time.sleep(60)"])
    assert r["cause"] == "slice_timeout"
    r = subprocess_slice({}, threading.Event(), 5, tmp_path, cmd=[sys.executable, "-c", "raise SystemExit(3)"])
    assert r["cause"] == "worker_ended" and "exit 3" in r["message"]


def test_subprocess_slice_returns_the_childs_result(tmp_path):
    code = "import sys,json;open(sys.argv[2],'w').write(json.dumps({'ok':True,'slice':{}}))"
    r = subprocess_slice({}, threading.Event(), 5, tmp_path, cmd=[sys.executable, "-c", code, "s", str(tmp_path / "result.json")])
    assert r == {"ok": True, "slice": {}}


def test_child_runs_a_real_failure_end_to_end(tmp_path):
    spec = {"model": str(tmp_path / "nope.stl"), "base": str(tmp_path / "nope.3mf"), "out_dir": str(tmp_path / "o")}
    r = subprocess_slice(spec, threading.Event(), 60, tmp_path)
    assert r["ok"] is False and r["cause"] == "slice_failed" and "nope" in r["message"]


@pytest.mark.parametrize("stderr,msg,cause", [
    ("TimeoutExpired: 5", "couldn't slice", "slice_timeout"),
    ("", "Bambu Studio not found at /x", "missing_binary"),
    ("", "Bambu Studio 1.0 is installed, but the lab is checked against 02.09.01.70", "studio_version"),
    ("segfault", "couldn't slice p.3mf: segfault", "slice_failed")])
def test_slicer_exceptions_map_to_hub_causes(tmp_path, stderr, msg, cause):
    job = failed_job(jobs_dir=tmp_path, tool="bambu-studio", message=stderr)
    assert slice_child.classify(LabToolError(msg, job))["cause"] == cause


def test_start_sequence_and_output_errors_map():
    from lab.quick.engine import QuickSliceError
    assert slice_child.classify(QuickSliceError("Refused: this slice doesn't have the X2D start sequence."))["outcome"] == "needs_attention"
    assert slice_child.classify(QuickSliceError("Bambu Studio's output isn't a valid 3MF archive"))["cause"] == "output_invalid"


def test_worker_id_matches_the_hubs_pattern(monkeypatch):
    import re
    monkeypatch.setattr(worker.socket, "gethostname", lambda: "Bill's MacBook Pro (2).local")
    w = worker.worker_record(presets=[], studio_version="02.09.01.70")
    assert re.fullmatch(r"[A-Za-z0-9._-]{1,40}", w["id"])
