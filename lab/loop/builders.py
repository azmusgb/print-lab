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
                    adjust: dict) -> str:
    settings = project_settings(paths)
    if settings["autonomy_level"] == 0:
        raise ValueError(f"{paths.name} is at autonomy level 0 (observe only); the lab can't plan experiments.")
    f = factor_info(factor)
    for s in (source, base):
        if not (paths.root / s).exists():
            raise ValueError(f"{s} isn't in {paths.name}. Sources: "
                             f"{', '.join(sorted('sources/' + p.name for p in paths.sources.glob('*.3mf')))}")
    q_path = paths.questions / f"{q_id}.json"
    load(q_path, "question")

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
        spec = {"kind": test_kind, "source": source, "object": object, "z": [z0, z1],
                "judged": [z0 + 6, z1 - 6] if z1 - z0 >= 12 else None, "base": base, "variants": spec_variants,
                "witness": False}
        return {"schema": 1, "record_type": "experiment", "id": eid, "project": paths.name, "question": q_id,
                "provenance": "prospective", "question_text": question_text, "hypothesis": hypothesis,
                "prediction": prediction, "why_this_test": why, "test_kind": test_kind,
                "factor": {"name": factor, "values": list(values), "unit": f.get("unit", "")},
                "factor_scope": f["scope"], "dependent_adjustments": dict(adjust), "controlled": {}, "baseline": {},
                "findings": [], "judge_on": judge_on, "expect": _parse_expect(expect, ids, references),
                "derived_from_artifact": [], "derived_from_result": [],
                "controls": {"witness_required": False, "anchor": None}, "reference_variants": list(references),
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


def _meshes(paths: ProjectPaths, exp: dict) -> list[tuple[str, object, dict]]:
    from lab.adapters.threemf import load_object
    from lab.geometry.coupons import height_strip
    spec = exp["build_spec"]
    z0, z1 = spec["z"]
    cache: dict[str, object] = {}
    out = []
    for v in spec["variants"]:
        src = v.get("source") or spec["source"]
        if src not in cache:
            cache[src] = height_strip(load_object(paths.root / src, spec["object"]), z0, z1)
        own = {**(exp.get("dependent_adjustments") or {}), **v.get("settings_patch", {})}
        for k in range(v.get("copies", 1)):
            name = v["id"] if v.get("copies", 1) == 1 else f"{v['id']} ({k + 1} of {v['copies']})"
            out.append((name, cache[src].copy(), own))
    return out


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
        parts = _meshes(paths, e)
        laid = plate_layout([(n, m) for n, m, _ in parts])
        art = paths.prints / f"{paths.name}_{exp_id}_{bid}.3mf"
        owns = [own for _, _, own in parts]
        shared = all(o == owns[0] for o in owns)  # one setting for the whole plate goes into the project settings
        art_sha = write_print_3mf(paths.root / e["build_spec"]["base"], laid, art,
                                  {"experiment_id": exp_id, "build_id": bid,
                                   "variants": [v["id"] for v in e["variants"]]},
                                  settings_patch=owns[0] if shared else None,
                                  object_settings=None if shared else owns)
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
