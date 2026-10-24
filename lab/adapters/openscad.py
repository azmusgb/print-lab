"""OpenSCAD: find the binary and render SCAD to STL with the Manifold backend."""
import os
import re
import shutil
import subprocess
from pathlib import Path

INSTALL = "brew install --cask openscad@snapshot"
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
