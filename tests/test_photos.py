import base64
import json

import pytest

from lab.loop.commands import add_photos
from lab.records.schema import load
from loop_fixtures import make_project, minimal_experiment, minimal_question, started

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


@pytest.fixture
def proj(tmp_path):
    return make_project(tmp_path, minimal_question(), [started(minimal_experiment())])


def test_photo_added_with_relative_path_and_hash(proj, tmp_path):
    src = tmp_path / "IMG_0770.PNG"
    src.write_bytes(PNG)
    out = add_photos(proj, "PR-009-01", [src])
    assert out[0]["path"] == "photos/PR-009-01-1.jpg" and len(out[0]["sha256"]) == 64
    assert (proj.root / out[0]["path"]).exists()
    e = load(proj.experiments / "E-009.json", "experiment")
    assert e["print_runs"][0]["photos"][0]["source"] == "IMG_0770.PNG"
    assert not out[0]["path"].startswith("/")


def test_bad_file_adds_nothing(proj, tmp_path):
    good, bad = tmp_path / "a.png", tmp_path / "b.HEIC"
    good.write_bytes(PNG)
    bad.write_text("not an image")
    with pytest.raises(ValueError, match="b.HEIC"):
        add_photos(proj, "PR-009-01", [good, bad])
    assert not list((proj.root / "photos").glob("*")) if (proj.root / "photos").exists() else True
    assert load(proj.experiments / "E-009.json", "experiment")["print_runs"][0]["photos"] == []


def test_unknown_run_lists_valid_runs(proj, tmp_path):
    with pytest.raises(ValueError, match="PR-009-01"):
        add_photos(proj, "PR-777", [tmp_path / "x.png"])
