"""The Quick Print base is made from a recipe, not saved in Studio (lab.quick.make_base)."""
import io
import json
import zipfile
from pathlib import Path

import pytest

from lab.quick import make_base

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "presets" / "quick" / "standard.json"


def settings_of(data_or_path):
    with zipfile.ZipFile(data_or_path) as z:
        return json.loads(z.read("Metadata/project_settings.config"))


def test_the_committed_base_is_exactly_what_its_recipe_makes():
    data, _ = make_base.build(RECIPE)
    assert (ROOT / "presets" / "quick" / "standard.3mf").read_bytes() == data  # re-run make_base if this fails


def test_the_same_recipe_makes_the_same_bytes_every_time():
    assert make_base.build(RECIPE)[0] == make_base.build(RECIPE)[0]


def test_the_filament_is_in_every_slot_and_the_rest_is_the_known_good_builds():
    data, _ = make_base.build(RECIPE)
    got = settings_of(io.BytesIO(data))
    recipe = json.loads(RECIPE.read_text())
    profile = json.loads((ROOT / recipe["filament"]).read_text())
    source = settings_of(ROOT / recipe["from"])
    assert set(got["filament_settings_id"]) == {profile["filament_settings_id"][0]} and len(got["filament_settings_id"]) == 4
    assert set(got["filament_flow_ratio"]) == {profile["filament_flow_ratio"][0]}
    assert set(got["filament_max_volumetric_speed"]) == {profile["filament_max_volumetric_speed"][0]}
    for key in ("printer_settings_id", "print_settings_id", "layer_height", "wall_loops", "sparse_infill_density",
                "filament_ids", "machine_start_gcode"):
        assert got[key] == source[key], key  # the printer's initialization is the build's, untouched


def test_the_base_is_a_valid_3mf_the_slicer_reads_its_settings_from():
    names = set(zipfile.ZipFile(ROOT / "presets" / "quick" / "standard.3mf").namelist())
    assert {"[Content_Types].xml", "_rels/.rels", "Metadata/project_settings.config"} <= names


def test_a_source_that_is_not_the_x2d_standard_process_is_refused(tmp_path):
    recipe = json.loads(RECIPE.read_text())
    src = tmp_path / "other.3mf"
    s = settings_of(ROOT / recipe["from"])
    s["layer_height"] = "0.28"
    with zipfile.ZipFile(src, "w") as z:
        z.writestr("Metadata/project_settings.config", json.dumps(s))
    fil = tmp_path / "f.json"
    fil.write_text((ROOT / recipe["filament"]).read_text())
    r = tmp_path / "r.json"
    r.write_text(json.dumps({**recipe, "from": "other.3mf", "filament": "f.json"}))
    with pytest.raises(make_base.RecipeError, match="layer_height"):
        make_base.build(r, root=tmp_path)


@pytest.mark.parametrize("bad", ["", "{", '{"name": "x"}'])
def test_a_broken_recipe_is_refused_in_words(tmp_path, bad):
    r = tmp_path / "r.json"
    r.write_text(bad)
    with pytest.raises(make_base.RecipeError, match="r.json"):
        make_base.build(r, root=tmp_path)


def test_a_filament_key_the_project_lacks_is_listed_not_invented():
    out, missing = make_base.with_filament({"filament_flow_ratio": ["1", "1"]},
                                           {"filament_flow_ratio": ["0.9"], "brand_new_key": ["x"], "inherits": "y"})
    assert out == {"filament_flow_ratio": ["0.9", "0.9"]} and missing == ["brand_new_key"]
