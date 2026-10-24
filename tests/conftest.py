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
