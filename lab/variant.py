"""`lab variant add`: a model made elsewhere (a Fusion export) becomes a registered source.

The new sources/<name>.3mf is written from a registered base project: the base's full printer settings with the one
new object on plate 1, so it can never be sliced from loose presets (v73 printed in air that way, 27 Oct 2026). It is
registered in sources/sources.json with its sha256, derived_from and a change line, and never overwrites a source:
builds pin a source's sha256, so a rewrite would mark every build of it stale. With --params, the design's parameters
are kept beside it (sources/<name>.params.json) and the change line names the ones that differ from the base's.
"""
import argparse
import json
import re
from pathlib import Path

from lab.jobs import sha256
from lab.records.project import ProjectPaths
from lab.records.store import atomic_write_json, now

NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}")
PLATE_CENTRE = (128.0, 128.0)


def _registry(paths: ProjectPaths) -> list[dict]:
    f = paths.sources / "sources.json"
    if not f.is_file():
        raise ValueError(f"{f} doesn't exist; this project has no registered sources to derive from.")
    data = json.loads(f.read_text())
    if not isinstance(data, list):
        raise ValueError(f"{f} isn't a list of sources.")
    return data


def registered_base(paths: ProjectPaths, base: str) -> tuple[str, Path]:
    """("sources/<file>.3mf", its path) for a base that is registered, a 3MF, and unchanged since registration."""
    base = base if base.startswith("sources/") else f"sources/{base}"
    entry = next((e for e in _registry(paths) if e.get("path") == base), None)
    if entry is None:
        raise ValueError(f"{base} isn't a registered source of {paths.name}; pick one from sources/sources.json.")
    base_path = paths.root / base
    if base_path.suffix != ".3mf" or not base_path.is_file():
        raise ValueError(f"The base must be a registered 3MF project that exists: {base}")
    if entry.get("sha256") and sha256(base_path) != entry["sha256"]:
        raise ValueError(f"{base} doesn't match its registered sha256; it changed since it was registered.")
    return base, base_path


def _read_params(path: Path) -> dict:
    try:
        p = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f"Can't read the parameters file {path}: {e}") from None
    if not isinstance(p, dict) or not isinstance(p.get("parameters"), list):
        raise ValueError(f"{path} has no 'parameters' list.")
    for q in p["parameters"]:
        if not isinstance(q, dict) or not isinstance(q.get("name"), str) or "expression" not in q:
            raise ValueError(f"{path}: every parameter needs a name and an expression.")
    return p


def _shown(q: dict) -> str:
    v, unit = q.get("value"), q.get("unit") or ""
    return f"{v:g} {unit}".strip() if isinstance(v, (int, float)) else str(q.get("expression"))


def change_line(params: dict | None, base_params: dict | None, base: str) -> str:
    """What differs from the base, in words: the changed parameters when both sides have them."""
    if params is None:
        return f"geometry from an exported model; settings from {base}"
    doc = params.get("document") or "a Fusion design"
    ver = f" v{params['version']}" if params.get("version") else ""
    made = f"geometry from Fusion '{doc}'{ver}; settings from {base}"
    if base_params is None:
        return made
    old = {q["name"]: q for q in base_params["parameters"]}
    new = {q["name"]: q for q in params["parameters"]}
    diffs = [f"{n} {_shown(old[n])} → {_shown(new[n])}" for n in new
             if n in old and str(old[n].get("expression")) != str(new[n].get("expression"))]
    diffs += [f"{n} added ({_shown(new[n])})" for n in new if n not in old]
    diffs += [f"{n} removed" for n in old if n not in new]
    return ("; ".join(diffs) if diffs else "parameters as the base's") + f"; {made}"


