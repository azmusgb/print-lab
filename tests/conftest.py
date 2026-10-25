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
    from lab.loop import capabilities
    monkeypatch.setattr(capabilities, "CAP_DIR", tmp_path / "capabilities-under-test")


@pytest.fixture(autouse=True)
def _no_sync(monkeypatch):
    """Tests never push to the real Local AI; a test that wants a sync turns it on against its own fake server."""
    monkeypatch.setenv("LAB_SYNC", "off")
