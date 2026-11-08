"""`lab quick slice`: slice an STL for the X2D on a Studio-saved base project. No network; the Pi Hub path comes later."""
import argparse
import json
import sys
from pathlib import Path

from lab.quick import settings as qs
from lab.quick.engine import QuickSliceError, quick_slice


def cmd_quick_slice(args) -> int:
    rot = tuple(float(v) for v in args.rotate.split(","))
    if len(rot) != 3:
        print("--rotate takes three numbers: x,y,z degrees", file=sys.stderr)
        return 2
    s = qs.QuickSettings(layer_height=args.layer_height, walls=args.walls, top_layers=args.top_layers,
                         bottom_layers=args.bottom_layers, infill_pct=args.infill, infill_pattern=args.infill_pattern,
                         supports=args.supports, brim=args.brim, brim_width=args.brim_width)
    try:
        res = quick_slice(Path(args.stl), Path(args.base), Path(args.out_dir), s, rotate=rot, scale=args.scale,
                          expect_source_sha256=args.expect_sha256)
    except QuickSliceError as e:
        print(f"Can't slice: {e}", file=sys.stderr)
        return 2
    if args.json:
        from dataclasses import asdict
        print(json.dumps(asdict(res), indent=2))
    elif res.status == "sliced":
        e = res.estimate
        print(f"Sliced {res.job_id}: {int(e['minutes'] // 60)} h {int(e['minutes'] % 60)} min, {e['grams']} g, "
              f"{res.layers['count']} layers\n{Path(args.out_dir) / res.job_id / res.artifact['file']}")
    else:
        print(f"Needs attention ({res.job_id}); not usable:", file=sys.stderr)
        for r in res.reasons:
            print(f"  - {r}", file=sys.stderr)
    return 0 if res.status == "sliced" else 1


def register(sub) -> None:
    q = sub.add_parser("quick", help="Quick Print: slice an ordinary STL for the X2D")
    qsub = q.add_subparsers(dest="quick_cmd", required=True)
    s = qsub.add_parser("slice", help="slice an STL on a Studio-saved base project and check the X2D start")
    s.add_argument("stl")
    s.add_argument("--base", required=True, help="a complete X2D project saved in Bambu Studio (.3mf)")
    s.add_argument("--out-dir", required=True)
    s.add_argument("--rotate", default="0,0,0", help="x,y,z degrees")
    s.add_argument("--scale", type=float, default=1.0)
    s.add_argument("--expect-sha256", help="refuse if the STL no longer has this sha256")
    s.add_argument("--layer-height", type=float, help=f"{qs.LAYER_HEIGHT[0]}–{qs.LAYER_HEIGHT[1]} mm")
    s.add_argument("--walls", type=int, help=f"{qs.WALLS[0]}–{qs.WALLS[1]}")
    s.add_argument("--top-layers", type=int)
    s.add_argument("--bottom-layers", type=int)
    s.add_argument("--infill", type=int, help=f"{qs.INFILL_PCT[0]}–{qs.INFILL_PCT[1]} %%")
    s.add_argument("--infill-pattern", choices=qs.INFILL_PATTERNS)
    s.add_argument("--supports", action=argparse.BooleanOptionalAction, default=None)
    s.add_argument("--brim", choices=list(qs.BRIM_TYPES))
    s.add_argument("--brim-width", type=float)
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_quick_slice)
