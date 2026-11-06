"""faceted_hex: the RIFT wall tile as a family. A hexagon with a faceted relief face, hollow behind a skin of constant
axial thickness, a sealed hollow roof so no infill sits behind the face, a U-shaped tape land on the back, and the
RAHE/RIFT mark cut into the land.

Built in the tile's own frame, as Fusion's "Rift simplified" models it: the back on z = 0, the face towards +z, corners
on ±x, the open top of the U towards +y. It prints standing on its -y side (`ORIENTATION`).

Seed 0 is the facet layout of "Rift simplified v6" (Fusion, 5 Nov 2026). Other seeds come with `lab design make`."""
import json
import math
from pathlib import Path

from build123d import Face, Polyline, Pos, Shell, Solid, Wire, extrude

from lab.design.family import Param

NAME = "faceted_hex"
VERSION = 1
ORIENTATION = "upright: stands on its -y side, face towards +z before the turn"

PARAMS = [
    Param("corner_diameter", 165.4, 100.0, 260.0, "Hex size across the corners"),
    Param("edge_depth", 9.0, 4.0, 20.0, "Height of the hex side wall, back to face edge"),
    Param("facet_rise", 10.0, 0.0, 20.0, "How far the highest facet peak rises above the edge"),
    Param("skin_axial", 2.4, 0.9, 5.0, "Face skin thickness, measured straight back (z)"),
    Param("perimeter_wall", 2.4, 0.9, 6.0, "Side wall thickness"),
    Param("land_width", 17.7, 5.0, 40.0, "Width of the U-shaped tape land on the back"),
    Param("land_thickness", 2.4, 0.9, 6.0, "Thickness of the tape land"),
    Param("roof_wall", 2.4, 0.9, 6.0, "Roof plate width per layer (45° roof); the space above it is sealed hollow"),
    Param("mark", 1.0, 0.0, 1.0, "1 cuts the RAHE/RIFT mark into the land, 0 leaves it plain", unit=""),
]

# Rift v6's layout, as drawn in Fusion at a 152.4 mm corner diameter, a 9 mm edge and a 10 mm rise: (x, y) as a
# fraction of the corner radius, and the height above the edge as a fraction of facet_rise. The six corners come first.
_R0 = 76.2
_V6_POINTS = [(-76.2, 0.0, 9.0), (-38.1, -65.9911, 9.0), (-38.1, 65.9911, 9.0), (38.1, -65.9911, 9.0),
              (38.1, 65.9911, 9.0), (76.2, 0.0, 9.0), (-27.432, 13.716, 17.0), (-12.192, -28.956, 15.0),
              (1.524, 35.052, 14.5), (12.192, 3.81, 19.0), (25.908, -21.336, 14.7355)]
V6_LAYOUT = {
    "points": [(x / _R0, y / _R0, (z - 9.0) / 10.0) for x, y, z in _V6_POINTS],
    "triangles": [(0, 1, 7), (0, 6, 2), (0, 7, 6), (1, 3, 7), (2, 8, 4), (2, 6, 8), (3, 5, 10), (3, 10, 7),
                  (4, 9, 5), (4, 8, 9), (5, 9, 10), (6, 7, 9), (6, 9, 8), (7, 10, 9)],
}

_MARK = Path(__file__).resolve().parent.parent / "assets" / "rift_mark.json"
_COS30 = math.cos(math.radians(30))


def _prism(corners2d: list[tuple[float, float]], z0: float, z1: float) -> Solid:
    face = Face(Wire.make_polygon([(x, y, z0) for x, y in corners2d], close=True))
    return extrude(face, amount=z1 - z0, dir=(0, 0, 1))


def _ring(r: float) -> list[tuple[float, float]]:
    return [(r * math.cos(math.radians(a)), r * math.sin(math.radians(a))) for a in range(0, 360, 60)]


def _tile(p: dict[str, float], layout: dict) -> Solid:
    """The solid tile before hollowing: the hex prism up to the edge, under the faceted face."""
    r = p["corner_diameter"] / 2
    e, rise = p["edge_depth"], p["facet_rise"]
    rim = _ring(r)
    pts = [(u * r, v * r, e + h * rise) for u, v, h in layout["points"]]
    # The first six points are the corners: snap them to the exact rim so the face and the side walls share edges.
    for i in range(6):
        x, y = min(rim, key=lambda c: math.dist(c, pts[i][:2]))
        pts[i] = (x, y, e)
    faces = [Face(Wire.make_polygon([pts[i] for i in tri], close=True)) for tri in layout["triangles"]]
    for (x0, y0), (x1, y1) in zip(rim, rim[1:] + rim[:1]):
        faces.append(Face(Wire.make_polygon([(x0, y0, 0), (x1, y1, 0), (x1, y1, e), (x0, y0, e)], close=True)))
    faces.append(Face(Wire.make_polygon([(x, y, 0) for x, y in reversed(rim)], close=True)))
    return Solid(Shell(faces))


