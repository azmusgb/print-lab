import json
import zipfile

import pytest
import trimesh

from lab.adapters import bambu, openscad, threemf


def test_read_settings_v56(hex_dir):
    s = bambu.read_settings(hex_dir / "hexagon_v56_X2D_0.6nozzle.3mf")
    assert s["nozzle_diameter"] == ["0.4", "0.4"]
    assert s["outer_wall_line_width"] == "0.42"


def test_list_objects_v57(hex_dir):
    names = {o.name for o in bambu.list_objects(hex_dir / "hexagon_v57_X2D_0.4nozzle.3mf")}
    assert {"hexagon_wall_tile_pair_v57_3in.stl", "hexagon_wall_tile_pair_v57_6in.stl",
            "hexagon_wall_tile_pair_v57_10in.stl"} <= names


def test_list_objects_plates_v57(hex_dir):
    plates = {o.name: o.plate for o in bambu.list_objects(hex_dir / "hexagon_v57_X2D_0.4nozzle.3mf")}
    assert plates["hexagon_wall_tile_pair_v57_3in.stl"] == 1 and plates["hexagon_wall_tile_pair_v57_10in.stl"] == 3


def test_load_object_ambiguous(hex_dir):
    with pytest.raises(ValueError) as e:
        threemf.load_object(hex_dir / "hexagon_v57_X2D_0.4nozzle.3mf", "hex")
    assert "hexagon_wall_tile_pair_v57_3in.stl" in str(e.value)


def test_load_object_6in_watertight(hex_dir):
    m = threemf.load_object(hex_dir / "hexagon_v57_X2D_0.4nozzle.3mf", "6in")
    assert m.is_watertight
    assert sorted(round(x) for x in m.extents) == [22, 132, 152]
    assert abs(m.bounds[0][2]) < 1e-6


def test_load_object_keeps_bed_rotation(hex_dir):
    m = threemf.load_object(hex_dir / "hexagon_v57_X2D_0.4nozzle.3mf", "10in")
    footprint = sorted(m.extents[:2])
    assert footprint[0] > 150  # the 10" pair sits at 45° on the plate, so both footprint sides are long


def test_write_print_3mf_roundtrip(tmp_path, hex_dir):
    base = hex_dir / "hexagon_v57_X2D_0.4nozzle.3mf"
    out = tmp_path / "hex-tile_E001_PR001.3mf"
    parts = [("a", trimesh.creation.box((10, 10, 10)), (100.0, 128.0)), ("b", trimesh.creation.box((5, 5, 5)), (150.0, 128.0))]
    digest = threemf.write_print_3mf(base, parts, out, {"experiment_id": "E-001"})
    assert len(digest) == 64
    z = zipfile.ZipFile(out)
    assert json.loads(z.read("Metadata/print_lab.json")) == {"experiment_id": "E-001"}
    assert z.read("Metadata/project_settings.config") == zipfile.ZipFile(base).read("Metadata/project_settings.config")
    objs = bambu.list_objects(out)
    assert [o.name for o in objs] == ["a", "b"] and {o.plate for o in objs} == {1}
    m = threemf.load_object(out, "a")
    assert sorted(round(x) for x in m.extents) == [10, 10, 10]


def test_write_print_3mf_tags_model_settings(tmp_path, hex_dir):
    base = hex_dir / "hexagon_v57_X2D_0.4nozzle.3mf"
    out = tmp_path / "tagged.3mf"
    parts = [("a", trimesh.creation.box((10, 10, 10)), (100.0, 128.0))]
    threemf.write_print_3mf(base, parts, out, {
        "experiment_id": "E-020",
        "build_id": "BLD-020-01",
        "print_run_id": "PR-020-01"
    })
    tags = threemf.read_3mf_tags(out)
    assert tags["experiment_id"] == "E-020"
    assert tags["build_id"] == "BLD-020-01"
    assert tags["print_run_id"] == "PR-020-01"

    with zipfile.ZipFile(out) as z:
        ms = z.read("Metadata/model_settings.config").decode()
    assert "<!-- print_lab_experiment: E-020 -->" in ms
    assert "<!-- print_lab_build: BLD-020-01 -->" in ms
    assert "<!-- print_lab_run: PR-020-01 -->" in ms
    assert '<metadata key="print_lab_experiment" value="E-020"/>' in ms
    assert '<metadata key="print_lab_build" value="BLD-020-01"/>' in ms
    assert '<metadata key="print_lab_run" value="PR-020-01"/>' in ms


