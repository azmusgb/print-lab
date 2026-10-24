"""Planning an experiment and building it: the build spec, the print file, the slice and what it measured (spec:
Commands, Test builders and the plate)."""
import hashlib
import json
import re
from pathlib import Path

from lab.adapters.bambu import extract_gcode, slice_estimate, slice_with_job
from lab.jobs import LabToolError, sha256
from lab.loop.outcome import _factors
from lab.loop.plate import layer_time_profile, median_layer_time, plate_of
from lab.records.project import ProjectPaths, project_settings
from lab.records.schema import load, validate
from lab.records.store import atomic_write_json, create_record, next_local_id, now, record_lock

BUILDER_VERSION = "1a1.1"
_HERE = Path(__file__).resolve().parent
_BUILDER_FILES = [_HERE / "builders.py", _HERE / "witness.py", _HERE / "tabs.py",
                  _HERE.parent / "adapters" / "threemf.py", _HERE.parent / "geometry" / "coupons.py"]
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def factor_info(name: str) -> dict:
    if "," in name or " " in name.strip():
        raise ValueError("An experiment changes one factor. Plan one experiment per factor.")
    f = _factors().get(name)
    if not f:
        raise ValueError(f"'{name}' isn't on the list of factors (lab/factors.json): {', '.join(_factors())}. "
                         "A new factor is added there by a reviewed change.")
    return f


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def builder_fingerprint() -> str:
    h = hashlib.sha256()
    for f in _BUILDER_FILES:
        if f.exists():
            h.update(f.name.encode() + b"\0" + f.read_bytes())
    return h.hexdigest()


def _tool_version(fn) -> str | None:
    try:
        return fn()[1]
    except (FileNotFoundError, OSError):
        return None


def input_fingerprints(paths: ProjectPaths, exp: dict, tools: bool = True) -> dict:
    """Everything a build depends on: the model and settings files, the build spec, the builder code and the tools."""
    from lab.adapters.bambu import bambu_binary
    from lab.adapters.openscad import openscad_binary
    spec = exp["build_spec"]
    sources = {spec["source"]} | {v["source"] for v in spec["variants"] if v.get("source")}
    fp = {"model": {s: sha256(paths.root / s) for s in sorted(sources)},
          "settings": sha256(paths.root / spec["base"]),
          "build_spec_sha256": hashlib.sha256(_canonical({"build_spec": spec, "factor": exp["factor"],
                                                          "dependent_adjustments": exp.get("dependent_adjustments")
                                                          or {}}).encode()).hexdigest(),
          "builder_version": BUILDER_VERSION, "builder_fingerprint": builder_fingerprint()}
    if tools:
        fp["openscad"] = _tool_version(openscad_binary)
        fp["bambu_studio"] = _tool_version(bambu_binary)
    return fp


def _parse_expect(text: str, ids: dict[str, str], refs: list[str]) -> dict | None:
    """'B>A:clearly' -> better/than/min_strength; 'A=B' -> same. Letters name this experiment's variants."""
    def vid(t):
        t = t.strip()
        if t in ids:
            return ids[t]
        if t in refs:
            return t
        raise ValueError(f"--expect names '{t}'; use this experiment's letters ({', '.join(ids)}) or a --reference.")
    if not text:
        return None
    if "=" in text:
        return {"same": [vid(t) for t in text.split("=")]}
    pair, _, strength = text.partition(":")
    b, _, a = pair.partition(">")
    return {"better": vid(b), "than": vid(a), "min_strength": strength or "clearly"}


