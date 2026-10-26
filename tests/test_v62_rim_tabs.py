from __future__ import annotations

import importlib.util
import math
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "projects/hex-tile/sources/scad/make_v62_rim_tabs.py"
SOURCE = ROOT / "projects/hex-tile/sources/hexagon_v60b125_X2D_0.6nozzle.3mf"

spec = importlib.util.spec_from_file_location("make_v62_rim_tabs", SCRIPT)
assert spec and spec.loader
v62 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v62)


def test_default_layout_keeps_v40_pitch_without_v41_event_burst():
    centers = v62._rim_tab_centers(0.6, 12.0, 0.2)
    assert len(centers) == 42
    assert {side for *_rest, side, _slot in centers} == set(range(6))
    assert all(sum(1 for c in centers if c[3] == side) == 7 for side in range(6))

    # Check the actual generated center-to-center spacing, including the varying
    # top/bottom insets—not just the idealized outer-hex R / n value.
    for side in range(6):
        pts = [(c[0], c[1]) for c in centers if c[3] == side]
        for a, b in zip(pts, pts[1:]):
            assert math.dist(a, b) <= 12.0

    events = v62._event_counts(centers, 0.6, 0.2)
    assert max(events.values()) <= 2

    # The horizontal top/bottom rows must no longer share one common Z.
    top_z = {round(c[1], 3) for c in centers if c[3] == 1}
    bottom_z = {round(c[1], 3) for c in centers if c[3] == 4}
    assert len(top_z) == 7
    assert len(bottom_z) == 7


def test_build_v62_from_real_v60b125_project(tmp_path: Path):
    out = tmp_path / "hexagon_v62r_X2D_0.6nozzle.3mf"
    stats = v62.build_v62(SOURCE, out)

    assert out.exists()
    assert stats["tabs"] == 42
    assert stats["tabs_per_side"] == 7
    assert stats["gap_mm"] == 0.4
    assert stats["tab_mm"] == 0.6
    assert stats["pitch_max_mm"] <= 12.0
    assert stats["max_tab_events_per_layer"] <= 2
    assert stats["watertight"] is True
    assert stats["volume_mm3"] > 0

    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None
        assert "3D/3dmodel.model" in z.namelist()
        xml = z.read("3D/3dmodel.model").decode()
        for oid in v62.OBJECT_IDS:
            assert v62._block(xml, oid)

        if "Metadata/model_settings.config" in z.namelist():
            settings = z.read("Metadata/model_settings.config").decode()
            assert "v62r" in settings
