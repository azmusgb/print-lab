"""Frozen print bytes, concurrent records, and default network isolation."""
import hashlib
import json
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from lab.loop.commands import add_photos
from lab.loop.guards import check_experiment, start
from lab.loop.send import send
from lab.loop.verify import verify_artifact
from lab.records.schema import load
from loop_fixtures import make_project, minimal_experiment, minimal_question, started
from test_guards import built, proj  # noqa: F401


def test_build_freezes_sliced_bytes(proj):
    eid = built(proj)
    b = load(proj.experiments / f"{eid}.json", "experiment")["builds"][-1]
    f = proj.root / b["sliced"]
    assert b["sliced_sha256"] == hashlib.sha256(f.read_bytes()).hexdigest()
    assert verify_artifact(proj, eid, f)["ok"]
    f.write_bytes(b"overwritten after build")
    assert not verify_artifact(proj, eid, f)["ok"]
    assert check_experiment(proj, eid).status == "rebuild"
    with pytest.raises(ValueError, match="artifact_integrity"):
        send(proj, eid, opener=lambda *args: pytest.fail("must not open changed bytes"))
    with pytest.raises(ValueError, match="artifact_integrity"):
        start(proj, eid)


def test_missing_digest_requires_a_fresh_build(proj):
    from lab.loop.builders import build_experiment
    from test_builders import fake_slicer
    eid = built(proj)
    p = proj.experiments / f"{eid}.json"
    e = json.loads(p.read_text())
    e["builds"][-1].pop("sliced_sha256")
    p.write_text(json.dumps(e))
    assert check_experiment(proj, eid).status == "rebuild"
    assert not verify_artifact(proj, eid, proj.root / e["builds"][-1]["sliced"])["ok"]
    with pytest.raises(ValueError, match="--replace"):
        build_experiment(proj, eid, replace=False, slicer=fake_slicer)
    fresh = build_experiment(proj, eid, replace=True, slicer=fake_slicer)
    assert fresh["sliced_sha256"] and fresh["id"] != e["builds"][-1]["id"]


def test_simultaneous_starts_create_one_run(tmp_path, monkeypatch):
    from lab.loop import guards
    paths = make_project(tmp_path, minimal_question(), [minimal_experiment()])
    from contextlib import contextmanager
    from lab.records.store import record_lock
    boundary = threading.Barrier(2)
    checks = []
    def checked(*args):
        checks.append(True)
        return SimpleNamespace(status="ready", build={"id": "BLD-009-01"})
    @contextmanager
    def simultaneous_lock(*args, **kwargs):
        # Both calls reach the lock boundary before either may write. On the old code both already passed
        # the printing check; on the corrected code neither has checked yet.
        boundary.wait(timeout=5)
        with record_lock(*args, **kwargs):
            yield
    p = paths.experiments / "E-009.json"
    e = json.loads(p.read_text()); e["status"] = "built"; p.write_text(json.dumps(e))
    monkeypatch.setattr(guards, "check_experiment", checked)
    monkeypatch.setattr(guards, "record_lock", simultaneous_lock)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(start, paths, "E-009") for _ in range(2)]
        for future in futures:
            future.result(timeout=10)
    final = load(p, "experiment")
    assert len(final["print_runs"]) == 1
    assert len(checks) == 1


def photo_project(tmp_path):
    return make_project(tmp_path, minimal_question(), [started(minimal_experiment())])


def fake_converter(monkeypatch, barrier=None):
    from lab.loop import commands
    def convert(args, **kwargs):
        Path(args[-1]).write_bytes(Path(args[-3]).read_bytes())
        if barrier:
            barrier.wait(timeout=5)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr("subprocess.run", convert)
    monkeypatch.setattr(commands, "_captured_at", lambda src: None)


def test_simultaneous_photo_imports_preserve_both_images(tmp_path, monkeypatch):
    paths = photo_project(tmp_path)
    fake_converter(monkeypatch, threading.Barrier(2))
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    a.write_bytes(b"first photograph"); b.write_bytes(b"second photograph")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda p: add_photos(paths, "PR-009-01", [p]), [a, b]))
    photos = load(paths.experiments / "E-009.json", "experiment")["print_runs"][0]["photos"]
    assert len({p["path"] for p in photos}) == 2
    assert {(paths.root / p["path"]).read_bytes() for p in photos} == {a.read_bytes(), b.read_bytes()}
    for p in photos:
        assert p["sha256"] == hashlib.sha256((paths.root / p["path"]).read_bytes()).hexdigest()


def test_photo_save_failure_rolls_back_only_new_files(tmp_path, monkeypatch):
    from lab.loop import commands
    paths = photo_project(tmp_path); fake_converter(monkeypatch)
    a = tmp_path / "a.png"; a.write_bytes(b"photo")
    first = add_photos(paths, "PR-009-01", [a])[0]
    def fail(*args):
        raise OSError("disk full")
    monkeypatch.setattr(commands, "save_experiment", fail)
    with pytest.raises(OSError, match="disk full"):
        add_photos(paths, "PR-009-01", [a])
    assert list(paths.photos.glob("*.jpg")) == [paths.root / first["path"]]


def test_network_blocks_private_public_and_dns_before_connecting():
    from lab import bambuddy
    assert bambuddy.base_url() == "off"
    for host in ("10.0.0.80", "1.1.1.1", "external.example"):
        with pytest.raises(PermissionError, match="non-loopback"):
            socket.getaddrinfo(host, 80)
        with socket.socket() as sock:
            with pytest.raises(PermissionError, match="non-loopback"):
                sock.connect((host, 80))
    assert socket.getaddrinfo("127.0.0.1", 80)