def add_variant(paths: ProjectPaths, *, mesh: Path, base: str, name: str, params: Path | None = None,
                note: str | None = None, flat: bool = False, change: str | None = None) -> dict:
    """Write and register sources/<name>.3mf; returns its sources.json entry. Nothing is left behind on failure.
    `change` replaces the change line worked out from the parameters (a generated design says what made it)."""
    import trimesh

    from lab.adapters.threemf import load_object, write_print_3mf
    from lab.geometry.upright import upright

    name = name.removesuffix(".3mf")
    if not NAME.fullmatch(name):
        raise ValueError(f"'{name}' can't be a source name: use letters, digits, '_', '-' and '.', up to 80.")
    reg = _registry(paths)
    base, base_path = registered_base(paths, base)
    rel = f"sources/{name}.3mf"
    out = paths.root / rel
    side = paths.sources / f"{name}.params.json"
    if out.exists() or side.exists() or any(e.get("path") == rel for e in reg):
        raise ValueError(f"{rel} already exists. Sources are never overwritten (builds pin their sha256); "
                         "pick a new name.")
    p = _read_params(params) if params else None
    base_side = base_path.with_suffix(".params.json")
    base_p = _read_params(base_side) if p and base_side.is_file() else None

    m = trimesh.load(Path(mesh), force="mesh")
    if m.is_empty:
        raise ValueError(f"No geometry in {mesh}.")
    if not m.is_watertight:
        raise ValueError(f"{mesh} isn't a closed solid, so its volume and the slice can't be trusted; "
                         "re-export the visible bodies.")
    m = m if flat else upright(m)
    meta: dict = {"made_by": "lab variant add", "from": Path(mesh).name, "base": base}
    if p:
        meta["design"] = {k: p[k] for k in ("document", "version", "family", "seed", "design") if k in p}
    try:
        write_print_3mf(base_path, [(name, m, PLATE_CENTRE)], out, meta)
        back = load_object(out, name)
        if abs(abs(back.volume) - abs(m.volume)) > 1e-5 * abs(m.volume) + 0.01 or \
                any(abs(a - b) > 0.002 for a, b in zip(back.extents, m.extents)):
            raise ValueError(f"{rel} didn't read back as the exported model (volume {abs(back.volume):.3f} vs "
                             f"{abs(m.volume):.3f} mm³); nothing was registered.")
        if p:
            atomic_write_json(side, p)
        new = {"path": rel, "sha256": sha256(out), "source": "derived", "derived_from": base,
               "change": change or change_line(p, base_p, base), "added": now()}
        if p:
            new["params"] = f"sources/{side.name}"
        if note:
            new["note"] = note
        atomic_write_json(paths.sources / "sources.json", reg + [new])
    except BaseException:
        out.unlink(missing_ok=True)
        side.unlink(missing_ok=True)
        raise
    return new


def cmd_variant_add(args) -> int:
    from lab.adapters.bambu import read_settings
    from lab.adapters.threemf import load_object
    from lab.checks import run_checks
    from lab.cli import _findings_text, project_dir
    from lab.findings import worst

    paths = ProjectPaths(project_dir(args.project))
    e = add_variant(paths, mesh=Path(args.mesh), base=args.base, name=args.name,
                    params=Path(args.params) if args.params else None, note=args.note, flat=args.flat)
    out = paths.root / e["path"]
    settings = read_settings(out) or {}
    nd = settings.get("nozzle_diameter", ["0.4"])
    m = load_object(out, Path(e["path"]).stem)
    fs = run_checks(m, nozzle=float(nd[0] if isinstance(nd, list) else nd), settings=settings, file_name=out.name)
    if args.json:
        from dataclasses import asdict
        print(json.dumps({"source": e, "extents": [round(float(x), 3) for x in m.extents],
                          "findings": [asdict(f) for f in fs]}, indent=2))
        return 0
    print(f"Registered {e['path']} ({' × '.join(f'{x:.1f}' for x in m.extents)} mm, from {e['derived_from']})")
    print(f"Change  {e['change']}")
    print("Findings" + ("" if fs else "  none"))
    print("\n".join(_findings_text(fs)))
    print(f"\nNext: uv run lab exp plan <question> \"<what it asks>\" --source {e['path']} "
          f"--object {Path(e['path']).stem} --base {e['derived_from']} --factor … --values … --hypothesis … "
          "--prediction …")
    return 2 if worst(fs) == "blocking" else 0


def register(sub) -> None:
    s = sub.add_parser("variant", help="register a model made elsewhere (a Fusion export) as a new source 3MF")
    vs = s.add_subparsers(dest="variant_cmd", required=True)
    a = vs.add_parser("add", help="write sources/<name>.3mf from a base project's settings and register it")
    a.add_argument("--mesh", required=True, help="the exported STL, modelled flat (turned upright unless --flat)")
    a.add_argument("--base", required=True, help="a registered sources/<file>.3mf whose settings to carry")
    a.add_argument("--name", required=True, help="the new source's name (also its object's name)")
    a.add_argument("--params", help="the design's parameters as JSON ({document, version, parameters: [...]})")
    a.add_argument("--note")
    a.add_argument("--flat", action="store_true", help="keep the model's own axes (it's already as printed)")
    a.add_argument("--json", action="store_true")
    a.add_argument("--project", default=argparse.SUPPRESS)
    a.set_defaults(fn=cmd_variant_add)
