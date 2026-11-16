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
    assert bambuddy.base_url() == "http://10.0.0.80:8000"
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
    assert bambuddy.print_log(timeout=60) == [{"id": 26}, {"id": 5}, {"id": 3}]
    req = seen["req"]
    assert req.full_url == "http://bambuddy.test/api/v1/print-log/?limit=100&offset=0"
    assert req.get_header("X-api-key") == "k1"
    assert req.get_method() == "GET"
    assert seen["timeout"] <= 5
    assert bambuddy.last_error() is None


def test_print_log_failures_say_why(monkeypatch):
    _stub(monkeypatch, exc=urllib.error.HTTPError("u", 401, "Unauthorized", {}, io.BytesIO(
        b'{"detail": "Authentication required"}')))
    assert bambuddy.print_log() is None
    assert "401 Authentication required" in bambuddy.last_error()
    _stub(monkeypatch, exc=urllib.error.URLError(TimeoutError("timed out")))
    assert bambuddy.print_log() is None
    assert bambuddy.last_error().startswith("Bambuddy didn't answer GET /api/v1/print-log/")
    _stub(monkeypatch, b"not json")
    assert bambuddy.print_log() is None
    assert "unreadable" in bambuddy.last_error()
    _stub(monkeypatch, b'{"total": 0}')
    assert bambuddy.print_log() is None
    assert "no items" in bambuddy.last_error()


def test_print_log_without_a_key_says_so(monkeypatch, tmp_path):
    monkeypatch.setenv("LAB_BAMBUDDY_KEY_FILE", str(tmp_path / "missing"))
    seen = _stub(monkeypatch, b"{}")
    assert bambuddy.print_log() is None and "req" not in seen
    assert "No Bambuddy API key" in bambuddy.last_error()


def _paged(monkeypatch, ids: list[int]):
    """A print log of `ids` (newest first, as Bambuddy's date order), served a page at a time; the offsets asked."""
    asked = []

    def fake(req, timeout=None):
        q = dict(x.split("=") for x in req.full_url.split("?", 1)[1].split("&"))
        limit, offset = int(q["limit"]), int(q["offset"])
        asked.append(offset)
        page = [{"id": i} for i in ids[offset:offset + limit]]
        return _Resp(json.dumps({"items": page, "total": len(ids)}).encode())
    monkeypatch.setattr("urllib.request.urlopen", fake)
    return asked


def test_print_log_pages_back_to_the_id_asked(monkeypatch):
    ids = list(range(250, 0, -1))
    asked = _paged(monkeypatch, ids)
    assert [x["id"] for x in bambuddy.print_log()] == ids[:100] and asked == [0]  # one page by default
    asked.clear()
    log = bambuddy.print_log(since_id=120)
    assert asked == [0, 100] and log[-1]["id"] == 51  # the page holding #121 is read whole
    asked.clear()
    assert len(bambuddy.print_log(since_id=0)) == 250 and asked == [0, 100, 200]


def test_print_log_stops_at_the_end_and_a_failed_page_fails_it(monkeypatch):
    asked = _paged(monkeypatch, list(range(100, 0, -1)))
    assert len(bambuddy.print_log(since_id=0)) == 100 and asked == [0]  # total reached: no empty page asked
    calls = []

    def flaky(req, timeout=None):
        calls.append(req.full_url)
        if len(calls) > 1:
            raise urllib.error.URLError("down")
        return _Resp(json.dumps({"items": [{"id": i} for i in range(300, 200, -1)], "total": 300}).encode())
    monkeypatch.setattr("urllib.request.urlopen", flaky)
    assert bambuddy.print_log(since_id=0) is None and "didn't answer" in bambuddy.last_error()


def test_find_print_pages_back(monkeypatch):
    asked = _paged(monkeypatch, list(range(250, 0, -1)))
    assert bambuddy.find_print(30) == {"id": 30} and asked == [0, 100, 200]
    asked.clear()
    assert bambuddy.find_print(240) == {"id": 240} and asked == [0]
    assert bambuddy.find_print(999) is None and bambuddy.last_error() is None  # not there is not a failure


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
