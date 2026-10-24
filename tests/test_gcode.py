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


@pytest.mark.slow
def test_real_slice_v57_3in(tmp_path, hex_dir):
    from lab.adapters import bambu
    sliced = bambu.slice_3mf(hex_dir / "hexagon_v57_X2D_0.4nozzle.3mf", tmp_path, 1, tmp_path / "jobs")
    layers = read_layers(bambu.extract_gcode(sliced, 1))
    assert len(layers) > 300 and all(l.est_time_s > 0 for l in layers)
    assert any(l.outer_wall_speeds_mm_s for l in layers)
