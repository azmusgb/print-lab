"""First-class physical print-run records.

Experiments describe the question. Runs describe exactly what was physically sent to a printer.
Legacy experiment.print_runs remain readable during migration, but new qualification/package work
should bind to RUN-*.json records in <project>/runs/.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from lab.records.project import ProjectPaths
from lab.records.store import atomic_write_json, now, read_json, record_lock

SCHEMA = "print-lab-run/1"
RUN_RE = re.compile(r"^RUN-(\d{3,})-(\d{2,})$")
EXPERIMENT_RE = re.compile(r"^E-(\d{3,})$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
STATUSES = ("planned", "printing", "completed", "failed", "aborted", "qualified")
REQUIRED_ARTIFACTS = ("model", "process", "filament", "slice")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_relpath(value: str) -> str:
    p = Path(value)
    if p.is_absolute() or ".." in p.parts or not value.strip():
        raise ValueError(f"Artifact path must stay inside the project: {value!r}")
    return p.as_posix()


def validate_artifact(spec: dict, *, name: str = "artifact") -> dict:
    if not isinstance(spec, dict):
        raise ValueError(f"{name} must be an object with path and sha256.")
    path = spec.get("path")
    digest = spec.get("sha256")
    if not isinstance(path, str):
        raise ValueError(f"{name}.path is required.")
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        raise ValueError(f"{name}.sha256 must be a lowercase SHA-256 digest.")
    return {"path": _safe_relpath(path), "sha256": digest}


def validate(record: dict) -> dict:
    if not isinstance(record, dict):
        raise ValueError("Run record must be an object.")
    rid = record.get("id")
    eid = record.get("experiment")
    if record.get("schema") != SCHEMA or record.get("record_type") != "run":
        raise ValueError("Run record has the wrong schema or record_type.")
    m = RUN_RE.fullmatch(str(rid or ""))
    em = EXPERIMENT_RE.fullmatch(str(eid or ""))
    if not m or not em:
        raise ValueError("Run id must look like RUN-025-01 and experiment like E-025.")
    if int(m.group(1)) != int(em.group(1)):
        raise ValueError("Run id must use the experiment number it belongs to.")
    if record.get("status") not in STATUSES:
        raise ValueError(f"Run status must be one of: {', '.join(STATUSES)}")
    build_id = record.get("build_id")
    if build_id is not None and not re.fullmatch(r"BLD-\d{3,}-\d{2,}", str(build_id)):
        raise ValueError("build_id must look like BLD-025-01.")
    artifacts = record.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("Run artifacts must be an object.")
    for key, spec in artifacts.items():
        validate_artifact(spec, name=f"artifacts.{key}")
    return record


def path_for(paths: ProjectPaths, run_id: str) -> Path:
    if not RUN_RE.fullmatch(run_id):
        raise ValueError("Run id must look like RUN-025-01.")
    return paths.runs / f"{run_id}.json"


def load(paths: ProjectPaths, run_id: str) -> dict:
    p = path_for(paths, run_id)
    if not p.exists():
        raise ValueError(f"Run {run_id} does not exist.")
    return validate(read_json(p))


def for_experiment(paths: ProjectPaths, eid: str) -> list[dict]:
    if not EXPERIMENT_RE.fullmatch(eid):
        raise ValueError("Experiment id must look like E-025.")
    out = []
    for p in (sorted(paths.runs.glob("RUN-*.json")) if paths.runs.is_dir() else []):
        r = validate(read_json(p))
        if r.get("experiment") == eid:
            out.append(r)
    return out


def latest_for_experiment(paths: ProjectPaths, eid: str) -> dict | None:
    got = for_experiment(paths, eid)
    return got[-1] if got else None


def _next_id(paths: ProjectPaths, eid: str) -> str:
    n = int(EXPERIMENT_RE.fullmatch(eid).group(1))
    prefix = f"RUN-{n:03d}-"
    nums = []
    for p in (paths.runs.glob(f"{prefix}*.json") if paths.runs.is_dir() else []):
        m = RUN_RE.fullmatch(p.stem)
        if m:
            nums.append(int(m.group(2)))
    return f"RUN-{n:03d}-{(max(nums) + 1 if nums else 1):02d}"


def create(paths: ProjectPaths, eid: str, *, build_id: str | None, artifacts: dict,
           estimate: dict | None = None, printer: str | None = None,
           status: str = "planned", started_at: str | None = None,
           source_run: str | None = None) -> dict:
    if not EXPERIMENT_RE.fullmatch(eid):
        raise ValueError("Experiment id must look like E-025.")
    if status not in STATUSES:
        raise ValueError(f"Run status must be one of: {', '.join(STATUSES)}")
    checked_artifacts = {k: validate_artifact(v, name=f"artifacts.{k}") for k, v in artifacts.items()}
    paths.runs.mkdir(parents=True, exist_ok=True)
    with record_lock(paths.locks, "run-id-allocation", f"create run for {eid}"):
        rid = _next_id(paths, eid)
        record = {
            "schema": SCHEMA,
            "record_type": "run",
            "id": rid,
            "experiment": eid,
            "build_id": build_id,
            "status": status,
            "printer": printer,
            "started_at": started_at,
            "finished_at": None,
            "estimate": estimate or {},
            "actual": {},
            "artifacts": checked_artifacts,
            "evidence": [],
            "source_run": source_run,
            "created_at": now(),
            "updated_at": now(),
        }
        validate(record)
        atomic_write_json(path_for(paths, rid), record)
    return record


def update(paths: ProjectPaths, run_id: str, **changes) -> dict:
    allowed = {"status", "printer", "started_at", "finished_at", "estimate", "actual", "artifacts", "evidence"}
    unknown = set(changes) - allowed
    if unknown:
        raise ValueError("Unknown run fields: " + ", ".join(sorted(unknown)))
    with record_lock(paths.locks, run_id, f"update {run_id}"):
        record = load(paths, run_id)
        if "artifacts" in changes:
            changes["artifacts"] = {k: validate_artifact(v, name=f"artifacts.{k}")
                                    for k, v in changes["artifacts"].items()}
        record.update(changes)
        record["updated_at"] = now()
        validate(record)
        atomic_write_json(path_for(paths, run_id), record)
        return record


def missing_required_artifacts(run: dict) -> list[str]:
    artifacts = run.get("artifacts") or {}
    return [key for key in REQUIRED_ARTIFACTS if key not in artifacts]


def artifact_problems(paths: ProjectPaths, run: dict, *, require_all: bool = True) -> list[dict]:
    """Verify run-bound files exist and still match the recorded SHA-256 values."""
    problems = []
    artifacts = run.get("artifacts") or {}
    if require_all:
        for key in missing_required_artifacts(run):
            problems.append({"code": "missing_artifact", "artifact": key,
                             "message": f"Run is missing required artifact {key}."})
    for key, spec in artifacts.items():
        checked = validate_artifact(spec, name=f"artifacts.{key}")
        path = paths.root / checked["path"]
        if not path.is_file():
            problems.append({"code": "artifact_file_missing", "artifact": key,
                             "message": f"Artifact file is missing: {checked['path']}"})
            continue
        actual = _sha256(path)
        if actual != checked["sha256"]:
            problems.append({"code": "artifact_hash_mismatch", "artifact": key,
                             "message": f"Artifact {key} changed: {checked['path']} expected {checked['sha256']} but found {actual}."})
    return problems
