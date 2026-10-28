"""Phone photos are checked by name, size and hash before they enter a record (Plan B, Task 3)."""
import contextlib
import hashlib
import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from lab import pull
from lab.loop.commands import load_experiment, set_criteria
from loop_fixtures import make_project, minimal_experiment, minimal_question, started
from test_pull import APART, PNG, PRINT, FakeLocalAI, _t

GOOD = hashlib.sha256(PNG).hexdigest()


@pytest.fixture
def project(tmp_path):
    paths = make_project(tmp_path, minimal_question(), [started(minimal_experiment())])
    set_criteria(paths, "E-009", [PRINT, APART])
    return paths


def req(photos, rid="rq-0000000000000001", at="2026-10-25T10:00:00+00:00"):
    return {"id": rid, "kind": "photos", "experiment": "E-009", "run": "PR-009-01",
            "payload": {"photos": photos}, "at": at}


def photos_of(project):
    return load_experiment(project, "E-009")["print_runs"][0].get("photos") or []


def handled(project):
    f = project.root / "requests.jsonl"
    return [json.loads(x) for x in f.read_text().splitlines()] if f.exists() else []


def fetched(fake):
    return [c for c in fake.calls if c[0] == "GET" and "/incoming/" in c[1]]


@pytest.mark.parametrize("photos", [
    [],
    [{"sha256": GOOD, "tab": "09A"}] * 51,
    [{"sha256": "../x", "tab": "09A"}],
    [{"sha256": GOOD.upper(), "tab": "09A"}],
    [{"sha256": GOOD[:63], "tab": "09A"}],
    [{"sha256": GOOD, "tab": "x" * 17}],
    [{"sha256": GOOD, "tab": 9}],
    "not a list",
    ["not a dict"],
], ids=["none", "51", "dotdot", "upper", "63chars", "tab17", "tab-int", "not-list", "not-dict"])
def test_photo_request_shape_is_checked(project, photos):
    with FakeLocalAI(requests=[req(photos)], incoming={GOOD: PNG}) as fake:
        out = pull.apply_pending(project.root, _t(fake.base))
    assert out[0]["status"] == "refused"
    assert fetched(fake) == []
    assert photos_of(project) == []


def test_photo_bytes_must_match_their_name(project):
    with FakeLocalAI(requests=[req([{"sha256": GOOD, "tab": "09A"}])], incoming={GOOD: PNG + b"x"}) as fake:
        out = pull.apply_pending(project.root, _t(fake.base))
    assert out[0]["status"] == "refused"
    assert "didn't match" in out[0]["message"]
    assert photos_of(project) == []


def test_photo_over_the_cap_is_refused(project, monkeypatch):
    big = b"\0" * (pull.MAX_PHOTO_BYTES + 1)
    with FakeLocalAI(requests=[req([{"sha256": hashlib.sha256(big).hexdigest(), "tab": "09A"}])],
                     incoming={hashlib.sha256(big).hexdigest(): big}) as fake:
        out = pull.apply_pending(project.root, _t(fake.base))
    assert out[0]["status"] == "refused"
    assert photos_of(project) == []


def test_photo_read_stops_at_the_cap_plus_one(project, monkeypatch):
    asked = []

    class Resp(io.BytesIO):
        def read(self, n=-1):
            asked.append(n)
            return b"\0" * n

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    monkeypatch.setattr(pull, "_open", lambda *a, **k: Resp())
    with FakeLocalAI(requests=[req([{"sha256": GOOD, "tab": "09A"}])]) as fake:
        out = pull.apply_pending(project.root, _t(fake.base))
    assert asked == [pull.MAX_PHOTO_BYTES + 1]
    assert out[0]["status"] == "refused"


def test_photo_download_failure_leaves_the_request_for_next_time(project):
    r = req([{"sha256": GOOD, "tab": "09A"}])
    with FakeLocalAI(requests=[r]) as fake:
        out = pull.apply_pending(project.root, _t(fake.base))
        assert out[0]["status"] == "error" and out[0]["message"] == "HTTP 404"
        assert handled(project) == []
        assert fake.results == {}
        fake.incoming[GOOD] = PNG
        out = pull.apply_pending(project.root, _t(fake.base))
    assert out[0]["status"] == "applied"
    assert len(photos_of(project)) == 1


def test_one_bad_photo_does_not_stop_the_other_requests(project):
    other = hashlib.sha256(PNG + b"2").hexdigest()
    reqs = [req([{"sha256": GOOD, "tab": "09A"}], "rq-0000000000000001", "2026-10-25T10:00:00+00:00"),
            req([{"sha256": other, "tab": "09B"}], "rq-0000000000000002", "2026-10-25T10:01:00+00:00")]
    with FakeLocalAI(requests=reqs, incoming={other: PNG + b"2"}) as fake:
        out = pull.apply_pending(project.root, _t(fake.base))
    assert [r["status"] for r in out] == ["error", "applied"]


