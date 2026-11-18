"""The camera-fit page in a real browser (Playwright) against server.py and a fake bridge; see camera_fit_page.mjs.
Skipped where node or its playwright package isn't available: set PLAYWRIGHT_NODE_MODULES to a node_modules that has it."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("camera_fit_page.mjs")


def test_the_page_in_a_browser():
    modules = os.environ.get("PLAYWRIGHT_NODE_MODULES")
    if not shutil.which("node") or not modules or not (Path(modules) / "playwright").is_dir():
        pytest.skip("node with playwright isn't available (set PLAYWRIGHT_NODE_MODULES)")
    r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=120,
                       env={**os.environ, "NODE_PATH": modules, "HOME": os.environ.get("PYTEST_REAL_HOME", os.environ["HOME"])})  # conftest fakes HOME; the browser cache is under the real one
    assert r.returncode == 0, r.stdout + r.stderr
