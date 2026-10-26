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
import sys

from lab.cli import ROOT as LAB_ROOT

_SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"}


def _inside_real_lab(path) -> bool:
    return Path(path).resolve().is_relative_to(LAB_ROOT.resolve())


def _snapshot() -> dict:
    out = {}
    for dirpath, dirnames, filenames in os.walk(LAB_ROOT):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for f in filenames:
            p = os.path.join(dirpath, f)
            try:
                st = os.stat(p)
            except FileNotFoundError:
                continue
            out[p] = (st.st_size, st.st_mtime_ns)
    return out


@pytest.fixture(autouse=True)
def _temporary_lab(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("LAB_HOME", str(tmp_path_factory.mktemp("lab-home")))


@pytest.fixture
def real_project_copy():
    """A copy of the real hex-tile project inside this test's temporary lab: tests that need the real records read
    the copy, and everything they write stays there."""
    import shutil
    src = LAB_ROOT / "projects" / "hex-tile"
    dst = Path(os.environ["LAB_HOME"]) / "projects" / "hex-tile"
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".locks", "photos", "jobs"))
    return dst


@pytest.fixture(autouse=True)
def _refuse_real_lab_writes(monkeypatch):
    from lab.records import store
    original = store.atomic_write_json

    def guarded(path, obj, *args, **kwargs):
        if _inside_real_lab(path):
            raise PermissionError(f"A test tried to write {path}, inside the real lab ({LAB_ROOT}). Give the test "
                                  "its own project under tmp_path.")
        return original(path, obj, *args, **kwargs)

    for name, mod in list(sys.modules.items()):
        if (name == "lab" or name.startswith("lab.")) and getattr(mod, "atomic_write_json", None) is original:
            monkeypatch.setattr(mod, "atomic_write_json", guarded)


@pytest.fixture(autouse=True)
def _real_lab_unchanged():
    before = _snapshot()
    yield
    after = _snapshot()
    changed = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))
    if changed:
        pytest.fail("This test changed files in the real lab: " + ", ".join(changed[:10]), pytrace=False)
