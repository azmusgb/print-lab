"""The suite must never touch the lab's real records (a test once rewrote projects/hex-tile/cases/CASE-001.json)."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from lab.cli import ROOT, main, project_dir


def test_cli_calls_without_a_project_root_go_to_a_temporary_lab():
    assert Path(os.environ["LAB_HOME"]).resolve() != ROOT.resolve()
    assert not project_dir("hex-tile").resolve().is_relative_to(ROOT.resolve())


def test_writing_a_record_inside_the_real_lab_is_refused_before_it_happens():
    from lab.records.store import atomic_write_json
    target = ROOT / "projects" / "hex-tile" / "cases" / "CASE-ISOLATION-PROBE.json"
    with pytest.raises(PermissionError, match="real lab"):
        atomic_write_json(target, {"probe": True})
    assert not target.exists()


def test_modules_that_imported_the_writer_by_name_are_guarded_too():
    from lab.loop import commands
    with pytest.raises(PermissionError, match="real lab"):
        commands.atomic_write_json(ROOT / "projects" / "probe.json", {})


def test_a_subprocess_inherits_the_temporary_lab():
    out = subprocess.run([sys.executable, "-c", "import os; print(os.environ['LAB_HOME'])"],
                         capture_output=True, text=True, check=True).stdout.strip()
    assert Path(out).resolve() == Path(os.environ["LAB_HOME"]).resolve()


def test_the_case_commands_run_against_a_temporary_project(capsys):
    rc = main(["case", "list"])
    assert rc == 0


def test_paths_fixed_at_import_point_away_from_the_real_lab():
    from lab import source
    from lab.loop import capabilities
    for p in (source.CAP_DIR, capabilities.CAP_DIR):
        assert not p.resolve().is_relative_to(ROOT.resolve())


def test_home_and_local_ai_point_nowhere_real():
    from lab import sync
    assert Path.home().resolve() != Path(os.environ["PYTEST_REAL_HOME"]).resolve()
    assert os.environ["LAB_LOCALAI_URL"].startswith("http://127.0.0.1:9")
    assert not Path(os.environ["LAB_LOCALAI_KEY_FILE"]).exists()
    assert not Path(os.environ["LAB_HUB_KEY_FILE"]).exists()
    assert os.environ["LAB_HUB_URL"].startswith("https://127.0.0.1:9")
    assert not sync.HOME.resolve().is_relative_to(Path(os.environ["PYTEST_REAL_HOME"]).resolve())


@pytest.mark.parametrize("argv", [["launchctl", "list"], ["/bin/launchctl", "list"],
                                  ["osascript", "-e", "display notification \"x\""]])
def test_launchd_and_notifications_are_refused(argv):
    with pytest.raises(PermissionError, match="tests don't"):
        subprocess.run(argv, capture_output=True)


def test_locks_and_new_records_inside_the_real_lab_are_refused():
    from lab.records.store import create_record, record_lock
    with pytest.raises(PermissionError, match="real lab"):
        with record_lock(ROOT / "projects" / "hex-tile" / ".locks", "probe", "test"):
            pass
    with pytest.raises(PermissionError, match="real lab"):
        create_record(Path(os.environ["LAB_HOME"]) / "locks", ROOT / "projects" / "probe-folder", "P",
                      lambda i: {"id": i})
    assert not (ROOT / "projects" / "probe-folder").exists()
