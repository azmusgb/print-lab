"""A19 P1: the quick slicing engine. Settings, the Q5 start-sequence check, output checks, layer paths; the real Studio
slice runs only where Bambu Studio is installed."""
import hashlib
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pytest
import trimesh

from lab.adapters import bambu
from lab.analysis.gcode import layer_paths
from lab.jobs import LabToolError
from lab.quick import engine, start_check
from lab.quick.settings import QuickSettingError, to_patch

FX = Path(__file__).parent / "fixtures" / "quick"
REF = start_check.load_reference()
BASE = Path(__file__).resolve().parents[1] / "projects/hex-tile/prints/hex-tile_E-022_BLD-022-01.3mf"


def wrapped(block: str, ids: str = "GFL99;GFL99") -> str:
    return f"{block}; MACHINE_START_GCODE_END\n; filament_ids = {ids}\n; machine_start_gcode = x\n"


# --- settings -------------------------------------------------------------------------------------------------------

def test_patch_uses_slicer_keys_and_strings():
    p = to_patch({"layer_height": 0.12, "wall_loops": 3, "enable_support": True, "sparse_infill_pattern": "gyroid"})
    assert p == {"layer_height": "0.12", "wall_loops": "3", "enable_support": "1", "sparse_infill_pattern": "gyroid"}


def test_top_layers_also_zero_the_thickness():
    assert to_patch({"top_shell_layers": 3}) == {"top_shell_layers": "3", "top_shell_thickness": "0"}


def test_brim_rules():
    assert to_patch({"brim_type": "outer_only"})["brim_width"] == "5"
    assert "brim_width" not in to_patch({"brim_type": "no_brim", "brim_width": 4})


@pytest.mark.parametrize("bad", [
    {"layer_height": 0.01}, {"layer_height": 0.6}, {"layer_height": float("nan")}, {"layer_height": "abc"},
    {"layer_height": True}, {"wall_loops": 0}, {"wall_loops": 2.5}, {"sparse_infill_density": 150},
    {"sparse_infill_density": 100}, {"sparse_infill_pattern": "nonsense"}, {"enable_support": "yes"},
    {"brim_type": "auto"}, {"brim_type": "outer_only", "brim_width": 100}, {"machine_start_gcode": "G28"}])
def test_bad_settings_are_refused(bad):
    with pytest.raises(QuickSettingError):
        to_patch(bad)


def test_edges_of_each_range_are_accepted():
    assert to_patch({"layer_height": 0.08})["layer_height"] == "0.08"
    assert to_patch({"layer_height": 0.28})["layer_height"] == "0.28"
    assert to_patch({"sparse_infill_density": 0})["sparse_infill_density"] == "0"


# --- Q5 start-sequence check ----------------------------------------------------------------------------------------

def test_loose_start_is_rejected():
    res = start_check.check_gcode(wrapped((FX / "loose_start_block.gcode").read_text(), ""), REF)
    assert not res.ok and res.block_lines == 12
    text = " ".join(res.reasons)
    assert "missing" in text and "known-good" in text and "no filament ids" in text


def test_good_start_block_has_no_block_reason():
    res = start_check.check_gcode(wrapped((FX / "good_start_block.gcode").read_text()), REF)
    assert res.block_lines >= 404 * 0.9
    assert not any("missing" in r or "lines against" in r for r in res.reasons)


def test_good_start_with_a_different_machine_start_is_rejected():
    res = start_check.check_gcode(wrapped((FX / "good_start_block.gcode").read_text()), REF)
    assert any("start G-code" in r for r in res.reasons)  # the header here is not the known-good one


def test_a_recorded_newer_machine_start_is_accepted_and_an_unknown_one_is_not():
    gcode = wrapped((FX / "good_start_block.gcode").read_text()).replace("machine_start_gcode = x", "machine_start_gcode = newer")
    ref = {**REF, "also_known_good": [{"machine_start_sha256": start_check.machine_start_sha256(gcode), "source": "test"}]}
    assert not any("start G-code" in r for r in start_check.check_gcode(gcode, ref).reasons)
    assert any("start G-code" in r for r in start_check.check_gcode(gcode, REF).reasons)
    assert len(start_check.accepted_machine_starts(REF)) == 2  # the hex-tile 2026/06/05 start and the 2026/10/20 one


