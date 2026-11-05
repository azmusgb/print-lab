"""The design rules the Fusion panel warns with: well formed, and the skin-gap rule matches the modelled tile."""
import ast
import json
import operator
import re
from pathlib import Path

import numpy as np
import pytest
import trimesh

from tests.conftest import need

ROOT = Path(__file__).resolve().parent.parent
RULE_FILES = sorted(ROOT.glob("projects/*/design-rules.json"))
RIFT = {"corner_diameter": 152.4, "edge_depth": 9.0, "facet_rise": 10.0, "skin_axial": 2.4, "perimeter_wall": 2.4,
        "land_width": 17.7, "land_thickness": 2.4}
OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def evaluate(expr: str, values: dict) -> float:
    """A Fusion length expression in mm: + - * / ( ), numbers with or without 'mm', and parameter names."""
    tree = ast.parse(re.sub(r"(\d)\s*mm\b", r"\1", expr), mode="eval")

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.BinOp) and type(n.op) in OPS:
            return OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return float(n.value)
        if isinstance(n, ast.Name):
            return values[n.id]
        raise ValueError(f"not a simple length expression: {expr}")
    return ev(tree)


def test_there_is_a_rules_file():
    assert any(f.parent.name == "hex-tile" for f in RULE_FILES)


@pytest.mark.parametrize("path", RULE_FILES, ids=lambda p: p.parent.name)
def test_rules_are_well_formed(path):
    rules = json.loads(path.read_text())["rules"]
    assert rules
    for r in rules:
        assert isinstance(r["parameter"], str) and r["reason"] and r["source"]
        assert r.get("min") or r.get("max")
        for bound in ("min", "max"):
            if r.get(bound):
                evaluate(r[bound], {k: 1.0 for k in RIFT} | {r["parameter"]: 1.0})


def _rule(name):
    rules = json.loads((ROOT / "projects/hex-tile/design-rules.json").read_text())["rules"]
    return next(r for r in rules if r["parameter"] == name)


def test_edge_depth_floor_at_the_rift_values():
    assert evaluate(_rule("edge_depth")["min"], RIFT) == pytest.approx(6.4)
    assert RIFT["edge_depth"] >= evaluate(_rule("edge_depth")["min"], RIFT)


def test_the_skin_gap_rule_is_safe_on_the_modelled_tile(hex_dir):
    """Rays through the land, along the corner axis of the flat RIFT export (face +Z): land, air, skin. The air gap
    must be at least what the rule assumes (edge_depth - skin_axial - land_thickness), and at least 1.6 mm."""
    m = trimesh.load(need(hex_dir / "RIFT_fusion_flat.stl"), force="mesh")
    lo, hi = m.bounds
    c = (lo + hi) / 2
    assumed = RIFT["edge_depth"] - RIFT["skin_axial"] - RIFT["land_thickness"]
    for inset in (4, 8, 12, 16):
        origin = [hi[0] - inset, c[1], lo[2] - 5]
        zs = np.sort(m.ray.intersects_location([origin], [[0, 0, 1]])[0][:, 2] - lo[2])
        assert len(zs) == 4, zs  # land bottom, land top, skin underside, face
        land_top, skin_under = zs[1], zs[2]
        assert land_top == pytest.approx(RIFT["land_thickness"], abs=0.01)
        assert skin_under - land_top >= assumed - 0.01
        assert skin_under - land_top >= 1.6
