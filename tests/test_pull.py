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


def test_check_active_print_still_printing(project):
    mock_ws = {
        "online": True,
        "printer": {
            "state": "printing",
            "progress": 50,
            "minutesLeft": 20,
            "seenAt": "2026-10-25T09:20:00+00:00",
        }
    }
    with pull.patch("lab.sync.fetch_workshop_status", return_value=mock_ws) if hasattr(pull, "patch") else \
            pytest.MonkeyPatch.context() as mp:
        from unittest.mock import patch
        with patch("lab.sync.fetch_workshop_status", return_value=mock_ws):
            res = pull.check_active_print(project)
            assert res is None


def test_check_active_print_records_completion_and_notifies(project):
    """A finished print with no printer log: the end time is unknown, so no minutes are invented; the owner is told
    once and the run is marked so the check doesn't repeat."""
    from unittest.mock import patch
    mock_ws = {
        "online": True,
        "printer": {
            "state": "finish",
            "progress": 100,
            "minutesLeft": 0,
            "seenAt": "2026-10-25T09:40:00+00:00",
        }
    }
    with patch("lab.sync.fetch_workshop_status", return_value=mock_ws), \
         patch("lab.pull.notify_desktop") as mock_notify:
        res = pull.check_active_print(project)
        assert res is not None
        assert res["action"] == "finished_time_unknown"
        assert res["experiment"] == "E-009"
        assert res["run"] == "PR-009-01"
        assert res["elapsed_minutes"] is None
        mock_notify.assert_called_once()
        from lab.loop.commands import load_experiment
        u = load_experiment(project, "E-009")["print_runs"][-1]["usage"]
        assert u == {"actual_minutes": None, "actual_g": None, "usage_source": "finished_unknown",
                     "completion_fraction": None}

        # Re-check should now be no-op because the run is marked
        res2 = pull.check_active_print(project)
        assert res2 is None


def test_pull_leaves_a_run_alone_once_the_printer_log_recorded_its_minutes(project):
    from unittest.mock import patch
    from lab.loop.commands import load_experiment, save_experiment
    e = load_experiment(project, "E-009")
    e["print_runs"][-1]["usage"] = {"actual_minutes": 51.0, "actual_g": None, "usage_source": "printer_log",
                                    "completion_fraction": None}
    save_experiment(project, e)
    ws = {"online": True, "printer": {"state": "finish", "progress": 100, "minutesLeft": 0,
                                      "seenAt": "2026-10-25T13:00:00+00:00"}}
    with patch("lab.sync.fetch_workshop_status", return_value=ws), patch("lab.pull.notify_desktop") as n:
        assert pull.check_active_print(project) is None
        n.assert_not_called()
    assert load_experiment(project, "E-009")["print_runs"][-1]["usage"]["actual_minutes"] == 51.0


# ---- observations from the phone (spec 2026-10-26-observation-records-design rev 2) -----------------------------

def _obs_snapshot(kind="pair", **outcomes):
    from lab.records.observations import ALLOWED
    out = {k: {"status": "not_assessed", "value": None, "note": None} for k in ALLOWED[kind]}
    out.update(outcomes)
    return {"subject": {"kind": kind, "experiment": "E-009", "run": "PR-009-01", "build": "BLD-009-01",
                        "variant": "E-009-A", "label": "9A", "tile": None, "identified": "confirmed", "note": None},
            "viewing": {"light": "room"}, "outcomes": out,
            "source": {"kind": "owner_report", "words": "twisted apart", "evidence": [], "occurred_at": None,
                       "attributed_by": "phone_session"}}