def plan_experiment(paths: ProjectPaths, q_id: str, *, factor: str, values: list[str], expect: str, judge_on: str,
                    test_kind: str, source: str, object: str, z: tuple[float, float], base: str,
                    question_text: str, hypothesis: str, prediction: str, why: str, references: list[str],
                    adjust: dict, anchor: str | None = None, stepped: bool = False, tabs: bool | None = None,
                    judged: tuple[float, float] | None = None) -> str:
    settings = project_settings(paths)
    if settings["autonomy_level"] == 0:
        raise ValueError(f"{paths.name} is at autonomy level 0 (observe only); the lab can't plan experiments.")
    f = factor_info(factor)
    if f.get("execution_scope") != "per_object_verified" and len(set(values)) > 1:
        raise ValueError(f"{factor} is plate-wide: Bambu Studio applies one value to the whole plate (per-object "
                         "overrides of it are ignored), so two values can't share a plate. Plan one value per "
                         "experiment and compare against the other plate with --reference.")
    for s in (source, base):
        if not (paths.root / s).exists():
            raise ValueError(f"{s} isn't in {paths.name}. Sources: "
                             f"{', '.join(sorted('sources/' + p.name for p in paths.sources.glob('*.3mf')))}")
    q_path = paths.questions / f"{q_id}.json"
    load(q_path, "question")
    anchor_spec = _anchor_spec(paths, anchor) if anchor else None
    cross_plate = bool(references or anchor)
    from lab.loop import capabilities
    notes = []
    if stepped and (f["kind"] != "setting" or f.get("execution_scope") != "per_object_verified"):
        raise ValueError(f"{factor} can't be stepped up a strip: only per-object, verified settings can (inner and "
                         "outer wall speed).")
    cap = capabilities.height_range_capability(factor)
    if stepped and not capabilities.capability_passed(cap):
        notes.append(f"stepped settings fell back to separate strips: {cap} hasn't passed for this Bambu Studio")
        stepped = False
    if tabs is None:
        tabs = capabilities.capability_passed(capabilities.TAB_ISOLATION)

    def make(eid: str) -> dict:
        n = int(eid.split("-")[1])
        ids = {LETTERS[i]: f"{eid}-{LETTERS[i]}" for i in range(len(values))}
        variants, spec_variants = [], []
        for i, val in enumerate(values):
            vid = ids[LETTERS[i]]
            sv = {"id": vid, "tab": f"{n}{LETTERS[i]}", "settings_patch": {}, "copies": 1}
            if f["kind"] == "setting":
                sv["settings_patch"] = {f["settings_key"]: val}
            elif f["kind"] == "plate":
                sv["copies"] = int(val)
            elif f["kind"] in ("model_version", "filament_profile"):
                sv["source"] = val
            variants.append({"id": vid, "tab": sv["tab"], "factor_value": val, "copies": sv["copies"]})
            spec_variants.append(sv)
        z0, z1 = float(z[0]), float(z[1])
        if cross_plate:
            variants.append({"id": "WITNESS-01", "tab": None, "role": "control"})
        if anchor:
            variants.append({"id": f"{eid}-ANCHOR", "tab": None, "role": "anchor", "same_as": anchor})
        spec = {"kind": test_kind, "source": source, "object": object, "z": [z0, z1],
                "judged": list(judged) if judged else [z0 + 6, z1 - 6] if z1 - z0 >= 12 else None, "base": base,
                "variants": spec_variants,
                "witness": cross_plate, "anchor": anchor_spec, "tabs": bool(tabs), "notes": notes}
        if stepped:
            h, k = (z1 - z0) / len(values), f["settings_key"]
            spec["stepped"] = {"key": k, "bands": [[round(i * h, 3), round((i + 1) * h, 3), val]
                                                   for i, val in enumerate(values)], "twin_reversed": True}
        return {"schema": 1, "record_type": "experiment", "id": eid, "project": paths.name, "question": q_id,
                "provenance": "prospective", "question_text": question_text, "hypothesis": hypothesis,
                "prediction": prediction, "why_this_test": why, "test_kind": test_kind,
                "factor": {"name": factor, "values": list(values), "unit": f.get("unit", "")},
                "factor_scope": f["scope"], "dependent_adjustments": dict(adjust), "controlled": {}, "baseline": {},
                "findings": [], "judge_on": judge_on, "expect": _parse_expect(expect, ids, references),
                "derived_from_artifact": [], "derived_from_result": [],
                "controls": {"witness_required": cross_plate, "anchor": anchor}, "reference_variants": list(references),
                "build_spec": spec, "status": "planned", "variants": variants, "builds": [], "approval": None,
                "print_runs": [], "owner_verdict": None, "superseded_verdicts": [], "anchors": [],
                "ai_observations": [], "comparison_validity": None, "prediction_outcome": None, "analysis": []}

    eid, e_path = create_record(paths.locks, paths.experiments, "E", make,
                                validate=lambda r: validate(r, "experiment", paths.experiments / f"{r['id']}.json"))
    with record_lock(paths.locks, q_id, f"lab exp plan {q_id}"):  # the parent last
        q = load(q_path, "question")
        q["experiments"].append(eid)
        atomic_write_json(q_path, validate(q, "question", q_path))
    return eid