def test_no_block_is_rejected():
    assert start_check.check_gcode("G28\n", REF).reasons == ["The G-code has no start block"]


def test_indented_commands_count_and_order_matters():
    block = "; EXECUTABLE_BLOCK_START\n   M620 S0A\n\tM621 S0A\n"
    seq = start_check.command_sequence(block)
    assert seq == ["M620", "M621"]
    assert start_check._is_subsequence(["M621", "M620"], seq) == ["M620"]  # out of order is a miss


def test_reference_is_the_known_good_start():
    assert len(REF["commands"]) > 100 and REF["block_lines"] == 404 and "M620" in REF["commands"]


# --- output checks and refusals -------------------------------------------------------------------------------------

def zip_of(tmp_path, entries: dict) -> Path:
    p = tmp_path / "o.gcode.3mf"
    with zipfile.ZipFile(p, "w") as z:
        for k, v in entries.items():
            z.writestr(k, v)
    return p


def test_corrupt_zip_is_refused(tmp_path):
    p = tmp_path / "o.gcode.3mf"
    p.write_bytes(b"not a zip")
    with pytest.raises(engine.QuickSliceError, match="valid 3MF"):
        engine.check_output(p)


def test_output_missing_the_plate_is_refused(tmp_path):
    with pytest.raises(engine.QuickSliceError, match="plate_1.gcode"):
        engine.check_output(zip_of(tmp_path, {"Metadata/slice_info.config": "x"}))


def test_wrong_model_type_and_empty_model(tmp_path):
    (tmp_path / "a.obj").write_text("v 0 0 0")
    with pytest.raises(engine.QuickSliceError, match="only STL"):
        engine.load_model(tmp_path / "a.obj")
    (tmp_path / "a.stl").write_bytes(b"junk")
    with pytest.raises(engine.QuickSliceError):
        engine.load_model(tmp_path / "a.stl")


def test_modified_source_is_refused_before_slicing(tmp_path):
    m = tmp_path / "m.stl"
    trimesh.creation.box(extents=(10, 10, 10)).export(m)
    with pytest.raises(engine.QuickSliceError, match="changed after"):
        engine.slice_quick(m, BASE, tmp_path / "out", expect_model_sha256="0" * 64)
    assert not (tmp_path / "out").exists()


def test_unknown_setting_stops_before_any_work(tmp_path):
    with pytest.raises(QuickSettingError):
        engine.slice_quick(tmp_path / "missing.stl", BASE, tmp_path / "out", settings={"nope": 1})


def test_missing_binary_and_wrong_version(tmp_path, monkeypatch):
    m = tmp_path / "m.stl"
    trimesh.creation.box(extents=(10, 10, 10)).export(m)
    monkeypatch.setenv("LAB_BAMBU", "/nonexistent/BambuStudio")
    with pytest.raises(LabToolError, match="not found"):
        engine.slice_quick(m, BASE, tmp_path / "out")
    monkeypatch.setattr(bambu, "bambu_binary", lambda: (Path("/bin/true"), "01.00.00.00"))
    with pytest.raises(LabToolError, match="checked against"):
        engine.slice_quick(m, BASE, tmp_path / "out")


def fake_slice(monkeypatch, tmp_path, gcode: str | None, ok_job=True, tool_version=bambu.EXPECTED_VERSION):
    """Replace Studio with a function that writes a given plate G-code, so the checks after it can be driven."""
    from lab.jobs import Job

    def fake(project, out_dir, plate, jobs_dir):
        out = Path(out_dir) / (Path(project).name.removesuffix(".3mf") + ".gcode.3mf")
        out.parent.mkdir(parents=True, exist_ok=True)
        if gcode is not None:
            with zipfile.ZipFile(out, "w") as z:
                z.writestr("Metadata/plate_1.gcode", gcode)
                z.writestr("Metadata/slice_info.config", '<x key="prediction" value="600"/><x key="weight" value="3.5"/>')
        return out, Job(id="job-1", tool="bambu-studio", tool_version=tool_version, command=[], input_sha256={},
                        exit_code=0, stdout="", stderr="", ok=ok_job)
    monkeypatch.setattr(bambu, "slice_with_job", fake)