def test_pull_records_a_phone_observation_session_once(project):
    from lab.records import observations as obs
    req = {"id": "rq-obs-1", "kind": "observation", "experiment": "E-009", "run": "PR-009-01",
           "payload": {"snapshots": [_obs_snapshot(separation={"status": "assessed", "value": "effort", "note": None})]},
           "at": "2026-10-27T10:00:00+00:00"}
    with FakeLocalAI(requests=[req]) as fake:
        out = pull.apply_pending(project.root, fake.base, "k")
    assert out[0]["status"] == "applied" and "OBS-0001" in out[0]["message"]
    rv = obs.latest(obs.load(project, "OBS-0001"))
    assert rv["submitted"]["channel"] == "phone" and rv["submitted"]["request_id"] == "rq-obs-1"
    # Local AI delivers it again after a lost acknowledgement and a wiped requests.jsonl: still one observation
    (project.root / "requests.jsonl").unlink()
    with FakeLocalAI(requests=[req]) as fake:
        out = pull.apply_pending(project.root, fake.base, "k")
    assert out[0]["status"] == "applied" and len(obs.all_observations(project)) == 1


def test_pull_refuses_an_observation_for_another_experiment(project):
    req = {"id": "rq-obs-2", "kind": "observation", "experiment": "E-009", "run": "PR-009-01",
           "payload": {"snapshots": [{**_obs_snapshot(), "subject": {**_obs_snapshot()["subject"], "experiment": "E-099"}}]},
           "at": "2026-10-27T10:00:00+00:00"}
    with FakeLocalAI(requests=[req]) as fake:
        out = pull.apply_pending(project.root, fake.base, "k")
    assert out[0]["status"] == "refused"


def test_pull_reports_a_correction_conflict(project):
    from lab.records import observations as obs
    obs.record_session(project, [_obs_snapshot()], submitted={"actor": "owner", "channel": "phone", "request_id": "x"})
    obs.correct(project, "OBS-0001", expected_rev=1, snapshot=_obs_snapshot(), reason="a",
                submitted={"actor": "owner", "channel": "phone"})
    req = {"id": "rq-obs-3", "kind": "observation_correction", "experiment": "E-009", "run": "PR-009-01",
           "payload": {"observation": "OBS-0001", "expected_rev": 1, "snapshot": _obs_snapshot(), "reason": "b"},
           "at": "2026-10-27T10:00:00+00:00"}
    with FakeLocalAI(requests=[req]) as fake:
        out = pull.apply_pending(project.root, fake.base, "k")
    assert out[0]["status"] == "conflict"


def test_pull_refuses_a_malformed_observation_instead_of_crashing(project):
    req = {"id": "rq-obs-4", "kind": "observation", "experiment": "E-009", "payload": {"snapshots": [{"x": 1}]},
           "at": "2026-10-27T10:00:00+00:00"}
    with FakeLocalAI(requests=[req]) as fake:
        out = pull.apply_pending(project.root, fake.base, "k")
    assert out[0]["status"] == "refused" and "subject" in out[0]["message"]


# ---- Bambuddy linking ------------------------------------------------------------------------------------------
LOG = json.loads((Path(__file__).parent / "fixtures" / "bambuddy_print_log.json").read_text())["items"]


def _entry(print_id: int, **changes) -> dict:
    e = next(x for x in LOG if x["id"] == print_id)
    return {**e, "print_name": "hex-tile_E-023_BLD-023-01", **changes}


@pytest.fixture
def lab023(tmp_path, monkeypatch):
    """hex-tile with E-023 printing BLD-023-01 on PR-023-01, and a key file for the fake Local AI."""
    key = tmp_path / "mac.key"
    key.write_text("k")
    monkeypatch.setenv("LAB_LOCALAI_KEY_FILE", str(key))
    e = started(minimal_experiment("E-023", "Q-023"), minutes=50.0, g=20.0)
    return make_project(tmp_path, minimal_question("Q-023", ("E-023",)), [e])


def _seen(paths) -> dict:
    return json.loads((paths.root / "bambuddy-seen.json").read_text())


def _run_pull(paths, monkeypatch, log, planned=None):
    from lab import bambuddy
    asked = []

    def archive(i, timeout=5.0):
        asked.append(i)
        return {"print_time_seconds": planned}
    monkeypatch.setattr(bambuddy, "print_log", log if callable(log) else (lambda *a, **k: log))
    monkeypatch.setattr(bambuddy, "archive", archive)
    with FakeLocalAI() as fake:
        return pull.pull(paths.root, fake.base), asked


