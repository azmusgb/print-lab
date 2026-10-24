import pytest

from lab.loop.builders import size_strip
from loop_fixtures import project_with_sources

pytestmark = pytest.mark.slow


def test_real_sizing_around_66_fits_45_min(tmp_path):
    p = project_with_sources(tmp_path)
    z0, z1 = size_strip(p, "sources/hexagon_v58_X2D_0.6nozzle.3mf", "v58_06_6in", 66, 45,
                        "sources/hexagon_v57_X2D_0.4nozzle.3mf")
    assert z0 <= 58 and z1 >= 74