def _cavity(p: dict[str, float], tile: Solid) -> Solid:
    """Everything behind the skin and inside the side walls, open at the back, less the 45° roof plate: below the
    plate is the open cavity, above it the sealed hollow roof."""
    r = p["corner_diameter"] / 2
    ri = r - p["perimeter_wall"] / _COS30
    top = r * _COS30 - p["perimeter_wall"]  # the inner face of the top wall (+y)
    reach = p["edge_depth"] + p["facet_rise"] + 2
    behind_skin = tile.moved(Pos(0, 0, -p["skin_axial"]))
    cavity = _prism(_ring(ri), 0, reach) & behind_skin
    # The roof plate: between y + z = top and y + z = top + roof_wall, across the whole width.
    z0, z1, h, w = -5.0, reach + 5, p["roof_wall"], p["corner_diameter"]
    plate_yz = [(top - z0, z0), (top - z1, z1), (top - z1 + h, z1), (top - z0 + h, z0)]
    plate = extrude(Face(Wire.make_polygon([(-w, y, z) for y, z in plate_yz], close=True)), amount=2 * w,
                    dir=(1, 0, 0))
    return cavity - plate


def _land(p: dict[str, float]) -> Solid:
    """The U-shaped tape land on the back: a ring land_width wide, open at the top (+y)."""
    r = p["corner_diameter"] / 2
    inner = r - p["land_width"] / _COS30
    ring = _prism(_ring(r), 0, p["land_thickness"]) - _prism(_ring(inner), -1, p["land_thickness"] + 1)
    open_top = inner * _COS30
    return ring - _prism([(-r - 1, open_top), (r + 1, open_top), (r + 1, r + 1), (-r - 1, r + 1)], -1,
                         p["land_thickness"] + 1)


def _mark_anchor(p: dict[str, float]) -> tuple[float, float]:
    """Where the mark's anchor sits: it moves with corner_diameter and land_width by the same linear terms Rift v6's
    sketch dimensions use."""
    dcd, dlw = p["corner_diameter"] - 152.4, p["land_width"] - 17.7
    return 54.9481 + dcd * 0.36056 - dlw * 0.43301, 19.1407 + dcd * 0.24151 - dlw * 0.25000


def mark_outline(p: dict[str, float]):
    """The mark's letter outline points as placed, and the land segment it sits on: (points, (outward normal of that
    segment, its outer edge and inner edge as distances along the normal, the open top's y))."""
    data = json.loads(_MARK.read_text())
    ax, ay = _mark_anchor(p)
    pts = [(ax + x, ay + y) for loops in data["faces"] for loop in loops for x, y in loop]
    r = p["corner_diameter"] / 2
    outer = r * _COS30
    inner = outer - p["land_width"]
    normal = (_COS30, 0.5)  # the side between the corners at 0° and 60°
    return pts, (normal, outer, inner, inner)


def _mark(p: dict[str, float]) -> Solid:
    """The RAHE/RIFT letters as solids 0.6 mm deep from the back, placed as Fusion places them."""
    data = json.loads(_MARK.read_text())
    ax, ay = _mark_anchor(p)
    letters = None
    for loops in data["faces"]:
        wires = [Wire(Polyline(*[(ax + x, ay + y, 0) for x, y in loop], close=True)) for loop in loops]
        face = Face(wires[0], wires[1:])
        solid = extrude(face, amount=data["depth"], dir=(0, 0, 1))
        letters = solid if letters is None else letters + solid
    return letters


def build(params: dict[str, float], seed: int = 0) -> Solid:
    """The tile for these parameters (already resolved and in range) and facet seed."""
    if seed != 0:
        raise NotImplementedError("seeded facet layouts arrive with `lab design make`; seed 0 is Rift v6")
    tile = _tile(params, V6_LAYOUT)
    part = (tile - _cavity(params, tile)) + _land(params)
    if params["mark"] >= 0.5:
        part = part - _mark(params)
    return part