def test_pull_links_new_prints_and_saves_last_id(lab023, monkeypatch):
    out, _ = _run_pull(lab023, monkeypatch, [_entry(25), _entry(24, print_name="benchy")])
    e = load_experiment(lab023, "E-023")
    assert e["print_runs"][0]["bambuddy"]["print"] == 25 and e["print_runs"][0]["bambuddy"]["snapshot_at"]
    assert {r["status"] for r in out} == {"applied"} and {r["id"] for r in out} == {"link-25"}
    assert len(out) == 2  # linked + snapshot
    assert _seen(lab023) == {"last_id": 25}
    out, _ = _run_pull(lab023, monkeypatch, [_entry(25), _entry(24, print_name="benchy")])
    assert out == []  # nothing new, nothing due


def test_pull_snapshots_a_print_that_was_printing_last_time(lab023, monkeypatch):
    _run_pull(lab023, monkeypatch, [_entry(25, status="printing", completed_at=None, duration_seconds=None)])
    assert load_experiment(lab023, "E-023")["print_runs"][0]["bambuddy"]["snapshot_at"] is None
    out, _ = _run_pull(lab023, monkeypatch, [_entry(25)])
    assert load_experiment(lab023, "E-023")["print_runs"][0]["bambuddy"]["snapshot_at"]
    assert [r["id"] for r in out] == ["link-25"]
    assert _seen(lab023) == {"last_id": 25}


def test_pull_asks_for_the_planned_time_once_per_archive(lab023, monkeypatch):
    log = [_entry(15, archive_id=7), _entry(16, archive_id=7, status="failed")]
    _, asked = _run_pull(lab023, monkeypatch, log, planned=3000.0)
    assert asked == [7]


@pytest.mark.parametrize("failure", ["none", "raises"])
def test_pull_with_bambuddy_down_keeps_last_id(lab023, monkeypatch, failure):
    (lab023.root / "bambuddy-seen.json").write_text(json.dumps({"last_id": 20}))

    def down(*a, **k):
        if failure == "raises":
            raise OSError("down")
        return None
    from unittest.mock import patch
    checked = []
    monkeypatch.setattr(pull, "check_active_print", lambda *a, **k: checked.append(1))
    out, _ = _run_pull(lab023, monkeypatch, down)
    assert out == [] and checked == [1]
    assert _seen(lab023) == {"last_id": 20}
    assert load_experiment(lab023, "E-023")["print_runs"][0].get("bambuddy") is None


def test_pull_does_not_report_or_sync_skipped_prints(lab023, monkeypatch):
    synced = []
    monkeypatch.setattr("lab.sync.sync", lambda *a, **k: synced.append(1))
    out, _ = _run_pull(lab023, monkeypatch, [_entry(25, print_name="hex-tile_E-999_BLD-999-01")])
    assert out == [] and synced == []


