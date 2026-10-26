import json
import zipfile
from pathlib import Path

import pytest

from lab.cli import main
from lab.loop.verify import format_verify_text, verify_artifact
from loop_fixtures import make_project, minimal_experiment, minimal_question


def _make_3mf(path: Path, settings: dict | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        if settings is not None:
            z.writestr("Metadata/project_settings.config", json.dumps(settings))
    return path


def test_verify_exact_match(tmp_path):
    art = _make_3mf(tmp_path / "artifact.3mf", {"enable_arc_fitting": 1, "outer_wall_speed": 100})
    import hashlib
    sha = hashlib.sha256(art.read_bytes()).hexdigest()

    e = minimal_experiment("E-009")
    e["status"] = "ready"
    e["builds"] = [
        {
            "id": "BLD-009-01",
            "ok": True,
            "artifact": "prints/artifact.3mf",
            "artifact_sha256": sha,
        }
    ]
    paths = make_project(tmp_path, minimal_question(), [e])
    (paths.root / "prints").mkdir(parents=True, exist_ok=True)
    (paths.root / "prints" / "artifact.3mf").write_bytes(art.read_bytes())

    res = verify_artifact(paths, "E-009", art)
    assert res["ok"] is True
    assert res["match"] == "exact"
    assert res["match_target"] == "artifact"
    assert res["candidate_sha256"] == sha
    assert "✓ VERIFIED" in format_verify_text(res)


def test_verify_mismatch_arc_fitting_lost(tmp_path):
    appr = _make_3mf(tmp_path / "approved.3mf", {
        "enable_arc_fitting": 1,
        "outer_wall_speed": 100,
        "layer_height": 0.2,
    })
    import hashlib
    sha_appr = hashlib.sha256(appr.read_bytes()).hexdigest()

    cand = _make_3mf(tmp_path / "candidate.3mf", {
        "enable_arc_fitting": 0,
        "outer_wall_speed": 200,
        "layer_height": 0.2,
    })

    e = minimal_experiment("E-009")
    e["status"] = "ready"
    e["builds"] = [
        {
            "id": "BLD-009-01",
            "ok": True,
            "artifact": "prints/approved.3mf",
            "artifact_sha256": sha_appr,
        }
    ]
    paths = make_project(tmp_path, minimal_question(), [e])
    (paths.root / "prints").mkdir(parents=True, exist_ok=True)
    (paths.root / "prints" / "approved.3mf").write_bytes(appr.read_bytes())

    res = verify_artifact(paths, "E-009", cand)
    assert res["ok"] is False
    assert res["match"] == "mismatch"
    assert any("Arc fitting" in w for w in res["warnings"])
    assert any(d["key"] == "enable_arc_fitting" and d["critical"] for d in res["differences"])
    assert any(d["key"] == "outer_wall_speed" for d in res["differences"])

    text = format_verify_text(res)
    assert "✗ MISMATCH" in text
    assert "[CRITICAL] Arc fitting" in text


def test_verify_missing_file(tmp_path):
    e = minimal_experiment("E-009")
    e["builds"] = [{"id": "BLD-009-01", "ok": True}]
    paths = make_project(tmp_path, minimal_question(), [e])

    with pytest.raises(FileNotFoundError):
        verify_artifact(paths, "E-009", tmp_path / "nonexistent.3mf")


def test_verify_cli(capsys):
    # Verify against real hex-tile E-020
    hex_art = Path("projects/hex-tile/prints/hex-tile_E-020_BLD-020-01.3mf")
    if not hex_art.exists():
        pytest.skip("hex-tile prints not present")

    rc = main(["exp", "verify", "E-020", str(hex_art)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "✓ VERIFIED" in out

    # Mismatch with a source 3MF
    src = Path("projects/hex-tile/sources/hexagon_v61s_X2D_0.6nozzle.3mf")
    rc = main(["exp", "verify", "E-020", str(src)])
    assert rc == 1
    out = capsys.readouterr().out
    assert "✗ MISMATCH" in out
