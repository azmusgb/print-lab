"""The rules a generated design must keep, from projects/<p>/design-constraints.json, checked against a family's
parameters, the base 3MF's slicer settings and the built part.

Each constraint names its check:
- `min` / `max`: a parameter against an expression over parameters and settings ("skin_axial + land_thickness + 1.6 mm");
- `infill_bands`: on the upright part, no band taller than `max_band_mm` where the slicer would have room for sparse
  infill inside the walls (more than `min_area_mm2` left after shrinking each layer by the wall loops);
- `mark_clearance`: the maker mark's letters keep `min_mm` from every edge of the land they're cut into.

A `block` result drops a design at the gate; a `warn` result shows with it (the fix may be a setting, not the model)."""
import ast
import json
import operator
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh

from lab.geometry.upright import upright

SETTING_NAMES = ("wall_loops", "top_shell_layers", "bottom_shell_layers", "layer_height", "outer_wall_line_width",
                 "inner_wall_line_width")
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


@dataclass
class Result:
    id: str
    ok: bool
    severity: str
    message: str
    value: float | None = None
    limit: float | None = None


def load(project_dir: Path) -> list[dict]:
    path = Path(project_dir) / "design-constraints.json"
    return json.loads(path.read_text())["constraints"]


def numeric_settings(settings: dict | None) -> dict[str, float]:
    """The slicer settings constraints may name, as numbers (a per-extruder list gives its first value)."""
    out = {}
    for name in SETTING_NAMES:
        v = (settings or {}).get(name)
        if isinstance(v, list):
            v = v[0] if v else None
        if v not in (None, ""):
            out[name] = float(v)
    return out


def evaluate_expression(expr: str, names: dict[str, float]) -> float:
    """A limit written as Fusion would: numbers (with or without "mm"), names, + - * / and brackets. Nothing else."""
    tree = ast.parse(re.sub(r"(\d)\s*mm\b", r"\1", expr), mode="eval")

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id not in names:
                raise KeyError(f"'{node.id}' isn't a parameter or a known setting")
            return names[node.id]
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -ev(node.operand)
        raise ValueError(f"unsupported expression: {expr}")

    return ev(tree)


def part_mesh(part) -> trimesh.Trimesh:
    """A build123d part as a closed trimesh, stood upright as it prints."""
    verts, tris = part.tessellate(0.005, 0.1)
    return upright(trimesh.Trimesh([(p.X, p.Y, p.Z) for p in verts], tris))


def infill_bands(mesh: trimesh.Trimesh, wall_mm: float, layer_h: float, min_area_mm2: float,
                 ends_mm: float = 0.0) -> list[tuple]:
    """(bottom, top, peak area) of each run of layers with more than min_area_mm2 of room for sparse infill. Layers
    within ends_mm of the bed or the top are the end walls, which the shell layers fill (a separate constraint); they're
    left out, but a band that runs into them still counts up to where they start."""
    top = mesh.bounds[1][2]
    zs = [z for z in np.arange(layer_h / 2, top, layer_h) if ends_mm < z < top - ends_mm]
    flags = []
    for z, sec in zip(zs, mesh.section_multiplane([0, 0, 0], [0, 0, 1], zs)):
        area = 0.0 if sec is None else sum(q.buffer(-wall_mm, join_style="mitre").area for q in sec.polygons_full)
        flags.append((float(z), area))
    bands, start = [], None
    for i, (_, a) in enumerate(flags + [(None, 0.0)]):
        if a > min_area_mm2 and start is None:
            start = i
        elif a <= min_area_mm2 and start is not None:
            run = flags[start:i]
            bands.append((run[0][0] - layer_h / 2, run[-1][0] + layer_h / 2, max(x[1] for x in run)))
            start = None
    return bands


def mark_clearance(family, params: dict[str, float]) -> float | None:
    """How close (mm) the mark's letters come to the land's outer edge, inner edge or open top; None without a mark."""
    if not hasattr(family, "mark_outline") or params.get("mark", 0) < 0.5:
        return None
    pts, (normal, outer, inner, open_top) = family.mark_outline(params)
    s = [x * normal[0] + y * normal[1] for x, y in pts]
    return min(outer - max(s), min(s) - inner, open_top - max(y for _, y in pts))


def check(constraints: list[dict], family, params: dict[str, float], part=None,
          settings: dict | None = None) -> list[Result]:
    """Every constraint for this family, in file order. Geometry checks need `part`; without it they're skipped."""
    names = {**numeric_settings(settings), **params}
    out = []
    for c in constraints:
        if c.get("family") not in (None, family.NAME):
            continue
        cid, sev, kind = c["id"], c.get("severity", "block"), c["check"]
        if kind in ("min", "max"):
            value = params[c["parameter"]]
            try:
                limit = evaluate_expression(c[kind], names)
            except KeyError as e:
                out.append(Result(cid, False, sev, f"can't evaluate {c[kind]!r}: {e.args[0]}"))
                continue
            ok = value >= limit - 1e-9 if kind == "min" else value <= limit + 1e-9
            word = "at least" if kind == "min" else "at most"
            out.append(Result(cid, ok, sev, f"{c['parameter']} {value:g} mm must be {word} {limit:g} mm: {c['reason']}",
                              value, limit))
        elif kind == "infill_bands":
            if part is None:
                continue
            missing = [n for n in ("wall_loops", "outer_wall_line_width", "inner_wall_line_width", "layer_height")
                       if n not in names]
            if missing:
                out.append(Result(cid, False, sev, f"needs the base settings: {', '.join(missing)}"))
                continue
            wall = names["outer_wall_line_width"] + (names["wall_loops"] - 1) * names["inner_wall_line_width"]
            ends = evaluate_expression(c["ends"], names) if c.get("ends") else 0.0
            bands = infill_bands(part_mesh(part), wall, names["layer_height"], c["min_area_mm2"], ends)
            tall = [b for b in bands if b[1] - b[0] > c["max_band_mm"] + 1e-9]
            worst = max((b[1] - b[0] for b in bands), default=0.0)
            where = "; ".join(f"{b[0]:.1f}–{b[1]:.1f} mm (up to {b[2]:.0f} mm²)" for b in (tall or bands))
            out.append(Result(cid, not tall, sev, (f"room for infill at {where}" if bands else "no room for infill")
                              + f": {c['reason']}", round(worst, 2), c["max_band_mm"]))
        elif kind == "mark_clearance":
            value = mark_clearance(family, params)
            if value is None:
                continue
            out.append(Result(cid, value >= c["min_mm"], sev,
                              f"the mark comes {value:.2f} mm from a land edge: {c['reason']}", round(value, 3),
                              c["min_mm"]))
        else:
            out.append(Result(cid, False, sev, f"unknown check '{kind}'"))
    return out
