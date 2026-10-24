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
