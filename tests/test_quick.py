"""A19 P1: the quick slicing engine. Unit tests use fakes; the real-Studio tests skip when Studio is absent."""
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pytest
import trimesh

from lab.adapters import bambu
from lab.analysis.gcode import layer_paths
from lab.jobs import LabToolError, failed_job, run_tool
from lab.quick import engine, validate
from lab.quick.settings import QuickSettings, settings_patch

FIX = Path(__file__).parent / "fixtures"
GOOD = (FIX / "quick" / "good_start_block.gcode").read_text()
LOOSE = (FIX / "quick" / "loose_start_block.gcode").read_text()
BASE = FIX / "hex" / "studio_saved_v58_strip.gcode.3mf"
TINY = (FIX / "gcode" / "tiny.gcode").read_text()


def _gcode(start: str, ids: str = "GFL99;GFL99") -> str:
    return start.rstrip() + f"\n; MACHINE_START_GCODE_END\n; filament_ids = {ids}\n"


def _stl(tmp_path, extents=(20, 20, 6)) -> Path:
    p = tmp_path / "part.stl"
    trimesh.creation.box(extents=extents).export(p)
    return p


def _studio():
    try:
        bambu.bambu_binary()
    except FileNotFoundError:
        return False
    return BASE.exists()


needs_studio = pytest.mark.skipif(not _studio(), reason="Bambu Studio not installed")


# ---- the Q5 start check --------------------------------------------------------------------------------------------

def test_known_good_start_passes():
    assert validate.check_start(_gcode(GOOD)).ok


def test_loose_start_fails_with_reasons():
    r = validate.check_start(_gcode(LOOSE))
    assert not r.ok and "M620" in r.missing_commands and any("lacks" in x for x in r.reasons)


def test_empty_filament_ids_fails():
    r = validate.check_start(_gcode(GOOD, ids='""'))
    assert not r.ok and r.filament_ids_empty


def test_no_start_block_fails():
    r = validate.check_start("G28\nG1 X1\n")
    assert not r.ok and "no machine start block" in r.reasons[0]


def test_indented_m620_counts():
    assert "M620" in validate.commands("  M620 S0A H-1 B\n M620.10 A0\n")


def test_base_without_start_code_is_refused(tmp_path):
    p = validate.project_problems({"machine_start_gcode": "", "filament_ids": ["GFL99"]})
    assert p and validate.project_problems(None) and not validate.project_problems(
        {"machine_start_gcode": "M620", "filament_ids": ["GFL99"]})


# ---- settings ----------------------------------------------------------------------------------------------------

def test_default_settings_patch_nothing():
    assert settings_patch(QuickSettings()) == {}


@pytest.mark.parametrize("s", [QuickSettings(layer_height=0.01), QuickSettings(layer_height=0.6),
                               QuickSettings(walls=0), QuickSettings(walls=20), QuickSettings(infill_pct=100),
                               QuickSettings(infill_pct=150), QuickSettings(infill_pattern="nonsense"),
                               QuickSettings(brim="outer", brim_width=100), QuickSettings(brim_width=3),
                               QuickSettings(top_layers=0)])
def test_out_of_range_settings_refused(s):
    with pytest.raises(ValueError):
        settings_patch(s)


def test_top_layers_also_zero_the_shell_thickness():
    assert settings_patch(QuickSettings(top_layers=3)) == {"top_shell_layers": "3", "top_shell_thickness": "0"}


# ---- source and base ---------------------------------------------------------------------------------------------

def test_modified_source_is_refused(tmp_path):
    with pytest.raises(engine.QuickSliceError, match="changed since"):
        engine.quick_slice(_stl(tmp_path), BASE, tmp_path / "o", expect_source_sha256="0" * 64)


def test_missing_source_and_bad_files(tmp_path):
    with pytest.raises(engine.QuickSliceError, match="doesn't exist"):
        engine.quick_slice(tmp_path / "nope.stl", BASE, tmp_path / "o")
    bad = tmp_path / "bad.stl"
    bad.write_text("not a model")
    with pytest.raises(engine.QuickSliceError):
        engine.quick_slice(bad, BASE, tmp_path / "o")


def test_oversize_and_flat_models_refused(tmp_path):
    with pytest.raises(engine.QuickSliceError, match="plate takes"):
        engine.load_source(_stl(tmp_path, (300, 20, 6)))
    with pytest.raises(engine.QuickSliceError, match="flat"):
        engine.load_source(_stl(tmp_path, (20, 20, 0.001)))
    assert engine.load_source(_stl(tmp_path, (300, 20, 6)), scale=0.5).bounds[1][0] == pytest.approx(75)


