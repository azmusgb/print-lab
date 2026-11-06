from pathlib import Path

import pytest

HEX = Path(__file__).parent / "fixtures" / "hex"


@pytest.fixture
def hex_dir() -> Path:
    return HEX


def need(path: Path) -> Path:
    """A fixture file the owner still has to download skips the test instead of failing it."""
    if not path.exists():
        pytest.skip(f"{path.name} not downloaded yet")
    return path


@pytest.fixture(autouse=True)
def _isolated_capabilities(tmp_path, monkeypatch):
    """Tests never see (or write) the lab's recorded capability results."""
    from lab import source
    from lab.loop import capabilities
    monkeypatch.setattr(capabilities, "CAP_DIR", tmp_path / "capabilities-under-test")
    monkeypatch.setattr(source, "CAP_DIR", tmp_path / "capabilities-under-test")  # its own copy of the path


@pytest.fixture(autouse=True)
def _no_sync(monkeypatch):
    """Tests never push to the real Local AI; a test that wants a sync turns it on against its own fake server."""
    monkeypatch.setenv("LAB_SYNC", "off")


# ---- The real lab is off limits --------------------------------------------------------------------------------
# A test once rewrote projects/hex-tile/cases/CASE-001.json. Three layers keep that from happening again:
# 1. every test gets its own empty LAB_HOME, so a CLI call without a project root lands in a temporary lab (child
#    processes inherit it);
# 2. writing a record anywhere inside the checkout is refused before it happens;
# 3. the checkout's files are compared before and after every test, which catches any other kind of write.
import os
import subprocess
import sys

from lab.cli import ROOT as LAB_ROOT

_SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"}
_SKIP_FILES = {".pull-state.json", ".pull.lock", ".DS_Store"}


def _inside_real_lab(path) -> bool:
    return Path(path).resolve().is_relative_to(LAB_ROOT.resolve())


