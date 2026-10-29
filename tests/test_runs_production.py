"""First-class runs and immutable production-package sealing."""
import hashlib
import json

import pytest

from lab import production, qualification, runs
from loop_fixtures import make_project, minimal_experiment, minimal_question, started


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifacts(paths):
    files = {
        "model": paths.sources / "part.3mf",
        "process": paths.presets / "process.json",
        "filament": paths.presets / "filament.json",
        "slice": paths.sliced / "part.gcode.3mf",
    }
    for key, path in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((key + "-exact-bytes").encode())
    return {key: {"path": path.relative_to(paths.root).as_posix(), "sha256": _sha(path)}
            for key, path in files.items()}


def _observation():
    return {"id": "OBS-0001", "revisions": [{"rev": 1, "subject": {"variant": "E-023-A", "group": None},
            "outcomes": {}, "source": {"kind": "owner"}, "viewing": {"light": "installed"}}]}


def _qualified_project(tmp_path, monkeypatch):
    q = minimal_question("Q-009", experiments=("E-019", "E-023"))
    ref = started(minimal_experiment("E-019", "Q-009"))
    ref["test_kind"] = "full_part"
    ref["status"] = "answered"
    cur = started(minimal_experiment("E-023", "Q-009"))
    cur["test_kind"] = "full_part"
    cur["status"] = "answered"
    cur["reference_variants"] = ["E-019-A"]
    cur["owner_verdict"] = {"kind": "acceptance", "good_enough": True, "blocking_defects": [],
                            "print_runs": ["RUN-023-01"], "lighting": "installed", "note": "good",
                            "by": "owner", "at": "2026-10-29T12:00:00+00:00"}
    paths = make_project(tmp_path, q, [ref, cur])
    monkeypatch.setattr(qualification.obs, "for_experiment", lambda p, eid: [_observation()])
    monkeypatch.setattr(qualification, "comparison_validity", lambda *a, **k: {"status": "valid", "reasons": []})
    return paths


def test_run_ids_are_per_experiment_and_records_are_separate(tmp_path):
    paths = make_project(tmp_path, minimal_question(), [minimal_experiment()])
    artifacts = _artifacts(paths)
    a = runs.create(paths, "E-009", build_id=None, artifacts=artifacts)
    b = runs.create(paths, "E-009", build_id=None, artifacts=artifacts)
    assert a["id"] == "RUN-009-01"
    assert b["id"] == "RUN-009-02"
    assert runs.latest_for_experiment(paths, "E-009")["id"] == "RUN-009-02"
    assert (paths.runs / "RUN-009-01.json").is_file()


def test_seal_refuses_artifact_hash_drift(tmp_path):
    paths = make_project(tmp_path, minimal_question(), [minimal_experiment()])
    artifacts = _artifacts(paths)
    run = runs.create(paths, "E-009", build_id=None, artifacts=artifacts, status="completed")
    (paths.root / artifacts["model"]["path"]).write_bytes(b"changed-after-run")
    qual = {"id": "QUAL-0001", "experiment": "E-009", "run": run["id"], "decision": "qualified",
            "previous_reference": "E-008", "at": "2026-10-29T20:00:00+00:00"}
    with pytest.raises(ValueError, match="changed"):
        production.seal(paths, qual, minimal_experiment(), run)
    assert not list(paths.production.glob("E-009-RUN-009-01-qualified-*"))


def test_qualification_of_first_class_run_seals_and_advances_reference(tmp_path, monkeypatch):
    paths = _qualified_project(tmp_path, monkeypatch)
    artifacts = _artifacts(paths)
    run = runs.create(paths, "E-023", build_id="BLD-023-01", artifacts=artifacts,
                      estimate={"minutes": 761.15, "g": 363.71, "layers": 660},
                      printer="Bambu Lab X2D", status="completed",
                      started_at="2026-10-29T20:24:54+00:00")
    payload = {"decision": "qualified", "reason": "Clean full part.", "reference_experiment": "E-019",
               "run_seen": run["id"], "build_seen": "BLD-023-01", "evidence_reviewed": True}
    rec = qualification.apply_request(paths, "E-023", payload)
    state = qualification.summary(paths)

    assert rec["run"] == "RUN-023-01"
    assert rec["production_package"]["run"] == "RUN-023-01"
    assert state["current_reference"] == "E-023"
    assert state["current_run"] == "RUN-023-01"
    assert state["current_package"]["id"] == rec["production_package"]["id"]

    package = paths.root / rec["production_package"]["path"]
    assert (package / "qualification.json").is_file()
    assert (package / "experiment.json").is_file()
    assert (package / "run.json").is_file()
    assert (package / "manifest.json").is_file()
    assert (package / "checksums.sha256").is_file()
    manifest = json.loads((package / "manifest.json").read_text())
    assert {x["kind"] for x in manifest["artifacts"]} >= {"model", "process", "filament", "slice"}


def test_gate_reports_missing_package_artifacts(tmp_path, monkeypatch):
    paths = _qualified_project(tmp_path, monkeypatch)
    run = runs.create(paths, "E-023", build_id="BLD-023-01", artifacts={}, status="completed")
    gate = qualification.gate(paths, "E-023", "E-019", evidence_reviewed=True)
    assert gate["run"] == run["id"]
    assert not gate["package_ready"]
    assert "package_artifacts_missing" in {p["code"] for p in gate["problems"]}
