"""Tests for `lab pull`: applying pending phone verdicts and photos from Local AI, and launchd pickup."""
import base64
import fcntl
import hashlib
import json
import os
import plistlib
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lab import pull, sync
from lab.loop.commands import load_experiment, set_criteria
from lab.records.project import ProjectPaths
from loop_fixtures import make_project, minimal_experiment, minimal_question, started

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
PRINT = "print=Printed cleanly?:clean,flawed,failed"
APART = "apart=Twists apart by hand?:yes,hard,no"


class FakeLocalAI:
    def __init__(self, requests=None, incoming=None):
        self.requests = list(requests or [])
        self.incoming = dict(incoming or {})
        self.results = {}
        self.calls = []

    def __enter__(self):
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _reply(self, code, body, ctype="application/json"):
                if isinstance(body, bytes):
                    b = body
                else:
                    b = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                key = self.headers.get("X-LocalAI-Mac-Key")
                fake.calls.append(("GET", self.path, key, None))
                if "/incoming/" in self.path:
                    sha = self.path.rsplit("/", 1)[1].split(".")[0]
                    if sha in fake.incoming:
                        self._reply(200, fake.incoming[sha], ctype="image/jpeg")
                    else:
                        self._reply(404, {"error": "not found"})
                elif "/requests" in self.path:
                    self._reply(200, {"items": fake.requests})
                elif "/photos" in self.path:
                    self._reply(200, {"have": []})
                else:
                    self._reply(404, {"error": "not found"})

            def do_POST(self):
                key = self.headers.get("X-LocalAI-Mac-Key")
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length)) if length else {}
                fake.calls.append(("POST", self.path, key, body))
                if "/requests/" in self.path and self.path.endswith("/result"):
                    parts = self.path.split("/")
                    req_id = parts[-2]
                    fake.results[req_id] = body
                    self._reply(200, {"ok": True})
                elif "/sync" in self.path:
                    self._reply(200, {"ok": True, "upserted": 1})
                else:
                    self._reply(200, {"ok": True})

            def do_PUT(self):
                key = self.headers.get("X-LocalAI-Mac-Key")
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                fake.calls.append(("PUT", self.path, key, body))
                self._reply(200, {"ok": True})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        return self

    def __exit__(self, *a):
        self.server.shutdown()


@pytest.fixture
def project(tmp_path):
    paths = make_project(tmp_path, minimal_question(), [started(minimal_experiment())])
    set_criteria(paths, "E-009", [PRINT, APART])
    return paths


def test_pull_applies_a_verdict_and_reports_it(project):
    req = {
        "id": "rq-0000000000000001",
        "kind": "verdict",
        "experiment": "E-009",
        "run": "PR-009-01",
        "payload": {
            "grades": {
                "E-009-A": {"print": "clean", "apart": "no"},
                "E-009-B": {"print": "clean", "apart": "yes"},
            }
        },
        "at": "2026-10-25T10:00:00+00:00",
    }
    with FakeLocalAI(requests=[req]) as fake:
        out = pull.apply_pending(project.root, fake.base, "k")

    assert out == [{"id": "rq-0000000000000001", "status": "applied", "message": "E-009 answered"}]
    assert load_experiment(project, "E-009")["owner_verdict"]["kind"] == "criteria"
    assert fake.results["rq-0000000000000001"]["status"] == "applied"


def test_pull_refuses_with_the_cli_message(project):
    from lab.loop.commands import record_verdict
    record_verdict(project, "E-009", rank=None, strength=None, inconclusive=None, accept=None, defects=[],
                   marks=[], witness=None, witness_override=None, anchors=[], not_about_target=False,
                   note=None, replace=False, runs=None, lighting="diagnostic",
                   grades={"E-009-A": {"print": "clean", "apart": "no"}, "E-009-B": {"print": "clean", "apart": "yes"}})

    req = {
        "id": "rq-0000000000000002",
        "kind": "verdict",
        "experiment": "E-009",
        "run": "PR-009-01",
        "payload": {
            "grades": {
                "E-009-A": {"print": "clean", "apart": "no"},
                "E-009-B": {"print": "clean", "apart": "yes"},
            }
        },
        "at": "2026-10-25T10:01:00+00:00",
    }
    with FakeLocalAI(requests=[req]) as fake:
        out = pull.apply_pending(project.root, fake.base, "k")

    assert out[0]["status"] == "refused"
    assert "already has a verdict" in out[0]["message"]
    assert fake.results["rq-0000000000000002"]["status"] == "refused"


