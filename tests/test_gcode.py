from pathlib import Path

import pytest

from lab.analysis.gcode import events_near, read_layers

TINY = (Path(__file__).parent / "fixtures" / "gcode" / "tiny.gcode").read_text()


def test_layers_counted():
    assert [l.z for l in read_layers(TINY)] == [0.2, 0.4, 0.6]


def test_speeds():
    layers = read_layers(TINY)
    assert layers[0].outer_wall_speeds_mm_s == [80.0] and layers[1].outer_wall_speeds_mm_s == [100.0]


def test_fan():
    layers = read_layers(TINY)
    assert layers[0].fan_pct == 100.0 and layers[2].fan_pct == pytest.approx(50.2, abs=0.1)


def test_seam_is_first_outer_wall_point():
    assert read_layers(TINY)[1].seam_xy == (20.0, 10.0)


def test_events_near():
    ev = events_near(read_layers(TINY), 0.3, window=0.15)  # layers 0.2 and 0.4
    assert ev["outer_wall_speed_change"] is True and ev["fan_change"] is False


def test_layer_time_positive():
    assert all(l.est_time_s > 0 for l in read_layers(TINY))


def test_diff_layers():
    from lab.analysis.gcode import LayerInfo, diff_layers, format_gcode_diff
    la = [
        LayerInfo(index=0, z=0.2, est_time_s=10.0, outer_wall_speeds_mm_s=[80.0], fan_pct=0.0),
        LayerInfo(index=1, z=0.4, est_time_s=10.0, outer_wall_speeds_mm_s=[100.0], fan_pct=50.0),
        LayerInfo(index=2, z=0.6, est_time_s=10.0, outer_wall_speeds_mm_s=[100.0], fan_pct=100.0),
    ]
    lb = [
        LayerInfo(index=0, z=0.2, est_time_s=10.0, outer_wall_speeds_mm_s=[80.0], fan_pct=0.0),
        LayerInfo(index=1, z=0.4, est_time_s=20.0, outer_wall_speeds_mm_s=[50.0], fan_pct=100.0),
        LayerInfo(index=2, z=0.6, est_time_s=20.0, outer_wall_speeds_mm_s=[50.0], fan_pct=100.0),
    ]

    res = diff_layers(la, lb)
    assert res["count_a"] == 3
    assert res["count_b"] == 3
    assert res["speed_diff_count"] == 2
    assert res["time_jump_count"] == 2
    assert res["fan_diff_count"] == 1
    assert res["time_delta"] == 20.0
    assert len(res["speed_intervals"]) == 1
    assert res["speed_intervals"][0] == (0.4, 0.6, -50.0)

    text = format_gcode_diff(res, name_a="plate_a", name_b="plate_b", show_layers=True)
    assert "G-code Plate Comparison:" in text
    assert "Delta: +0.3 min (+20 s)" in text
    assert "Outer Wall Speed (2 layers differ):" in text
    assert "Z 0.4–0.6 mm: delta -50 mm/s" in text
    assert "Layer Detail:" in text


def test_gcode_cli_diff(capsys):
    from lab.cli import main
    p1 = Path("projects/hex-tile/prints/sliced/hex-tile_E-007_BLD-007-01.gcode.3mf")
    p2 = Path("projects/hex-tile/prints/sliced/hex-tile_E-008_BLD-008-01.gcode.3mf")
    if not p1.exists() or not p2.exists():
        pytest.skip("hex-tile sliced prints not present")

    rc = main(["gcode", str(p1), "--diff", str(p2)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "G-code Plate Comparison:" in out
    assert "Outer Wall Speed:" in out


@pytest.mark.slow
def test_real_slice_v57_3in(tmp_path, hex_dir):
    from lab.adapters import bambu
    sliced = bambu.slice_3mf(hex_dir / "hexagon_v57_X2D_0.4nozzle.3mf", tmp_path, 1, tmp_path / "jobs")
    layers = read_layers(bambu.extract_gcode(sliced, 1))
    assert len(layers) > 300 and all(l.est_time_s > 0 for l in layers)
    assert any(l.outer_wall_speeds_mm_s for l in layers)