def test_rotation_changes_the_footprint(tmp_path):
    m = engine.load_source(_stl(tmp_path, (20, 10, 6)), rotate=(0, 0, 90))
    assert (m.bounds[1] - m.bounds[0])[0] == pytest.approx(10)


def test_base_that_is_not_a_project_is_refused(tmp_path):
    z = tmp_path / "x.3mf"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("a.txt", "x")
    with pytest.raises(engine.QuickSliceError, match="project_settings"):
        engine.quick_slice(_stl(tmp_path), z, tmp_path / "o")


# ---- slicer failure modes, with a fake Studio ----------------------------------------------------------------

def _fake(monkeypatch, behaviour):
    """Replace the slicer: behaviour(out_path) writes what the fake Studio produced; returns exit ok."""
    def fake(path_3mf, out_dir, plate, jobs_dir, timeout=1800):
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / (path_3mf.name.removesuffix(".3mf") + ".gcode.3mf")
        behaviour(out, path_3mf)
        job = run_tool(["true"], inputs=[path_3mf], outputs=[], jobs_dir=jobs_dir, tool="bambu-studio",
                       tool_version=bambu.EXPECTED_VERSION)
        return out, job
    monkeypatch.setattr(bambu, "slice_with_job", fake)


def _sliced_zip(out: Path, project: Path, gcode: str, info: bool = True, plate: bool = True):
    with zipfile.ZipFile(project) as p:
        settings = p.read("Metadata/project_settings.config")
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("Metadata/project_settings.config", settings)
        if plate:
            z.writestr("Metadata/plate_1.gcode", gcode)
        if info:
            z.writestr("Metadata/slice_info.config", '<c><metadata key="prediction" value="600"/>'
                                                       '<metadata key="weight" value="3.5"/></c>')


def _layered(start: str) -> str:
    return _gcode(start) + "; CHANGE_LAYER\n; Z_HEIGHT: 0.2\n; FEATURE: Outer wall\nG1 X10 Y10 E1\nG1 X20 Y10 E1\n"


def test_good_fake_slice_is_usable(tmp_path, monkeypatch):
    _fake(monkeypatch, lambda out, proj: _sliced_zip(out, proj, _layered(GOOD)))
    r = engine.quick_slice(_stl(tmp_path), BASE, tmp_path / "o")
    assert r.status == "sliced" and r.estimate == {"minutes": 10.0, "grams": 3.5} and r.layers["count"] == 1
    rec = json.loads((tmp_path / "o" / r.job_id / "quick_slice.json").read_text())
    assert rec["artifact"]["sha256"] and rec["transform"]["position_mm"] == [128.0, 128.0]


def test_loose_slice_needs_attention_even_with_exit_zero(tmp_path, monkeypatch):
    _fake(monkeypatch, lambda out, proj: _sliced_zip(out, proj, _layered(LOOSE)))
    r = engine.quick_slice(_stl(tmp_path), BASE, tmp_path / "o")
    assert r.status == "needs_attention" and any("lacks" in x for x in r.reasons)


def test_output_missing(tmp_path, monkeypatch):
    _fake(monkeypatch, lambda out, proj: None)
    r = engine.quick_slice(_stl(tmp_path), BASE, tmp_path / "o")
    assert r.status == "needs_attention" and "no output file" in r.reasons[0]


def test_corrupt_zip_and_wrong_output_type(tmp_path, monkeypatch):
    _fake(monkeypatch, lambda out, proj: out.write_bytes(b"not a zip"))
    assert "not a valid 3MF" in engine.quick_slice(_stl(tmp_path), BASE, tmp_path / "o").reasons[0]
    _fake(monkeypatch, lambda out, proj: _sliced_zip(out, proj, "", plate=False))
    r = engine.quick_slice(_stl(tmp_path), BASE, tmp_path / "o2")
    assert r.status == "needs_attention" and any("project, not a sliced file" in x for x in r.reasons)


def test_changed_machine_start_in_output_is_flagged(tmp_path, monkeypatch):
    def beh(out, proj):
        _sliced_zip(out, proj, _layered(GOOD))
        with zipfile.ZipFile(out, "a") as z:
            z.writestr("Metadata/project_settings.config", json.dumps({"machine_start_gcode": "G28", "filament_ids": ["x"]}))
    _fake(monkeypatch, beh)
    r = engine.quick_slice(_stl(tmp_path), BASE, tmp_path / "o")
    assert any("machine start code differs" in x for x in r.reasons)


