"""OpenSCAD: find the binary and render SCAD to STL with the Manifold backend."""
import os
import re
import shutil
import subprocess
from pathlib import Path

INSTALL = "brew install --cask openscad@snapshot"
MIN_YEAR = 2025
_CANDIDATES = ["/opt/homebrew/bin/openscad", "/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD"]


def openscad_binary() -> tuple[Path, str]:
    """The OpenSCAD to use (LAB_OPENSCAD, else the snapshot) and its version string, e.g. '2026.10.11'."""
    override = os.environ.get("LAB_OPENSCAD")
    candidates = [override] if override else [shutil.which("openscad"), *_CANDIDATES]
    for c in candidates:
        if c and Path(c).exists():
            out = subprocess.run([c, "--version"], capture_output=True, text=True)
            m = re.search(r"version\s+(\S+)", out.stdout + out.stderr)
            if m:
                return Path(c), m.group(1)
    raise FileNotFoundError(f"OpenSCAD not found. Install it: {INSTALL}")


def render(scad: Path, out_stl: Path, defines: dict, jobs_dir: Path):
    """Render scad to out_stl with the Manifold backend; -D name=value for each define. Raises LabToolError."""
    from lab.jobs import LabToolError, failed_job, run_tool

    try:
        binary, version = openscad_binary()
    except FileNotFoundError as e:
        raise LabToolError(str(e), failed_job(jobs_dir=jobs_dir, tool="openscad", message=str(e), inputs=[scad])) from None
    year = re.match(r"(\d{4})", version)
    if not year or int(year.group(1)) < MIN_YEAR:
        msg = (f"OpenSCAD {version} is too old: the lab needs a {MIN_YEAR} or later build with the Manifold backend. "
               f"Install it: {INSTALL}")
        raise LabToolError(msg, failed_job(jobs_dir=jobs_dir, tool="openscad", message=msg, tool_version=version,
                                           inputs=[scad]))
    args = [str(binary), "--backend=manifold", "-o", str(out_stl)]
    for k, v in defines.items():
        val = ("true" if v else "false") if isinstance(v, bool) else (f'"{v}"' if isinstance(v, str) else v)
        args += ["-D", f"{k}={val}"]
    args.append(str(scad))
    job = run_tool(args, inputs=[scad], outputs=[out_stl], jobs_dir=jobs_dir, tool="openscad", tool_version=version)
    if not job.ok:
        raise LabToolError(f"OpenSCAD couldn't render {scad.name}: {job.stderr.strip()[-400:]}", job)
    return job
