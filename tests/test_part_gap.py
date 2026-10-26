"""Two parts closer than one printed line fuse (v58's tiles, 0.1 mm apart): the checks say so before printing."""
import trimesh

from lab.checks import run_checks


def _two(gap):
    a = trimesh.creation.box([10, 40, 20]).apply_translation([-5 - gap / 2, 0, 10])
    b = trimesh.creation.box([10, 40, 20]).apply_translation([5 + gap / 2, 0, 10])
    return trimesh.util.concatenate([a, b])


def test_parts_closer_than_a_line_are_reported_as_fusing():
    f = [x for x in run_checks(_two(0.1), nozzle=0.4) if x.rule == "parts-too-close"]
    assert len(f) == 1 and f[0].severity == "warning"
    assert "0.1 mm" in f[0].where and "fuse" in f[0].why and "0.5" in f[0].fix


def test_parts_a_line_or_more_apart_are_fine():
    assert not [x for x in run_checks(_two(0.6), nozzle=0.4) if x.rule == "parts-too-close"]


def test_parts_gap_under_1mm_on_06_nozzle_reported_as_fusing():
    # CASE-001 proven threshold: 0.75 mm fuses on 0.6 nozzle
    f = [x for x in run_checks(_two(0.75), nozzle=0.6) if x.rule == "parts-too-close"]
    assert len(f) == 1 and f[0].severity == "warning"
    assert "0.8 mm" in f[0].where or "0.7 mm" in f[0].where
    assert "CASE-001" in f[0].why
    assert "1.0 mm" in f[0].fix

    # 1.2 mm gap is clean
    assert not [x for x in run_checks(_two(1.2), nozzle=0.6) if x.rule == "parts-too-close"]
