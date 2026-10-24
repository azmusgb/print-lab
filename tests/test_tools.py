import re
import subprocess

import pytest

from lab.adapters.openscad import openscad_binary
from lab.adapters.bambu import bambu_binary


@pytest.mark.slow
def test_tools_present():
    _, scad_version = openscad_binary()
    assert int(re.match(r"(\d{4})", scad_version).group(1)) >= 2025
    path, bambu_version = bambu_binary()
    assert bambu_version == "02.08.02.61"
    assert subprocess.run([str(path), "--help"], capture_output=True, text=True).returncode == 0