def test_tag_3mf_injects_and_updates_tags(tmp_path, hex_dir):
    base = hex_dir / "hexagon_v57_X2D_0.4nozzle.3mf"
    test_file = tmp_path / "test_run.3mf"
    import shutil
    shutil.copyfile(base, test_file)

    threemf.tag_3mf(test_file, experiment_id="E-099", build_id="BLD-099-01", print_run_id="PR-099-02")
    tags = threemf.read_3mf_tags(test_file)
    assert tags["experiment_id"] == "E-099"
    assert tags["build_id"] == "BLD-099-01"
    assert tags["print_run_id"] == "PR-099-02"

    with zipfile.ZipFile(test_file) as z:
        ms = z.read("Metadata/model_settings.config").decode()
    assert "<!-- print_lab_experiment: E-099 -->" in ms
    assert '<metadata key="print_lab_experiment" value="E-099"/>' in ms


def _config_level_metadata(path):
    import xml.etree.ElementTree as ET
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("Metadata/model_settings.config"))
    return [m.get("key") for m in root.findall("metadata")]


def test_tags_stay_out_of_config_level(tmp_path, hex_dir):
    # Bambu Studio refuses a model_settings.config with <metadata> directly under <config>
    # ("Cannot find object for metadata, id -1"), so every build failed to slice (E-021, 26 Oct).
    base = hex_dir / "hexagon_v57_X2D_0.4nozzle.3mf"
    out = tmp_path / "tagged.3mf"
    parts = [("a", trimesh.creation.box((10, 10, 10)), (100.0, 128.0))]
    threemf.write_print_3mf(base, parts, out, {"experiment_id": "E-021", "build_id": "BLD-021-01"})
    assert _config_level_metadata(out) == []
    threemf.tag_3mf(out, print_run_id="PR-021-01")
    assert _config_level_metadata(out) == []
    assert threemf.read_3mf_tags(out) == {"experiment_id": "E-021", "build_id": "BLD-021-01",
                                          "print_run_id": "PR-021-01"}


def test_missing_openscad_message(monkeypatch):
    monkeypatch.setenv("LAB_OPENSCAD", "/nonexistent/openscad")
    with pytest.raises(FileNotFoundError) as e:
        openscad.openscad_binary()
    assert "brew install --cask openscad@snapshot" in str(e.value)


def test_missing_bambu_message(monkeypatch):
    monkeypatch.setenv("LAB_BAMBU", "/nonexistent/BambuStudio")
    with pytest.raises(FileNotFoundError) as e:
        bambu.bambu_binary()
    assert "02.09.01.70" in str(e.value)


def test_bambu_binary_windows_fallback(monkeypatch, tmp_path):
    fake_exe = tmp_path / "bambu-studio.exe"
    fake_exe.touch()
    monkeypatch.setenv("LAB_BAMBU", str(fake_exe))
    monkeypatch.setattr(bambu.sys, "platform", "win32")
    monkeypatch.setattr(bambu.subprocess, "run", lambda *args, **kwargs: type("Proc", (), {"stdout": "", "stderr": ""})())
    monkeypatch.setattr(bambu, "_read_windows_version", lambda path: "02.09.01.70")
    p, v = bambu.bambu_binary()
    assert p == fake_exe
    assert v == "02.09.01.70"


@pytest.mark.slow
def test_render_cube(tmp_path):
    scad = tmp_path / "cube.scad"
    scad.write_text("cube(size);")
    job = openscad.render(scad, tmp_path / "cube.stl", {"size": 10}, tmp_path / "jobs")
    assert job.ok
    assert sorted(round(x) for x in trimesh.load(tmp_path / "cube.stl").extents) == [10, 10, 10]


@pytest.mark.slow
def test_slice_v57_3in(tmp_path, hex_dir):
    sliced = bambu.slice_3mf(hex_dir / "hexagon_v57_X2D_0.4nozzle.3mf", tmp_path, 1, tmp_path / "jobs")
    assert sliced.exists()
    assert "; CHANGE_LAYER" in bambu.extract_gcode(sliced, 1)


@pytest.mark.slow
def test_slice_written_print_3mf(tmp_path, hex_dir):
    out = tmp_path / "print.3mf"
    threemf.write_print_3mf(hex_dir / "hexagon_v57_X2D_0.4nozzle.3mf",
                            [("box", trimesh.creation.box((20, 20, 10)), (128.0, 128.0))], out, {})
    sliced = bambu.slice_3mf(out, tmp_path, 1, tmp_path / "jobs")
    assert "; CHANGE_LAYER" in bambu.extract_gcode(sliced, 1)


@pytest.mark.slow
def test_slice_relative_path(tmp_path, hex_dir, monkeypatch):
    monkeypatch.chdir(hex_dir.parent.parent.parent)
    rel = hex_dir.relative_to(hex_dir.parent.parent.parent) / "hexagon_v57_X2D_0.4nozzle.3mf"
    sliced = bambu.slice_3mf(rel, tmp_path / "out", 1, tmp_path / "jobs")
    assert sliced.exists()
