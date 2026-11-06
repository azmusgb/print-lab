"""The gate and the gallery: candidates are built, checked against the constraints and lab inspect, written, sliced
(a fake slicer here; Bambu Studio never runs in tests) and shown; a candidate that breaks a block constraint is
dropped with its reason and leaves no files."""
import json
from types import SimpleNamespace

import pytest

from lab.adapters import bambu
from lab.analysis.gcode import feature_bands
from lab.design import gallery, gate
from lab.design.families import faceted_hex as fh
from lab.records.project import ProjectPaths

BASE = "RIFT_6IN_marked_pair.3mf"
GCODE = "".join(f"; CHANGE_LAYER\n; Z_HEIGHT: {z / 5:.1f}\n; FEATURE: Outer wall\nG1 X1 E1\n"
                + ("; FEATURE: Sparse infill\nG1 X2 E1\n" if z in (3, 4, 5, 700, 701) else "")
                for z in range(1, 716))


@pytest.fixture
def fake_slicer(monkeypatch):
    def slice_with_job(plate, out_dir, n, jobs):
        out = out_dir / plate.name.replace(".3mf", ".gcode.3mf")
        out.write_bytes(b"")
        return out, SimpleNamespace(id="job-fake")
    monkeypatch.setattr(bambu, "slice_with_job", slice_with_job)
    monkeypatch.setattr(bambu, "slice_estimate", lambda p: (157.9, 77.2))
    monkeypatch.setattr(bambu, "extract_gcode", lambda p, n: GCODE)


def test_feature_bands_finds_runs_of_layers():
    assert feature_bands(GCODE, "Sparse infill") == [(0.4, 1.0, 3), (139.8, 140.2, 2)]
    assert feature_bands(GCODE, "Bridge") == []
    assert feature_bands("", "Sparse infill") == []


def test_a_kept_candidate_is_written_and_sliced(real_project_copy, fake_slicer):
    paths = ProjectPaths(real_project_copy)
    rec = gate.evaluate(paths, fh, {}, 0, ("sources/" + BASE, real_project_copy / "sources" / BASE))
    assert rec["dropped"] == []
    assert rec["validity"]["shells"] == 2 and rec["validity"]["volume_mm3"] == pytest.approx(64323.4, abs=1)
    assert any(w.startswith("top-wall-all-shells") for w in rec["warnings"])
    assert rec["slice"] == {"job": "job-fake", "minutes": 157.9, "grams": 77.2,
                            "sparse_infill": [{"from_mm": 0.4, "to_mm": 1.0, "layers": 3},
                                              {"from_mm": 139.8, "to_mm": 140.2, "layers": 2}]}
    out = real_project_copy / "designs" / "faceted_hex" / rec["id"]
    for f in ("model.step", "model.stl", "params.json", "render.svg", "plate.3mf", "gate.json"):
        assert (out / f).is_file(), f
    assert json.loads((out / "params.json").read_text())["seed"] == 0


def test_a_candidate_breaking_a_block_constraint_is_dropped_without_files(real_project_copy):
    paths = ProjectPaths(real_project_copy)
    rec = gate.evaluate(paths, fh, {"roof_wall": 6}, 0, ("sources/" + BASE, real_project_copy / "sources" / BASE),
                        do_slice=False)
    assert any(d.startswith("no-infill-behind-face") for d in rec["dropped"])
    assert not (real_project_copy / "designs" / "faceted_hex" / rec["id"]).exists()


def test_make_refuses_an_unregistered_base_and_bad_params_before_building(real_project_copy):
    paths = ProjectPaths(real_project_copy)
    with pytest.raises(ValueError, match="isn't a registered source"):
        gate.make(paths, fh, {}, [1], "nope.3mf", do_slice=False)
    with pytest.raises(ValueError, match="outside"):
        gate.make(paths, fh, {"skin_axial": 0.1}, [1], BASE, do_slice=False)


def test_make_records_the_run_and_the_gallery_shows_it(real_project_copy, fake_slicer):
    paths = ProjectPaths(real_project_copy)
    lines = []
    run = gate.make(paths, fh, {}, [0, 1], BASE, progress=lines.append)
    assert [c["seed"] for c in run["candidates"]] == [0, 1] and run["finished"] and len(lines) == 2
    html = gallery.render(paths, run["path"])
    assert "<title>hex-tile designs" in html and ">2<" in html and "of 2 kept" in html
    assert html.count("Every kept candidate: top-wall-all-shells") == 1  # shared warnings once, not per card
    assert html.count('class="cand"') == 2 and "lab variant add --mesh" in html
    assert "Dropped</h2>" not in html


def test_the_gallery_lists_dropped_candidates(real_project_copy, fake_slicer):
    paths = ProjectPaths(real_project_copy)
    run = gate.make(paths, fh, {"roof_wall": 6}, [0], BASE)
    html = gallery.render(paths, run["path"])
    assert "of 1 kept" in html and "Dropped</h2>" in html and "no-infill-behind-face" in html
    assert "No candidate passed the gate" in html
