"""Bambu Studio: the only source of slicing truth."""
import os
import re
import subprocess
import tempfile
from pathlib import Path

EXPECTED_VERSION = "02.08.02.61"
DEFAULT = "/Applications/BambuStudio.app/Contents/MacOS/BambuStudio"


def bambu_binary() -> tuple[Path, str]:
    """The Bambu Studio CLI (LAB_BAMBU, else the app) and its version, read from --help."""
    path = Path(os.environ.get("LAB_BAMBU", DEFAULT))
    if not path.exists():
        raise FileNotFoundError(f"Bambu Studio not found at {path}. Install Bambu Studio {EXPECTED_VERSION}.")
    # --help writes result.json into the working directory, so run it somewhere disposable.
    with tempfile.TemporaryDirectory() as d:
        out = subprocess.run([str(path), "--help"], capture_output=True, text=True, cwd=d)
    m = re.search(r"BambuStudio-(\d+\.\d+\.\d+\.\d+)", out.stdout + out.stderr)
    if not m:
        raise FileNotFoundError(f"Couldn't read the Bambu Studio version from {path}.")
    return path, m.group(1)


import json
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass


@dataclass
class ObjectInfo:
    id: str
    name: str
    plate: int


def read_settings(path_3mf: Path) -> dict:
    """The project's process, filament and printer settings (Metadata/project_settings.config)."""
    with zipfile.ZipFile(path_3mf) as z:
        return json.loads(z.read("Metadata/project_settings.config"))


def list_objects(path_3mf: Path) -> list[ObjectInfo]:
    """Every object in the project with its name and the plate it sits on (0 when on no plate)."""
    with zipfile.ZipFile(path_3mf) as z:
        root = ET.fromstring(z.read("Metadata/model_settings.config"))
    plate_of: dict[str, int] = {}
    for plate in root.iter("plate"):
        pid = next((int(m.get("value")) for m in plate.findall("metadata") if m.get("key") == "plater_id"), 0)
        for inst in plate.iter("model_instance"):
            for m in inst.findall("metadata"):
                if m.get("key") == "object_id":
                    plate_of[m.get("value")] = pid
    out = []
    for obj in root.findall("object"):
        name = next((m.get("value") for m in obj.findall("metadata") if m.get("key") == "name"), "")
        out.append(ObjectInfo(id=obj.get("id"), name=name, plate=plate_of.get(obj.get("id"), 0)))
    return out


def slice_3mf(path_3mf: Path, out_dir: Path, plate: int, jobs_dir: Path) -> Path:
    """Slice one plate with Bambu Studio; returns the sliced .gcode.3mf. Raises LabToolError."""
    from lab.jobs import LabToolError, run_tool

    binary, version = bambu_binary()
    path_3mf, out_dir, jobs_dir = Path(path_3mf).resolve(), Path(out_dir).resolve(), Path(jobs_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    name = path_3mf.name.removesuffix(".3mf") + ".gcode.3mf"
    out = out_dir / name
    args = [str(binary), "--slice", str(plate), "--outputdir", str(out_dir), "--export-3mf", name, str(path_3mf)]
    job = run_tool(args, inputs=[path_3mf], outputs=[out], jobs_dir=jobs_dir, tool="bambu-studio",
                   tool_version=version, cwd=out_dir)
    if not job.ok:
        raise LabToolError(f"Bambu Studio couldn't slice {path_3mf.name}: "
                           f"{(job.stderr or job.stdout).strip()[-400:]}", job)
    return out


def extract_gcode(sliced: Path, plate: int) -> str:
    with zipfile.ZipFile(sliced) as z:
        return z.read(f"Metadata/plate_{plate}.gcode").decode("utf-8", "replace")
