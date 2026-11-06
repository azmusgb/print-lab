"""The `lab` command. Exit codes: 0 done, 1 a tool or input error (the message says what to do), 2 blocking findings."""
import argparse
import json
import os
import sys
import zipfile
from dataclasses import asdict
from pathlib import Path

from lab.findings import worst

ROOT = Path(__file__).resolve().parent.parent


def project_dir(name: str) -> Path:
    return Path(os.environ.get("LAB_HOME", ROOT)) / "projects" / name


def _strict(o):
    """JSON has no NaN: a measurement that doesn't exist (an open mesh's volume) is null."""
    if isinstance(o, float) and o != o:
        return None
    if isinstance(o, dict):
        return {k: _strict(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_strict(v) for v in o]
    return o


def _load(args):
    from lab.geometry.mesh import load_mesh
    return load_mesh(Path(args.file), args.object)


def _nozzle(args) -> float:
    import re
    if args.nozzle:
        return float(args.nozzle)
    m = re.search(r"(0\.[46])\s*nozzle", Path(args.file).name, re.I)
    if m:
        return float(m.group(1))
    if Path(args.file).suffix == ".3mf":
        from lab.adapters.bambu import read_settings
        nd = read_settings(Path(args.file)).get("nozzle_diameter", ["0.4"])
        return float(nd[0] if isinstance(nd, list) else nd)
    return 0.4


def _findings_text(fs) -> list[str]:
    return [f"  [{f.severity}] {f.rule}: {f.where}\n      {f.why}\n      Fix: {f.fix}" for f in fs]


def cmd_inspect(args) -> int:
    from lab.adapters.bambu import read_settings
    from lab.checks import run_checks
    from lab.geometry.facets import facet_switches, front_facets
    from lab.geometry.mesh import mesh_facts
    from lab.geometry.sections import layer_outlines, outline_jumps

    m = _load(args)
    path = Path(args.file)
    settings = read_settings(path) if path.suffix == ".3mf" else None
    facts = mesh_facts(m)
    facets = front_facets(m)
    sw = facet_switches(facets)
    jumps = [j for j in outline_jumps(layer_outlines(m)) if j[0] > 5]
    fs = run_checks(m, nozzle=_nozzle(args), settings=settings, file_name=path.name)
    if args.json:
        print(json.dumps(_strict({"facts": asdict(facts), "switches": [asdict(s) for s in sw],
                                  "outline_jumps": jumps, "findings": [asdict(f) for f in fs]}),
                         indent=2, allow_nan=False))
    else:
        e = [f.elevation_deg for f in facets]
        print(f"{path.name}" + (f" [{args.object}]" if args.object else ""))
        print(f"Geometry  {' × '.join(f'{x:g}' for x in facts.extents)} mm, {facts.volume_cm3:g} cm³, "
              f"{'closed' if facts.watertight else 'NOT closed'}, {facts.bodies} piece(s), "
              f"bed contact {facts.bed_contact_mm2:g} mm², centre of mass at {facts.com_z:g} mm")
        sides = sorted({f.side for f in facets})
        print(f"Front facets  {len(facets)} on {', '.join(sides) or 'no side'}"
              + (f", facing {min(e):+.1f}° to {max(e):+.1f}°" if e else ""))
        print("Facet switches  " + (", ".join(f"{s.z_mm:g} mm ({s.side})" for s in sw) or "none"))
        print("Layer-shape jumps above 5 mm  " + (", ".join(f"{z:g} mm" for z, _ in jumps) or "none"))
        print("Findings" + ("" if fs else "  none"))
        print("\n".join(_findings_text(fs)))
    return 2 if worst(fs) == "blocking" else 0


def cmd_orient(args) -> int:
    from lab.geometry.orientation import score_orientations
    m = _load(args)
    print(f"{'angle':>6} {'A-surface':>10} {'stability':>10} {'height':>8} {'score':>6}")
    for s in score_orientations(m, [float(a) for a in args.angles.split(",")]):
        print(f"{s.angle:>5g}° {s.a_surface:>10.2f} {s.stability:>10.2f} {s.height_mm:>7.1f} {s.score:>6.1f}")
    return 0


def cmd_coupon(args) -> int:
    from lab.geometry.coupons import height_strip
    if args.kind != "height_strip":
        print(f"Only height_strip coupons are made in Stage 1A, not {args.kind}.", file=sys.stderr)
        return 1
    z0, z1 = (float(v) for v in args.z.split(":"))
    strip = height_strip(_load(args), z0, z1)
    strip.export(args.out)
    print(f"Wrote {args.out}: {' × '.join(f'{x:.1f}' for x in strip.extents)} mm")
    return 0


def cmd_slice(args) -> int:
    from lab.adapters.bambu import slice_with_job
    from lab.experiments import link_slice_job
    path = Path(args.file)
    pdir = project_dir(args.project)
    out, job = slice_with_job(path, Path(args.out_dir) if args.out_dir else path.parent, args.plate, pdir / "jobs")
    if exp := link_slice_job(pdir, path, job.id):
        print(f"Slice job {job.id} recorded on {exp}")
    info = zipfile.ZipFile(out).read("Metadata/slice_info.config").decode()
    import re
    pred = re.search(r'key="prediction" value="(\d+)"', info)
    weight = re.search(r'key="weight" value="([\d.]+)"', info)
    t = int(pred.group(1)) if pred else 0
    print(f"Sliced {out}\nTime {t // 3600} h {t % 3600 // 60} min, filament {weight.group(1) if weight else '?'} g")
    return 0


def cmd_tent(args) -> int:
    from lab.geometry.tent import render_tent_stl, write_tent_scad
    out_path = Path(args.out)
    write_tent_scad(out_path, lean_deg=args.lean, fins=args.fins, tile_width=args.width, neck_mm=args.neck)
    print(f"Generated {out_path} ({args.lean:g}° lean, {args.fins} fins, {args.neck:g} mm neck)")
    if getattr(args, "render", False):
        stl_path = out_path.with_suffix(".stl")
        try:
            render_tent_stl(out_path, stl_path)
            print(f"Rendered STL: {stl_path}")
        except Exception as e:
            print(f"OpenSCAD render failed: {e}", file=sys.stderr)
            return 1
    return 0


def cmd_gcode(args) -> int:
    from lab.adapters.bambu import extract_gcode
    from lab.analysis.gcode import diff_layers, events_near, format_gcode_diff, read_layers
    path_a = Path(args.file)
    layers_a = read_layers(extract_gcode(path_a, args.plate))

    if getattr(args, "diff", None):
        path_b = Path(args.diff)
        plate_b = getattr(args, "plate2", args.plate)
        layers_b = read_layers(extract_gcode(path_b, plate_b))
        diff = diff_layers(layers_a, layers_b, near=args.near)
        if getattr(args, "json", False):
            print(json.dumps(diff, indent=2))
        else:
            print(format_gcode_diff(diff, name_a=path_a.name, name_b=path_b.name,
                                    show_layers=getattr(args, "layers", False) or args.near is not None))
        return 0

    times = [l.est_time_s for l in layers_a]
    print(f"{len(layers_a)} layers, z {layers_a[0].z:g}–{layers_a[-1].z:g} mm, layer time {min(times):.1f}–{max(times):.1f} s")
    if args.near is not None:
        ev = events_near(layers_a, args.near)
        print(f"Within 5 mm of {args.near:g} mm: outer-wall speed change {ev['speed_change_z'] or 'none'}, fan change "
              f"{ev['fan_change_z'] or 'none'}, layer-time jump {ev['layer_time_jump_z'] or 'none'}")
    return 0


def _version_dict(path: Path) -> dict:
    from lab.adapters.bambu import read_settings
    from lab.history.revisions import scad_params
    return {"model": scad_params(path)} if path.suffix == ".scad" else {"settings": read_settings(path)}


def cmd_plan(args) -> int:
    from lab.experiments import check_plan, load, save
    exp = load(Path(args.experiment))
    if Path(args.before).suffix != Path(args.after).suffix:
        raise ValueError("Compare files of the same kind: two .scad files (model) or two .3mf files (settings).")
    fs = check_plan(exp, _version_dict(Path(args.before)), _version_dict(Path(args.after)))
    blocking = [f for f in fs if f.severity == "blocking"]
    exp.status = "blocked" if blocking else "checked"
    exp.blocked_reason = "; ".join(f.why for f in blocking)
    exp.findings = [asdict(f) for f in fs]
    save(exp, Path(args.experiment).parent.parent)
    print(f"{exp.id}: {exp.status}")
    print("\n".join(_findings_text(fs)))
    return 2 if blocking else 0


def cmd_history(args) -> int:
    from lab.history import audit, inventory, lineage, revisions
    hdir = project_dir(args.project) / "history"
    hdir.mkdir(parents=True, exist_ok=True)
    if args.action == "ingest":
        folder = Path(args.folder).resolve()
        arts = inventory.inventory(folder)
        mine = inventory.dedupe([a for a in arts if a.lineage == args.project])
        revs = revisions.revisions(mine, args.project)

        # Only this project's files are written, with paths relative to the folder: a Downloads folder also holds
        # private files whose names must never land in the repo.
        def rel(p: str) -> str:
            return str(Path(p).relative_to(folder)) if p else p

        out_arts = [{**asdict(a), "path": rel(a.path),
                     "duplicate_of": rel(a.duplicate_of)} for a in mine]
        out_revs = [{**asdict(r), "artifacts": [rel(p) for p in r.artifacts]} for r in revs]
        (hdir / "inventory.json").write_text(json.dumps(out_arts, indent=2))
        (hdir / "revisions.json").write_text(json.dumps(out_revs, indent=2, default=str))
        print(f"{len(mine)} {args.project} files of {len(arts)} in the folder, "
              f"{sum(1 for a in mine if a.duplicate_of)} duplicates, {len(revs)} revisions")
        return 0
    revs = [revisions.Revision(**r) for r in json.loads((hdir / "revisions.json").read_text())]
    trans = lineage.transitions(revs)
    if args.action == "timeline":
        for t in trans:
            changed = list(t.scad_changes) + list(t.settings_changes)
            print(f"v{t.from_v}→v{t.to_v}  {t.grade}  {t.factors} change(s): {', '.join(changed[:8])}"
                  + (" …" if len(changed) > 8 else "") + (f"  (no files for {t.gap})" if t.gap else ""))
        return 0
    outcomes_path = hdir / "outcomes.json"
    outs = audit.load_outcomes(outcomes_path) if outcomes_path.exists() else []
    print(audit.audit_text(revs, trans, outs), end="")
    return 0


REFRESHES_PAGE = ("migrate", "question", "exp", "setup", "photos", "observe")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="lab", description="Print lab: measure, check, cut coupons, slice, learn.")
    p.add_argument("--project", default=os.environ.get("LAB_PROJECT", "hex-tile"))
    sub = p.add_subparsers(dest="cmd", required=True)

    def model_cmd(name, fn, help_):
        s = sub.add_parser(name, help=help_)
        s.add_argument("file")
        s.add_argument("--object", help="part of the object's name, for a 3MF with several objects")
        s.set_defaults(fn=fn)
        return s

    s = model_cmd("inspect", cmd_inspect, "measure a model and run the checks")
    s.add_argument("--nozzle")
    s.add_argument("--json", action="store_true")
    s = model_cmd("orient", cmd_orient, "score lean angles")
    s.add_argument("--angles", default="0,10,15,20")
    s = model_cmd("coupon", cmd_coupon, "cut a coupon")
    s.add_argument("--kind", default="height_strip")
    s.add_argument("--z", required=True, help="from:to in mm")
    s.add_argument("--out", required=True)
    t = sub.add_parser("tent", help="generate braced 15° leaned-pair tent stabilizer geometry (OpenSCAD)")
    t.add_argument("--out", default="tent_pair.scad")
    t.add_argument("--lean", type=float, default=15.0)
    t.add_argument("--fins", type=int, default=3)
    t.add_argument("--width", type=float, default=152.4)
    t.add_argument("--neck", type=float, default=0.4)
    t.add_argument("--render", action="store_true", help="render to STL with OpenSCAD")
    t.set_defaults(fn=cmd_tent)
    s = sub.add_parser("slice", help="slice a 3MF plate with Bambu Studio")
    s.add_argument("file"); s.add_argument("--plate", type=int, default=1); s.add_argument("--out-dir")
    s.set_defaults(fn=cmd_slice)
    s = sub.add_parser("gcode", help="read a sliced plate's G-code, or diff two sliced plates")
    s.add_argument("file"); s.add_argument("--plate", type=int, default=1); s.add_argument("--near", type=float)
    s.add_argument("--diff", help="compare with another sliced 3MF or G-code file")
    s.add_argument("--plate2", type=int, default=1, help="plate number for the diff file (default 1)")
    s.add_argument("--layers", action="store_true", help="show layer-by-layer diff table")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_gcode)
    s = sub.add_parser("plan", help="check an experiment against the version before it")
    s.add_argument("experiment"); s.add_argument("--before", required=True); s.add_argument("--after", required=True)
    s.set_defaults(fn=cmd_plan)
    s = sub.add_parser("history", help="past revisions: ingest a folder, audit, timeline")
    s.add_argument("action", choices=["ingest", "audit", "timeline"]); s.add_argument("folder", nargs="?")
    s.set_defaults(fn=cmd_history)

    from lab import cli_loop, observe_cli
    cli_loop.register(sub)
    observe_cli.register(sub)
    from lab import page, pull, source, status, sync, variant, watch
    from lab.design import cli as design_cli
    design_cli.register(sub)
    page.register(sub)
    pull.register(sub)
    source.register(sub)
    status.register(sub)
    sync.register(sub)
    variant.register(sub)
    watch.register(sub)

    args = p.parse_args(argv)
    try:
        rc = args.fn(args)
        if args.cmd in REFRESHES_PAGE:
            try:
                page.refresh(project_dir(args.project))
                sync.background(project_dir(args.project))
            except Exception as e:  # the page is a view; never fail the command over it
                print(f"(page not rebuilt: {e})", file=sys.stderr)
        return rc
    except (ValueError, FileNotFoundError) as e:
        print(str(e), file=sys.stderr)
        return 1
    except Exception as e:
        from lab.jobs import LabToolError
        if isinstance(e, LabToolError):
            print(f"{e} (job {e.job.id})", file=sys.stderr)
            return 1
        raise


if __name__ == "__main__":
    sys.exit(main())
