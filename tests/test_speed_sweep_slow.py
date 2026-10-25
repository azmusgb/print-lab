import pytest

from lab.loop.builders import build_experiment, plan_experiment
from lab.loop.guards import check_experiment
from loop_fixtures import project_with_sources
from test_speed_sweep import SWEEP

pytestmark = pytest.mark.slow


def test_a_real_outer_wall_sweep_prints_each_strip_at_its_own_speed(tmp_path):
    p = project_with_sources(tmp_path)
    eid = plan_experiment(p, "Q-009", **{**SWEEP, "z": (64.0, 68.0), "tabs": False})
    build_experiment(p, eid, replace=False)
    r = check_experiment(p, eid)
    real = r.realization
    assert real["status"] == "realized", r.text
    speeds = sorted(round(x["realized"]) for x in real["variants"].values())
    assert speeds == [40, 60, 80, 100]
    assert "factor_not_applied" not in [g.code for g in r.guards if not g.ok]
