import re

import pytest

from lab.adapters.bambu import extract_gcode
from lab.loop.builders import build_experiment, plan_experiment
from loop_fixtures import PLAN, project_with_sources

pytestmark = pytest.mark.slow


def test_real_build_of_two_v58_strips_matches_e004(tmp_path):
    p = project_with_sources(tmp_path)
    eid = plan_experiment(p, "Q-009", **{**PLAN, "factor": "objects_on_plate", "values": ["2"], "expect": "A=A"})
    b = build_experiment(p, eid, replace=False)
    assert b["estimate"]["minutes"] == pytest.approx(62, abs=3)
    assert b["measured"]["layer_time_median_s"] == pytest.approx(36.8, abs=1.5)


def test_real_per_object_speeds_reach_the_gcode(tmp_path):
    p = project_with_sources(tmp_path)
    eid = plan_experiment(p, "Q-009", **PLAN)
    b = build_experiment(p, eid, replace=False)
    g = extract_gcode(p.root / b["sliced"], 1)
    speeds, feat, feed = set(), None, 0
    for line in g.splitlines():
        if line.startswith("; FEATURE:"):
            feat = line[10:].strip()
        elif line.startswith(("G1", "G0")):
            if m := re.search(r"F(\d+(?:\.\d+)?)", line):
                feed = round(float(m.group(1)) / 60)
            if feat == "Inner wall" and " E" in line:
                speeds.add(feed)
    # 250 mm/s is capped by the filament's maximum flow (about 147 mm/s at these line sizes)
    assert 80 in speeds and max(speeds) > 120
