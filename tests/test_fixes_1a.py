"""Fixes after Stage 1A: the deferred review minors and the Studio-saved 3MF reader bug, each pinned by a test."""
import json
import stat
import time
import zipfile

import pytest
import trimesh

from lab.adapters import bambu
from lab.adapters.threemf import load_object, write_print_3mf
from lab.checks import run_checks
from lab.jobs import LabToolError


def test_reads_a_3mf_saved_by_bambu_studio(hex_dir):
    # Studio keeps each mesh in 3D/Objects/object_N.model, referenced with p:path from the main model.
    m = load_object(hex_dir / "studio_saved_v58_strip.gcode.3mf", "v58")
    assert m.is_watertight
    assert m.extents[2] == pytest.approx(12.0, abs=0.01)
    assert m.extents[1] == pytest.approx(152.4, abs=0.1)


def two_boxes(second=(10, 10, 20)):
    return trimesh.util.concatenate([trimesh.creation.box((10, 10, 20)).apply_translation([0, 0, 10]),
                                     trimesh.creation.box(second).apply_translation([20, 0, second[2] / 2])])


def test_two_unlike_pieces_are_warned():
    # A one-piece part that came out as a stray second body: the pieces differ, so it isn't a pair.
    fs = [f for f in run_checks(two_boxes((4, 4, 6)), nozzle=0.4) if f.rule == "mesh-validity"]
    assert len(fs) == 1 and fs[0].severity == "warning" and "2 separate pieces" in fs[0].why


def test_two_matching_pieces_are_a_pair():
    assert not [f for f in run_checks(two_boxes(), nozzle=0.4) if f.rule == "mesh-validity"]


def test_the_hex_pair_is_a_pair(hex_dir):
    m = trimesh.load(hex_dir / "hex_pair_v53_6in.stl", force="mesh")
    assert not [f for f in run_checks(m, nozzle=0.4) if f.rule == "mesh-validity"]


def test_inspect_json_is_strict_for_an_open_mesh(tmp_path):
    from test_cli import lab
    box = trimesh.creation.box((20, 20, 20))
    open_box = trimesh.Trimesh(box.vertices, box.faces[:-2])
    p = tmp_path / "open_box.stl"
    open_box.export(p)
    r = lab("inspect", p, "--json", "--nozzle", "0.4")

    def no_nan(c):
        raise AssertionError(f"not strict JSON: {c}")
    data = json.loads(r.stdout, parse_constant=no_nan)
    assert data["facts"]["volume_cm3"] is None


def test_nozzle_in_file_name_any_case():
    fs = run_checks(trimesh.creation.box((10, 10, 10)), nozzle=0.6, file_name="tile_X2D_0.4NOZZLE.3mf")
    mm = [f for f in fs if f.rule == "nozzle-mismatch"]
    assert mm and mm[0].data["file name"] == "0.4"


def test_hung_bambu_help_times_out(tmp_path, monkeypatch):
    p = tmp_path / "BambuStudio"
    p.write_text("#!/bin/sh\nsleep 30\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("LAB_BAMBU", str(p))
    monkeypatch.setattr(bambu, "HELP_TIMEOUT_S", 1)
    t = time.monotonic()
    with pytest.raises(FileNotFoundError, match="didn't answer"):
        bambu.bambu_binary()
    assert time.monotonic() - t < 10


def test_missing_bambu_says_where_to_get_it(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_BAMBU", str(tmp_path / "nope"))
    with pytest.raises(FileNotFoundError, match=r"github.com/bambulab/BambuStudio/releases/tag/v02.09.01.70"):
        bambu.bambu_binary()


def test_3mf_without_bambu_metadata_is_a_clear_error(tmp_path):
    p = tmp_path / "plain.3mf"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("3D/3dmodel.model", "<model/>")
    with pytest.raises(ValueError, match="isn't a Bambu Studio project"):
        load_object(p, "")
    assert bambu.read_settings(p) is None


def test_object_not_on_the_build_plate_is_a_clear_error(tmp_path, hex_dir):
    src = hex_dir / "hexagon_v57_X2D_0.4nozzle.3mf"
    p = tmp_path / "no_build.3mf"
    with zipfile.ZipFile(src) as zi, zipfile.ZipFile(p, "w") as zo:
        for n in zi.namelist():
            data = zi.read(n)
            if n == "3D/3dmodel.model":
                import re
                data = re.sub(rb"<build>.*</build>", b"<build></build>", data, flags=re.S)
            zo.writestr(n, data)
    with pytest.raises(ValueError, match="not on the build plate"):
        load_object(p, "v57_6in")


def test_object_names_are_escaped_in_print_files(tmp_path, hex_dir):
    out = tmp_path / "odd.3mf"
    name = 'a&b<"c>'
    write_print_3mf(hex_dir / "hexagon_v57_X2D_0.4nozzle.3mf", [(name, trimesh.creation.box((5, 5, 5)), (0, 0))],
                    out, {})
    assert bambu.list_objects(out)[0].name == name
    assert load_object(out, "a&b").extents[0] == pytest.approx(5)


def test_slice_job_is_linked_to_its_print_run(tmp_path):
    from lab.experiments import link_slice_job
    pdir = tmp_path / "proj"
    (pdir / "experiments").mkdir(parents=True)
    (pdir / "experiments" / "E-009.json").write_text(json.dumps(
        {"id": "E-009", "print_runs": [{"id": "PR-020"}, {"id": "PR-021"}]}))
    p = tmp_path / "x.3mf"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("Metadata/print_lab.json", json.dumps({"experiment_id": "E-009", "print_run_id": "PR-021"}))
    assert link_slice_job(pdir, p, "job-1") == "E-009"
    e = json.loads((pdir / "experiments" / "E-009.json").read_text())
    assert e["print_runs"][1]["slice_job"] == "job-1" and "slice_job" not in e["print_runs"][0]


def test_slice_job_link_skips_files_from_outside_the_lab(tmp_path):
    from lab.experiments import link_slice_job
    p = tmp_path / "y.3mf"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("x", "")
    assert link_slice_job(tmp_path, p, "job-1") is None


def test_slice_job_link_ignores_an_experiment_id_that_leaves_the_project(tmp_path):
    # A 3MF from elsewhere could name any file; only E-<number> inside the project's experiments is ever written.
    from lab.experiments import link_slice_job
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({"id": "x", "print_runs": [{"id": "PR-001"}]}))
    pdir = tmp_path / "proj"
    (pdir / "experiments").mkdir(parents=True)
    p = tmp_path / "evil.3mf"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("Metadata/print_lab.json", json.dumps({"experiment_id": "../../outside", "print_run_id": "PR-001"}))
    assert link_slice_job(pdir, p, "job-1") is None
    assert "slice_job" not in outside.read_text()
