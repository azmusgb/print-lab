"""Additive Print Lab v2 projection layered on top of page_index.build_index.

The legacy index remains authoritative for questions/experiments. This module adds
first-class RUN records and production-package summaries without changing the
print-lab-index/1 schema or placing RUN-* IDs into the raw records map (older Pi
Hub versions reject those IDs there).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from lab import runs
from lab.records.project import ProjectPaths
from lab.records.store import read_json

REQUIRED_ARTIFACTS = tuple(runs.REQUIRED_ARTIFACTS)


def _artifact_state(paths: ProjectPaths, run: dict) -> dict:
    artifacts = run.get("artifacts") or {}
    bound = sorted(k for k in artifacts if isinstance(artifacts.get(k), dict))
    missing = [k for k in REQUIRED_ARTIFACTS if k not in artifacts]
    files_missing = []
    for key in bound:
        spec = artifacts.get(key) or {}
        rel = spec.get("path")
        if not isinstance(rel, str) or not (paths.root / rel).is_file():
            files_missing.append(key)
    return {
        "bound": len(bound),
        "required": len(REQUIRED_ARTIFACTS),
        "kinds": bound,
        "missing": missing,
        "files_missing": files_missing,
        "ready": not missing and not files_missing,
    }


def _run_projection(paths: ProjectPaths, record: dict) -> dict:
    return {
        "id": record.get("id"),
        "experiment": record.get("experiment"),
        "build": record.get("build_id"),
        "status": record.get("status"),
        "printer": record.get("printer"),
        "started_at": record.get("started_at"),
        "finished_at": record.get("finished_at"),
        "estimate": record.get("estimate") or {},
        "actual": record.get("actual") or {},
        "source_run": record.get("source_run"),
        "artifacts": _artifact_state(paths, record),
        "artifact_bindings": {
            key: {"path": spec.get("path"), "sha256": spec.get("sha256")}
            for key, spec in sorted((record.get("artifacts") or {}).items())
            if isinstance(spec, dict)
        },
        "evidence_count": len(record.get("evidence") or []),
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
    }


def _runs(paths: ProjectPaths, problems: list) -> list[dict]:
    out = []
    for path in sorted(paths.runs.glob("RUN-*.json")) if paths.runs.is_dir() else []:
        try:
            out.append(_run_projection(paths, runs.load(paths, path.stem)))
        except (OSError, ValueError) as exc:
            problems.append({"file": f"runs/{path.name}", "error": str(exc)})
    return sorted(out, key=lambda r: (r.get("experiment") or "", r.get("id") or ""), reverse=True)


def _package_projection(path: Path) -> dict | None:
    manifest_file = path / "manifest.json"
    if not manifest_file.is_file():
        return None
    try:
        manifest = read_json(manifest_file)
    except (OSError, ValueError):
        return None
    checksums = path / "checksums.sha256"
    return {
        "id": manifest.get("id") or path.name,
        "path": f"production/{path.name}",
        "experiment": manifest.get("experiment"),
        "run": manifest.get("run"),
        "qualification": manifest.get("qualification"),
        "previous_reference": manifest.get("previous_reference"),
        "sealed_at": manifest.get("sealed_at"),
        "artifact_count": len(manifest.get("artifacts") or []),
        "evidence_count": len(manifest.get("evidence") or []),
        "sealed": checksums.is_file(),
    }


def _production(paths: ProjectPaths, qualification: dict) -> dict:
    packages = []
    if paths.production.is_dir():
        for path in sorted((p for p in paths.production.iterdir() if p.is_dir()), reverse=True):
            item = _package_projection(path)
            if item:
                packages.append(item)

    raw_current = qualification.get("current_package") if isinstance(qualification, dict) else None
    current_id = None
    current_path = None
    if isinstance(raw_current, dict):
        current_id = raw_current.get("id")
        current_path = raw_current.get("path")
    elif isinstance(raw_current, str):
        current_id = raw_current
        current_path = raw_current

    current = next(
        (p for p in packages if p.get("id") == current_id or p.get("path") == current_path),
        None,
    )
    if current is None and isinstance(raw_current, dict):
        current = {
            "id": raw_current.get("id"),
            "path": raw_current.get("path"),
            "experiment": raw_current.get("experiment"),
            "run": raw_current.get("run"),
            "manifest_sha256": raw_current.get("manifest_sha256"),
            "sealed": True,
        }
    return {"current": current, "packages": packages}


def _attach_runs(experiments: list[dict], projected_runs: list[dict], qualification: dict) -> None:
    by_exp: dict[str, list[dict]] = {}
    for run in projected_runs:
        by_exp.setdefault(str(run.get("experiment") or ""), []).append(run)
    current_run = qualification.get("current_run") if isinstance(qualification, dict) else None
    for exp in experiments:
        mine = by_exp.get(str(exp.get("id") or ""), [])
        exp["run_ids"] = [r["id"] for r in mine if r.get("id")]
        exp["active_run"] = next((r["id"] for r in mine if r.get("status") == "printing"), None)
        exp["qualified_run"] = current_run if any(r.get("id") == current_run for r in mine) else None


def augment_index(pdir: Path, index: dict) -> dict:
    """Return *index* enriched with additive v2 run/release projections.

    RUN records intentionally stay out of index['records'] during this bridge so
    older Pi Hub sync validators remain compatible.
    """
    paths = ProjectPaths(Path(pdir))
    problems = index.setdefault("problems", [])
    qualification = index.get("qualification") if isinstance(index.get("qualification"), dict) else {}
    projected_runs = _runs(paths, problems)
    production = _production(paths, qualification)
    experiments = index.get("experiments") if isinstance(index.get("experiments"), list) else []
    _attach_runs(experiments, projected_runs, qualification)
    index["runs"] = projected_runs
    index["production"] = production

    material = {
        "runs": projected_runs,
        "production": production,
        "qualification": qualification,
    }
    digest = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]
    index["fingerprint"] = f"{index.get('fingerprint') or ''}:v2{digest}"
    return index