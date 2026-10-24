import pytest

from lab.loop.builders import size_strip
from loop_fixtures import project_with_sources

SRC, BASE = "sources/hexagon_v58_X2D_0.6nozzle.3mf", "sources/hexagon_v57_X2D_0.4nozzle.3mf"


@pytest.fixture
def proj(tmp_path):
    return project_with_sources(tmp_path)


def flat(z0, z1, minutes_per_mm=4.0, edge=None):
    """A fake slice: steady 18 s layers, optionally disturbed for `edge` mm next to each cut."""
    prof = []
    h = round(z1 - z0, 3)
    for i in range(1, int(h / 0.2) + 1):
        z = round(0.2 * i, 3)
        t = 18.0
        if edge and min(z, h - z) < edge:
            t = 8.0
        prof.append([z, t])
    return h * minutes_per_mm, prof


def test_smallest_fitting_strip_chosen(proj):
    z = size_strip(proj, SRC, "v58_06_6in", 66, 70, BASE, measure=lambda a, b: flat(a, b))
    assert z == (58.0, 74.0)   # judged 64-68, margin 6: 16 mm at 4 min/mm = 64 min


def test_margin_grows_on_cut_edge_effect(proj):
    # cut effects reach 6.5 mm in: a 6 mm margin isn't representative, 8 is
    z = size_strip(proj, SRC, "v58_06_6in", 66, 90, BASE, measure=lambda a, b: flat(a, b, edge=6.5))
    assert z == (56.0, 76.0)


def test_no_representative_strip_fits_is_an_error(proj):
    with pytest.raises(ValueError, match=r"No representative strip fits 30 min; the smallest is 64 min \(margin 6 mm\)"):
        size_strip(proj, SRC, "v58_06_6in", 66, 30, BASE, measure=lambda a, b: flat(a, b))


def test_never_falls_back_to_a_non_representative_strip(proj):
    def spiky(z0, z1):  # every candidate's judged band has disturbed edge layers
        m = (z1 - z0 - 4) / 2
        minutes, prof = flat(z0, z1)
        return minutes, [[z, 40.0 if abs(z - m) < 0.5 or abs(z - (m + 4)) < 0.5 else t] for z, t in prof]
    with pytest.raises(ValueError, match="No representative strip around 66 mm"):
        size_strip(proj, SRC, "v58_06_6in", 66, 200, BASE, measure=spiky)
