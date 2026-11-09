"""Seal a qualified first-class Run into an immutable production package."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from lab import runs
from lab.records.project import ProjectPaths

SCHEMA = "print-lab-production-package/1"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _copy_verified(project_root: Path, tmp: Path, kind: str, spec: dict) -> dict:
    checked = runs.validate_artifact(spec, name=f"artifacts.{kind}")
    src = project_root / checked["path"]
    if not src.is_file():
        raise ValueError(f"Run artifact {kind} is missing: {checked['path']}")
    actual = _sha256(src)
    if actual != checked["sha256"]:
        raise ValueError(
            f"Run artifact {kind} changed: {checked['path']} expected {checked['sha256']} but found {actual}."
        )
    dest = tmp / "artifacts" / kind / src.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return {"kind": kind, "source": checked["path"], "path": dest.relative_to(tmp).as_posix(), "sha256": actual}


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n")


def package_name(experiment_id: str, run_id: str, at: str) -> str:
    day = datetime.fromisoformat(at.replace("Z", "+00:00")).date().isoformat()
    return f"{experiment_id}-{run_id}-qualified-{day}"


def seal(paths: ProjectPaths, qualification: dict, experiment: dict, run: dict) -> dict:
    """Verify every bound artifact and atomically publish one immutable package folder.

    A package is never overwritten. A changed artifact hash aborts before the package appears.
    """
    if qualification.get("decision") != "qualified":
        raise ValueError("Only a qualified decision can create a production package.")
    runs.validate(run)
    if run.get("experiment") != experiment.get("id") or qualification.get("experiment") != experiment.get("id"):
        raise ValueError("Qualification, experiment and run do not describe the same experiment.")
    if qualification.get("run") != run.get("id"):
        raise ValueError("Qualification is bound to a different run.")
    if run.get("status") not in ("completed", "qualified"):
        raise ValueError("Only a completed run can be sealed as production.")

    missing = runs.missing_required_artifacts(run)
    if missing:
        raise ValueError("Run is not package-ready; missing artifacts: " + ", ".join(missing))

    name = package_name(experiment["id"], run["id"], qualification["at"])
    production = paths.production
    production.mkdir(parents=True, exist_ok=True)
    final = production / name
    if final.exists():
        raise ValueError(f"Production package already exists and will not be overwritten: {final.name}")

    temp = Path(tempfile.mkdtemp(prefix=".tmp-package-", dir=production))
    try:
        copied = []
        for kind in sorted((run.get("artifacts") or {})):
            copied.append(_copy_verified(paths.root, temp, kind, run["artifacts"][kind]))

        _write_json(temp / "experiment.json", experiment)
        _write_json(temp / "run.json", run)
        _write_json(temp / "qualification.json", qualification)

        evidence = []
        for item in run.get("evidence") or []:
            if not isinstance(item, dict) or not item.get("path") or not item.get("sha256"):
                continue
            evidence.append(_copy_verified(paths.root, temp, "evidence", item))

        manifest = {
            "schema": SCHEMA,
            "id": name,
            "project": paths.name,
            "experiment": experiment["id"],
            "run": run["id"],
            "qualification": qualification["id"],
            "previous_reference": qualification.get("previous_reference"),
            "artifacts": copied,
            "evidence": evidence,
            "sealed_at": qualification["at"],
        }
        _write_json(temp / "manifest.json", manifest)

        checksum_lines = []
        for p in sorted(x for x in temp.rglob("*") if x.is_file()):
            checksum_lines.append(f"{_sha256(p)}  {p.relative_to(temp).as_posix()}")
        (temp / "checksums.sha256").write_text("\n".join(checksum_lines) + "\n")

        manifest_hash = _sha256(temp / "manifest.json")
        os.replace(temp, final)
        return {
            "schema": SCHEMA,
            "id": name,
            "path": final.relative_to(paths.root).as_posix(),
            "manifest_sha256": manifest_hash,
            "run": run["id"],
            "experiment": experiment["id"],
        }
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise
