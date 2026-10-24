import shutil

import pytest

from lab.history.inventory import inventory
from lab.history.revisions import revisions


@pytest.fixture
def folder(tmp_path, hex_dir):
    for f in hex_dir.iterdir():
        shutil.copy(f, tmp_path / f.name)
    shutil.copy(hex_dir / "hex_pair_v53_6in.stl", tmp_path / "hex_pair_v53_6in.stl 2.stl")
    shutil.copy(hex_dir / "hex_tile_v31_6in.stl", tmp_path / "parametric_faceted_hex_wall_tile_mount_v31.stl")
    return tmp_path


def by_name(arts, name):
    return next(a for a in arts if a.path.endswith(name))


def test_duplicates_collapsed(folder):
    arts = inventory(folder)
    dup = by_name(arts, "hex_pair_v53_6in.stl 2.stl")
    assert dup.duplicate_of and dup.duplicate_of.endswith("hex_pair_v53_6in.stl")


def test_lineage_separates_mount(folder):
    arts = inventory(folder)
    assert by_name(arts, "parametric_faceted_hex_wall_tile_mount_v31.stl").lineage != "hex-tile"
    assert by_name(arts, "hex_tile_v31_6in.stl").lineage == "hex-tile"


def test_version_and_size_parsed(folder):
    a = by_name(inventory(folder), "hex_pair_v53_6in.stl")
    assert (a.version, a.size_in, a.kind) == (53, 6, "stl")


def test_nozzle_from_name(folder):
    assert by_name(inventory(folder), "hexagon_v56_X2D_0.6nozzle.3mf").nozzle == "0.6"


def test_unicode_names_read(folder):
    a = by_name(inventory(folder), "Hex Tile v55 0.20mm @BBL X2D.json")
    assert a.kind == "json" and a.version == 55 and a.lineage == "hex-tile" and len(a.sha256) == 64


def test_scad_params_normalised(folder):
    revs = {r.version: r for r in revisions(inventory(folder), "hex-tile")}
    assert revs[57].scad_params["rib_w"] == 0.45 and revs[57].scad_params["closed_back"] is True


def test_revision_v56_settings_nozzle(folder):
    revs = {r.version: r for r in revisions(inventory(folder), "hex-tile")}
    assert revs[56].nozzle_profile == "0.4"


def test_revision_mesh_facts(folder):
    revs = {r.version: r for r in revisions(inventory(folder), "hex-tile")}
    six = revs[53].mesh["6in"]
    assert six["watertight"] and any(60 <= z <= 72 for z, _ in six["outline_jumps"])
