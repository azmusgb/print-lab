"""Per-target sync and pull: each target has its own result, nothing is swallowed (Plan B, Task 2)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from lab import pull, sync
from lab.loop.commands import load_experiment, set_criteria
from loop_fixtures import make_project, minimal_experiment, minimal_question, started
from test_pull import APART, PRINT, FakeLocalAI
from test_sync import Fake
from test_page_index import _project

VERDICT = {"id": "rq-0000000000000001", "kind": "verdict", "experiment": "E-009", "run": "PR-009-01",
           "payload": {"grades": {"E-009-A": {"print": "clean", "apart": "no"},
                                  "E-009-B": {"print": "clean", "apart": "yes"}}},
           "at": "2026-10-25T10:00:00+00:00"}


def lai(base):
    return sync.Target("Local AI", base, "X-LocalAI-Mac-Key", "lk", None)


def hub(base):
    return sync.Target("Pi Hub", base, "X-Hub-Mac-Key", "hk", None)


def use(monkeypatch, *ts):
    monkeypatch.setattr(sync, "targets", lambda base=None: list(ts))
    monkeypatch.setattr(pull, "targets", lambda base=None: list(ts))


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_SYNC", "on")
    p = _project(tmp_path)
    (p.root / "photos").mkdir(exist_ok=True)
    (p.root / "photos" / "PR-001-01-1.jpg").write_bytes(b"\xff\xd8jpeg")
    e = json.loads((p.experiments / "E-001.json").read_text())
    e["print_runs"][0]["photos"] = [{"path": "photos/PR-001-01-1.jpg", "source": "IMG_1.HEIC"}]
    (p.experiments / "E-001.json").write_text(json.dumps(e))
    return p


def saved(p):
    return json.loads((p.root / "sync.json").read_text())


def test_sync_is_ok_only_when_every_target_is(lab, monkeypatch):
    with Fake() as a, Fake(status=409) as b:
        use(monkeypatch, lai(a.url), hub(b.url))
        r = sync.sync(lab.root)
    assert not r["ok"] and r["message"].startswith("Pi Hub: ")
    assert r["targets"]["Local AI"]["ok"] is True and r["targets"]["Pi Hub"]["ok"] is False
    assert r["photos_sent"] == 2 and saved(lab)["targets"]["Local AI"]["photos_sent"] == 1


def test_a_target_that_cannot_be_built_is_a_failed_target(lab, monkeypatch):
    with Fake() as a:
        use(monkeypatch, lai(a.url), ("Pi Hub", "Save the house CA first: x"))
        r = sync.sync(lab.root)
    assert r["targets"]["Pi Hub"] == {"ok": False, "message": "Save the house CA first: x"}
    assert r["targets"]["Local AI"]["ok"] and not r["ok"]
    assert r["message"] == "Pi Hub: Save the house CA first: x"


def test_a_recovered_target_clears_its_failure(lab, monkeypatch):
    with Fake() as a, Fake(status=409) as b:
        use(monkeypatch, lai(a.url), hub(b.url))
        assert not sync.sync(lab.root)["ok"]
        b.status = 200
        r = sync.sync(lab.root)
    assert r["ok"] and r["message"] == "synced" and all(t["ok"] for t in saved(lab)["targets"].values())


def test_missing_photo_file_fails_that_target(lab, monkeypatch):
    real = sync.build_index

    def vanished(pdir):  # the index knows the photo; the file is gone by the time it's uploaded
        ix = real(pdir)
        (pdir / "photos" / "PR-001-01-1.jpg").unlink()
        return ix
    monkeypatch.setattr(sync, "build_index", vanished)
    with Fake() as a:
        use(monkeypatch, lai(a.url))
        r = sync.sync(lab.root)
    assert not r["ok"] and "photos/PR-001-01-1.jpg" in r["targets"]["Local AI"]["message"]
    assert not any(c[0] == "POST" for c in a.calls)


def _reply_server(code, body):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            b = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
    s = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, f"http://127.0.0.1:{s.server_address[1]}"


def test_hub_detail_text_is_reported(lab, monkeypatch):
    s, url = _reply_server(404, {"detail": "No project x."})
    try:
        use(monkeypatch, hub(url))
        r = sync.sync(lab.root)
    finally:
        s.shutdown()
    assert r["targets"]["Pi Hub"]["message"] == "No project x." and r["message"] == "Pi Hub: No project x."


def test_one_target_raising_anything_does_not_stop_the_others(lab, monkeypatch):
    real = sync._sync_to_target

    def boom(pdir, t, ix, timeout=10):
        if t.name == "Local AI":
            raise KeyError("odd")
        return real(pdir, t, ix, timeout)
    monkeypatch.setattr(sync, "_sync_to_target", boom)
    with Fake() as a, Fake() as b:
        use(monkeypatch, lai(a.url), hub(b.url))
        r = sync.sync(lab.root)
    assert r["targets"]["Pi Hub"]["ok"] and not r["targets"]["Local AI"]["ok"] and "odd" in r["message"]


def test_an_apply_that_raises_anything_fails_only_that_target(lab, monkeypatch):
    real = pull.apply_pending

    def boom(pdir, t, timeout=10):
        if t.name == "Local AI":
            raise RuntimeError("kaboom")
        return real(pdir, t, timeout)
    monkeypatch.setattr(pull, "apply_pending", boom)
    with Fake() as a, FakeLocalAI() as b:
        use(monkeypatch, lai(a.url), hub(b.base))
        r = sync.sync(lab.root)
    assert not r["targets"]["Local AI"]["ok"] and "kaboom" in r["targets"]["Local AI"]["message"]
    assert r["targets"]["Pi Hub"]["ok"]


# ---- pull ------------------------------------------------------------------------------------------------------
@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(pull, "link_new_prints", lambda *a, **k: [])
    monkeypatch.setattr(pull, "check_active_print", lambda *a, **k: None)
    monkeypatch.setattr("lab.sync.sync", lambda *a, **k: None)
    paths = make_project(tmp_path, minimal_question(), [started(minimal_experiment())])
    set_criteria(paths, "E-009", [PRINT, APART])
    return paths


def test_pull_runs_every_target_and_reports_a_down_one(project, monkeypatch, capsys):
    with FakeLocalAI(requests=[VERDICT]) as a:
        use(monkeypatch, lai(a.base), hub("http://127.0.0.1:9"))
        out = pull.pull(project.root, timeout=1)
    assert load_experiment(project, "E-009")["owner_verdict"]["kind"] == "criteria"
    err = [r for r in out if r["status"] == "error"]
    assert len(err) == 1 and err[0]["id"] == "Pi Hub" and err[0]["message"]
    assert "Pi Hub" in capsys.readouterr().err
    monkeypatch.setattr("lab.cli.project_dir", lambda p=None: project.root)
    with FakeLocalAI() as a:
        use(monkeypatch, lai(a.base), hub("http://127.0.0.1:9"))
        assert pull.cmd_pull(type("A", (), {"project": None})()) == 1


def test_a_target_that_cannot_be_built_is_a_pull_error(project, monkeypatch):
    with FakeLocalAI() as a:
        use(monkeypatch, lai(a.base), ("Pi Hub", "Save the house CA first: x"))
        out = pull.pull(project.root)
    assert out == [{"id": "Pi Hub", "status": "error", "message": "Save the house CA first: x"}]


def test_any_exception_from_one_target_is_isolated_in_pull(project, monkeypatch):
    real = pull.apply_pending

    def boom(pdir, t, timeout=10):
        if t.name == "Local AI":
            raise RuntimeError("kaboom")
        return real(pdir, t, timeout)
    monkeypatch.setattr(pull, "apply_pending", boom)
    with FakeLocalAI() as a, FakeLocalAI(requests=[VERDICT]) as b:
        use(monkeypatch, lai(a.base), hub(b.base))
        out = pull.pull(project.root)
    assert [r["id"] for r in out if r["status"] == "error"] == ["Local AI"]
    assert any(r["status"] == "applied" for r in out)


def test_same_request_id_on_two_targets_applies_once(project, monkeypatch):
    with FakeLocalAI(requests=[VERDICT]) as a, FakeLocalAI(requests=[VERDICT]) as b:
        use(monkeypatch, lai(a.base), hub(b.base))
        out = pull.pull(project.root)
    assert [r["status"] for r in out] == ["applied", "duplicate"]
    assert b.results[VERDICT["id"]]["status"] == "duplicate"


def test_pull_checks_telemetry_on_local_ai(project, monkeypatch):
    bases = []
    monkeypatch.setattr(pull, "check_active_print", lambda paths, base=None, timeout=5: bases.append(base))
    monkeypatch.setenv("LAB_LOCALAI_URL", "https://lai.example")
    with FakeLocalAI() as b:
        use(monkeypatch, hub(b.base), ("Local AI", "No Local AI key (x)"))
        pull.pull(project.root)
    assert bases == ["https://lai.example"]


def test_pull_syncs_every_target_after_applying(project, monkeypatch):
    calls = []
    monkeypatch.setattr("lab.sync.sync", lambda *a, **k: calls.append((a, k)))
    with FakeLocalAI(requests=[VERDICT]) as a:
        use(monkeypatch, lai(a.base))
        pull.pull(project.root)
    assert len(calls) == 1 and calls[0][0] == (project.root,) and "base" not in calls[0][1]


# ---- redirects -------------------------------------------------------------------------------------------------
def test_a_redirect_is_an_error_and_the_key_is_never_re_sent(lab, monkeypatch):
    seen = []

    class Other(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            seen.append(dict(self.headers))
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")
    other = ThreadingHTTPServer(("127.0.0.1", 0), Other)
    threading.Thread(target=other.serve_forever, daemon=True).start()
    where = f"http://127.0.0.1:{other.server_address[1]}/stolen"

    class Redirect(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            self.send_response(302)
            self.send_header("Location", where)
            self.send_header("Content-Length", "0")
            self.end_headers()
    first = ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
    threading.Thread(target=first.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{first.server_address[1]}"
    try:
        use(monkeypatch, hub(base))
        r = sync.sync(lab.root)
        assert r["targets"]["Pi Hub"]["message"] == "HTTP 302"
        with pytest.raises(sync.RemoteError, match="HTTP 302"):
            pull.apply_pending(lab.root, hub(base))
    finally:
        first.shutdown()
        other.shutdown()
    assert not any("X-Hub-Mac-Key" in h for h in seen) and seen == []


# ---- status ----------------------------------------------------------------------------------------------------
def test_status_shows_each_target():
    from lab.status import format_status_text
    st = {"project": "p", "question": None, "active_print": None, "printer": None, "needs": [], "problems": [],
          "sync": {"ok": False, "message": "Pi Hub: nope", "at": "2026-10-28T10:00:00+00:00",
                   "targets": {"Local AI": {"ok": True, "message": "synced"},
                               "Pi Hub": {"ok": False, "message": "nope"}}}}
    text = format_status_text(st)
    assert "✓ Local AI" in text and "✗ Pi Hub: nope" in text
    old = format_status_text({**st, "sync": {"ok": True, "message": "synced", "at": "2026-10-28T10:00:00+00:00"}})
    assert "Sync:    ✓ Synced (" in old
