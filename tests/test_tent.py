from pathlib import Path

from lab.cli import main
from lab.geometry.tent import generate_tent_scad, write_tent_scad


def test_generate_tent_scad():
    code = generate_tent_scad(lean_deg=15.0, fins=4, tile_width=150.0, neck_mm=0.5)
    assert "lean_deg = 15;" in code
    assert "fin_count = 4;" in code
    assert "neck_thickness = 0.5;" in code
    assert "module tent_pair()" in code
    assert "module fin_brace" in code


def test_write_tent_scad(tmp_path):
    out = tmp_path / "tent.scad"
    res = write_tent_scad(out, lean_deg=12.0)
    assert res.exists()
    assert "lean_deg = 12;" in res.read_text()


def test_tent_cli(tmp_path, capsys):
    out = tmp_path / "test_tent.scad"
    rc = main(["tent", "--out", str(out), "--lean", "15", "--fins", "3"])
    assert rc == 0
    assert out.exists()
    out_msg = capsys.readouterr().out
    assert "Generated" in out_msg
    assert "15° lean" in out_msg