def _raise(kind):
    def fake(path_3mf, out_dir, plate, jobs_dir, timeout=1800):
        msg = {"binary": "Bambu Studio not found at /x", "version": "Bambu Studio 1.0 is installed",
               "crash": "Bambu Studio couldn't slice p.3mf: segfault",
               "timeout": "Bambu Studio couldn't slice p.3mf: "}[kind]
        job = failed_job(jobs_dir=jobs_dir, tool="bambu-studio", message="TimeoutExpired: 5" if kind == "timeout" else msg,
                         inputs=[path_3mf])
        raise LabToolError(msg, job)
    return fake


@pytest.mark.parametrize("kind", ["binary", "version", "crash", "timeout"])
def test_slicer_failures_become_needs_attention(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(bambu, "slice_with_job", _raise(kind))
    r = engine.quick_slice(_stl(tmp_path), BASE, tmp_path / "o")
    assert r.status == "needs_attention" and r.reasons and not r.artifact
    if kind == "timeout":
        assert "didn't finish" in r.reasons[0]


def test_transform_and_settings_kept_in_the_project(tmp_path, monkeypatch):
    seen = {}
    def beh(out, proj):
        seen["meta"] = json.loads(zipfile.ZipFile(proj).read("Metadata/print_lab.json"))
        seen["settings"] = json.loads(zipfile.ZipFile(proj).read("Metadata/project_settings.config"))
        _sliced_zip(out, proj, _layered(GOOD))
    _fake(monkeypatch, beh)
    engine.quick_slice(_stl(tmp_path), BASE, tmp_path / "o", QuickSettings(walls=4), rotate=(0, 0, 90), scale=1.5)
    assert seen["meta"]["transform"]["rotate_deg"] == [0, 0, 90] and seen["meta"]["transform"]["scale"] == 1.5
    assert seen["meta"]["settings"] == {"walls": 4} and seen["settings"]["wall_loops"] == "4"


# ---- layer geometry --------------------------------------------------------------------------------------------

def test_layer_paths_split_extrusion_and_travel():
    layers = layer_paths(TINY)
    assert [l["z"] for l in layers] == [0.2, 0.4, 0.6]
    assert layers[0]["extrusion"] and layers[0]["extruded_mm"] > 0
    assert all(len(seg) == 4 for segs in layers[0]["extrusion"].values() for seg in segs)


def test_layer_paths_read_the_start_block_as_no_layers():
    assert layer_paths(_gcode(GOOD)) == []


# ---- real Studio ------------------------------------------------------------------------------------------------

@needs_studio
def test_real_studio_slice_is_valid(tmp_path):
    r = engine.quick_slice(_stl(tmp_path), BASE, tmp_path / "o")
    assert r.status == "sliced", r.reasons
    assert r.tool["version"] == bambu.EXPECTED_VERSION and r.layers["count"] > 20 and r.estimate["grams"] > 0


@needs_studio
@pytest.mark.parametrize("s", [QuickSettings(layer_height=0.12), QuickSettings(walls=5), QuickSettings(top_layers=7),
                               QuickSettings(bottom_layers=6), QuickSettings(infill_pct=40),
                               QuickSettings(infill_pattern="gyroid"), QuickSettings(supports=True),
                               QuickSettings(brim="outer", brim_width=8)])
def test_every_exposed_setting_changes_the_output(tmp_path, s):
    part = tmp_path / "step.stl"
    a = trimesh.creation.box(extents=(20, 20, 6)); a.apply_translation([0, 0, 3])
    b = trimesh.creation.box(extents=(40, 20, 4)); b.apply_translation([0, 0, 8])
    trimesh.util.concatenate([a, b]).export(part)
    base = engine.quick_slice(part, BASE, tmp_path / "base")
    got = engine.quick_slice(part, BASE, tmp_path / "got", s)
    assert base.status == got.status == "sliced", (base.reasons, got.reasons)
    assert got.artifact["gcode_sha256"] != base.artifact["gcode_sha256"]


@needs_studio
@pytest.mark.parametrize("pat", ["honeycomb", "cubic", "line"])
def test_other_infill_patterns_change_the_output(tmp_path, pat):
    part = _stl(tmp_path, (30, 30, 10))
    base = engine.quick_slice(part, BASE, tmp_path / "base", QuickSettings(infill_pattern="grid"))
    got = engine.quick_slice(part, BASE, tmp_path / "got", QuickSettings(infill_pattern=pat))
    assert got.status == "sliced" and got.artifact["gcode_sha256"] != base.artifact["gcode_sha256"]
