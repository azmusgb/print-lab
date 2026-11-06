"""`lab design`: make candidates from a family and gate them (lab.design.gate)."""
import argparse
import json
from pathlib import Path


def _seeds(count: int, chosen: list[int] | None) -> list[int]:
    """--seed values when given (0 is the family's reference layout), else seeds 1..count."""
    if chosen:
        return list(dict.fromkeys(chosen))
    if count < 1:
        raise ValueError("--seeds needs at least 1.")
    return list(range(1, count + 1))


def cmd_design_make(args) -> int:
    from lab.cli import project_dir
    from lab.design.families import FAMILIES
    from lab.design.family import read_params
    from lab.design.gallery import write
    from lab.design.gate import make
    from lab.records.project import ProjectPaths

    family = FAMILIES.get(args.family)
    if family is None:
        raise ValueError(f"No family '{args.family}'; there is {', '.join(sorted(FAMILIES))}.")
    params = read_params(Path(args.params), only=family.PARAMS) if args.params else {}
    for kv in args.set or []:
        k, _, v = kv.partition("=")
        if not v:
            raise ValueError(f"--set takes name=value, not {kv!r}.")
        params[k.strip()] = float(v.removesuffix("mm").strip())
    paths = ProjectPaths(project_dir(args.project))
    run = make(paths, family, params, _seeds(args.seeds, args.seed), args.base,
               do_slice=not args.no_slice)
    page = write(paths, Path(run["path"]))
    kept = [c for c in run["candidates"] if not c["dropped"]]
    if args.json:
        print(json.dumps({**run, "gallery": str(page)}, indent=2))
    else:
        print(f"{len(kept)} of {len(run['candidates'])} kept. Run record: {run['path']}\nGallery: {page}")
    return 0


def cmd_design_gallery(args) -> int:
    from lab.cli import project_dir
    from lab.design.gallery import write
    from lab.design.gate import designs_dir
    from lab.records.project import ProjectPaths

    paths = ProjectPaths(project_dir(args.project))
    runs = sorted((designs_dir(paths) / "runs").glob("*.json"))
    if not runs:
        raise ValueError("No design runs yet; make some with: uv run lab design make --family … --base …")
    run = next((r for r in runs if r.stem == args.run), None) if args.run else runs[-1]
    if run is None:
        raise ValueError(f"No run {args.run}; there are {', '.join(r.stem for r in runs)}.")
    print(write(paths, run))
    return 0


def cmd_design_choose(args) -> int:
    from lab.cli import project_dir
    from lab.design.choose import choose
    from lab.records.project import ProjectPaths

    e = choose(ProjectPaths(project_dir(args.project)), args.design, name=args.name, note=args.note)
    if args.json:
        print(json.dumps(e, indent=2))
        return 0
    print(f"Registered {e['path']} (from {e['derived_from']})\nChange  {e['change']}")
    print(f"\nNext: uv run lab exp plan <question> \"<what it asks>\" --source {e['path']} "
          f"--object {Path(e['path']).stem} --base {e['derived_from']} --factor … --values … --hypothesis … "
          "--prediction …")
    return 0


def register(sub) -> None:
    s = sub.add_parser("design", help="make candidate models from a family, gated before anyone looks")
    ds = s.add_subparsers(dest="design_cmd", required=True)
    m = ds.add_parser("make", help="build, check and slice one candidate per seed")
    m.add_argument("--family", required=True)
    m.add_argument("--base", required=True, help="a registered sources/<file>.3mf whose settings slice the candidates")
    m.add_argument("--seeds", type=int, default=12, help="how many seeds: 1..N (default 12)")
    m.add_argument("--seed", type=int, action="append", help="one seed, repeatable, instead of --seeds (0 is the "
                                                             "family's reference layout)")
    m.add_argument("--params", help="a params.json (the family's own or a Fusion export) to start from")
    m.add_argument("--set", action="append", help="name=value, repeatable; applied after --params")
    m.add_argument("--no-slice", action="store_true", help="stop after the checks (no Bambu Studio)")
    m.add_argument("--json", action="store_true")
    m.add_argument("--project", default=argparse.SUPPRESS)
    m.set_defaults(fn=cmd_design_make)
    c = ds.add_parser("choose", help="register a kept candidate as a source (lab variant add, with its parameters)")
    c.add_argument("design", help="the design id from the gallery (a unique prefix is enough)")
    c.add_argument("--name", help="the source's name (default <family>_s<seed>_<id>)")
    c.add_argument("--note")
    c.add_argument("--json", action="store_true")
    c.add_argument("--project", default=argparse.SUPPRESS)
    c.set_defaults(fn=cmd_design_choose)
    g = ds.add_parser("gallery", help="(re)write a run's gallery page")
    g.add_argument("run", nargs="?", help="the run id (designs/runs/<run>.json); the latest when left out")
    g.add_argument("--project", default=argparse.SUPPRESS)
    g.set_defaults(fn=cmd_design_gallery)
