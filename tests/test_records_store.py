import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from lab.records.store import (RecordError, atomic_write_json, create_record, next_local_id, parse_budget, read_json,
                               record_lock)
from lab.records.project import ProjectPaths, project_settings


def test_atomic_write_leaves_original_when_replace_fails(tmp_path, monkeypatch):
    p = tmp_path / "E-001.json"
    atomic_write_json(p, {"a": 1})

    def boom(*a):
        raise OSError("disk")
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        atomic_write_json(p, {"a": 2})
    assert json.loads(p.read_text()) == {"a": 1}
    assert [f.name for f in tmp_path.iterdir()] == ["E-001.json"]


def test_invalid_json_names_file_and_line(tmp_path):
    p = tmp_path / "E-002.json"
    p.write_text('{"a": 1,\n "b": }')
    with pytest.raises(RecordError, match=r"E-002.json.*line 2"):
        read_json(p)


HOLD = """
import sys, time
from pathlib import Path
from lab.records.store import record_lock
with record_lock(Path(sys.argv[1]), "E-004", "lab exp verdict E-004"):
    print("held", flush=True)
    time.sleep(5)
"""


def test_lock_timeout_names_holder(tmp_path):
    p = subprocess.Popen([sys.executable, "-c", HOLD, str(tmp_path)], stdout=subprocess.PIPE, text=True,
                         cwd=Path(__file__).parent.parent)
    try:
        assert p.stdout.readline().strip() == "held"
        with pytest.raises(RecordError, match=r"lab exp verdict E-004.*PID \d+"):
            with record_lock(tmp_path, "E-004", "lab exp observe E-004", timeout_s=0.5):
                pass
    finally:
        p.kill()


def test_lock_freed_when_holder_dies(tmp_path):
    p = subprocess.Popen([sys.executable, "-c", HOLD, str(tmp_path)], stdout=subprocess.PIPE, text=True,
                         cwd=Path(__file__).parent.parent)
    assert p.stdout.readline().strip() == "held"
    p.kill(); p.wait()
    with record_lock(tmp_path, "E-004", "lab exp observe E-004", timeout_s=1):
        pass


ALLOC = """
import sys
from pathlib import Path
from lab.records.store import create_record
d = Path(sys.argv[1])
print(create_record(d / ".locks", d, "E", lambda i: {"id": i})[0])
"""


def test_parallel_allocation_never_collides(tmp_path):
    ps = [subprocess.Popen([sys.executable, "-c", ALLOC, str(tmp_path)], stdout=subprocess.PIPE, text=True,
                           cwd=Path(__file__).parent.parent) for _ in range(8)]
    ids = sorted(p.communicate()[0].strip() for p in ps)
    assert ids == [f"E-{i:03d}" for i in range(1, 9)]
    assert sorted(f.name for f in tmp_path.glob("E-*.json")) == [f"E-{i:03d}.json" for i in range(1, 9)]
    assert json.loads((tmp_path / "E-003.json").read_text()) == {"id": "E-003"}


def test_crash_before_link_leaves_no_record(tmp_path, monkeypatch):
    def boom(*a):
        raise OSError("killed")
    monkeypatch.setattr(os, "link", boom)
    with pytest.raises(OSError):
        create_record(tmp_path / ".locks", tmp_path, "E", lambda i: {"id": i})
    assert not list(tmp_path.glob("E-*"))


def test_create_record_validates(tmp_path):
    def bad(rec):
        raise RecordError(tmp_path / "x", "id", "nope")
    with pytest.raises(RecordError):
        create_record(tmp_path / ".locks", tmp_path, "Q", lambda i: {"id": i}, validate=bad)
    assert not list(tmp_path.glob("Q-*"))


def test_local_ids():
    assert next_local_id({"builds": [{"id": "BLD-004-01"}]}, "builds", "BLD-004") == "BLD-004-02"
    assert next_local_id({}, "print_runs", "PR-005") == "PR-005-01"


@pytest.mark.parametrize("text,want", [("180m,100g", {"minutes": 180, "g": 100}), ("3h", {"minutes": 180, "g": None}),
                                       ("2h30m", {"minutes": 150, "g": None}), ("100g", {"minutes": None, "g": 100})])
def test_parse_budget(text, want):
    assert parse_budget(text) == want


def test_budget_without_units_refused():
    with pytest.raises(ValueError, match="units"):
        parse_budget("180,100")


def test_project_settings_defaults(tmp_path):
    s = project_settings(ProjectPaths(tmp_path))
    assert s["autonomy_level"] == 2 and s["plate_time_tolerance_pct"] == 10
    assert s["plate_time_tolerance_source"] == "provisional"
    assert s["budget"] == {"max_test_minutes": 45, "max_test_g": 25, "max_minutes": 180, "max_g": 100}