def _snapshot() -> dict:
    """Every file and folder in the checkout. Inode and ctime are included because a rewrite can keep the size and
    put the mtime back, but replacing a file changes its inode and any change moves its ctime."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(LAB_ROOT):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        filenames = [f for f in filenames if f not in _SKIP_FILES]
        for name in dirnames + filenames:
            p = os.path.join(dirpath, name)
            try:
                st = os.lstat(p)
            except FileNotFoundError:
                continue
            out[p] = (st.st_size, st.st_mtime_ns, st.st_ctime_ns, st.st_ino) if name in filenames else ("dir",)
    return out


_REAL_HOME = os.path.expanduser("~")
_REFUSED_PROGRAMS = {"launchctl", "osascript"}


@pytest.fixture(autouse=True)
def _temporary_lab(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("LAB_HOME", str(tmp_path_factory.mktemp("lab-home")))


@pytest.fixture(autouse=True)
def _nothing_outside_the_checkout(tmp_path_factory, monkeypatch):
    """Tests don't reach the owner's home folder, the real Local AI, launchd or the notification centre."""
    from lab import sync
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("PYTEST_REAL_HOME", _REAL_HOME)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("LAB_LOCALAI_URL", "http://127.0.0.1:9")  # the discard port: nothing answers
    monkeypatch.setenv("LAB_LOCALAI_KEY_FILE", str(home / "no-such.key"))
    monkeypatch.setenv("LAB_HUB_URL", "https://127.0.0.1:9")  # same: the hub can't be reached from a test
    monkeypatch.setenv("LAB_HUB_KEY_FILE", str(home / "no-such-hub.key"))
    monkeypatch.setattr(sync, "HOME", home / ".claude" / "localai-chat")
    real_run = subprocess.run

    def run(args, *a, **k):
        argv = args if isinstance(args, (list, tuple)) else [args]
        if argv and Path(str(argv[0])).name in _REFUSED_PROGRAMS:
            raise PermissionError(f"tests don't run {Path(str(argv[0])).name}; inject a fake runner instead")
        return real_run(args, *a, **k)
    monkeypatch.setattr(subprocess, "run", run)


@pytest.fixture
def real_project_copy():
    """A copy of the real hex-tile project inside this test's temporary lab: tests that need the real records read
    the copy, and everything they write stays there."""
    import shutil
    src = LAB_ROOT / "projects" / "hex-tile"
    dst = Path(os.environ["LAB_HOME"]) / "projects" / "hex-tile"
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".locks", "photos", "jobs", "production", "designs"))
    return dst


def _refuse(path) -> None:
    if _inside_real_lab(path):
        raise PermissionError(f"A test tried to write {path}, inside the real lab ({LAB_ROOT}). Give the test its "
                              "own project under tmp_path.")


@pytest.fixture(autouse=True)
def _refuse_real_lab_writes(monkeypatch):
    """Refuse before writing: records (atomic_write_json, and _write_temp under create_record) and record locks,
    wherever a module imported them from."""
    from lab.records import store
    originals = {"atomic_write_json": store.atomic_write_json, "_write_temp": store._write_temp,
                 "record_lock": store.record_lock, "create_record": store.create_record}

    def atomic_write_json(path, obj, *a, **k):
        _refuse(path)
        return originals["atomic_write_json"](path, obj, *a, **k)

    def _write_temp(folder, obj, *a, **k):
        _refuse(folder)
        return originals["_write_temp"](folder, obj, *a, **k)

    def record_lock(lock_dir, *a, **k):
        _refuse(lock_dir)
        return originals["record_lock"](lock_dir, *a, **k)

    def create_record(lock_dir, folder, *a, **k):  # it makes its folder before writing anything
        _refuse(folder)
        _refuse(lock_dir)
        return originals["create_record"](lock_dir, folder, *a, **k)

    guarded = {"atomic_write_json": atomic_write_json, "_write_temp": _write_temp, "record_lock": record_lock,
               "create_record": create_record}
    for name, mod in list(sys.modules.items()):
        if name == "lab" or name.startswith("lab."):
            for attr, orig in originals.items():
                for k, v in list(vars(mod).items()):
                    if v is orig:  # catches aliased imports too
                        monkeypatch.setattr(mod, k, guarded[attr])


@pytest.fixture(autouse=True)
def _real_lab_unchanged():
    before = _snapshot()
    yield
    after = _snapshot()
    changed = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))
    if changed:
        pytest.fail("This test changed files in the real lab: " + ", ".join(changed[:10]), pytrace=False)


def pytest_addoption(parser):
    parser.addoption("--live-network", action="store_true", default=False,
                     help="Explicitly allow non-loopback network connections in tests")


@pytest.fixture(autouse=True)
def _network_is_local_by_default(request, monkeypatch):
    """Mocked services and loopback servers work; household/public services require explicit opt-in."""
    import ipaddress
    import socket
    if request.config.getoption("--live-network"):
        return
    monkeypatch.setenv("LAB_BAMBUDDY_URL", "off")
    real_connect, real_connect_ex = socket.socket.connect, socket.socket.connect_ex
    real_getaddrinfo, real_sendto = socket.getaddrinfo, socket.socket.sendto

    def check(host):
        if host in (None, "", "localhost", b"localhost"):
            return
        try:
            if ipaddress.ip_address(host.decode() if isinstance(host, bytes) else host).is_loopback:
                return
        except ValueError:
            pass
        raise PermissionError("Tests block non-loopback networking; use a mocked service or explicitly opt in "
                              "with --live-network")

    def connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            check(address[0])
        return real_connect(sock, address)

    def connect_ex(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            check(address[0])
        return real_connect_ex(sock, address)

    def getaddrinfo(host, *args, **kwargs):
        check(host)
        return real_getaddrinfo(host, *args, **kwargs)

    def sendto(sock, data, *args):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            check(args[-1][0])
        return real_sendto(sock, data, *args)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket.socket, "sendto", sendto)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