@pytest.fixture
def box(tmp_path):
    m = tmp_path / "m.stl"
    trimesh.creation.box(extents=(10, 10, 10)).export(m)
    return m


@pytest.mark.skipif(not BASE.exists(), reason="stand-in base project not present")
def test_loose_slice_is_refused_and_leaves_no_file(tmp_path, monkeypatch, box):
    fake_slice(monkeypatch, tmp_path, wrapped((FX / "loose_start_block.gcode").read_text(), ""))
    with pytest.raises(engine.QuickSliceError, match="start sequence"):
        engine.slice_quick(box, BASE, tmp_path / "out", reference=REF)
    assert not list((tmp_path / "out" / "sliced").glob("*.gcode.3mf"))


@pytest.mark.skipif(not BASE.exists(), reason="stand-in base project not present")
def test_slice_that_exits_zero_but_has_no_output_is_refused(tmp_path, monkeypatch, box):
    fake_slice(monkeypatch, tmp_path, None)
    with pytest.raises(FileNotFoundError):
        engine.slice_quick(box, BASE, tmp_path / "out", reference=REF)


@pytest.mark.skipif(not BASE.exists(), reason="stand-in base project not present")
def test_project_keeps_the_transform_and_the_patch(tmp_path, monkeypatch, box):
    fake_slice(monkeypatch, tmp_path, "x")  # refused later; we only read the project it built
    t = np.eye(4); t[:3, :3] = trimesh.transformations.rotation_matrix(np.pi / 2, [0, 0, 1])[:3, :3]
    with pytest.raises(engine.QuickSliceError):
        engine.slice_quick(box, BASE, tmp_path / "out", settings={"wall_loops": 4}, transform=t, reference=REF)
    with zipfile.ZipFile(tmp_path / "out" / "quick.3mf") as z:
        loops = json.loads(z.read("Metadata/project_settings.config"))["wall_loops"]
        meta = json.loads(z.read("Metadata/print_lab.json"))
        model = z.read("3D/3dmodel.model").decode()
    assert set(loops if isinstance(loops, list) else [loops]) == {"4"}
    assert 'transform="1 0 0 0 1 0 0 0 1 128.00000 128.00000 0"' in model
    assert meta["model_sha256"] == hashlib.sha256(box.read_bytes()).hexdigest() and meta["settings"] == {"wall_loops": "4"}


# --- layer paths ----------------------------------------------------------------------------------------------------

TINY = (Path(__file__).parent / "fixtures" / "gcode" / "tiny.gcode").read_text()


def test_layer_paths_separate_extrusion_and_travel():
    layers = layer_paths(TINY)
    assert [l["z"] for l in layers] == [0.2, 0.4, 0.6]
    first = layers[0]
    assert first["extrusion"][0]["feature"] == "Outer wall"
    assert first["extrusion"][0]["points"] == [(10.0, 10.0), (60.0, 10.0), (60.0, 60.0)]
    assert first["extrusion"][1] == {"feature": "Inner wall", "points": [(12.0, 12.0), (58.0, 12.0)]}
    assert first["travel"] == [[(0.0, 0.0), (10.0, 10.0)], [(60.0, 60.0), (12.0, 12.0)]]


def test_layer_paths_empty_without_layers():
    assert layer_paths("G28\nG1 X5 Y5 E1\n") == []


# --- real Studio ----------------------------------------------------------------------------------------------------

def studio_present() -> bool:
    try:
        return bambu.bambu_binary()[1] == bambu.EXPECTED_VERSION
    except FileNotFoundError:
        return False


@pytest.mark.skipif(not (studio_present() and BASE.exists()), reason="Bambu Studio or the base project is absent")
@pytest.mark.slow
def test_real_slice_passes_and_a_setting_changes_it(tmp_path, box):
    a = engine.slice_quick(box, BASE, tmp_path / "a", name="a")
    b = engine.slice_quick(box, BASE, tmp_path / "b", name="b", settings={"layer_height": 0.12})
    assert a.studio_version == bambu.EXPECTED_VERSION and a.start_block_lines >= 364
    assert b.layers > a.layers and a.sliced_sha256 != b.sliced_sha256
