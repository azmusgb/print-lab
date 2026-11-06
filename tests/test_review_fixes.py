"""Findings from the final review, each pinned by a test."""
import json
import os
import shutil
import stat

import numpy as np
import pytest
import trimesh

from lab.adapters import bambu, openscad
from lab.geometry.coupons import height_strip
from lab.history.inventory import describe, inventory
from lab.history.revisions import revisions
from lab.jobs import LabToolError


def three_boxes():
    boxes = [trimesh.creation.box((10, 10, 20)).apply_translation([dx, 0, 10]) for dx in (0, 20, 40)]
    return trimesh.util.concatenate(boxes)


def test_coupon_refuses_multi_body():
    with pytest.raises(ValueError, match="separate pieces"):
        height_strip(three_boxes(), 2, 8)


def fake_tool(tmp_path, name, output):
    p = tmp_path / name
    p.write_text(f"#!/bin/sh\necho '{output}'\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return p


def test_wrong_bambu_version_refused(tmp_path, monkeypatch, hex_dir):
    monkeypatch.setenv("LAB_BAMBU", str(fake_tool(tmp_path, "BambuStudio", "BambuStudio-02.09.00.10:")))
    with pytest.raises(LabToolError, match="02.09.00.10.*02.09.01.70"):
        bambu.slice_3mf(hex_dir / "hexagon_v57_X2D_0.4nozzle.3mf", tmp_path / "out", 1, tmp_path / "jobs")
    assert list((tmp_path / "jobs").glob("*.json"))


def test_old_openscad_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_OPENSCAD", str(fake_tool(tmp_path, "openscad", "OpenSCAD version 2021.01")))
    scad = tmp_path / "c.scad"
    scad.write_text("cube(1);")
    with pytest.raises(LabToolError, match="2021.01"):
        openscad.render(scad, tmp_path / "c.stl", {}, tmp_path / "jobs")
    assert list((tmp_path / "jobs").glob("*.json"))


def test_missing_bambu_writes_job(tmp_path, monkeypatch, hex_dir):
    monkeypatch.setenv("LAB_BAMBU", "/nonexistent/BambuStudio")
    with pytest.raises(LabToolError, match="02.09.01.70"):
        bambu.slice_3mf(hex_dir / "hexagon_v57_X2D_0.4nozzle.3mf", tmp_path / "out", 1, tmp_path / "jobs")
    job = json.loads(next((tmp_path / "jobs").glob("*.json")).read_text())
    assert job["ok"] is False and "not found" in job["stderr"]


def test_bare_hexagon_needs_x2d_name(tmp_path):
    (tmp_path / "Hexagon v3 coaster.stl").write_text("x")
    (tmp_path / "hexagon_v56_X2D_0.6nozzle.3mf").write_text("x")
    assert describe(tmp_path / "Hexagon v3 coaster.stl").lineage is None
    assert describe(tmp_path / "hexagon_v56_X2D_0.6nozzle.3mf").lineage == "hex-tile"


def test_en_dash_names(tmp_path):
    for n in ("hex_tile_v55–final.stl", "Hex Tile – v55.stl"):
        (tmp_path / n).write_text("x")
        a = describe(tmp_path / n)
        assert a.version == 55 and a.lineage == "hex-tile", n


def test_duplicate_of_unrelated_file_keeps_mesh(tmp_path, hex_dir):
    src = hex_dir / "hex_pair_v53_6in.stl"
    shutil.copy(src, tmp_path / "download.stl")
    os.utime(tmp_path / "download.stl", (1, 1))  # older, so the inventory sees it first
    shutil.copy(src, tmp_path / "hex_pair_v53_6in.stl")
    mine = [a for a in inventory(tmp_path) if a.lineage == "hex-tile"]
    revs = {r.version: r for r in revisions(mine, "hex-tile")}
    assert "6in" in revs[53].mesh and "error" not in revs[53].mesh["6in"]


def test_mesh_error_has_no_absolute_path(tmp_path):
    (tmp_path / "hex_pair_v99_6in.stl").write_bytes(b"solid broken\nfacet nonsense\n")
    revs = revisions([a for a in inventory(tmp_path) if a.lineage == "hex-tile"], "hex-tile")
    err = json.dumps(revs[0].mesh)
    assert str(tmp_path) not in err
