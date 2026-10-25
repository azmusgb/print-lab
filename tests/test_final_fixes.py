"""Fixes from the final Stage 1A.1 review: each pins a way an invalid comparison could have counted as evidence."""
import contextlib
import json

import pytest

from lab.loop import commands
from lab.loop.builders import plan_experiment
from lab.loop.guards import check_experiment
from lab.records.store import atomic_write_json
from loop_fixtures import PLAN, make_project, minimal_experiment, minimal_question, project_with_sources, started
from test_commands_verdict import V
from test_guards import built, codes


@pytest.fixture
def proj(tmp_path):
    return project_with_sources(tmp_path)


@pytest.fixture
def printed(tmp_path):
    return make_project(tmp_path, minimal_question(), [started(minimal_experiment())])


def test_a_factor_the_builder_cant_apply_is_refused_at_plan(proj):
    with pytest.raises(ValueError, match="model_parameter.*can't build"):
        plan_experiment(proj, "Q-009", **{**PLAN, "factor": "model_parameter", "values": ["rib_depth=1", "rib_depth=3"],
                                          "expect": "A=B"})


def test_variants_that_dont_differ_in_the_factor_block(proj):
    eid = built(proj, lambda e: e["build_spec"]["variants"][1]["settings_patch"].update(inner_wall_speed="250"))
    r = check_experiment(proj, eid)
    assert r.status == "blocked" and "factor_not_applied" in codes(r, "blocked")


def test_a_reference_that_cant_be_compared_blocks(proj):
    ref = started(minimal_experiment("E-050"))  # printed, but its print file is gone
    atomic_write_json(proj.experiments / "E-050.json", ref)
    eid = built(proj, references=["E-050-A"])
    r = check_experiment(proj, eid)
    assert "reference_not_comparable" in codes(r, "blocked") and "E-050-A" in r.text


def test_a_ranking_on_a_failed_print_is_refused(printed):
    e = json.loads((printed.experiments / "E-009.json").read_text())
    e["print_runs"][0]["failed"] = {"at_pct": 10}
    atomic_write_json(printed.experiments / "E-009.json", e)
    with pytest.raises(ValueError, match="failed"):
        V(printed, rank="B>A", strength="clearly")
    assert V(printed, inconclusive="stopped at 10 %")["prediction_outcome"] == "inconclusive"


def test_a_ranking_not_under_the_diagnostic_light_is_unresolved(printed):
    assert V(printed, rank="B>A", strength="clearly", lighting="room")["prediction_outcome"] == "unresolved"
    assert V(printed, rank="B>A", strength="clearly", replace=True)["prediction_outcome"] == "supported"


def test_an_anchor_judgment_must_name_the_experiments_anchor(printed):
    with pytest.raises(ValueError, match="no anchor"):
        V(printed, rank="B>A", strength="clearly", anchors=["X=Y:same"])


def test_rebuild_rereads_each_experiment_under_its_lock(printed, monkeypatch):
    real, seen = commands.record_lock, []

    @contextlib.contextmanager
    def lock(lock_dir, rid, command, **kw):
        seen.append(rid)
        p = printed.experiments / f"{rid}.json"
        e = json.loads(p.read_text())
        e["hypothesis"] = "changed by a verdict that just finished"
        atomic_write_json(p, e)
        with real(lock_dir, rid, command, **kw):
            yield
    monkeypatch.setattr(commands, "record_lock", lock)
    V(printed, rank="B>A", strength="clearly")  # gives rebuild something to refresh
    seen.clear()
    e = json.loads((printed.experiments / "E-009.json").read_text())
    e["prediction_outcome"] = None  # stale cache, so rebuild saves
    atomic_write_json(printed.experiments / "E-009.json", e)
    commands.rebuild_question(printed, "Q-009")
    assert "E-009" in seen
    e = json.loads((printed.experiments / "E-009.json").read_text())
    assert e["hypothesis"] == "changed by a verdict that just finished" and e["prediction_outcome"] == "supported"
