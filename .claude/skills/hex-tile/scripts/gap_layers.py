"""Count the layers of a sliced hex-tile pair that put plastic across the middle of the gap between the tiles.

Usage: uv run python .claude/skills/hex-tile/scripts/gap_layers.py prints/sliced/<file>.gcode.3mf [...]

The pair stands with its thickness along the bed X axis; the gap is the middle of the X extent (measured on the
middle half of the pair's length, away from a strip's version tab). A layer counts when an extrusion move's
midpoint lies within 0.35 mm of that middle.

What it proves: whether the slicer actually printed the joining features, and on how many layers. It does NOT
prove contact: a rib that stops short of the partner (v59, E-011) still crosses the middle and counts.
Reference values: E-014 (v58 ribs) 657/660; E-011 (v59 ribs, 0.5 mm short) 157/160; E-020 (v61s staggered
tacks) 622/660 = one tack per 0.6 mm band, bottom and top few mm excepted.
"""
import re
import sys
import zipfile

MOVE = re.compile(r"^G[123]\b")


def gap_layers(path: str) -> tuple[int, int]:
    z = zipfile.ZipFile(path)
    gcode = z.read(next(n for n in z.namelist() if n.endswith(".gcode"))).decode()
    x = y = 0.0
    layers = []
    for chunk in gcode.split("; CHANGE_LAYER")[1:]:
        mids = []
        for line in chunk.splitlines():
            if not MOVE.match(line):
                continue
            mx, my, me = (re.search(rf"{a}([-\d.]+)", line) for a in "XYE")
            nx = float(mx.group(1)) if mx else x
            ny = float(my.group(1)) if my else y
            if me and float(me.group(1)) > 0:
                mids.append(((x + nx) / 2, (y + ny) / 2))
            x, y = nx, ny
        layers.append(mids)
    pts = [m for layer in layers for m in layer]
    ys = sorted(p[1] for p in pts)
    lo, hi = ys[len(ys) // 4], ys[3 * len(ys) // 4]       # middle half along the pair, away from a strip's version tab
    xs = [p[0] for p in pts if lo <= p[1] <= hi]
    centre = (max(xs) + min(xs)) / 2
    return sum(any(abs(m[0] - centre) < 0.35 for m in layer) for layer in layers), len(layers)


if __name__ == "__main__":
    for p in sys.argv[1:]:
        hit, total = gap_layers(p)
        print(f"{p.rsplit('/', 1)[-1]}: {hit} of {total} layers bridge the gap")
