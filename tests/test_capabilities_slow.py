import pytest

from lab.loop import capabilities

pytestmark = pytest.mark.slow


def test_cap_height_range_against_real_slice(tmp_path, monkeypatch):
    monkeypatch.setattr(capabilities, "CAP_DIR", tmp_path)
    r = capabilities.run_capability("CAP-BAMBU-HEIGHT-RANGE-inner_wall_speed", tmp_path / "work")
    assert r["passed"], r["evidence"]


def test_cap_tab_isolation_against_real_slice(tmp_path, monkeypatch):
    monkeypatch.setattr(capabilities, "CAP_DIR", tmp_path)
    r = capabilities.run_capability("CAP-TAB-ISOLATION", tmp_path / "work")
    assert r["passed"], r["evidence"]
