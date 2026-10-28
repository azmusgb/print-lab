"""Sync targets: Local AI and the Pi Hub, each with its own address, trust and key header (Plan B, Task 1)."""
import json
import shutil
import ssl
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from lab import sync
from lab.sync import Target


@pytest.fixture
def keys(tmp_path, monkeypatch):
    lai, hub = tmp_path / "mac.key", tmp_path / "hub.key"
    lai.write_text("localai-secret\n")
    hub.write_text("hub-secret\n")
    monkeypatch.setenv("LAB_LOCALAI_KEY_FILE", str(lai))
    monkeypatch.setenv("LAB_HUB_KEY_FILE", str(hub))
    monkeypatch.setenv("LAB_HUB_CA", str(tmp_path / "no-such-ca.crt"))
    return lai, hub


def test_no_hub_key_reports_missing_hub(keys, monkeypatch):
    monkeypatch.setenv("LAB_HUB_KEY_FILE", str(keys[1].parent / "absent.key"))
    assert sync.targets() == [("Pi Hub", "No Pi Hub key (save ~/.config/print-lab/hub.key)")]


def test_hub_target_when_set_up(keys, tmp_path, monkeypatch):
    ca = _make_ca(tmp_path)
    monkeypatch.setenv("LAB_HUB_CA", str(ca))
    ts = sync.targets()
    assert [t.name for t in ts] == ["Pi Hub"]
    assert ts[0].header == "X-Hub-Mac-Key" and ts[0].key == "hub-secret"


def test_hub_needs_https(keys, monkeypatch):
    monkeypatch.setenv("LAB_HUB_URL", "http://10.0.0.30")
    hub = sync.targets()[0]
    assert hub == ("Pi Hub", "The Pi Hub address must start with https://")


def test_hub_needs_the_house_ca(keys):
    hub = sync.targets()[0]
    assert hub[0] == "Pi Hub" and hub[1].startswith("Save the house CA first")


def test_hub_with_an_empty_key_fails(keys, monkeypatch, tmp_path):
    keys[1].write_text("\n")
    monkeypatch.setenv("LAB_HUB_CA", str(_make_ca(tmp_path)))
    hub = sync.targets()[0]
    assert hub[0] == "Pi Hub" and "key" in hub[1].lower()


def test_the_default_hub_address_is_https(keys, tmp_path, monkeypatch):
    monkeypatch.delenv("LAB_HUB_URL", raising=False)
    monkeypatch.setenv("LAB_HUB_CA", str(_make_ca(tmp_path)))
    assert sync.hub_target().base == "https://home.home.arpa"


def _make_ca(tmp_path):
    if not shutil.which("openssl"):
        pytest.skip("openssl isn't installed")
    crt, key = tmp_path / "ca.crt", tmp_path / "ca.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out", str(crt),
                    "-days", "2", "-subj", "/CN=test"], check=True, capture_output=True)
    return crt


def test_hub_context_trusts_only_the_house_ca(keys, tmp_path, monkeypatch):
    ca = _make_ca(tmp_path)
    monkeypatch.setenv("LAB_HUB_CA", str(ca))
    monkeypatch.setenv("LAB_HUB_URL", "https://hub.example")
    t = sync.hub_target()
    assert t.context.verify_mode == ssl.CERT_REQUIRED
    certs = t.context.get_ca_certs()
    assert len(certs) == 1 and ("commonName", "test") in [x[0] for x in certs[0]["subject"]]


def test_hub_target_is_none_without_a_key_file(keys, monkeypatch, tmp_path):
    monkeypatch.setenv("LAB_HUB_KEY_FILE", str(tmp_path / "absent.key"))
    assert sync.hub_target() is None


def test_explicit_base_is_hub(keys, monkeypatch, tmp_path):
    monkeypatch.setenv("LAB_HUB_CA", str(_make_ca(tmp_path)))
    ts = sync.targets("http://127.0.0.1:1234/")
    assert len(ts) == 1 and ts[0].name == "Pi Hub" and ts[0].base == "http://127.0.0.1:1234"


class Fake:
    def __init__(self, status=200, body=None):
        self.headers, self.status, self.body = [], status, body or {"have": []}

    def __enter__(self):
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers.get('Content-Length', 0)))
                self.do_GET()

            def do_GET(self):
                fake.headers.append({k.lower(): v for k, v in self.headers.items()})
                b = json.dumps(fake.body).encode()
                self.send_response(fake.status)
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        return self

    def __exit__(self, *a):
        self.server.shutdown()


def test_each_target_sends_only_its_own_header(keys):
    with Fake() as lai, Fake() as hub:
        sync._call(Target("Local AI", lai.base, "X-LocalAI-Mac-Key", "localai-secret", None), "GET", "/x", 5)
        sync._call(Target("Pi Hub", hub.base, "X-Hub-Mac-Key", "hub-secret", None), "GET", "/x", 5)
    assert lai.headers[0]["x-localai-mac-key"] == "localai-secret" and "x-hub-mac-key" not in lai.headers[0]
    assert hub.headers[0]["x-hub-mac-key"] == "hub-secret" and "x-localai-mac-key" not in hub.headers[0]


@pytest.mark.parametrize("body,expected", [({"error": "older push"}, "older push"), ({"detail": "Bad key"}, "Bad key"),
                                           ({}, "HTTP 409")])
def test_error_text_is_the_replys_error_or_detail_else_the_code(body, expected):
    assert sync._error(body, 409) == expected


def test_a_hub_error_reaches_the_sync_message(tmp_path):
    with Fake(status=401, body={"detail": "Bad Mac key"}) as f:
        r = sync._sync_to_target(tmp_path, Target("Pi Hub", f.base, "X-Hub-Mac-Key", "k", None),
                                 {"project": "p", "experiments": []})
    assert r["ok"] is False and r["message"] == "Bad Mac key"


@pytest.mark.parametrize("bad", ["abc\ndef", "abc\r\ndef", "abc def", "abc\tdef", "abc\x00def", "abc\x7fdef", "abcé"])
def test_a_key_with_whitespace_or_control_characters_is_refused_without_quoting_it(keys, tmp_path, monkeypatch, bad):
    keys[1].write_text(bad)
    keys[0].write_text(bad)
    monkeypatch.setenv("LAB_HUB_CA", str(_make_ca(tmp_path)))
    with pytest.raises(ValueError) as h:
        sync.hub_target()
    assert "Pi Hub key file has characters a key can't contain" in str(h.value) and "abc" not in str(h.value)
    with pytest.raises(ValueError) as l:
        sync.localai_target("http://127.0.0.1:9")
    assert "Local AI key file has characters a key can't contain" in str(l.value) and "abc" not in str(l.value)


def test_a_bad_key_text_never_reaches_sync_json_or_the_target_list(keys, tmp_path, monkeypatch):
    keys[1].write_text("abc\ndef")
    monkeypatch.setenv("LAB_HUB_CA", str(_make_ca(tmp_path)))
    ts = sync.targets()
    assert ts[0][0] == "Pi Hub" and "abc" not in ts[0][1] and "def" not in ts[0][1]
    pdir = tmp_path / "proj"
    pdir.mkdir()
    sync.sync(pdir)
    assert "abc" not in (pdir / "sync.json").read_text()
    r = sync.sync(pdir, "http://127.0.0.1:9")
    assert "abc" not in json.dumps(r) and "abc" not in (pdir / "sync.json").read_text()