def _anchor_spec(paths: ProjectPaths, same_as: str) -> dict:
    """What it takes to print an earlier variant again exactly: its source, cut, settings and spot on the plate."""
    from lab.loop.outcome import printed_build
    oid = same_as.rsplit("-", 1)[0]
    p = paths.experiments / f"{oid}.json"
    if not p.exists():
        raise ValueError(f"The anchor {same_as} names {oid}, which isn't in {paths.name}.")
    orig = load(p, "experiment")
    spec, build = orig.get("build_spec"), printed_build(orig)
    if not spec or not build:
        raise ValueError(f"{same_as} can't be an anchor: {oid} " + ("was made before Stage 1A.1 (no build spec)"
                                                                     if not spec else "was never printed") + ".")
    sv = next((v for v in spec["variants"] if v["id"] == same_as), None)
    if not sv:
        raise ValueError(f"{same_as} isn't a variant of {oid}.")
    names = (build.get("plate") or {}).get("objects") or []
    places = (build.get("plate") or {}).get("placements") or []
    placement = next((pl for n, pl in zip(names, places) if n == same_as or n.startswith(same_as + " (")), None)
    src = sv.get("source") or spec["source"]
    return {"same_as": same_as, "source": src, "object": spec["object"], "z": spec["z"], "base": spec["base"],
            "settings_patch": {**(orig.get("dependent_adjustments") or {}), **sv.get("settings_patch", {})},
            "placement": placement, "build_id": build["id"],
            "inputs": {"model": sha256(paths.root / src), "settings": sha256(paths.root / spec["base"])}}


def _meshes(paths: ProjectPaths, exp: dict) -> list[tuple[str, object, dict]]:
    from lab.adapters.threemf import load_object
    from lab.geometry.coupons import height_strip
    spec = exp["build_spec"]
    a = spec.get("anchor")
    if a:
        now_in = {"model": sha256(paths.root / a["source"]), "settings": sha256(paths.root / a["base"])}
        if now_in != a["inputs"]:
            raise ValueError(f"The anchor {a['same_as']} can't be printed as it was: its "
                             + ", ".join(k for k in now_in if now_in[k] != a["inputs"][k])
                             + " changed since it was planned.")
    z0, z1 = spec["z"]
    cache: dict[str, object] = {}
    out = []
    if spec.get("tabs"):
        from lab.loop import capabilities
        if not capabilities.capability_passed(capabilities.TAB_ISOLATION):
            raise ValueError("Tabs were planned, but CAP-TAB-ISOLATION hasn't passed for this Bambu Studio; run "
                             "`lab capability run CAP-TAB-ISOLATION` or plan without tabs.")
    n = exp["id"].split("-")[1].lstrip("0")

    def tabbed(mesh, text):
        if not spec.get("tabs"):
            return mesh
        from lab.loop.tabs import attach_tab
        return attach_tab(mesh, text, paths.jobs)
    if spec.get("stepped"):
        strip = height_strip(load_object(paths.root / spec["source"], spec["object"]), z0, z1)
        own = dict(exp.get("dependent_adjustments") or {})
        out = [("STEP-1", tabbed(strip.copy(), f"{n}S1"), own), ("STEP-2", tabbed(strip.copy(), f"{n}S2"), own)]
        spec_variants = []
    else:
        spec_variants = spec["variants"]
    for v in spec_variants:
        src = v.get("source") or spec["source"]
        if src not in cache:
            cache[src] = height_strip(load_object(paths.root / src, spec["object"]), z0, z1)
        own = {**(exp.get("dependent_adjustments") or {}), **v.get("settings_patch", {})}
        for k in range(v.get("copies", 1)):
            name = v["id"] if v.get("copies", 1) == 1 else f"{v['id']} ({k + 1} of {v['copies']})"
            out.append((name, tabbed(cache[src].copy(), v.get("tab") or name), own))
    a = spec.get("anchor")
    if a:
        anchor = height_strip(load_object(paths.root / a["source"], a["object"]), *a["z"])
        out.insert(0, (f"{exp['id']}-ANCHOR", anchor, dict(a["settings_patch"])))
    return out


