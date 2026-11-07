"""Bambu Studio: the only source of slicing truth."""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

EXPECTED_VERSION = "02.09.01.70"
if sys.platform == "win32":
    DEFAULT = str(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Bambu Studio" / "bambu-studio.exe")
else:
    DEFAULT = "/Applications/BambuStudio.app/Contents/MacOS/BambuStudio"
DOWNLOAD = f"https://github.com/bambulab/BambuStudio/releases/tag/v{EXPECTED_VERSION}"
HELP_TIMEOUT_S = 60


def _read_windows_version(path: Path) -> str | None:
    """Read FileVersion on Windows from PE metadata via PowerShell or registry."""
    try:
        cmd = ["powershell", "-NoProfile", "-Command",
               f"[System.Diagnostics.FileVersionInfo]::GetVersionInfo('{path}').FileVersion"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        ver = res.stdout.strip()
        if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", ver):
            return ver
    except Exception:
        pass

    try:
        import winreg
        for hkey in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for subkey in (r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
                           r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"):
                try:
                    with winreg.OpenKey(hkey, subkey) as root:
                        for i in range(winreg.QueryInfoKey(root)[0]):
                            try:
                                child_name = winreg.EnumKey(root, i)
                                with winreg.OpenKey(root, child_name) as child:
                                    name, _ = winreg.QueryValueEx(child, "DisplayName")
                                    if "Bambu Studio" in str(name):
                                        ver, _ = winreg.QueryValueEx(child, "DisplayVersion")
                                        if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", str(ver).strip()):
                                            return str(ver).strip()
                            except (OSError, FileNotFoundError):
                                pass
                except (OSError, FileNotFoundError):
                    pass
    except Exception:
        pass
    return None


def bambu_binary() -> tuple[Path, str]:
    """The Bambu Studio CLI (LAB_BAMBU, else the app) and its version, read from --help or OS metadata."""
    path = Path(os.environ.get("LAB_BAMBU", DEFAULT))
    if not path.exists():
        raise FileNotFoundError(f"Bambu Studio not found at {path}. Install Bambu Studio {EXPECTED_VERSION} from "
                                f"{DOWNLOAD} (or set LAB_BAMBU to where it is).")
    # --help writes result.json into the working directory, so run it somewhere disposable.
    with tempfile.TemporaryDirectory() as d:
        try:
            out = subprocess.run([str(path), "--help"], capture_output=True, text=True, cwd=d,
                                 timeout=HELP_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            raise FileNotFoundError(f"Bambu Studio at {path} didn't answer within {HELP_TIMEOUT_S} s. Close any "
                                    "open Studio windows and try again.") from None
    m = re.search(r"BambuStudio-(\d+\.\d+\.\d+\.\d+)", out.stdout + out.stderr)
    version = m.group(1) if m else None
    if not version and sys.platform == "win32":
        version = _read_windows_version(path)
    if not version:
        raise FileNotFoundError(f"Couldn't read the Bambu Studio version from {path}.")
    return path, version


import json
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass


@dataclass
class ObjectInfo:
    id: str
    name: str
    plate: int


def read_settings(path_3mf: Path) -> dict | None:
    """The project's process, filament and printer settings (Metadata/project_settings.config); None for a 3MF that
    isn't a Bambu Studio project."""
    with zipfile.ZipFile(path_3mf) as z:
        if "Metadata/project_settings.config" not in z.namelist():
            return None
        return json.loads(z.read("Metadata/project_settings.config"))


def list_objects(path_3mf: Path) -> list[ObjectInfo]:
    """Every object in the project with its name and the plate it sits on (0 when on no plate)."""
    with zipfile.ZipFile(path_3mf) as z:
        if "Metadata/model_settings.config" not in z.namelist():
            raise ValueError(f"{Path(path_3mf).name} isn't a Bambu Studio project (it has no object list). Open it in "
                             "Bambu Studio and save it, or export the model as STL.")
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
    return slice_with_job(path_3mf, out_dir, plate, jobs_dir)[0]


def slice_with_job(path_3mf: Path, out_dir: Path, plate: int, jobs_dir: Path):
    """slice_3mf, also returning the Job that sliced it."""
    from lab.jobs import LabToolError, failed_job, run_tool

    path_3mf, out_dir, jobs_dir = Path(path_3mf).resolve(), Path(out_dir).resolve(), Path(jobs_dir).resolve()
    try:
        binary, version = bambu_binary()
    except FileNotFoundError as e:
        raise LabToolError(str(e), failed_job(jobs_dir=jobs_dir, tool="bambu-studio", message=str(e),
                                               inputs=[path_3mf])) from None
    if version != EXPECTED_VERSION:
        msg = (f"Bambu Studio {version} is installed, but the lab is checked against {EXPECTED_VERSION}; slices from "
               "another version can behave differently. Install that version, or update the lab's expected version.")
        raise LabToolError(msg, failed_job(jobs_dir=jobs_dir, tool="bambu-studio", message=msg, tool_version=version,
                                           inputs=[path_3mf]))
    out_dir.mkdir(parents=True, exist_ok=True)
    name = path_3mf.name.removesuffix(".3mf") + ".gcode.3mf"
    out = out_dir / name
    args = [str(binary), "--slice", str(plate), "--outputdir", str(out_dir), "--export-3mf", name, str(path_3mf)]
    job = run_tool(args, inputs=[path_3mf], outputs=[out], jobs_dir=jobs_dir, tool="bambu-studio",
                   tool_version=version, cwd=out_dir)
    if not job.ok:
        raise LabToolError(f"Bambu Studio couldn't slice {path_3mf.name}: "
                           f"{(job.stderr or job.stdout).strip()[-400:]}", job)
    return out, job


def extract_gcode(sliced: Path, plate: int) -> str:
    with zipfile.ZipFile(sliced) as z:
        return z.read(f"Metadata/plate_{plate}.gcode").decode("utf-8", "replace")


def slice_estimate(sliced: Path) -> tuple[float, float]:
    """Bambu Studio's own estimate for plate 1 of a sliced file: (minutes, grams)."""
    with zipfile.ZipFile(sliced) as z:
        info = z.read("Metadata/slice_info.config").decode()
    pred = re.search(r'key="prediction" value="(\d+)"', info)
    weight = re.search(r'key="weight" value="([\d.]+)"', info)
    return (round(int(pred.group(1)) / 60, 1) if pred else 0.0), (float(weight.group(1)) if weight else 0.0)