def test_pull_never_applies_an_id_twice(project):
    req = {
        "id": "rq-0000000000000003",
        "kind": "verdict",
        "experiment": "E-009",
        "run": "PR-009-01",
        "payload": {
            "grades": {
                "E-009-A": {"print": "clean", "apart": "no"},
                "E-009-B": {"print": "clean", "apart": "yes"},
            }
        },
        "at": "2026-10-25T10:00:00+00:00",
    }
    with FakeLocalAI(requests=[req]) as fake:
        out1 = pull.apply_pending(project.root, fake.base, "k")
        assert out1[0]["status"] == "applied"
        out2 = pull.apply_pending(project.root, fake.base, "k")
        assert out2[0]["status"] == "duplicate"
        assert fake.results["rq-0000000000000003"]["status"] == "duplicate"


def test_pull_adds_photos_with_their_tabs(project):
    sha1 = hashlib.sha256(PNG + b"1").hexdigest()
    sha2 = hashlib.sha256(PNG + b"2").hexdigest()
    req = {
        "id": "rq-0000000000000004",
        "kind": "photos",
        "experiment": "E-009",
        "run": "PR-009-01",
        "payload": {
            "photos": [
                {"sha256": sha1, "tab": "09A"},
                {"sha256": sha2, "tab": "09B"},
            ]
        },
        "at": "2026-10-25T10:00:00+00:00",
    }
    incoming = {sha1: PNG + b"1", sha2: PNG + b"2"}
    with FakeLocalAI(requests=[req], incoming=incoming) as fake:
        out = pull.apply_pending(project.root, fake.base, "k")

    assert out[0]["status"] == "applied"
    e = load_experiment(project, "E-009")
    photos = e["print_runs"][0]["photos"]
    assert len(photos) == 2
    assert photos[0]["tab"] == "09A"
    assert photos[1]["tab"] == "09B"


def test_pull_applies_in_sent_order(project):
    sha1 = hashlib.sha256(PNG).hexdigest()
    req_verdict = {
        "id": "rq-0000000000000006",
        "kind": "verdict",
        "experiment": "E-009",
        "run": "PR-009-01",
        "payload": {
            "grades": {
                "E-009-A": {"print": "clean", "apart": "no"},
                "E-009-B": {"print": "clean", "apart": "yes"},
            }
        },
        "at": "2026-10-25T10:05:00+00:00",
    }
    req_photos = {
        "id": "rq-0000000000000005",
        "kind": "photos",
        "experiment": "E-009",
        "run": "PR-009-01",
        "payload": {"photos": [{"sha256": sha1, "tab": "09A"}]},
        "at": "2026-10-25T10:00:00+00:00",
    }
    # Served out of order
    with FakeLocalAI(requests=[req_verdict, req_photos], incoming={sha1: PNG}) as fake:
        out = pull.apply_pending(project.root, fake.base, "k")

    assert [r["id"] for r in out] == ["rq-0000000000000005", "rq-0000000000000006"]
    assert all(r["status"] == "applied" for r in out)


def test_pull_ignores_unknown_payload_fields(project):
    req = {
        "id": "rq-0000000000000007",
        "kind": "verdict",
        "experiment": "E-009",
        "run": "PR-009-01",
        "payload": {
            "grades": {
                "E-009-A": {"print": "clean", "apart": "no"},
                "E-009-B": {"print": "clean", "apart": "yes"},
            },
            "approve": True,
            "replace_build": True,
            "arbitrary_field": 12345,
        },
        "at": "2026-10-25T10:00:00+00:00",
    }
    with FakeLocalAI(requests=[req]) as fake:
        out = pull.apply_pending(project.root, fake.base, "k")

    assert out[0]["status"] == "applied"
    e = load_experiment(project, "E-009")
    assert "approved" not in e.get("owner_verdict", {})


