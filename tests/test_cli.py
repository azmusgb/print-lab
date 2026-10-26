import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent


def lab(*args, env_home=None):
    import os
    env = dict(os.environ)
    if env_home:
        env["LAB_HOME"] = str(env_home)
    return subprocess.run(["uv", "run", "--frozen", "lab", *map(str, args)], capture_output=True, text=True, cwd=ROOT, env=env)


def test_inspect_text(hex_dir):
    r = lab("inspect", hex_dir / "hex_pair_v53_6in.stl")
    assert r.returncode in (0, 2), r.stderr
    assert "Front facets" in r.stdout and "89.75" in r.stdout


def test_inspect_json(hex_dir):
    r = lab("inspect", hex_dir / "hex_pair_v53_6in.stl", "--json")
    data = json.loads(r.stdout)
    assert data["facts"]["watertight"] is True and data["switches"]


def test_inspect_ambiguous_object(hex_dir):
    r = lab("inspect", hex_dir / "hexagon_v57_X2D_0.4nozzle.3mf", "--object", "hex")
    assert r.returncode == 1 and "hexagon_wall_tile_pair_v57_6in.stl" in r.stderr


def test_inspect_3mf_nozzle_mismatch_exit_2(hex_dir):
    r = lab("inspect", hex_dir / "hexagon_v56_X2D_0.6nozzle.3mf", "--object", "6in")
    assert r.returncode == 2 and "nozzle-mismatch" in r.stdout


def test_orient_table(hex_dir):
    r = lab("orient", hex_dir / "hex_pair_v53_6in.stl", "--angles", "0,15")
    assert r.returncode == 0 and "15" in r.stdout and "score" in r.stdout.lower()


def test_coupon_writes_stl(tmp_path, hex_dir):
    out = tmp_path / "strip.stl"
    r = lab("coupon", hex_dir / "hex_pair_v53_6in.stl", "--kind", "height_strip", "--z", "60:100", "--out", out)
    assert r.returncode == 0, r.stderr and out.exists()


def test_plan_blocked_exit_2(tmp_path, hex_dir):
    exp = {"id": "E-009", "project": "hex-tile", "question": "q", "hypothesis": "h", "prediction": "p",
           "why_this_test": "w", "test_kind": "height_strip", "factor": {"name": "rib_w", "values": [0.45, 2.5]}}
    p = tmp_path / "E-009.json"
    p.write_text(json.dumps(exp))
    after = tmp_path / "hex_wall_tile_v58.scad"
    after.write_text((hex_dir / "hex_wall_tile_v57.scad").read_text()
                     .replace("rib_w         = 0.45;", "rib_w         = 2.5;")
                     .replace("rib_kiss      = 0.15;", "rib_kiss      = 0.10;"))
    r = lab("plan", p, "--before", hex_dir / "hex_wall_tile_v57.scad", "--after", after)
    assert r.returncode == 2 and "stacked-changes" in r.stdout and "rib_kiss" in r.stdout


def test_plan_unlike_files_refused(tmp_path, hex_dir):
    p = tmp_path / "E-010.json"
    p.write_text(json.dumps({"id": "E-010", "project": "hex-tile", "question": "q", "hypothesis": "h",
                             "prediction": "p", "why_this_test": "w", "test_kind": "height_strip",
                             "factor": {"name": "rib_w", "values": [1, 2]}}))
    r = lab("plan", p, "--before", hex_dir / "hex_wall_tile_v57.scad", "--after", hex_dir / "hexagon_v58_X2D_0.6nozzle.3mf")
    assert r.returncode == 1 and "same kind" in r.stderr


def test_history_audit_runs(tmp_path, hex_dir):
    folder = tmp_path / "old"
    shutil.copytree(hex_dir, folder)
    assert lab("history", "ingest", folder, env_home=tmp_path).returncode == 0
    r = lab("history", "audit", env_home=tmp_path)
    assert r.returncode == 0 and "## Evidence" in r.stdout


def test_ingest_keeps_only_the_project_lineage_and_relative_paths(tmp_path, hex_dir):
    folder = tmp_path / "Downloads"
    shutil.copytree(hex_dir, folder)
    (folder / "2023_TaxReturn.pdf").write_text("private")
    assert lab("history", "ingest", folder, env_home=tmp_path).returncode == 0
    hist = tmp_path / "projects" / "hex-tile" / "history"
    text = (hist / "inventory.json").read_text() + (hist / "revisions.json").read_text()
    assert "TaxReturn" not in text and str(tmp_path) not in text
    assert all(a["lineage"] == "hex-tile" for a in json.loads((hist / "inventory.json").read_text()))
