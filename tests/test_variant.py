"""`lab variant add`: a Fusion export becomes a registered source 3MF that carries a base project's settings."""
import json
import shutil
import zipfile

import pytest
import trimesh

from lab.adapters.threemf import load_object
from lab.cli import main
from lab.jobs import sha256
from lab.records.project import ProjectPaths
from lab.variant import add_variant, change_line
from tests.conftest import need

BASE = "hexagon_v57_X2D_0.4nozzle.3mf"


@pytest.fixture
def project(tmp_path, hex_dir):
    paths = ProjectPaths(tmp_path / "projects" / "hex-tile")
    paths.sources.mkdir(parents=True)
    shutil.copy2(need(hex_dir / BASE), paths.sources / BASE)
    (paths.sources / "sources.json").write_text(json.dumps(
        [{"path": f"sources/{BASE}", "sha256": sha256(paths.sources / BASE), "source": "fixture"}]))
    return paths


@pytest.fixture
def flat_stl(tmp_path):
    """A flat 'tile': 60 wide (x), 40 tall (y, the top edge), 9 deep (z, face up)."""
    f = tmp_path / "tile.stl"
    trimesh.creation.box(extents=[60, 40, 9]).export(f)
    return f


def _params(tmp_path, name, **values):
    f = tmp_path / name
    f.write_text(json.dumps({"document": "Rift simplified v3", "version": 12, "parameters": [
        {"name": k, "expression": f"{v} mm", "value": v, "unit": "mm"} for k, v in values.items()]}))
    return f


def test_writes_an_upright_source_with_the_base_settings(project, flat_stl):
    e = add_variant(project, mesh=flat_stl, base=BASE, name="RIFT_test")
    out = project.root / "sources" / "RIFT_test.3mf"
    assert e["path"] == "sources/RIFT_test.3mf" and e["sha256"] == sha256(out)
    assert e["derived_from"] == f"sources/{BASE}" and e["source"] == "derived"
    m = load_object(out, "RIFT_test")
    assert [round(float(x), 3) for x in m.extents] == [60, 9, 40]  # standing: the top edge is up, the face is -Y
    with zipfile.ZipFile(out) as z, zipfile.ZipFile(project.sources / BASE) as b:
        assert z.read("Metadata/project_settings.config") == b.read("Metadata/project_settings.config")
    reg = json.loads((project.sources / "sources.json").read_text())
    assert reg[-1] == e and len(reg) == 2


def test_flat_keeps_the_model_axes(project, flat_stl):
    add_variant(project, mesh=flat_stl, base=f"sources/{BASE}", name="flat_one", flat=True)
    m = load_object(project.sources / "flat_one.3mf", "flat_one")
    assert [round(float(x), 3) for x in m.extents] == [60, 40, 9]


def test_never_overwrites_a_source(project, flat_stl):
    add_variant(project, mesh=flat_stl, base=BASE, name="once")
    before = sha256(project.sources / "once.3mf")
    with pytest.raises(ValueError, match="never overwritten"):
        add_variant(project, mesh=flat_stl, base=BASE, name="once")
    assert sha256(project.sources / "once.3mf") == before
    with pytest.raises(ValueError, match="never overwritten"):
        add_variant(project, mesh=flat_stl, base=BASE, name=BASE)


def test_refuses_an_unregistered_or_changed_base(project, flat_stl):
    with pytest.raises(ValueError, match="isn't a registered source"):
        add_variant(project, mesh=flat_stl, base="nope.3mf", name="x")
    with open(project.sources / BASE, "ab") as f:
        f.write(b"\0")
    with pytest.raises(ValueError, match="registered sha256"):
        add_variant(project, mesh=flat_stl, base=BASE, name="x")
    assert not (project.sources / "x.3mf").exists()


def test_refuses_an_open_mesh_and_a_bad_name(project, tmp_path):
    open_mesh = trimesh.creation.box(extents=[10, 10, 10])
    open_mesh.update_faces([True] * 11 + [False])
    f = tmp_path / "open.stl"
    open_mesh.export(f)
    with pytest.raises(ValueError, match="closed solid"):
        add_variant(project, mesh=f, base=BASE, name="x")
    with pytest.raises(ValueError, match="can't be a source name"):
        add_variant(project, mesh=f, base=BASE, name="../escape")
    assert sorted(p.name for p in project.sources.iterdir()) == [BASE, "sources.json"]


def test_a_failed_write_leaves_nothing(project, flat_stl, monkeypatch):
    import lab.variant as variant

    def boom(*a, **k):
        raise RuntimeError("disk full")
    monkeypatch.setattr(variant, "atomic_write_json", boom)
    with pytest.raises(RuntimeError):
        add_variant(project, mesh=flat_stl, base=BASE, name="x", params=_params(project.root, "p.json", a=1))
    assert sorted(p.name for p in project.sources.iterdir()) == [BASE, "sources.json"]


def test_params_are_kept_and_the_change_line_names_the_difference(project, flat_stl, tmp_path):
    first = add_variant(project, mesh=flat_stl, base=BASE, name="v1",
                        params=_params(tmp_path, "v1.json", edge_depth=9, skin_axial=2.4))
    assert first["params"] == "sources/v1.params.json"
    assert first["change"] == f"geometry from Fusion 'Rift simplified v3' v12; settings from sources/{BASE}"
    second = add_variant(project, mesh=flat_stl, base="v1.3mf", name="v2", note="deeper",
                         params=_params(tmp_path, "v2.json", edge_depth=7.5, skin_axial=2.4))
    assert second["change"].startswith("edge_depth 9 mm → 7.5 mm; geometry from Fusion")
    assert second["note"] == "deeper" and second["derived_from"] == "sources/v1.3mf"
    assert json.loads((project.sources / "v2.params.json").read_text())["parameters"][0]["value"] == 7.5


def test_change_line_without_params():
    assert change_line(None, None, "sources/b.3mf") == "geometry from an exported model; settings from sources/b.3mf"
    p = {"parameters": [{"name": "a", "expression": "1 mm", "value": 1, "unit": "mm"}]}
    assert change_line(p, p, "sources/b.3mf").startswith("parameters as the base's;")


def test_cli_registers_and_prints_the_next_command(project, flat_stl, monkeypatch, capsys):
    monkeypatch.setenv("LAB_HOME", str(project.root.parent.parent))
    rc = main(["variant", "add", "--mesh", str(flat_stl), "--base", BASE, "--name", "cli_one", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["source"]["path"] == "sources/cli_one.3mf"
    assert out["extents"] == [60, 9, 40]
    rc = main(["variant", "add", "--mesh", str(flat_stl), "--base", BASE, "--name", "cli_one"])
    assert rc == 1 and "never overwritten" in capsys.readouterr().err