def _lay_out(exp: dict, parts: list[tuple[str, object, dict]], base_settings: dict) -> list:
    """The row of pieces; an anchor at its original spot; the witness at least 25 mm beyond the row."""
    from lab.geometry.coupons import BRIM, PLATE, plate_layout
    from lab.loop.witness import MIN_GAP_MM, WITNESS_VERSION, witness_wall
    spec = exp["build_spec"]
    laid = plate_layout([(n, m) for n, m, _ in parts])
    a = spec.get("anchor")
    if a and a.get("placement"):
        (ax, ay), (cx, cy) = a["placement"], laid[0][2]
        laid = [(n, m, (round(x + ax - cx, 3), round(y + ay - cy, 3))) for n, m, (x, y) in laid]
        for n, m, (x, y) in laid:
            if x - m.extents[0] / 2 < BRIM or x + m.extents[0] / 2 > PLATE - BRIM:
                raise ValueError(f"With the anchor at its original spot, {n} falls off the plate; plan fewer pieces.")
    if spec.get("witness"):
        raw = base_settings.get("outer_wall_line_width") or "0.42"
        lw = float(str(raw[0] if isinstance(raw, list) else raw).rstrip("%") or 0.42)
        w = witness_wall(spec["z"][1] - spec["z"][0], lw if lw < 2 else 0.42)
        edge = max(x + m.extents[0] / 2 for _, m, (x, _) in laid)
        wx = edge + MIN_GAP_MM + w.extents[0] / 2
        if wx + w.extents[0] / 2 > PLATE - BRIM:
            raise ValueError(f"No room for the witness wall {WITNESS_VERSION} at least {MIN_GAP_MM:g} mm from the "
                             "pieces; plan fewer pieces on the plate.")
        laid.append((WITNESS_VERSION, w, (round(wx, 3), PLATE / 2)))
    return laid


def render_plate(paths: ProjectPaths, e: dict, bid: str, art: Path, mirror: bool) -> str:
    """Write the experiment's print file (no slicing). Returns its SHA-256."""
    from lab.adapters.bambu import read_settings
    from lab.adapters.threemf import write_print_3mf
    parts = _meshes(paths, e)
    if mirror:
        parts = parts[::-1]  # a repeat print mirrors the placements (A left, B right; then B left, A right)
    base_settings = read_settings(paths.root / e["build_spec"]["base"]) or {}
    laid = _lay_out(e, parts, base_settings)
    if len(laid) > len(parts):
        parts = parts + [(laid[-1][0], laid[-1][1], {})]
    owns = [own for _, _, own in parts]
    shared = all(o == owns[0] for o in owns)  # one setting for the whole plate goes into the project settings
    st = e["build_spec"].get("stepped")
    ranges = None
    if st:
        bands = [(b0, b1, {st["key"]: val}) for b0, b1, val in st["bands"]]
        rev = [(b0, b1, {st["key"]: val}) for (b0, b1, _), (_, _, val) in zip(st["bands"], reversed(st["bands"]))]
        ranges = [bands if n == "STEP-1" else rev if n == "STEP-2" else [] for n, _, _ in laid]
    return write_print_3mf(paths.root / e["build_spec"]["base"], laid, art,
                           {"experiment_id": e["id"], "build_id": bid, "variants": [v["id"] for v in e["variants"]]},
                           settings_patch=owns[0] if shared else None, object_settings=None if shared else owns,
                           height_ranges=ranges)


def same_output(paths: ProjectPaths, e: dict, build: dict) -> bool:
    """Would today's builder write the same print file? (Both placements are tried: a repeat mirrors.)"""
    import tempfile
    from lab.adapters.threemf import content_sha256
    have = content_sha256(paths.root / build["artifact"])
    with tempfile.TemporaryDirectory() as d:
        for mirror in (False, True):
            out = Path(d) / f"{mirror}.3mf"
            render_plate(paths, e, build["id"], out, mirror)
            if content_sha256(out) == have:
                return True
    return False


