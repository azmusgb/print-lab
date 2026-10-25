"""One-time move of the hand-written E-001..E-004 into Stage 1A.1 records, around a new Q-001 (spec: Moving the
existing records). Known facts are kept; anything not recorded at the time stays null; the old record is kept under
`legacy` so nothing is lost."""
import copy
import json
import shutil
from pathlib import Path

from lab.adapters.bambu import extract_gcode, slice_estimate
from lab.jobs import sha256
from lab.loop.plate import layer_time_profile, median_layer_time, plate_of
from lab.records.project import DEFAULT_BUDGET, ProjectPaths
from lab.records.schema import validate
from lab.records.store import atomic_write_json, read_json

FIXTURES = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "hex"
SOURCES = ["hexagon_v56_X2D_0.6nozzle.3mf", "hexagon_v57_X2D_0.4nozzle.3mf", "hexagon_v58_X2D_0.6nozzle.3mf"]
QUESTION = "What causes the bands on v58's face?"
OLD_STATUS = {"answered": "answered", "printing": "printing", "planned": "built", "sliced": "built"}


def _sources(paths: ProjectPaths) -> list[dict]:
    paths.sources.mkdir(parents=True, exist_ok=True)
    known = {}
    inv = paths.root / "history" / "inventory.json"
    if inv.exists():
        known = {a["path"]: a["sha256"] for a in json.loads(inv.read_text())}
    out = []
    for name in SOURCES:
        dst = paths.sources / name
        if not dst.exists():
            shutil.copy2(FIXTURES / name, dst)
        h = sha256(dst)
        if name in known and known[name] != h:
            raise ValueError(f"{name} doesn't match the history inventory's fingerprint; the copy may not be the file "
                             "the history recorded. Check it before migrating.")
        out.append({"path": f"sources/{name}", "sha256": h, "source": "migration_fixture"})
    atomic_write_json(paths.sources / "sources.json", out)  # a list, not a record
    return out


def _build(paths, bid, run, inputs) -> dict:
    art = paths.prints / run["file"]
    sliced = paths.sliced / run["file"].replace(".3mf", ".gcode.3mf")
    b = {"id": bid, "ok": True, "at": None, "inputs": inputs, "job": run.get("slice_job"),
         "artifact": f"prints/{run['file']}", "artifact_sha256": run.get("artifact_sha256"), "sliced": None,
         "estimate": None, "plate": plate_of(art) if art.exists() else None, "measured": None}
    if sliced.exists():
        minutes, g = slice_estimate(sliced)
        prof = layer_time_profile(extract_gcode(sliced, 1))
        b.update(sliced=f"prints/sliced/{sliced.name}", estimate={"minutes": minutes, "g": g},
                 measured={"layer_time_median_s": median_layer_time(prof), "layer_time_profile": prof})
    return b


def _verdict(order, strength, note, runs, about=None):
    return {"kind": "ranking", "print_runs": runs, "order": order, "strength": strength, "about_target": about,
            "lighting": None, "marks": [], "witness": None, "witness_override": None, "note": note, "by": "owner",
            "at": None}


