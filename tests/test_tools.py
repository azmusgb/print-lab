import re
import subprocess

import pytest

from lab.adapters.openscad import openscad_binary
from lab.adapters.bambu import bambu_binary


@pytest.mark.slow
def test_tools_present(tmp_path):
    _, scad_version = openscad_binary()
    assert int(re.match(r"(\d{4})", scad_version).group(1)) >= 2025
    path, bambu_version = bambu_binary()
    assert bambu_version == "02.09.01.70"
    # --help writes result.json into its working directory: keep it out of the checkout
    assert subprocess.run([str(path), "--help"], capture_output=True, text=True, cwd=tmp_path).returncode == 0
