"""Slice one model for the X2D through a complete project, and publish nothing that fails a check.

Order: check the settings, check the model is the one named, build the project from the Studio-saved base (never an STL
with loose presets), slice with the pinned Studio, then check the output (a real zip, a plate, the Q5 start sequence)
before anything is returned. A slice that fails any check is deleted, so a caller can't pick up a partial file."""
import re
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import trimesh

from lab.adapters import bambu, threemf
from lab.jobs import sha256
from lab.quick import settings as quick_settings
from lab.quick import start_check

BED_CENTRE = (128.0, 128.0)  # the same placement the P0 probe sliced at


class QuickSliceError(Exception):
    """A slice that can't be offered; the message is for the owner."""


@dataclass
class QuickSlice:
    sliced: str
    sliced_sha256: str
    project_sha256: str
    base_sha256: str
    model_sha256: str
    settings: dict
    studio_version: str | None
    job_id: str
    minutes: float
    grams: float
    layers: int
    size_bytes: int
    start_block_lines: int = 0
    notes: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return asdict(self)


def load_model(path: Path, max_bytes: int = 50 << 20) -> trimesh.Trimesh:
    path = Path(path)
    if path.suffix.lower() not in (".stl", ".3mf"):
        raise QuickSliceError(f"{path.name}: only STL and 3MF models are supported")
    if path.stat().st_size > max_bytes:
        raise QuickSliceError(f"{path.name} is larger than {max_bytes >> 20} MiB")
    try:
        loaded = trimesh.load(path, force="mesh")
    except Exception as e:
        raise QuickSliceError(f"{path.name} couldn't be read as a model: {e}") from None
    if not isinstance(loaded, trimesh.Trimesh) or len(loaded.faces) == 0:
        raise QuickSliceError(f"{path.name} holds no triangles")
    return loaded


def check_output(sliced: Path, plate: int = 1) -> str:
    """The sliced file's G-code, only if it is a real zip with that plate. Raises QuickSliceError."""
    try:
        with zipfile.ZipFile(sliced) as z:
            names = set(z.namelist())
            for need in (f"Metadata/plate_{plate}.gcode", "Metadata/slice_info.config"):
                if need not in names:
                    raise QuickSliceError(f"The slice has no {need}")
            return z.read(f"Metadata/plate_{plate}.gcode").decode("utf-8", "replace")
    except zipfile.BadZipFile:
        raise QuickSliceError("Bambu Studio's output isn't a valid 3MF archive") from None


def slice_quick(model: Path, base_3mf: Path, out_dir: Path, *, settings: dict | None = None,
                transform: np.ndarray | None = None, expect_model_sha256: str | None = None,
                reference: dict | None = None, jobs_dir: Path | None = None, name: str = "quick") -> QuickSlice:
    """Raises QuickSettingError, QuickSliceError or LabToolError; on any of them no sliced file is left behind."""
    model, base_3mf, out_dir = Path(model), Path(base_3mf), Path(out_dir)
    patch = quick_settings.to_patch(settings or {})
    model_sha = sha256(model)
    if expect_model_sha256 and model_sha != expect_model_sha256:
        raise QuickSliceError("The model changed after it was uploaded (its sha256 differs); upload it again")
    if not base_3mf.is_file():
        raise QuickSliceError(f"The base project {base_3mf.name} is missing")
    ref = reference if reference is not None else start_check.load_reference()
    mesh = load_model(model)
    if transform is not None:
        mesh = mesh.copy()
        mesh.apply_transform(np.asarray(transform, dtype=float))
    out_dir.mkdir(parents=True, exist_ok=True)
    project = out_dir / f"{name}.3mf"
    meta = {"quick_print": name, "model_sha256": model_sha, "base_sha256": sha256(base_3mf), "settings": patch}
    project_sha = threemf.write_print_3mf(base_3mf, [(name, mesh, BED_CENTRE)], project, meta, settings_patch=patch)
    sliced, job = bambu.slice_with_job(project, out_dir / "sliced", 1, Path(jobs_dir) if jobs_dir else out_dir / "jobs")
    try:
        gcode = check_output(sliced)
        verdict = start_check.check_gcode(gcode, ref)
        if not verdict.ok:
            raise QuickSliceError("Refused: this slice doesn't have the X2D start sequence. " + "; ".join(verdict.reasons))
        minutes, grams = bambu.slice_estimate(sliced)
        layers = re.search(r"^; total layer number: (\d+)", gcode, re.M)
        return QuickSlice(sliced=str(sliced), sliced_sha256=sha256(sliced), project_sha256=project_sha,
                          base_sha256=meta["base_sha256"], model_sha256=model_sha, settings=patch,
                          studio_version=job.tool_version, job_id=job.id, minutes=minutes, grams=grams,
                          layers=int(layers.group(1)) if layers else 0, size_bytes=sliced.stat().st_size,
                          start_block_lines=verdict.block_lines)
    except Exception:
        sliced.unlink(missing_ok=True)
        raise