def migrate_project(paths: ProjectPaths) -> list[str]:
    q_path = paths.questions / "Q-001.json"
    if q_path.exists():
        return ["already migrated"]
    old = {n: read_json(paths.experiments / f"E-00{n}.json") for n in (1, 2, 3, 4)}
    src = _sources(paths)
    inputs = {"model": {s["path"]: s["sha256"] for s in src}, "settings": src[1]["sha256"],
              "builder_version": "script (before 1A.1)"}
    report = []
    new = {}
    for n, o in old.items():
        eid = f"E-00{n}"
        e = {"schema": 1, "record_type": "experiment", "id": eid, "project": paths.name, "question": "Q-001",
             "provenance": "prospective" if n in (3, 4) else "migrated", "question_text": o["question"],
             "hypothesis": o["hypothesis"], "prediction": o["prediction"], "why_this_test": o.get("why_this_test", ""),
             "test_kind": o["test_kind"], "factor": o["factor"], "controlled": o.get("controlled", {}),
             "dependent_adjustments": o.get("dependent_adjustments", {}), "baseline": o.get("baseline", {}),
             "findings": o.get("findings", []), "judge_on": None, "expect": None, "derived_from_artifact": [],
             "derived_from_result": [], "controls": {"witness_required": False, "anchor": None},
             "reference_variants": [], "build_spec": None, "status": OLD_STATUS.get(o["status"], "built"),
             "variants": [], "builds": [], "approval": None, "print_runs": [], "owner_verdict": None,
             "superseded_verdicts": [], "anchors": [], "ai_observations": [], "comparison_validity": None,
             "prediction_outcome": None, "analysis": [], "legacy": copy.deepcopy(o)}
        runs = o["print_runs"]
        e["builds"] = [_build(paths, f"BLD-00{n}-{i + 1:02d}", r, inputs) for i, r in enumerate(runs)]
        if n == 1:
            e["variants"] = [{"id": "E-001-A", "tab": None, "factor_value": "v56"},
                             {"id": "E-001-B", "tab": None, "factor_value": "v58"}]
            e["judge_on"] = "the mid-height line"
            e["print_runs"] = [{"id": "PR-002", "build_id": "BLD-001-02", "started_at": None, "setup": None,
                                "usage": None, "failed": None, "photos": []}]
            words = runs[1]["result"]["owner_words"]
            e["owner_verdict"] = _verdict([["E-001-B"], ["E-001-A"]], None, words, ["PR-002"])
            for obs in ("v56", "v58"):
                e["ai_observations"].append({"type": "photo_reading", "variant": "E-001-A" if obs == "v56" else "E-001-B",
                                             "assessment": runs[1]["result"]["reading"][obs], "confidence": None,
                                             "confirmed": False, "at": "2026-10-24"})
        elif n == 2:
            e["variants"] = [{"id": "E-002-A", "tab": None, "factor_value": "v58 alone on the plate"}]
            e["reference_variants"] = ["E-001-B"]
            e["judge_on"] = "face smoothness"
            e["print_runs"] = [{"id": "PR-004", "build_id": "BLD-002-01", "started_at": None,
                                "setup": {"filament_dried": False, "vibration_calibration": False,
                                          "source": "owner: 'all i did was print the 3mf - thats it'"},
                                "usage": None, "failed": None, "photos": []}]
            res = runs[0]["result"]
            e["owner_verdict"] = _verdict([["E-002-A"], ["E-001-B"]], "a lot", res["owner_words"], ["PR-004"])
            m1 = new["E-001"]["builds"][1]["measured"]["layer_time_median_s"] if new["E-001"]["builds"][1]["measured"] else None
            m2 = e["builds"][0]["measured"]["layer_time_median_s"] if e["builds"][0]["measured"] else None
            e["analysis"] = [{"claim": f"plate layout (1 object, {m2} s/layer, against E-001's 2 objects, {m1} s/layer) "
                                       "may explain the difference", "provenance": "post_hoc", "at": "2026-10-24"}]
            for obs in res.get("ai_observations", []):
                e["ai_observations"].append({"type": obs["type"], "variant": "E-002-A", "assessment": obs["assessment"],
                                             "confidence": None, "confirmed": False, "at": "2026-10-24",
                                             "where": obs.get("where", "")})
        elif n == 3:
            e["variants"] = [{"id": "E-003-A", "tab": None, "factor_value": "inner walls at the outer wall's speed"}]
            e["reference_variants"] = ["E-002-A"]
            e["judge_on"] = "bands"
            e["expect"] = {"better": "E-003-A", "than": "E-002-A", "min_strength": "clearly"}
        else:
            e["variants"] = [{"id": "E-004-A", "tab": None, "factor_value": 2, "copies": 2}]
            e["reference_variants"] = ["E-002-A"]
            e["judge_on"] = "bands"
            e["expect"] = {"better": "E-002-A", "than": "E-004-A", "min_strength": "clearly"}
            sd = runs[0].get("send_dialog", {})
            e["print_runs"] = [{"id": "PR-006", "build_id": "BLD-004-01", "started_at": None,
                                "setup": {"nozzle": "0.4/0.4mm", "plate": sd.get("plate"), "filament": sd.get("filament"),
                                          "flow_dynamics_calibration": sd.get("flow_dynamics_calibration"),
                                          "auto_bed_leveling": sd.get("auto_bed_leveling"),
                                          "filament_dried": False, "vibration_calibration": False},
                                "usage": None, "failed": None, "photos": []}]
        validate(e, "experiment", paths.experiments / f"{eid}.json")
        new[eid] = e
    for eid, e in new.items():
        atomic_write_json(paths.experiments / f"{eid}.json", e)
        report.append(f"{eid}: {e['provenance']}, {len(e['builds'])} build(s), status {e['status']}")
    q = {"schema": 1, "record_type": "question", "id": "Q-001", "project": paths.name, "question": QUESTION,
         "status": "active", "autonomy_level": 2, "budget": dict(DEFAULT_BUDGET),
         "experiments": list(new), "stops": [],
         "plans": [{"id": "P-001", "after": "E-004", "if": "the two-object strips are clearly rougher",
                    "next": "one pair per plate against a minimum layer time"},
                   {"id": "P-002", "after": "E-004", "if": "no meaningful difference",
                    "next": "E-003 (inner walls at the outer wall's speed), then the matte filament profile"}]}
    validate(q, "question", q_path)
    atomic_write_json(q_path, q)  # the parent last
    report.append("Q-001: created around E-001..E-004")
    return report
