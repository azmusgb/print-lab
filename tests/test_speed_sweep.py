"""The speed sweep: 3 to 6 strips on one plate, one wall speed each, graded clean / faint / banded by the owner."""
import json

import pytest

from lab.loop import commands
from lab.loop.builders import build_experiment, flow_cap, plan_experiment
from lab.loop.outcome import prediction_outcome, sweep_finding
from lab.records.schema import load
from loop_fixtures import PLAN, project_with_sources
from test_builders import fake_slicer
from test_commands_verdict import V

SWEEP = {**PLAN, "factor": "outer_wall_speed", "values": ["40", "60", "80", "100"], "test_kind": "speed_sweep",
         "expect": "", "question_text": "Which outer-wall speeds band?", "prediction": "Bands from 100 mm/s."}


@pytest.fixture
def proj(tmp_path):
    return project_with_sources(tmp_path)


def test_the_flow_cap_comes_from_the_settings_like_the_slicer_computes_it(proj):
    # 12 mm³/s over a 0.45 × 0.2 mm rounded line: the 147 mm/s E-005's inner walls really printed at
    assert flow_cap(proj, SWEEP["base"], "inner_wall_speed") == pytest.approx(147.4, abs=0.2)
    assert flow_cap(proj, SWEEP["base"], "outer_wall_speed") == pytest.approx(159.1, abs=0.2)


def test_a_sweep_plans_one_strip_per_speed_with_the_speed_on_its_tab(proj):
    e = load(proj.experiments / f"{plan_experiment(proj, 'Q-009', **SWEEP)}.json", "experiment")
    assert [v["factor_value"] for v in e["variants"]] == ["40", "60", "80", "100"]
    assert [v["tab"] for v in e["variants"]] == ["40", "60", "80", "100"]
    assert [v["settings_patch"] for v in e["build_spec"]["variants"]][0] == {"outer_wall_speed": "40"}


@pytest.mark.parametrize("change, message", [
    ({"values": ["40", "200", "80"]}, "159 mm/s"),                      # over the flow cap: printed at the cap
    ({"factor": "nozzle_temperature", "values": ["210", "220", "230"]}, "speed"),  # not a per-object speed
    ({"values": ["40", "60"]}, "3 to 6"),
    ({"values": ["40", "50", "60", "70", "80", "90", "100"]}, "3 to 6"),
])
def test_a_sweep_that_cant_show_anything_is_refused(proj, change, message):
    with pytest.raises(ValueError, match=message):
        plan_experiment(proj, "Q-009", **{**SWEEP, **change})


def test_the_prediction_bands_from_a_speed_is_kept(proj):
    e = load(proj.experiments / f"{plan_experiment(proj, 'Q-009', **{**SWEEP, 'expect': 'bands>=100'})}.json",
             "experiment")
    assert e["expect"] == {"bands_from": 100.0}


def _printed(proj, expect="bands>=100"):
    eid = plan_experiment(proj, "Q-009", **{**SWEEP, "expect": expect})
    build_experiment(proj, eid, replace=False, slicer=fake_slicer)
    p = proj.experiments / f"{eid}.json"
    e = json.loads(p.read_text())
    e["status"] = "printing"
    e["print_runs"] = [{"id": f"PR-{eid[2:]}-01", "build_id": e["builds"][-1]["id"], "started_at": "2026-10-25T09:00:00+00:00",
                        "setup": {}, "usage": None, "failed": None, "photos": []}]
    p.write_text(json.dumps(e))
    return eid


def test_grades_are_recorded_by_speed_and_every_strip_needs_one(proj):
    eid = _printed(proj)
    with pytest.raises(ValueError, match="100"):
        V(proj, eid, grades="40=clean,60=clean,80=faint")
    e = V(proj, eid, grades="40=clean,60=clean,80=faint,100=banded")
    assert e["owner_verdict"]["kind"] == "sweep"
    assert e["owner_verdict"]["grades"] == {f"{eid}-A": "clean", f"{eid}-B": "clean", f"{eid}-C": "faint",
                                            f"{eid}-D": "banded"}
    assert sweep_finding(e) == "clean up to 60, faint at 80, bands from 100 mm/s"


@pytest.mark.parametrize("grades, outcome", [
    ("40=clean,60=clean,80=clean,100=banded", "supported"),
    ("40=clean,60=banded,80=banded,100=banded", "refuted"),
    ("40=clean,60=clean,80=clean,100=clean", "refuted"),
    ("40=clean,60=clean,80=faint,100=banded", "unresolved"),
])
def test_a_threshold_prediction_is_judged_strip_by_strip(proj, grades, outcome):
    eid = _printed(proj)
    assert V(proj, eid, grades=grades)["prediction_outcome"] == outcome


def test_a_sweep_without_a_prediction_is_a_finding_and_never_moves_the_streak(proj):
    from lab.loop import ledger
    eid = _printed(proj, expect="")
    e = V(proj, eid, grades="40=clean,60=clean,80=banded,100=banded")
    assert e["prediction_outcome"] is None and sweep_finding(e) == "clean up to 60, bands from 80 mm/s"
    q = load(proj.questions / "Q-009.json", "question")
    assert ledger.streak(q, commands.all_experiments(proj)) == 0


def test_grades_judged_in_room_light_dont_count(proj):
    eid = _printed(proj)
    assert V(proj, eid, grades="40=clean,60=clean,80=clean,100=banded", lighting="room")["prediction_outcome"] == \
        "unresolved"


def test_the_page_shows_each_strip_grade_and_the_finding(proj):
    from lab import page_index
    eid = _printed(proj, expect="")
    V(proj, eid, grades="40=clean,60=clean,80=faint,100=banded")
    x = {e["id"]: e for e in page_index.build_index(proj.root)["experiments"]}[eid]
    assert [v["grade"] for v in x["variants"]] == ["clean", "clean", "faint", "banded"]
    assert x["finding"] == "clean up to 60, faint at 80, bands from 100 mm/s"


def test_only_a_sweep_has_a_finding(proj):
    from loop_fixtures import minimal_experiment
    e = minimal_experiment()
    e["variants"][0]["factor_value"] = "sources/hexagon_v58_X2D_0.6nozzle.3mf"
    assert sweep_finding(e) is None
