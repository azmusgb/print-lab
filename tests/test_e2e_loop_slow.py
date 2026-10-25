"""The whole experiment loop through the `lab` command, in a temporary lab folder, with real Bambu Studio slices
(spec: Testing, end to end), plus a build that dies before its last write and a change made while another process
holds the lock."""
import json
import re
import subprocess
import sys
import textwrap
import zipfile

import pytest

from lab.cli import main
from loop_fixtures import project_with_sources

pytestmark = pytest.mark.slow

PLAN = ["--factor", "inner_wall_speed", "--values", "250,80", "--expect", "B>A:clearly", "--judge-on", "bands",
        "--source", "sources/hexagon_v58_X2D_0.6nozzle.3mf", "--object", "v58_06_6in",
        "--base", "sources/hexagon_v57_X2D_0.4nozzle.3mf", "--hypothesis", "Fast inner walls starve the outer wall.",
        "--prediction", "B (80) is clearly smoother.", "--no-tabs"]


@pytest.fixture
def lab(tmp_path, monkeypatch, capsys):
    paths = project_with_sources(tmp_path)
    monkeypatch.setenv("LAB_HOME", str(tmp_path))

    def run(*argv, code=0):
        rc = main(list(argv))
        out = capsys.readouterr()
        assert rc == code, f"lab {' '.join(argv)} → {rc}\n{out.out}\n{out.err}"
        return out.out + out.err
    run.paths = paths
    return run


def _exp(paths, eid):
    return json.loads((paths.experiments / f"{eid}.json").read_text())


def test_end_to_end_loop(lab):
    p = lab.paths
    qid = re.search(r"Created (Q-\d+)", lab("question", "new", "Do slower inner walls help?", "--budget", "3h,100g"))[1]

    e1 = re.search(r"Planned (E-\d+)", lab("exp", "plan", qid, "Slow vs fast inner walls", "--z", "63:69", *PLAN))[1]
    lab("exp", "build", e1)
    assert "READY" in lab("exp", "check", e1)

    out = lab("exp", "start", e1)
    run = _exp(p, e1)["print_runs"][-1]
    assert run["id"] in out and run["setup"] is not None

    out = lab("exp", "verdict", e1, "--rank", "B>A", "--strength", "clearly")
    assert "outcome supported, comparison valid" in out
    est1 = _exp(p, e1)["builds"][-1]["estimate"]

    # an experiment over the per-test budget needs approval; a rebuild voids it and start refuses
    e2 = re.search(r"Planned (E-\d+)", lab("exp", "plan", qid, "The same on a taller strip", "--z", "60:72", *PLAN))[1]
    lab("exp", "build", e2)
    assert "NEEDS APPROVAL" in lab("exp", "check", e2, code=2)
    status = lab("question", "status", qid)
    assert f"{_n(est1['minutes'])} / 180 min" in status and f"{e2} is needs approval" in status
    lab("exp", "approve", e2, "--reason", "taller strip")
    assert _exp(p, e2)["status"] == "approved"
    with zipfile.ZipFile(p.root / "sources/hexagon_v57_X2D_0.4nozzle.3mf", "a") as z:
        z.comment = b"re-exported"  # the settings file changed, so --replace really builds again
    assert "BLD-" in lab("exp", "build", e2, "--replace")
    assert len(_exp(p, e2)["builds"]) == 2
    assert _exp(p, e2)["approval"] is None
    assert f"Can't start {e2}:\n  per_test_time" in lab("exp", "start", e2, code=1)

    # an owner stop can't be approved away; resume lifts it and keeps it in the record
    lab("question", "stop", qid, "--reason", "pause for the full tile")
    assert "owner_stopped" in lab("exp", "approve", e2, "--reason", "try anyway", code=1)
    lab("question", "resume", qid, "--reason", "back on")
    lab("exp", "approve", e2, "--reason", "taller strip")
    q = json.loads((p.questions / f"{qid}.json").read_text())
    assert [s["reason"] for s in q["stops"]] == ["pause for the full tile"] and q["stops"][0]["resumed_at"]

    before = lab("question", "status", qid)
    out = lab("question", "rebuild", qid)
    assert f"{e1}: unchanged" in out and f"{e2}: unchanged (not printed yet)" in out
    assert lab("question", "status", qid) == before


def _n(x):
    return f"{x:.1f}".rstrip("0").rstrip(".")


def test_build_that_dies_before_its_last_write_leaves_the_experiment_unchanged(lab, monkeypatch):
    import os
    p = lab.paths
    qid = re.search(r"Created (Q-\d+)", lab("question", "new", "Atomicity", "--budget", "3h,100g"))[1]
    eid = re.search(r"Planned (E-\d+)", lab("exp", "plan", qid, "Slow vs fast", "--z", "63:69", *PLAN))[1]
    original = (p.experiments / f"{eid}.json").read_bytes()
    real = os.replace

    def dies_on_the_experiment(src, dst):
        if str(dst).endswith(f"{eid}.json"):
            raise OSError("injected: power cut")
        return real(src, dst)
    monkeypatch.setattr("lab.records.store.os.replace", dies_on_the_experiment)
    with pytest.raises(OSError):
        main(["exp", "build", eid])
    monkeypatch.setattr("lab.records.store.os.replace", real)

    assert (p.experiments / f"{eid}.json").read_bytes() == original
    assert not list(p.experiments.glob("*.tmp*"))
    assert f"orphaned print file: prints/hex-tile_{eid}_BLD-{eid[2:]}-01.3mf" in lab("question", "rebuild", qid)


def test_a_change_waits_for_the_lock_then_names_the_holder_and_changes_nothing(lab, monkeypatch):
    p = lab.paths
    qid = re.search(r"Created (Q-\d+)", lab("question", "new", "Locks", "--budget", "3h,100g"))[1]
    eid = re.search(r"Planned (E-\d+)", lab("exp", "plan", qid, "Slow vs fast", "--z", "63:69", *PLAN))[1]
    original = (p.experiments / f"{eid}.json").read_bytes()
    holder = subprocess.Popen([sys.executable, "-c", textwrap.dedent(f"""
        import sys, time
        from lab.records.store import record_lock
        with record_lock({str(p.locks)!r}, {eid!r}, "lab exp build {eid}"):
            print("held", flush=True)
            time.sleep(30)
        """)], stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "held"
        from functools import partial
        from lab.records import store
        monkeypatch.setattr("lab.loop.commands.record_lock", partial(store.record_lock, timeout_s=1.0))
        out = lab("exp", "abandon", eid, "--reason", "while locked", code=1)
        assert f"lab exp build {eid}" in out and f"PID {holder.pid}" in out
    finally:
        holder.kill()
        holder.wait()
    assert (p.experiments / f"{eid}.json").read_bytes() == original
