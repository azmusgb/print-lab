"""Quick slice: an STL plus a Studio-saved base project in, a validated X2D `.gcode.3mf` and a result record out.
No network. Every outcome, good or bad, writes `quick_slice.json` beside the files; a usable slice is `status: sliced`,
anything else is `needs_attention` with the reasons, and its artifact is never offered."""
import hashlib
import json
import re
import secrets
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import trimesh

from lab.adapters import bambu, threemf
from lab.analysis.gcode import layer_paths
from lab.jobs import LabToolError, sha256
from lab.quick import validate
from lab.quick.settings import QuickSettings, settings_patch

BED_MM = (256.0, 256.0, 256.0)  # X2D build volume; Studio is the final judge and refuses what doesn't fit
SLICE_TIMEOUT_S = 1800


class QuickSliceError(Exception):
    """The inputs can't be sliced at all (nothing was run). The message says what to fix."""


@dataclass
class QuickResult:
    job_id: str
    status: str  # sliced | needs_attention
    reasons: list[str] = field(default_factory=list)
    source: dict = field(default_factory=dict)
    transform: dict = field(default_factory=dict)
    settings: dict = field(default_factory=dict)
    base: dict = field(default_factory=dict)
    tool: dict = field(default_factory=dict)
    artifact: dict = field(default_factory=dict)
    estimate: dict = field(default_factory=dict)
    layers: dict = field(default_factory=dict)
    start_check: dict = field(default_factory=dict)
    created: str = ""


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def new_job_id() -> str:
    return f"quick_{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}"


def load_source(path: Path, rotate=(0.0, 0.0, 0.0), scale: float = 1.0) -> trimesh.Trimesh:
    """The STL as one mesh, rotated (degrees about x, y, z) and scaled; refuses empty, flat and oversize models."""
    if not scale > 0:
        raise QuickSliceError(f"scale {scale:g} must be above 0")
    try:
        m = trimesh.load(path, file_type=path.suffix.lstrip(".").lower() or "stl", force="mesh")
    except Exception as e:
        raise QuickSliceError(f"{path.name} couldn't be read as a model: {e}") from None
    if not isinstance(m, trimesh.Trimesh) or len(m.faces) == 0:
        raise QuickSliceError(f"{path.name} has no triangles")
    m = m.copy()
    for axis, deg in zip(([1, 0, 0], [0, 1, 0], [0, 0, 1]), rotate):
        if deg:
            m.apply_transform(trimesh.transformations.rotation_matrix(np.radians(deg), axis))
    m.apply_scale(scale)
    ext = m.bounds[1] - m.bounds[0]
    if min(ext) < 0.01:
        raise QuickSliceError(f"{path.name} is flat (its smallest side is {min(ext):.3f} mm)")
    if any(e > b for e, b in zip(ext, BED_MM)):
        raise QuickSliceError(f"{path.name} is {ext[0]:.1f} × {ext[1]:.1f} × {ext[2]:.1f} mm; the X2D plate takes "
                              f"{BED_MM[0]:g} × {BED_MM[1]:g} × {BED_MM[2]:g}. Scale or rotate it.")
    return m


def _gcode_of(sliced: Path) -> str:
    with zipfile.ZipFile(sliced) as z:
        return z.read("Metadata/plate_1.gcode").decode("utf-8", "replace")


def _artifact_problems(sliced: Path) -> list[str]:
    """Output the slicer claimed to write but that isn't a usable plate-1 file."""
    if not sliced.exists():
        return ["the slicer wrote no output file"]
    if not zipfile.is_zipfile(sliced):
        return ["the output is not a valid 3MF (zip) file"]
    with zipfile.ZipFile(sliced) as z:
        names = set(z.namelist())
        bad = z.testzip()
    out = []
    if bad:
        out.append(f"the output file is corrupt ({bad})")
    if "Metadata/plate_1.gcode" not in names:
        out.append("the output has no sliced plate (Metadata/plate_1.gcode); it is a project, not a sliced file")
    if "Metadata/slice_info.config" not in names:
        out.append("the output has no slice_info.config, so no estimate")
    return out


