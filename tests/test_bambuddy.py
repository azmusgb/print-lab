"""lab/bambuddy.py: lab-name parsing, status words, UTC timestamps and the read-only print-log client."""
import io
import json
import urllib.error
from datetime import datetime, timezone

import pytest

from lab import bambuddy


def test_parse_lab_name():
    assert bambuddy.parse_lab_name("hex-tile_E-023_BLD-023-01") == {
        "project": "hex-tile", "exp": "E-023", "build": "BLD-023-01"}
    for bad in ("HEX_TILE_v72", "", None, "hex-tile_E-023_BLD-023-01.3mf"):
        assert bambuddy.parse_lab_name(bad) is None


def test_status_word():
    assert bambuddy.status_word("completed") == "Finished"
    assert bambuddy.status_word("failed") == "Failed"
    assert bambuddy.status_word("cancelled") == "Cancelled"
    assert bambuddy.status_word("printing") == "Printing"
    assert bambuddy.status_word("paused") == "Paused"
    assert bambuddy.status_word(None) == "Unknown"


def test_parse_time():
    assert bambuddy.parse_time("2026-10-27T20:36:30.716390") == datetime(
        2026, 10, 27, 20, 36, 30, 716390, tzinfo=timezone.utc)
    aware = bambuddy.parse_time("2026-10-27T20:36:30+02:00")
    assert aware.utcoffset().total_seconds() == 7200
    assert bambuddy.parse_time("nonsense") is None
    assert bambuddy.parse_time(None) is None


def test_base_url_and_key(monkeypatch, tmp_path):
    monkeypatch.delenv("LAB_BAMBUDDY_URL", raising=False)
    assert bambuddy.base_url() == "http://10.0.0.30:8000"
    monkeypatch.setenv("LAB_BAMBUDDY_URL", "off")
    assert bambuddy.base_url() == "off"
    (tmp_path / "key").write_text(" abc \n")
    monkeypatch.setenv("LAB_BAMBUDDY_KEY_FILE", str(tmp_path / "key"))
    assert bambuddy.key() == "abc"
    monkeypatch.setenv("LAB_BAMBUDDY_KEY_FILE", str(tmp_path / "missing"))
    assert bambuddy.key() is None


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _stub(monkeypatch, body=None, exc=None):
    seen = {}

    def fake(req, timeout=None):
        seen["req"], seen["timeout"] = req, timeout
        if exc:
            raise exc
        return _Resp(body)
    monkeypatch.setattr("urllib.request.urlopen", fake)
    return seen


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("LAB_BAMBUDDY_URL", "http://bambuddy.test")
    (tmp_path / "key").write_text("k1")
    monkeypatch.setenv("LAB_BAMBUDDY_KEY_FILE", str(tmp_path / "key"))


def test_print_log_off(monkeypatch):
    monkeypatch.setenv("LAB_BAMBUDDY_URL", "off")
    seen = _stub(monkeypatch, b"{}")
    assert bambuddy.print_log() is None
    assert "req" not in seen


def test_print_log_newest_first_and_request(monkeypatch):
    seen = _stub(monkeypatch, json.dumps({"items": [{"id": 3}, {"id": 26}, {"id": 5}], "total": 3}).encode())
    assert bambuddy.print_log(limit=7, timeout=60) == [{"id": 26}, {"id": 5}, {"id": 3}]
    req = seen["req"]
    assert req.full_url == "http://bambuddy.test/api/v1/print-log/?limit=7"
    assert req.get_header("X-api-key") == "k1"
    assert req.get_method() == "GET"
    assert seen["timeout"] <= 5


def test_print_log_failures(monkeypatch):
    _stub(monkeypatch, exc=urllib.error.HTTPError("u", 500, "boom", {}, None))
    assert bambuddy.print_log() is None
    _stub(monkeypatch, b"not json")
    assert bambuddy.print_log() is None
    _stub(monkeypatch, b'{"total": 0}')
    assert bambuddy.print_log() is None


def test_archive(monkeypatch):
    seen = _stub(monkeypatch, b'{"id": 9}')
    assert bambuddy.archive(9) == {"id": 9}
    assert seen["req"].full_url == "http://bambuddy.test/api/v1/archives/9"
    _stub(monkeypatch, exc=OSError("down"))
    assert bambuddy.archive(9) is None


def test_a_naive_midnight_adjacent_time_is_read_as_utc_not_local(monkeypatch):
    import time
    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()
    try:
        t = bambuddy.parse_time("2026-10-28T02:30:00")  # 22:30 EDT on the 27th if it were local
        assert t.isoformat() == "2026-10-28T02:30:00+00:00"
    finally:
        monkeypatch.undo()
        time.tzset()
