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
LEGACY_RUN_RE = re.compile(r"^PR-(\d{3,})-(\d{2,})$")
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


def for_source_run(paths: ProjectPaths, source_run: str) -> dict | None:
    """The canonical run linked to one legacy PR-* attempt, if it has been migrated."""
    if not LEGACY_RUN_RE.fullmatch(str(source_run or "")):
        return None
    for p in (sorted(paths.runs.glob("RUN-*.json")) if paths.runs.is_dir() else []):
        record = validate(read_json(p))
        if record.get("source_run") == source_run:
            return record
    return None


def _next_id(paths: ProjectPaths, eid: str, source_run: str | None = None) -> str:
    n = int(EXPERIMENT_RE.fullmatch(eid).group(1))
    if source_run:
        m = LEGACY_RUN_RE.fullmatch(source_run)
        if m and int(m.group(1)) == n:
            candidate = f"RUN-{n:03d}-{int(m.group(2)):02d}"
            if not path_for(paths, candidate).exists():
                return candidate
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
        rid = _next_id(paths, eid, source_run)
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


def artifacts_from_build(paths: ProjectPaths, experiment: dict, build: dict | None) -> dict:
    """Bind only artifact identities already proven by a successful legacy build.

    `process` is the generated print 3MF after Print Lab's settings patches. `filament`
    points at the build's base Bambu project, which is the settings/profile carrier used
    by that generated plate. A multi-model build intentionally leaves `model` unbound
    until the Run schema can represent more than one source model.
    """
    if not isinstance(build, dict):
        return {}
    out = {}
    inputs = build.get("inputs") if isinstance(build.get("inputs"), dict) else {}
    models = inputs.get("model") if isinstance(inputs.get("model"), dict) else {}
    if len(models) == 1:
        rel, digest = next(iter(models.items()))
        if isinstance(rel, str) and isinstance(digest, str) and SHA256_RE.fullmatch(digest):
            out["model"] = {"path": _safe_relpath(rel), "sha256": digest}

    artifact = build.get("artifact")
    artifact_sha = build.get("artifact_sha256")
    if isinstance(artifact, str) and isinstance(artifact_sha, str) and SHA256_RE.fullmatch(artifact_sha):
        out["process"] = {"path": _safe_relpath(artifact), "sha256": artifact_sha}

    spec = experiment.get("build_spec") if isinstance(experiment.get("build_spec"), dict) else {}
    base = spec.get("base")
    settings_sha = inputs.get("settings")
    if isinstance(base, str) and isinstance(settings_sha, str) and SHA256_RE.fullmatch(settings_sha):
        out["filament"] = {"path": _safe_relpath(base), "sha256": settings_sha}

    sliced = build.get("sliced")
    if isinstance(sliced, str):
        slice_path = paths.root / _safe_relpath(sliced)
        if slice_path.is_file():
            out["slice"] = {"path": _safe_relpath(sliced), "sha256": _sha256(slice_path)}
    return out


def _legacy_status(experiment: dict, legacy: dict, *, latest: bool) -> str:
    if legacy.get("failed"):
        return "failed"
    if experiment.get("status") == "abandoned":
        return "aborted"
    usage = legacy.get("usage") if isinstance(legacy.get("usage"), dict) else None
    verdict = experiment.get("owner_verdict") if isinstance(experiment.get("owner_verdict"), dict) else {}
    judged_runs = verdict.get("print_runs") if isinstance(verdict.get("print_runs"), list) else []
    if usage or legacy.get("id") in judged_runs or experiment.get("status") == "answered":
        return "completed"
    if latest and experiment.get("status") == "printing":
        return "printing"
    return "completed"


def _legacy_actual(legacy: dict) -> dict:
    usage = legacy.get("usage") if isinstance(legacy.get("usage"), dict) else {}
    actual = {}
    if usage.get("actual_minutes") is not None:
        actual["minutes"] = usage.get("actual_minutes")
    if usage.get("actual_g") is not None:
        actual["g"] = usage.get("actual_g")
    if usage.get("usage_source") is not None:
        actual["usage_source"] = usage.get("usage_source")
    if usage.get("completion_fraction") is not None:
        actual["completion_fraction"] = usage.get("completion_fraction")
    elif isinstance(legacy.get("failed"), dict) and legacy["failed"].get("at_fraction") is not None:
        actual["completion_fraction"] = legacy["failed"].get("at_fraction")
    return actual


def reconcile_legacy_experiment(paths: ProjectPaths, experiment: dict) -> list[dict]:
    """Create/update canonical RUN records from the legacy PR attempts of one experiment.

    This is intentionally idempotent and additive: PR records remain the compatibility
    source for the established experiment loop while RUN records become the durable
    physical-execution identity used by Qualification and production sealing.
    """
    legacy_runs = experiment.get("print_runs") if isinstance(experiment.get("print_runs"), list) else []
    builds = {b.get("id"): b for b in (experiment.get("builds") or []) if isinstance(b, dict) and b.get("id")}
    out = []
    for i, legacy in enumerate(legacy_runs):
        if not isinstance(legacy, dict) or not LEGACY_RUN_RE.fullmatch(str(legacy.get("id") or "")):
            continue
        source_run = legacy["id"]
        build = builds.get(legacy.get("build_id"))
        status = _legacy_status(experiment, legacy, latest=i == len(legacy_runs) - 1)
        artifacts = artifacts_from_build(paths, experiment, build)
        estimate = (build or {}).get("estimate") or {}
        actual = _legacy_actual(legacy)
        record = for_source_run(paths, source_run)
        if record is None:
            record = create(
                paths,
                experiment["id"],
                build_id=legacy.get("build_id"),
                artifacts=artifacts,
                estimate=estimate,
                status=status,
                started_at=legacy.get("started_at"),
                source_run=source_run,
            )
            if actual:
                record = update(paths, record["id"], actual=actual)
        else:
            changes = {}
            if record.get("status") != "qualified" and record.get("status") != status:
                changes["status"] = status
            if not record.get("started_at") and legacy.get("started_at"):
                changes["started_at"] = legacy.get("started_at")
            if estimate and record.get("estimate") != estimate:
                changes["estimate"] = estimate
            merged_artifacts = {**(record.get("artifacts") or {}), **artifacts}
            if merged_artifacts != (record.get("artifacts") or {}):
                changes["artifacts"] = merged_artifacts
            if actual and record.get("actual") != actual:
                changes["actual"] = actual
            if changes:
                record = update(paths, record["id"], **changes)
        out.append(record)
    return out


def reconcile_legacy_project(paths: ProjectPaths) -> list[dict]:
    """Reconcile every readable experiment, returning non-fatal migration problems."""
    from lab.records.schema import load as load_record

    problems = []
    for path in sorted(paths.experiments.glob("E-*.json")) if paths.experiments.is_dir() else []:
        try:
            reconcile_legacy_experiment(paths, load_record(path, "experiment"))
        except (OSError, ValueError) as exc:
            problems.append({"file": f"experiments/{path.name}", "error": f"canonical run migration: {exc}"})
    return problems


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