def build_experiment(paths: ProjectPaths, exp_id: str, *, replace: bool, slicer=slice_with_job) -> dict:
    """Build and slice the experiment's plate. Unchanged inputs: the existing build, nothing written."""
    from lab.adapters.threemf import write_print_3mf
    from lab.geometry.coupons import plate_layout
    with record_lock(paths.locks, exp_id, f"lab exp build {exp_id}"):
        e_path = paths.experiments / f"{exp_id}.json"
        e = load(e_path, "experiment")
        if e["status"] in ("printing", "answered", "abandoned"):
            raise ValueError(f"{exp_id} is {e['status']}; it can't be rebuilt.")
        if not e.get("build_spec"):
            raise ValueError(f"{exp_id} has no build spec (it was made before Stage 1A.1); plan a new experiment.")
        fp = input_fingerprints(paths, e)
        last = e["builds"][-1] if e["builds"] else None
        if last and last["ok"] and last.get("inputs") == fp:
            return last
        if last and last["ok"] and not replace:
            raise ValueError(f"{exp_id} changed since {last['id']} was built (" + ", ".join(
                k for k in fp if (last.get("inputs") or {}).get(k) != fp[k]) + "). Use --replace to build it again; "
                "the old build is kept.")
        bid = next_local_id(e, "builds", f"BLD-{exp_id[2:]}")
        printed = {r.get("build_id") for r in e.get("print_runs") or []}
        mirror = sum(1 for b in e["builds"] if b["ok"] and b["id"] in printed) % 2 == 1
        art = paths.prints / f"{paths.name}_{exp_id}_{bid}.3mf"
        art_sha = render_plate(paths, e, bid, art, mirror)
        build = {"id": bid, "ok": False, "at": now(), "inputs": fp, "job": None, "artifact": str(art.relative_to(paths.root)),
                 "artifact_sha256": art_sha, "sliced": None, "estimate": None, "plate": plate_of(art),
                 "measured": None, "error": None}
        try:
            sliced, job = slicer(art, paths.sliced, 1, paths.jobs)
        except LabToolError as err:
            build.update(job=err.job.id, error=str(err))
            e["builds"].append(build)
            e["status"] = "build_failed"
            atomic_write_json(e_path, validate(e, "experiment", e_path))
            raise
        minutes, g = slice_estimate(sliced)
        prof = layer_time_profile(extract_gcode(sliced, 1))
        build.update(ok=True, job=job.id, sliced=str(Path(sliced).resolve().relative_to(paths.root.resolve())),
                     estimate={"minutes": minutes, "g": g},
                     measured={"layer_time_median_s": median_layer_time(prof), "layer_time_profile": prof})
        man_path = paths.prints / "manifest.json"
        man = json.loads(man_path.read_text()) if man_path.exists() else []
        man.append({"experiment_id": exp_id, "build_id": bid, "file": art.name, "artifact_sha256": art_sha})
        atomic_write_json(man_path, man)
        e["builds"].append(build)
        e["status"] = "built"
        e["approval"] = None  # an approval belongs to one build
        atomic_write_json(e_path, validate(e, "experiment", e_path))  # the experiment last
        return build


JUDGED_HALF_MM = 2.0
MARGINS_MM = (6.0, 8.0, 10.0, 12.0)
EDGE_TOLERANCE = 0.25


def _real_measure(paths: ProjectPaths, source: str, object: str, base: str):
    import tempfile
    from lab.adapters.threemf import load_object, write_print_3mf
    from lab.geometry.coupons import height_strip, plate_layout
    mesh = load_object(paths.root / source, object)

    def measure(z0: float, z1: float):
        with tempfile.TemporaryDirectory() as d:
            art = Path(d) / "size.3mf"
            write_print_3mf(paths.root / base, plate_layout([("size", height_strip(mesh, z0, z1))]), art,
                            {"sizing": [z0, z1]})
            sliced, _ = slice_with_job(art, Path(d) / "sliced", 1, Path(d) / "jobs")
            minutes, _ = slice_estimate(sliced)
            return minutes, layer_time_profile(extract_gcode(sliced, 1))
    return measure


def size_strip(paths: ProjectPaths, source: str, object: str, around_z: float, target_minutes: float, base: str,
               min_margin_mm: float = 6.0, measure=None) -> tuple[float, float]:
    """The smallest representative strip around a height that fits the time. Representative first: the judged band
    (around_z ± 2 mm) must show no cut-edge effect (its first and last 3 layers within 25 % of its median layer
    time). Never falls back to a strip that isn't representative."""
    import statistics
    measure = measure or _real_measure(paths, source, object, base)
    smallest = None
    for m in [x for x in MARGINS_MM if x >= min_margin_mm]:
        z0, z1 = around_z - JUDGED_HALF_MM - m, around_z + JUDGED_HALF_MM + m
        minutes, prof = measure(z0, z1)
        band = [t for z, t in prof if m <= z <= m + 2 * JUDGED_HALF_MM]
        if len(band) < 7:
            continue
        med = statistics.median(band)
        edges = band[:3] + band[-3:]
        if any(abs(t - med) > EDGE_TOLERANCE * med for t in edges):
            continue  # the cut still reaches the judged band: a bigger margin
        if smallest is None:
            smallest = (minutes, m)
        if minutes <= target_minutes:
            return (round(z0, 2), round(z1, 2))
    if smallest:
        raise ValueError(f"No representative strip fits {target_minutes:g} min; the smallest is {smallest[0]:g} min "
                         f"(margin {smallest[1]:g} mm). Raise the budget or test a narrower question.")
    raise ValueError(f"No representative strip around {around_z:g} mm: the cut edges still reach the judged band at a "
                     f"{MARGINS_MM[-1]:g} mm margin. Test a full part instead, or a different height.")
