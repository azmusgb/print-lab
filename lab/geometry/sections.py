"""Per-layer outlines: where the layer shape jumps (tabs, pad ends, joins starting partway up) and where material is
thinner than one printed line."""
from dataclasses import dataclass

import numpy as np
import trimesh
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union


@dataclass
class Layer:
    z: float
    perimeter_mm: float
    area_mm2: float
    islands: int


def _layer_polygons(m: trimesh.Trimesh, layer_h: float):
    zs = np.arange(layer_h / 2, m.bounds[1][2], layer_h)
    for z, sec in zip(zs, m.section_multiplane([0, 0, 0], [0, 0, 1], zs)):
        if sec is None:
            yield float(z), Polygon()
            continue
        yield float(z), unary_union(list(sec.polygons_full))


def layer_outlines(m: trimesh.Trimesh, layer_h: float = 0.2) -> list[Layer]:
    out = []
    for z, poly in _layer_polygons(m, layer_h):
        parts = getattr(poly, "geoms", [poly]) if not poly.is_empty else []
        out.append(Layer(z=round(z, 3), perimeter_mm=round(float(poly.length), 2), area_mm2=round(float(poly.area), 2),
                         islands=len(parts)))
    return out


def outline_jumps(layers: list[Layer], min_jump_mm: float = 30.0) -> list[tuple[float, float]]:
    """Heights where the layer shape changes abruptly: the outline length jumps, or parts join or separate."""
    return [(b.z, round(b.perimeter_mm - a.perimeter_mm, 1)) for a, b in zip(layers, layers[1:])
            if abs(b.perimeter_mm - a.perimeter_mm) > min_jump_mm or a.islands != b.islands]


def thin_regions(m: trimesh.Trimesh, line_w: float, layer_h: float = 0.2, max_lines: float = 2.0,
                 min_area: float = 0.05, with_reach: bool = False) -> list[tuple]:
    """Layers with material narrower than max_lines printed lines: what vanishes when each layer is opened (shrunk and
    grown back) by max_lines/2 line widths. Narrower than 2 lines means the slicer can't fit a closed loop there.
    with_reach adds how far the lost material reaches from what stays (mm): a shallow cut into a surface, such as
    lettering 0.6 mm deep, leaves slivers that reach its depth; a free-standing thin wall reaches its own length."""
    out = []
    r = max_lines * line_w / 2
    for z, poly in _layer_polygons(m, layer_h):
        if poly.is_empty:
            continue
        kept = poly.buffer(-r, join_style="mitre").buffer(r, join_style="mitre")
        lost = poly.area - kept.area
        if lost > min_area:
            row = (round(z, 3), round(float(lost), 3))
            out.append(row + (round(_reach(poly.difference(kept), kept), 2),) if with_reach else row)
    return out


def _reach(lost, kept) -> float:
    """The furthest any vertex of the lost pieces lies from the kept material; inf when nothing is kept."""
    if kept.is_empty:
        return float("inf")
    rings = [g.exterior for g in getattr(lost, "geoms", [lost]) if g.geom_type == "Polygon" and g.area > 0.005]
    return max((kept.distance(Point(c)) for ring in rings for c in ring.coords), default=0.0)
