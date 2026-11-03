"""`lab pull` sends its verdict notice to the phone through Pi Hub (platform step 5, D2), not as a Mac banner."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from lab import pull, sync

EVENT = {"action": "telemetry_applied", "experiment": "E-022", "run": "PR-022-01", "elapsed_minutes": 51, "grams": 9}


@pytest.fixture
def hub(monkeypatch):
    """A stand-in Pi Hub: answers /api/notify/print-lab with the next status in `statuses` (then 200)."""
    got, statuses = [], []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            got.append({"path": self.path, "key": self.headers.get(sync.HUB_HEADER), "body": body})
            self.send_response(statuses.pop(0) if statuses else 200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')

        def log_message(self, *a):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    monkeypatch.setattr(sync, "hub_target", lambda: sync.Target("Pi Hub", base, sync.HUB_HEADER, "lab-key", None))
    yield got, statuses
    server.shutdown()


def test_the_verdict_notice_links_to_the_judge_sheet():
    n = pull.verdict_notice(EVENT, now_ts=1000)
    assert n == {"kind": "verdict", "title": "E-022 is ready for a verdict", "body": "Print PR-022-01 finished.",
                 "click": "https://hub.rahe-home.duckdns.org/lab?e=E-022&do=judge", "dedupe": "verdict-PR-022-01",
                 "at": 1000}
    unknown = pull.verdict_notice({**EVENT, "elapsed_minutes": None})
    assert "printer's history" in unknown["body"]


def test_a_notice_is_posted_with_the_lab_key(hub):
    got, _ = hub
    assert pull.flush_notices([pull.verdict_notice(EVENT)]) == []
    assert got[0]["path"] == "/api/notify/print-lab" and got[0]["key"] == "lab-key"
    assert got[0]["body"]["kind"] == "verdict" and "at" not in got[0]["body"]


def test_one_pi_hub_didnt_take_is_kept_with_the_rest_then_sent(hub):
    got, statuses = hub
    a, b = pull.verdict_notice(EVENT), pull.verdict_notice({**EVENT, "run": "PR-022-02"})
    statuses.append(502)
    assert pull.flush_notices([a, b]) == [a, b]
    assert pull.flush_notices([a, b]) == []
    assert [g["body"]["dedupe"] for g in got] == ["verdict-PR-022-01", "verdict-PR-022-01", "verdict-PR-022-02"]


def test_a_400_or_an_old_notice_is_dropped(hub, capsys):
    got, statuses = hub
    statuses.append(400)
    assert pull.flush_notices([pull.verdict_notice(EVENT)]) == []
    assert "refused a phone notice as invalid" in capsys.readouterr().err
    old = pull.verdict_notice(EVENT, now_ts=1000)
    assert pull.flush_notices([old], now_ts=1000 + 3601) == [] and len(got) == 1


def test_no_hub_key_drops_them_and_an_unreachable_hub_keeps_them(monkeypatch):
    n = pull.verdict_notice(EVENT)
    monkeypatch.setattr(sync, "hub_target", lambda: None)
    assert pull.flush_notices([n]) == []
    monkeypatch.setattr(sync, "hub_target", lambda: sync.Target("Pi Hub", "http://127.0.0.1:9", sync.HUB_HEADER, "k", None))
    assert pull.flush_notices([n], timeout=2) == [n]
