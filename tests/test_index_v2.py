import hashlib
import json

from lab import runs
from lab.index_v2 import augment_index
from lab.records.project import ProjectPaths


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_augment_index_projects_runs_and_current_package(tmp_path):
    paths = ProjectPaths(tmp_path / "projects" / "hex-tile")
    artifacts = {}
    for kind, rel in {
        "model": "sources/model.3mf",
        "process": "presets/process.json",
        "filament": "presets/filament.json",
        "slice": "prints/sliced/job.gcode.3mf",
    }.items():
        path = paths.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        data = f"{kind}-bytes".encode()
        path.write_bytes(data)
        artifacts[kind] = {"path": rel, "sha256": _sha(data)}

    run = runs.create(
        paths,
        "E-025",
        build_id="BLD-025-01",
        artifacts=artifacts,
        estimate={"minutes": 761.2, "g": 363.71, "layers": 660},
        printer="Bambu Lab X2D 0.4 nozzle",
        status="printing",
        started_at="2026-10-29T20:00:00+00:00",
        source_run="PR-025-01",
    )

    package_id = "E-025-RUN-025-01-qualified-2026-10-30"
    package = paths.production / package_id
    package.mkdir(parents=True)
    (package / "manifest.json").write_text(json.dumps({
        "id": package_id,
        "experiment": "E-025",
        "run": run["id"],
        "qualification": "QUAL-0004",
        "previous_reference": "E-019",
        "artifacts": [{"kind": "model"}],
        "evidence": [],
        "sealed_at": "2026-10-30T01:00:00+00:00",
    }))
    (package / "checksums.sha256").write_text("abc  manifest.json\n")

    ix = {
        "schema": "print-lab-index/1",
        "project": "hex-tile",
        "fingerprint": "base",
        "experiments": [{"id": "E-025", "status": "printing"}],
        "qualification": {
            "current_reference": "E-025",
            "current_run": run["id"],
            "current_package": {
                "id": package_id,
                "path": f"production/{package_id}",
                "run": run["id"],
                "experiment": "E-025",
                "manifest_sha256": "f" * 64,
            },
        },
        "problems": [],
        "records": {},
    }

    out = augment_index(paths.root, ix)

    assert out["runs"][0]["id"] == "RUN-025-01"
    assert out["runs"][0]["artifacts"]["ready"] is True
    assert out["runs"][0]["artifacts"]["bound"] == 4
    assert out["experiments"][0]["run_ids"] == ["RUN-025-01"]
    assert out["experiments"][0]["active_run"] == "RUN-025-01"
    assert out["experiments"][0]["qualified_run"] == "RUN-025-01"
    assert out["production"]["current"]["id"] == package_id
    assert out["production"]["current"]["sealed"] is True
    assert out["fingerprint"].startswith("base:v2")
    assert "RUN-025-01" not in out["records"]


def test_augment_index_reports_missing_artifact_file_without_hashing(tmp_path):
    paths = ProjectPaths(tmp_path / "projects" / "hex-tile")
    artifacts = {
        "model": {"path": "sources/missing.3mf", "sha256": "a" * 64},
        "process": {"path": "presets/missing.json", "sha256": "b" * 64},
        "filament": {"path": "presets/missing-filament.json", "sha256": "c" * 64},
        "slice": {"path": "prints/sliced/missing.3mf", "sha256": "d" * 64},
    }
    runs.create(paths, "E-025", build_id="BLD-025-01", artifacts=artifacts, status="planned")

    out = augment_index(paths.root, {
        "schema": "print-lab-index/1",
        "project": "hex-tile",
        "fingerprint": "base",
        "experiments": [{"id": "E-025", "status": "planned"}],
        "qualification": {},
        "problems": [],
        "records": {},
    })

    state = out["runs"][0]["artifacts"]
    assert state["ready"] is False
    assert state["missing"] == []
    assert set(state["files_missing"]) == {"model", "process", "filament", "slice"}
