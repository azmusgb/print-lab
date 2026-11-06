"""The gate: every candidate a family makes is built, measured and sliced before anyone looks at it.

For each (params, seed): 1. validity (one valid solid, closed when meshed); 2. the project's design constraints;
3. `lab inspect`'s checks on the upright mesh; then the files are written, and 4. it's sliced with the base 3MF's
settings, which gives 5. the risk bands (heights where sparse infill prints) and the cost (minutes, grams).

A candidate that fails 1, a `block` constraint, or a blocking check is dropped with its reasons and no files. One that
passes is written to projects/<p>/designs/<family>/<id>/: model.step, model.stl, params.json, render.svg, plate.3mf,
plate.gcode.3mf and gate.json. A slice that fails is recorded in gate.json; the candidate stays, unsliced.

Each `make` run is recorded in designs/runs/<run>.json, rewritten after every candidate, so a run that stops partway
still says what it finished."""
from dataclasses import asdict
from pathlib import Path

from lab.design import constraints as C
from lab.design.family import design_id, resolve
from lab.records.project import ProjectPaths
from lab.records.store import atomic_write_json, now
from lab.variant import PLATE_CENTRE, registered_base


def designs_dir(paths: ProjectPaths) -> Path:
    return paths.root / "designs"


def _nozzle(settings: dict | None) -> float:
    nd = (settings or {}).get("nozzle_diameter", ["0.4"])
    return float(nd[0] if isinstance(nd, list) else nd)


def evaluate(paths: ProjectPaths, family, params: dict[str, float], seed: int, base: tuple[str, Path],
             do_slice: bool = True) -> dict:
    """Gate one candidate; returns its gate record (also written as gate.json when it passes)."""
    from build123d import export_step, export_stl

    from lab.adapters.bambu import extract_gcode, read_settings, slice_estimate, slice_with_job
    from lab.adapters.threemf import write_print_3mf
    from lab.analysis.gcode import feature_bands
    from lab.checks import run_checks
    from lab.jobs import LabToolError

    base_rel, base_path = base
    params = resolve(family.PARAMS, params)
    did = design_id(family.NAME, family.VERSION, params, seed)
    rec: dict = {"id": did, "family": family.NAME, "version": family.VERSION, "seed": seed, "params": params,
                 "base": base_rel, "made": now(), "dropped": [], "warnings": []}
    settings = read_settings(base_path)

    try:
        part = family.build(params, seed)
    except Exception as e:  # a generator that can't build this point is a dropped candidate, not a crashed run
        rec["dropped"].append(f"build failed: {e}")
        return rec
    mesh = C.part_mesh(part)
    rec["validity"] = {"valid": bool(part.is_valid), "solids": len(part.solids()), "shells": len(part.shells()),
                       "closed": bool(mesh.is_watertight), "volume_mm3": round(float(part.volume), 2),
                       "extents_mm": [round(float(x), 3) for x in mesh.extents]}
    v = rec["validity"]
    if not (v["valid"] and v["solids"] == 1 and v["closed"]):
        rec["dropped"].append(f"not one closed valid solid: {v}")
        return rec

    results = C.check(C.load(paths.root), family, params, part, settings)
    rec["constraints"] = [asdict(r) for r in results]
    rec["dropped"] += [f"{r.id}: {r.message}" for r in results if not r.ok and r.severity == "block"]
    rec["warnings"] += [f"{r.id}: {r.message}" for r in results if not r.ok and r.severity != "block"]

    findings = run_checks(mesh, nozzle=_nozzle(settings), settings=settings, file_name=f"{did}.stl")
    rec["findings"] = [asdict(f) for f in findings]
    rec["dropped"] += [f"{f.rule}: {f.why}" for f in findings if f.severity == "blocking"]
    if rec["dropped"]:
        return rec

    out = designs_dir(paths) / family.NAME / did
    out.mkdir(parents=True, exist_ok=True)
    export_step(part, str(out / "model.step"))
    export_stl(part, str(out / "model.stl"), tolerance=0.005, angular_tolerance=0.1)
    atomic_write_json(out / "params.json", {"family": family.NAME, "version": family.VERSION, "seed": seed,
                                            "params": params})
    if hasattr(family, "render_svg"):
        (out / "render.svg").write_text(family.render_svg(params, seed))

    if do_slice:
        name = f"{family.NAME}_{did}"
        plate = out / "plate.3mf"
        write_print_3mf(base_path, [(name, mesh, PLATE_CENTRE)], plate,
                        {"made_by": "lab design make", "design": did, "base": base_rel})
        try:
            sliced, job = slice_with_job(plate, out, 1, paths.jobs)
            minutes, grams = slice_estimate(sliced)
            gcode = extract_gcode(sliced, 1)
            rec["slice"] = {"job": job.id, "minutes": minutes, "grams": grams,
                            "sparse_infill": [{"from_mm": a, "to_mm": b, "layers": n}
                                              for a, b, n in feature_bands(gcode, "Sparse infill")]}
        except LabToolError as e:
            rec["slice"] = {"error": str(e)}
    atomic_write_json(out / "gate.json", rec)
    return rec


def make(paths: ProjectPaths, family, params: dict[str, float], seeds: list[int], base: str,
         do_slice: bool = True, progress=print) -> dict:
    """Gate every seed in turn; returns the run record (designs/runs/<run>.json, rewritten as each one finishes)."""
    base_t = registered_base(paths, base)
    resolve(family.PARAMS, params)  # refuse a bad parameter before the first build, not after it
    started = now()
    run = {"run": started.replace(":", "").replace("-", "")[:15], "family": family.NAME, "version": family.VERSION,
           "params": params, "seeds": seeds, "base": base_t[0], "started": started, "candidates": []}
    path = designs_dir(paths) / "runs" / f"{run['run']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, run)
    for seed in seeds:
        rec = evaluate(paths, family, params, seed, base_t, do_slice)
        run["candidates"].append({k: rec.get(k) for k in ("id", "seed", "dropped", "warnings", "slice")})
        atomic_write_json(path, run)
        s = rec.get("slice") or {}
        progress(f"seed {seed}: {rec['id']} " + (f"dropped ({'; '.join(rec['dropped'])})" if rec["dropped"] else
                 "kept" + (f", {s['minutes']:g} min, {s['grams']:g} g" if "minutes" in s else "")
                 + (f", slice failed: {s['error']}" if "error" in s else "")))
    run["finished"] = now()
    atomic_write_json(path, run)
    run["path"] = str(path)
    return run
