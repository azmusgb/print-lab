"""The Fusion Params Panel page in headless Chromium, with the Fusion palette bridge stubbed (no Fusion needed)."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
# Resolved at import: the suite points HOME at a temporary directory while tests run.
PLAYWRIGHT_HOMES = [Path(p).expanduser() for p in (os.environ.get("PLAYWRIGHT_NODE_MODULES"), "~/dev/ai-harness/LocalAI/node_modules") if p]

BROWSERS = Path("~/Library/Caches/ms-playwright").expanduser()


def _node_path():
    for home in PLAYWRIGHT_HOMES:
        if (home / "playwright" / "package.json").is_file():
            return str(home)
    return None


def test_the_panel_page_behaves_in_a_browser():
    node, modules = shutil.which("node"), _node_path()
    if not node or not modules:
        pytest.skip("needs node with the playwright package (set PLAYWRIGHT_NODE_MODULES)")
    done = subprocess.run([node, str(ROOT / "tests" / "params_panel_dom.mjs")], capture_output=True, text=True, timeout=120,
                          env={**os.environ, "NODE_PATH": modules, "PLAYWRIGHT_BROWSERS_PATH": os.environ.get("PLAYWRIGHT_BROWSERS_PATH", str(BROWSERS))})
    assert done.returncode == 0, done.stdout + done.stderr


# --- ParamsPanel.py with adsk stubbed ---

@pytest.fixture
def panel(monkeypatch):
    import importlib.util
    import sys
    import types

    adsk = types.ModuleType("adsk")
    adsk.core = types.ModuleType("adsk.core")
    adsk.core.__getattr__ = lambda name: type(name, (), {})  # the event-handler base classes the add-in subclasses
    adsk.fusion = types.ModuleType("adsk.fusion")
    monkeypatch.setitem(sys.modules, "adsk", adsk)
    monkeypatch.setitem(sys.modules, "adsk.core", adsk.core)
    monkeypatch.setitem(sys.modules, "adsk.fusion", adsk.fusion)
    spec = importlib.util.spec_from_file_location("params_panel_under_test", ROOT / "tools" / "fusion" / "ParamsPanel" / "ParamsPanel.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    monkeypatch.setattr(m, "_lab_projects", lambda: ["hex-tile"])
    m._lab_status.clear()
    return m


def test_the_lab_footer_says_when_uv_is_not_found(panel, monkeypatch):
    monkeypatch.setattr(panel, "_uv", lambda: None)
    panel._refresh_lab_status("hex-tile")
    assert "uv not found" in panel._lab_status["hex-tile"]["error"]


def test_the_lab_footer_reports_a_failed_launch_instead_of_raising(panel, monkeypatch):
    monkeypatch.setattr(panel, "_uv", lambda: "/nonexistent/uv")

    def boom(args, timeout):
        raise OSError("exec format error")

    monkeypatch.setattr(panel, "_run", boom)
    panel._refresh_lab_status("hex-tile")
    assert "could not run" in panel._lab_status["hex-tile"]["error"].lower()
