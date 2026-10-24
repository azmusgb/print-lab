import numpy as np
import trimesh

from lab.adapters.bambu import read_settings
from lab.adapters.threemf import load_object
from lab.checks import run_checks
from lab.geometry.mesh import load_mesh


def rules(findings, severity=None):
    return {f.rule for f in findings if severity is None or f.severity == severity}


def test_v57_joins_flagged(hex_dir):
    m = load_object(hex_dir / "hexagon_v57_X2D_0.4nozzle.3mf", "6in")
    fs = run_checks(m, nozzle=0.4)
    f = next(f for f in fs if f.rule == "feature-below-line-width")
    assert f.severity == "warning" and "0.42" in f.why


def test_v53_overhang_flip(hex_dir):
    fs = run_checks(load_mesh(hex_dir / "hex_pair_v53_6in.stl"), nozzle=0.4)
    f = next(f for f in fs if f.rule == "overhang-flip-on-A")
    assert f.severity == "warning" and f.data["switches"]


def test_v56_nozzle_mismatch(hex_dir):
    p = hex_dir / "hexagon_v56_X2D_0.6nozzle.3mf"
    fs = run_checks(load_object(p, "6in"), nozzle=0.6, settings=read_settings(p), file_name=p.name)
    assert "nozzle-mismatch" in rules(fs, "blocking")


def test_v57_04_no_nozzle_mismatch(hex_dir):
    p = hex_dir / "hexagon_v57_X2D_0.4nozzle.3mf"
    fs = run_checks(load_object(p, "6in"), nozzle=0.4, settings=read_settings(p), file_name=p.name)
    assert "nozzle-mismatch" not in rules(fs)


def ten_inch_box(angle):
    b = trimesh.creation.box((254, 31.5, 220))
    b.apply_transform(trimesh.transformations.rotation_matrix(np.radians(angle), [0, 0, 1]))
    b.apply_translation([0, 0, -b.bounds[0][2]])
    return b


def test_bed_fit_10in_straight_fails():
    assert "bed-fit" in rules(run_checks(ten_inch_box(0), nozzle=0.4), "blocking")


def test_bed_fit_10in_45deg_ok():
    assert "bed-fit" not in rules(run_checks(ten_inch_box(45), nozzle=0.4))


def test_non_watertight_reported_not_crashing():
    b = trimesh.creation.box((20, 4, 30))
    b.update_faces(np.arange(len(b.faces)) != 0)
    b.apply_translation([0, 0, -b.bounds[0][2]])
    fs = run_checks(b, nozzle=0.4)
    assert "mesh-validity" in rules(fs, "blocking")
