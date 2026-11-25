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


# --- start-up: Fusion runs the add-in before its window has anywhere to dock a palette ---

class _FakeEvent:
    def __init__(self):
        self.handlers = []

    def add(self, handler):
        self.handlers.append(handler)


class _FakePalette:
    def __init__(self, app):
        self._app, self._docked = app, None
        self.isVisible = False
        self.incomingFromHTML = _FakeEvent()

    @property
    def dockingState(self):
        return self._docked

    @dockingState.setter
    def dockingState(self, value):
        if not self._app.isStartupComplete:  # what Fusion 2706.1.17 raises while its splash screen is still up
            raise RuntimeError("2 : InternalValidationError : pArea")
        self._docked = value


class _FakeCollection:
    def __init__(self, make):
        self._make, self.items = make, {}

    def itemById(self, item_id):
        return self.items.get(item_id)

    def add(self, item_id, *_args):
        self.items[item_id] = self._make()
        return self.items[item_id]

    addButtonDefinition = add


class _FakeApp:
    def __init__(self, startup_complete):
        import types

        self.isStartupComplete = startup_complete
        self.startupCompleted, self.documentActivated = _FakeEvent(), _FakeEvent()
        self.messages = []
        self.userInterface = types.SimpleNamespace(
            commandDefinitions=_FakeCollection(lambda: types.SimpleNamespace(commandCreated=_FakeEvent())),
            allToolbarPanels=_FakeCollection(lambda: None),
            palettes=_FakeCollection(lambda: _FakePalette(self)),
            commandTerminated=_FakeEvent(),
            messageBox=self.messages.append,
        )


def _start(panel, startup_complete):
    import types

    app = _FakeApp(startup_complete)
    panel.adsk.core.Application = types.SimpleNamespace(get=lambda: app)
    panel.adsk.core.PaletteDockingStates = types.SimpleNamespace(PaletteDockStateRight="right")
    panel._handlers.clear()
    panel.run(None)
    return app


def test_the_panel_docks_at_once_when_fusion_has_finished_starting(panel):
    app = _start(panel, startup_complete=True)
    palette = app.userInterface.palettes.itemById(panel.PALETTE_ID)
    assert app.messages == []
    assert palette.dockingState == "right" and palette.isVisible


def test_the_panel_waits_for_fusion_to_finish_starting_before_it_docks(panel):
    app = _start(panel, startup_complete=False)
    assert app.messages == []  # was: "Parameters Panel failed to start … InternalValidationError : pArea"
    assert app.userInterface.palettes.itemById(panel.PALETTE_ID) is None
    assert len(app.startupCompleted.handlers) == 1

    app.isStartupComplete = True
    app.startupCompleted.handlers[0].notify(None)
    palette = app.userInterface.palettes.itemById(panel.PALETTE_ID)
    assert app.messages == []
    assert palette.dockingState == "right" and palette.isVisible


def test_a_panel_that_cannot_open_after_start_up_says_so(panel, monkeypatch):
    app = _start(panel, startup_complete=False)

    def broken():
        raise RuntimeError("no dock area")

    monkeypatch.setattr(panel, "_show_palette", broken)
    app.startupCompleted.handlers[0].notify(None)
    assert len(app.messages) == 1 and "no dock area" in app.messages[0]