def quick_slice(source: Path, base: Path, out_dir: Path, settings: QuickSettings | None = None, *,
                rotate=(0.0, 0.0, 0.0), scale: float = 1.0, expect_source_sha256: str | None = None,
                job_id: str | None = None, timeout: int = SLICE_TIMEOUT_S) -> QuickResult:
    """Slice `source` on `base`'s settings. Raises QuickSliceError for inputs that can't be sliced (nothing run);
    every other problem returns a result with status needs_attention."""
    source, base, out_dir = Path(source), Path(base), Path(out_dir)
    settings = settings or QuickSettings()
    if not source.is_file():
        raise QuickSliceError(f"{source} doesn't exist")
    if not base.is_file():
        raise QuickSliceError(f"base project {base} doesn't exist")
    src_sha = sha256(source)
    if expect_source_sha256 and expect_source_sha256 != src_sha:
        raise QuickSliceError(f"{source.name} changed since it was registered (sha256 {src_sha[:12]}…, expected "
                              f"{expect_source_sha256[:12]}…). Register it again.")
    try:
        patch = settings_patch(settings)
    except ValueError as e:
        raise QuickSliceError(str(e)) from None
    base_settings = bambu.read_settings(base) if zipfile.is_zipfile(base) else None
    if problems := validate.project_problems(base_settings):
        raise QuickSliceError("; ".join(problems) + ". Save a complete X2D project in Studio and use that as the base.")
    mesh = load_source(source, rotate, scale)

    job = job_id or new_job_id()
    work = out_dir / job
    work.mkdir(parents=True, exist_ok=True)
    ext = [round(float(v), 3) for v in (mesh.bounds[1] - mesh.bounds[0])]
    res = QuickResult(
        job_id=job, status="needs_attention", created=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        source={"name": source.name, "sha256": src_sha, "triangles": int(len(mesh.faces)),
                "watertight": bool(mesh.is_watertight)},
        transform={"rotate_deg": list(rotate), "scale": scale, "size_mm": ext, "position_mm": [128.0, 128.0]},
        settings=settings.asdict(),
        base={"name": base.name, "sha256": sha256(base), "machine_start_sha256": validate.machine_start_hash(base_settings)})
    project = work / f"{job}.3mf"
    meta = {"quick_print": job, "source_sha256": src_sha, "transform": res.transform, "settings": res.settings}
    threemf.write_print_3mf(base, [(source.stem, mesh, (128.0, 128.0))], project, meta, settings_patch=patch or None)
    res.base["project_sha256"] = sha256(project)

    sliced = None
    try:
        sliced, sjob = bambu.slice_with_job(project, work / "sliced", 1, work / "jobs", timeout=timeout)
        res.tool = {"name": "bambu-studio", "version": sjob.tool_version, "job": sjob.id}
    except LabToolError as e:
        res.reasons.append(str(e))
        res.tool = {"name": "bambu-studio", "version": e.job.tool_version, "job": e.job.id}
        timed_out = "TimeoutExpired" in (e.job.stderr or "")
        if timed_out:
            res.reasons.insert(0, f"Bambu Studio didn't finish within {timeout} s")
        return _write(work, res)

    if problems := _artifact_problems(sliced):
        res.reasons += problems
        return _write(work, res)
    gcode = _gcode_of(sliced)
    chk = validate.check_start(gcode)
    res.start_check = asdict(chk)
    res.reasons += chk.reasons
    out_settings = validate.sliced_settings(sliced) or {}
    if validate.machine_start_hash(out_settings) != res.base["machine_start_sha256"]:
        res.reasons.append("the sliced project's machine start code differs from the base project's")
    est_min, grams = bambu.slice_estimate(sliced)
    paths = layer_paths(gcode)
    res.estimate = {"minutes": est_min, "grams": grams}
    res.layers = {"count": len(paths), "top_z": paths[-1]["z"] if paths else None,
                  "summary": [{"index": p["index"], "z": p["z"], "extruded_mm": round(p["extruded_mm"], 1),
                               "travel_mm": round(p["travel_mm"], 1), "features": sorted(p["extrusion"])}
                              for p in paths]}
    if not paths:
        res.reasons.append("the G-code has no layers")
    res.artifact = {"file": str(sliced.relative_to(work)), "bytes": sliced.stat().st_size, "sha256": sha256(sliced),
                    "gcode_sha256": _sha(gcode.encode())}
    if not res.reasons:
        res.status = "sliced"
    return _write(work, res)


def _write(work: Path, res: QuickResult) -> QuickResult:
    (work / "quick_slice.json").write_text(json.dumps(asdict(res), indent=2))
    return res
