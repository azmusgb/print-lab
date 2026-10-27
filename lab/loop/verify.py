"""Pre-print artifact / G-code verification (`lab exp verify <eid> <candidate.3mf>`).

Ensures the file sent to Bambu Studio or the printer matches the approved build artifact,
catching accidental re-slices, lost arc fitting, and changed slicer settings before printing.
"""
import hashlib
from pathlib import Path

from lab.adapters.bambu import read_settings, slice_estimate
from lab.loop.commands import load_experiment
from lab.records.project import ProjectPaths

KEY_SETTINGS = (
    ("enable_arc_fitting", "Arc fitting (enable_arc_fitting)"),
    ("nozzle_diameter", "Nozzle diameter"),
    ("layer_height", "Layer height"),
    ("initial_layer_print_height", "Initial layer height"),
    ("wall_loops", "Wall loops"),
    ("top_shell_layers", "Top shell layers"),
    ("bottom_shell_layers", "Bottom shell layers"),
    ("sparse_infill_density", "Infill density"),
    ("sparse_infill_pattern", "Infill pattern"),
    ("outer_wall_speed", "Outer wall speed"),
    ("inner_wall_speed", "Inner wall speed"),
    ("sparse_infill_speed", "Infill speed"),
    ("top_surface_speed", "Top surface speed"),
    ("enable_support", "Support enabled"),
    ("seam_position", "Seam position"),
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_artifact(paths: ProjectPaths, eid: str, candidate_file: Path | str, *, build_id: str | None = None) -> dict:
    e = load_experiment(paths, eid)
    builds = e.get("builds") or []
    if not builds:
        raise ValueError(f"Experiment {eid} has no builds to verify against.")

    if build_id:
        build = next((b for b in builds if b["id"] == build_id), None)
        if not build:
            raise ValueError(f"Build {build_id} not found on experiment {eid}.")
    elif e.get("approval") and e["approval"].get("build_id"):
        appr_id = e["approval"]["build_id"]
        build = next((b for b in builds if b["id"] == appr_id), builds[-1])
    else:
        build = builds[-1]

    candidate_path = Path(candidate_file).resolve()
    if not candidate_path.exists():
        raise FileNotFoundError(f"Candidate file not found: {candidate_path}")

    candidate_sha = _sha256(candidate_path)

    artifact_rel = build.get("artifact")
    artifact_path = (paths.root / artifact_rel).resolve() if artifact_rel else None
    artifact_sha = build.get("artifact_sha256") or (_sha256(artifact_path) if artifact_path and artifact_path.exists() else None)

    sliced_rel = build.get("sliced")
    sliced_path = (paths.root / sliced_rel).resolve() if sliced_rel else None
    sliced_sha = _sha256(sliced_path) if sliced_path and sliced_path.exists() else None

    # Check exact hash matches
    if candidate_sha == artifact_sha:
        return {
            "ok": True,
            "match": "exact",
            "match_target": "artifact",
            "experiment_id": eid,
            "build_id": build["id"],
            "candidate_path": str(candidate_path),
            "candidate_sha256": candidate_sha,
            "approved_path": str(artifact_path) if artifact_path else None,
            "approved_sha256": artifact_sha,
            "differences": [],
            "warnings": [],
        }

    if sliced_sha and candidate_sha == sliced_sha:
        return {
            "ok": True,
            "match": "exact",
            "match_target": "sliced_gcode",
            "experiment_id": eid,
            "build_id": build["id"],
            "candidate_path": str(candidate_path),
            "candidate_sha256": candidate_sha,
            "approved_path": str(sliced_path),
            "approved_sha256": sliced_sha,
            "differences": [],
            "warnings": [],
        }

    # Content-based match (ignoring dynamic metadata/comments such as run ID tags)
    from lab.adapters.threemf import content_sha256
    if artifact_path and artifact_path.exists():
        try:
            if content_sha256(candidate_path) == content_sha256(artifact_path):
                return {
                    "ok": True,
                    "match": "content_exact",
                    "match_target": "artifact",
                    "experiment_id": eid,
                    "build_id": build["id"],
                    "candidate_path": str(candidate_path),
                    "candidate_sha256": candidate_sha,
                    "approved_path": str(artifact_path),
                    "approved_sha256": artifact_sha,
                    "differences": [],
                    "warnings": [],
                }
        except Exception:
            pass

    # Hash mismatch: analyze settings differences
    cand_settings = read_settings(candidate_path) if candidate_path.suffix == ".3mf" else None
    appr_settings = None
    if artifact_path and artifact_path.exists() and artifact_path.suffix == ".3mf":
        appr_settings = read_settings(artifact_path)
    if not appr_settings and sliced_path and sliced_path.exists() and sliced_path.suffix == ".3mf":
        appr_settings = read_settings(sliced_path)

    differences = []
    warnings = []

    if cand_settings and appr_settings:
        # Check critical settings first
        for key, label in KEY_SETTINGS:
            v_appr = appr_settings.get(key)
            v_cand = cand_settings.get(key)
            if v_appr != v_cand:
                is_crit = False
                if key == "enable_arc_fitting" and str(v_appr) == "1" and str(v_cand) != "1":
                    warnings.append("CRITICAL: Arc fitting (enable_arc_fitting) was lost/disabled in candidate!")
                    is_crit = True
                differences.append({
                    "key": key,
                    "label": label,
                    "approved": v_appr,
                    "candidate": v_cand,
                    "critical": is_crit,
                })

        # Check all other settings diffs
        all_keys = sorted(set(appr_settings.keys()) | set(cand_settings.keys()))
        known_keys = {k for k, _ in KEY_SETTINGS}
        for k in all_keys:
            if k in known_keys:
                continue
            v_appr = appr_settings.get(k)
            v_cand = cand_settings.get(k)
            if v_appr != v_cand:
                differences.append({
                    "key": k,
                    "label": k,
                    "approved": v_appr,
                    "candidate": v_cand,
                    "critical": False,
                })
    elif not cand_settings and candidate_path.suffix == ".3mf":
        warnings.append("Candidate 3MF has no Bambu Studio settings config (Metadata/project_settings.config).")

    # Check slice estimates if available
    try:
        cand_est_m, cand_est_g = slice_estimate(candidate_path)
        appr_est = build.get("estimate") or {}
        appr_m = appr_est.get("minutes")
        appr_g = appr_est.get("g")
        if appr_m is not None and (abs(cand_est_m - appr_m) > 1.0 or abs(cand_est_g - (appr_g or 0)) > 1.0):
            differences.append({
                "key": "slice_estimate",
                "label": "Slice estimate (minutes, grams)",
                "approved": f"{appr_m} min, {appr_g} g",
                "candidate": f"{cand_est_m} min, {cand_est_g} g",
                "critical": False,
            })
    except Exception:
        pass

    return {
        "ok": False,
        "match": "mismatch",
        "match_target": None,
        "experiment_id": eid,
        "build_id": build["id"],
        "candidate_path": str(candidate_path),
        "candidate_sha256": candidate_sha,
        "approved_path": str(artifact_path) if artifact_path else None,
        "approved_sha256": artifact_sha,
        "differences": differences,
        "warnings": warnings,
    }


def format_verify_text(res: dict) -> str:
    lines = []
    if res["ok"]:
        lines.append(f"✓ VERIFIED: candidate matches approved build {res['build_id']} ({res['match_target']})")
        lines.append(f"  Experiment: {res['experiment_id']}")
        lines.append(f"  File:       {res['candidate_path']}")
        lines.append(f"  SHA-256:    {res['candidate_sha256']}")
        return "\n".join(lines)

    lines.append(f"✗ MISMATCH: candidate differs from approved build {res['build_id']}")
    lines.append(f"  Experiment: {res['experiment_id']}")
    lines.append(f"  Candidate:  {res['candidate_path']}")
    lines.append(f"  SHA-256:    {res['candidate_sha256']}")
    if res.get("approved_path"):
        lines.append(f"  Approved:   {res['approved_path']}")
        lines.append(f"  SHA-256:    {res['approved_sha256']}")

    if res.get("warnings"):
        lines.append("")
        lines.append("Warnings:")
        for w in res["warnings"]:
            lines.append(f"  ⚠ {w}")

    diffs = res.get("differences") or []
    if diffs:
        lines.append("")
        crit = [d for d in diffs if d.get("critical")]
        non_crit = [d for d in diffs if not d.get("critical")]
        lines.append(f"Differences ({len(diffs)} total):")
        for d in crit:
            lines.append(f"  [CRITICAL] {d['label']}: approved={d['approved']!r} -> candidate={d['candidate']!r}")
        for d in non_crit[:15]:
            lines.append(f"  • {d['label']}: approved={d['approved']!r} -> candidate={d['candidate']!r}")
        if len(non_crit) > 15:
            lines.append(f"  … and {len(non_crit) - 15} more differences")
    else:
        lines.append("  (Files differ by hash but no specific settings difference was identified)")

    return "\n".join(lines)
