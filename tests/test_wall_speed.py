import trimesh

from lab.checks import run_checks


def _dummy_mesh():
    return trimesh.creation.box([10, 10, 10])


def test_wall_speed_ratio_warning_when_over_2x():
    settings = {
        "inner_wall_speed": 250,
        "outer_wall_speed": 80,
    }
    findings = run_checks(_dummy_mesh(), nozzle=0.6, settings=settings)
    f = [x for x in findings if x.rule == "wall-speed-ratio"]
    assert len(f) == 1
    assert f[0].severity == "warning"
    assert "ratio 3.1x" in f[0].where
    assert "CASE-002" in f[0].why
    assert "144 mm/s" in f[0].fix


def test_wall_speed_ratio_clean_when_under_2x():
    settings = {
        "inner_wall_speed": 120,
        "outer_wall_speed": 80,
    }
    findings = run_checks(_dummy_mesh(), nozzle=0.6, settings=settings)
    assert not any(x.rule == "wall-speed-ratio" for x in findings)


def test_wall_speed_ignored_without_settings():
    findings = run_checks(_dummy_mesh(), nozzle=0.6, settings=None)
    assert not any(x.rule == "wall-speed-ratio" for x in findings)
