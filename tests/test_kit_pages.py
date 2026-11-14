"""The platform's own pages in print-lab load the appliance-ui kit copy in tools/ui (Pi Hub amendment A22, step 13 P1)."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "tools" / "ui"
PANEL = ROOT / "tools" / "fusion" / "ParamsPanel"


def test_the_fusion_panel_links_the_kit_by_a_relative_path_that_resolves():
    page = (PANEL / "palette.html").read_text()
    listed = json.loads((KIT / "VERSION").read_text())["files"]
    hrefs = re.findall(r'<link rel="stylesheet" href="([^"]+)">', page)
    assert hrefs == ["../../ui/tokens.css", "../../ui/components.css"]
    for h in hrefs:
        f = (PANEL / h).resolve()
        assert f.is_file() and f.parent == KIT.resolve() and f.name in listed


def test_the_add_in_opens_the_panel_from_its_resolved_folder():
    # The add-in is installed as a link in Fusion's AddIns folder; from the unresolved path, ../../ui would miss the kit.
    src = (PANEL / "ParamsPanel.py").read_text()
    assert "html = str(HERE / 'palette.html')" in src and "HERE = Path(__file__).resolve().parent" in src
