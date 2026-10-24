import hashlib

import pytest

from lab.loop.setup_log import append_event, current_setup, effective_events, repair_line
from lab.records.project import ProjectPaths
from lab.records.store import RecordError


@pytest.fixture
def paths(tmp_path):
    return ProjectPaths(tmp_path / "projects" / "hex-tile")


def test_events_get_ids_and_current_setup(paths):
    a = append_event(paths, "nozzle_changed", {"diameter_mm": 0.4})
    b = append_event(paths, "filament_dried", {"hours": 6, "spool": "C6719062"})
    assert (a["id"], b["id"]) == ("SET-00001", "SET-00002")
    cur = current_setup(paths)
    assert cur["nozzle_changed"]["fields"]["diameter_mm"] == 0.4 and cur["filament_dried"]["fields"]["hours"] == 6


def test_correction_supersedes_at_original_time(paths):
    a = append_event(paths, "nozzle_changed", {"diameter_mm": 0.4})
    append_event(paths, "correction", {}, supersedes=a["id"],
                 replacement={"kind": "nozzle_changed", "fields": {"diameter_mm": 0.6}})
    ev = effective_events(paths)
    assert len(ev) == 1 and ev[0]["id"] == "SET-00001" and ev[0]["fields"]["diameter_mm"] == 0.6
    assert ev[0]["at"] == a["at"]


def test_malformed_line_stops_reading_until_repaired(paths):
    append_event(paths, "nozzle_changed", {"diameter_mm": 0.4})
    with open(paths.setup_log, "a") as f:
        f.write('{"schema": 1, "record_type": "setup_event", "id": "SET-00002", "kind": "filament_dr\n')
    with pytest.raises(RecordError, match="line 2"):
        effective_events(paths)
    repair_line(paths, 2, {"kind": "filament_dried", "fields": {"hours": 6}, "at": "2026-10-25T08:00:00+00:00"},
                "truncated while pasting")
    ev = effective_events(paths)
    assert [e["kind"] for e in ev] == ["nozzle_changed", "filament_dried"] and ev[1]["id"] == "SET-00002"


def test_repair_applies_only_when_hash_matches(paths):
    append_event(paths, "nozzle_changed", {"diameter_mm": 0.4})
    with open(paths.setup_log, "a") as f:
        f.write("not json\n")
    repair_line(paths, 2, {"kind": "filament_dried", "fields": {}, "at": "t"}, "bad paste")
    lines = paths.setup_log.read_text().splitlines()
    lines[1] = "different garbage"
    paths.setup_log.write_text("\n".join(lines) + "\n")
    with pytest.raises(RecordError, match="line 2"):
        effective_events(paths)


def test_readable_line_is_not_repaired(paths):
    append_event(paths, "nozzle_changed", {"diameter_mm": 0.4})
    with pytest.raises(ValueError, match="correction"):
        repair_line(paths, 1, {"kind": "x", "fields": {}, "at": "t"}, "oops")


def test_current_setup_at_a_past_time(paths):
    a = append_event(paths, "nozzle_changed", {"diameter_mm": 0.4})
    then = a["at"]
    import time
    time.sleep(1.1)
    append_event(paths, "nozzle_changed", {"diameter_mm": 0.6})
    assert current_setup(paths, then)["nozzle_changed"]["fields"]["diameter_mm"] == 0.4
    assert current_setup(paths)["nozzle_changed"]["fields"]["diameter_mm"] == 0.6


def test_original_bytes_never_change(paths):
    append_event(paths, "nozzle_changed", {"diameter_mm": 0.4})
    with open(paths.setup_log, "a") as f:
        f.write("broken\n")
    before = hashlib.sha256(paths.setup_log.read_bytes()).hexdigest()
    repair_line(paths, 2, {"kind": "filament_dried", "fields": {}, "at": "t"}, "bad paste")
    append_event(paths, "vibration_calibration", {})
    assert paths.setup_log.read_bytes().startswith(b"")
    assert hashlib.sha256(paths.setup_log.read_bytes().rsplit(b"\n", 2)[0] + b"\n").hexdigest() == before
