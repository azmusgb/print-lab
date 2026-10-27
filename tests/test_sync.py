"""`lab sync`: the Mac pushes its read-only projection (page.json) and new photos to Local AI (slim 1B)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from lab import sync
from test_page import _html


class Fake:
    def __init__(self, have=(), status=200):
        self.have, self.status, self.calls = set(have), status, []

    def __enter__(self):
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _reply(self, code, body):
                b = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                fake.calls.append(("GET", self.path, self.headers.get("X-LocalAI-Mac-Key"), None))
                self._reply(200, {"have": sorted(fake.have)})

            def do_PUT(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                fake.calls.append(("PUT", self.path, self.headers.get("X-LocalAI-Mac-Key"), body))
                fake.have.add(self.path.rsplit("/", 1)[1][:-4])
                self._reply(200, {"ok": True})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fake.calls.append(("POST", self.path, self.headers.get("X-LocalAI-Mac-Key"), body))
                self._reply(fake.status, {"ok": True, "upserted": 4} if fake.status == 200
                            else {"error": "An older push than the one stored"})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        return self

    def __exit__(self, *a):
        self.server.shutdown()


@pytest.fixture
def lab(tmp_path, monkeypatch):
    key = tmp_path / "mac.key"
    key.write_text("test-key\n")
    monkeypatch.setenv("LAB_LOCALAI_KEY_FILE", str(key))
    p, _ = _html(tmp_path)
    return p


def test_sync_sends_the_key_only_missing_photos_then_the_index(lab):
    with Fake() as f:
        r = sync.sync(lab.root, base=f.url)
    assert r["ok"] and r["photos_sent"] == 1
    kinds = [(c[0], c[1].split("/")[-1]) for c in f.calls]
    assert kinds[0] == ("GET", "photos") and kinds[1][0] == "PUT" and kinds[-1] == ("POST", "sync")
    assert all(c[2] == "test-key" for c in f.calls)
    assert f.calls[1][3] == b"\xff\xd8jpeg" and f.calls[1][1] == "/api/lab/hex-tile/photos/" + \
        __import__("hashlib").sha256(b"\xff\xd8jpeg").hexdigest() + ".jpg"
    pushed = f.calls[-1][3]
    assert pushed["schema"] == "print-lab-index/1" and "E-001" in pushed["records"]
    assert json.loads((lab.root / "sync.json").read_text())["ok"] is True


def test_photos_local_ai_already_has_are_not_sent_again(lab):
    with Fake() as f:
        sync.sync(lab.root, base=f.url)
        f.calls.clear()
        r = sync.sync(lab.root, base=f.url)
    assert r["photos_sent"] == 0 and [c[0] for c in f.calls] == ["GET", "POST"]


def test_a_refused_push_is_reported_not_retried(lab):
    with Fake(status=409) as f:
        r = sync.sync(lab.root, base=f.url)
    assert not r["ok"] and "older push" in r["message"] and [c[0] for c in f.calls].count("POST") == 1
    assert json.loads((lab.root / "sync.json").read_text())["ok"] is False


def test_unreachable_local_ai_fails_quietly(lab):
    r = sync.sync(lab.root, base="http://127.0.0.1:9", timeout=1)
    assert not r["ok"] and r["message"]


def test_background_sync_is_off_when_asked(lab, monkeypatch):
    started = []
    monkeypatch.setattr(sync.subprocess, "Popen", lambda *a, **k: started.append(a))
    monkeypatch.setenv("LAB_SYNC", "off")
    sync.background(lab.root)
    monkeypatch.setenv("LAB_SYNC", "on")
    sync.background(lab.root)
    assert len(started) == 1


def test_the_page_says_when_it_last_synced(lab):
    from lab import page
    (lab.root / "sync.json").write_text(json.dumps({"ok": False, "at": "2026-10-25T02:00:00+00:00",
                                                    "message": "Local AI didn't answer"}))
    assert "Local AI: not synced (Local AI didn&#x27;t answer)" in page.build(lab.root, colours={})


def test_sync_sends_the_saved_spool_colours(lab):
    (lab.root / "page.json").write_text(json.dumps({"colours": {"terracotta": "#c0623a"}}))
    with Fake() as f:
        assert sync.sync(lab.root, base=f.url)["ok"]
    assert f.calls[-1][3]["colours"] == {"terracotta": "#c0623a"}


def test_sync_sends_no_colours_without_page_json(lab):
    (lab.root / "page.json").unlink(missing_ok=True)
    with Fake() as f:
        assert sync.sync(lab.root, base=f.url)["ok"]
    assert f.calls[-1][3]["colours"] == {}