def test_pull_skips_when_locked(project):
    req = {
        "id": "rq-0000000000000008",
        "kind": "verdict",
        "experiment": "E-009",
        "run": "PR-009-01",
        "payload": {
            "grades": {
                "E-009-A": {"print": "clean", "apart": "no"},
                "E-009-B": {"print": "clean", "apart": "yes"},
            }
        },
        "at": "2026-10-25T10:00:00+00:00",
    }
    lock_file = project.root / ".pull.lock"
    with open(lock_file, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with FakeLocalAI(requests=[req]) as fake:
            out = pull.apply_pending(project.root, fake.base, "k")

    assert out == []
    assert len(fake.calls) == 0


def test_sync_pulls_first_and_refreshes(project, monkeypatch):
    from test_page import _html
    key = project.root / "mac.key"
    key.write_text("test-key\n")
    monkeypatch.setenv("LAB_LOCALAI_KEY_FILE", str(key))
    monkeypatch.setenv("LAB_SYNC", "on")

    from lab import page
    page.write(project.root, {})

    req = {
        "id": "rq-0000000000000009",
        "kind": "verdict",
        "experiment": "E-009",
        "run": "PR-009-01",
        "payload": {
            "grades": {
                "E-009-A": {"print": "clean", "apart": "no"},
                "E-009-B": {"print": "clean", "apart": "yes"},
            }
        },
        "at": "2026-10-25T10:00:00+00:00",
    }
    with FakeLocalAI(requests=[req]) as fake:
        r = sync.sync(project.root, base=fake.base)

    assert r["ok"]
    post_calls = [c for c in fake.calls if c[0] == "POST" and "/sync" in c[1]]
    assert len(post_calls) == 1
    pushed_ix = post_calls[0][3]
    e_entry = next(x for x in pushed_ix["experiments"] if x["id"] == "E-009")
    assert e_entry["verdict"] is not None


def test_pull_is_off_with_lab_sync_off(project, monkeypatch):
    key = project.root / "mac.key"
    key.write_text("test-key\n")
    monkeypatch.setenv("LAB_LOCALAI_KEY_FILE", str(key))
    monkeypatch.setenv("LAB_SYNC", "off")

    req = {
        "id": "rq-0000000000000010",
        "kind": "verdict",
        "experiment": "E-009",
        "run": "PR-009-01",
        "payload": {
            "grades": {
                "E-009-A": {"print": "clean", "apart": "no"},
                "E-009-B": {"print": "clean", "apart": "yes"},
            }
        },
        "at": "2026-10-25T10:00:00+00:00",
    }
    with FakeLocalAI(requests=[req]) as fake:
        sync.sync(project.root, base=fake.base)

    assert not any("/requests" in c[1] for c in fake.calls)


def test_plist_has_label_interval_and_command(tmp_path):
    text = pull.plist_text(tmp_path, "/custom/bin/uv")
    data = plistlib.loads(text.encode())
    assert data["Label"] == "com.printlab.pull"
    assert data["StartInterval"] == 60
    assert data["RunAtLoad"] is True
    assert data["ProgramArguments"] == ["/custom/bin/uv", "run", "--project", str(tmp_path), "lab", "pull"]
    assert data["StandardOutPath"].endswith("Library/Logs/print-lab-pull.log")
    assert data["StandardErrorPath"].endswith("Library/Logs/print-lab-pull.log")


def test_install_writes_plist_to_the_given_dir(tmp_path):
    runner = MagicMock()
    plist_path = pull.install(repo=tmp_path, uv="/usr/bin/uv", agent_dir=tmp_path, runner=runner)
    assert plist_path == tmp_path / "com.printlab.pull.plist"
    assert plist_path.exists()
    runner.assert_called_once_with(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist_path)],
                                   check=True, capture_output=True, text=True)


def test_uninstall_boots_out_and_removes_file(tmp_path):
    runner = MagicMock()
    plist = tmp_path / "com.printlab.pull.plist"
    plist.write_text("dummy")
    pull.uninstall(agent_dir=tmp_path, runner=runner)
    runner.assert_called_once_with(["launchctl", "bootout", f"gui/{os.getuid()}", str(plist)],
                                   capture_output=True, text=True)
    assert not plist.exists()


def test_install_fails_if_uv_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(pull.shutil, "which", lambda cmd: None)
    with pytest.raises(ValueError, match="uv isn't on PATH."):
        pull.install(repo=tmp_path, uv=None, agent_dir=tmp_path)