def test_download_network_failure_is_an_error_not_a_crash(project, monkeypatch):
    def timed_out(*a, **k):
        raise TimeoutError("timed out")
    monkeypatch.setattr(pull, "_open", timed_out)
    with FakeLocalAI(requests=[req([{"sha256": GOOD, "tab": "09A"}])]) as fake:
        out = pull.apply_pending(project.root, _t(fake.base))
    assert out[0]["status"] == "error" and "timed out" in out[0]["message"]
    assert handled(project) == []


def test_photo_redirect_is_an_error_and_the_second_server_gets_nothing(project):
    seen = []

    class Other(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            seen.append(dict(self.headers))
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()
    other = ThreadingHTTPServer(("127.0.0.1", 0), Other)
    threading.Thread(target=other.serve_forever, daemon=True).start()
    where = f"http://127.0.0.1:{other.server_address[1]}/stolen"

    class Incoming(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if "/incoming/" in self.path:
                self.send_response(302)
                self.send_header("Location", where)
                self.send_header("Content-Length", "0")
            else:
                b = json.dumps({"items": [req([{"sha256": GOOD, "tab": "09A"}])]}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)
                return
            self.end_headers()
    first = ThreadingHTTPServer(("127.0.0.1", 0), Incoming)
    threading.Thread(target=first.serve_forever, daemon=True).start()
    try:
        out = pull.apply_pending(project.root, _t(f"http://127.0.0.1:{first.server_address[1]}"))
    finally:
        first.shutdown()
        other.shutdown()
    assert seen == []
    assert out[0]["status"] == "error" and out[0]["message"] == "HTTP 302"
    assert handled(project) == []


def test_a_result_post_that_raises_anything_is_printed_and_the_loop_goes_on(project, monkeypatch, capsys):
    def post_or_list(t, m, path, *a, **k):
        if m == "POST":
            raise RuntimeError("boom")
        return (200, {"items": [req([{"sha256": GOOD, "tab": "09A"}], "rq-0000000000000001"),
                                req([{"sha256": GOOD, "tab": "09A"}], "rq-0000000000000002",
                                    "2026-10-25T10:01:00+00:00")]})
    monkeypatch.setattr(pull, "_call", post_or_list)
    monkeypatch.setattr(pull, "_open", lambda *a, **k: contextlib.nullcontext(io.BytesIO(PNG)))
    out = pull.apply_pending(project.root, _t("http://127.0.0.1:9"))
    assert [r["status"] for r in out] == ["applied", "applied"]
    assert "boom" in capsys.readouterr().err


# ---- final fix wave --------------------------------------------------------------------------------------------
@pytest.mark.parametrize("photo", [{"sha256": GOOD, "tab": None}, {"sha256": GOOD}], ids=["tab-null", "tab-absent"])
def test_photo_without_a_tab_is_applied(project, photo):
    with FakeLocalAI(requests=[req([photo])], incoming={GOOD: PNG}) as fake:
        out = pull.apply_pending(project.root, _t(fake.base))
    assert out[0]["status"] == "applied"
    (entry,) = photos_of(project)
    assert "tab" not in entry


def test_a_dropped_connection_mid_photo_is_an_error_not_a_crash(project):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            body = json.dumps({"items": [req([{"sha256": GOOD, "tab": None}])]}).encode() \
                if "/requests" in self.path else PNG[:10]
            self.send_response(200)
            self.send_header("Content-Length", str(len(body) if "/requests" in self.path else len(PNG)))  # lies
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        out = pull.apply_pending(project.root, _t(f"http://127.0.0.1:{srv.server_port}"))
    finally:
        srv.shutdown()
        srv.server_close()
        th.join()
    assert out[0]["status"] == "error"
    assert handled(project) == []


def test_a_local_failure_adding_photos_is_worded_as_local_and_retried(project, monkeypatch):
    def full(*a, **k):
        raise OSError("No space left on device")
    monkeypatch.setattr(pull, "add_photos", full)
    with FakeLocalAI(requests=[req([{"sha256": GOOD, "tab": "09A"}])], incoming={GOOD: PNG}) as fake:
        out = pull.apply_pending(project.root, _t(fake.base))
    assert out[0]["status"] == "error"
    assert out[0]["message"] == "Couldn't add the photos on the Mac: No space left on device"
    assert handled(project) == [] and fake.results == {}