def test_pull_skips_linking_while_another_pull_holds_the_lock(lab023, monkeypatch):
    with open(lab023.root / ".pull.lock", "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        out, _ = _run_pull(lab023, monkeypatch, [_entry(25)])
    assert out == [] and not (lab023.root / "bambuddy-seen.json").exists()


def _saved_outside(paths, outside):
    from lab import page
    page.write(paths.root, {}, outside)


def _outside(paths):
    return json.loads((paths.root / "page.json").read_text())["outside"]


def test_pull_drops_a_print_it_linked_from_outside_and_adds_a_new_one(lab023, monkeypatch):
    stale = [{"print": 25, "archive": 25, "name": "x", "status_word": "Finished", "started": None, "ended": None}]
    _saved_outside(lab023, stale)
    synced = []
    monkeypatch.setattr("lab.sync.sync", lambda *a, **k: synced.append(1))
    _run_pull(lab023, monkeypatch, [_entry(25), _entry(24, print_name="benchy")])
    assert [o["print"] for o in _outside(lab023)] == [24] and synced == [1]


def test_pull_with_bambuddy_silent_keeps_outside_and_does_not_sync_for_it(lab023, monkeypatch):
    saved = [{"print": 3, "archive": 3, "name": "x", "status_word": "Finished", "started": None, "ended": None}]
    _saved_outside(lab023, saved)
    synced = []
    monkeypatch.setattr("lab.sync.sync", lambda *a, **k: synced.append(1))
    _run_pull(lab023, monkeypatch, lambda *a, **k: None)
    assert _outside(lab023) == saved and synced == []


def test_pull_does_not_sync_when_outside_is_unchanged(lab023, monkeypatch):
    _saved_outside(lab023, [])
    synced = []
    monkeypatch.setattr("lab.sync.sync", lambda *a, **k: synced.append(1))
    _run_pull(lab023, monkeypatch, [_entry(25, print_name="hex-tile_E-999_BLD-999-01")])
    assert _outside(lab023) != [] and synced == [1]  # a new outside print is a change
    synced.clear()
    _run_pull(lab023, monkeypatch, [_entry(25, print_name="hex-tile_E-999_BLD-999-01")])
    assert synced == []


def test_sync_sends_outside_and_it_changes_the_fingerprint(lab023, monkeypatch):
    from lab import page
    _saved_outside(lab023, [])
    sent = []
    with FakeLocalAI() as fake:
        sync.sync(lab023.root, base=fake.base)
        _saved_outside(lab023, [{"print": 9, "archive": 9, "name": "n", "status_word": "Finished", "started": None,
                                 "ended": None}])
        sync.sync(lab023.root, base=fake.base)
        posts = [c[3] for c in fake.calls if c[0] == "POST" and "/sync" in c[1]]
    assert posts[0]["outside"] == [] and [o["print"] for o in posts[1]["outside"]] == [9]
    assert posts[0]["fingerprint"] != posts[1]["fingerprint"]


def test_a_second_pull_with_an_unchanged_log_leaves_page_json_alone(lab023, monkeypatch):
    import time
    log = [_entry(25, print_name="hex-tile_E-999_BLD-999-01")]
    monkeypatch.setattr("lab.sync.sync", lambda *a, **k: None)
    _saved_outside(lab023, [])
    _run_pull(lab023, monkeypatch, log)
    f = lab023.root / "page.json"
    before, mtime = f.read_text(), f.stat().st_mtime_ns
    time.sleep(0.02)
    _run_pull(lab023, monkeypatch, log)
    assert f.read_text() == before and f.stat().st_mtime_ns == mtime


def test_a_status_change_of_an_outside_print_is_a_change(lab023, monkeypatch):
    synced = []
    monkeypatch.setattr("lab.sync.sync", lambda *a, **k: synced.append(1))
    _saved_outside(lab023, [])
    other = dict(print_name="hex-tile_E-999_BLD-999-01")
    _run_pull(lab023, monkeypatch, [_entry(25, status="printing", completed_at=None, **other)])
    synced.clear()
    _run_pull(lab023, monkeypatch, [_entry(25, status="completed", **other)])
    assert synced == [1] and _outside(lab023)[0]["status_word"] == "Finished"


def test_sync_fingerprint_changes_when_only_an_outside_status_changes(lab023, monkeypatch):
    row = {"print": 9, "archive": 9, "name": "n", "status_word": "Printing", "started": None, "ended": None}
    _saved_outside(lab023, [row])
    with FakeLocalAI() as fake:
        sync.sync(lab023.root, base=fake.base)
        _saved_outside(lab023, [{**row, "status_word": "Finished"}])
        sync.sync(lab023.root, base=fake.base)
        posts = [c[3] for c in fake.calls if c[0] == "POST" and "/sync" in c[1]]
    assert posts[0]["fingerprint"] != posts[1]["fingerprint"]
