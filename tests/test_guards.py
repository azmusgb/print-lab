import json

import pytest

from lab.loop.builders import build_experiment, plan_experiment
from lab.loop.guards import approve, check_experiment, run_check, start
from lab.records.schema import load
from lab.records.store import atomic_write_json
from loop_fixtures import PLAN, project_with_sources
from test_builders import fake_slicer


@pytest.fixture
def proj(tmp_path):
    return project_with_sources(tmp_path)


def built(proj, tweak=None, **kw):
    eid = plan_experiment(proj, "Q-009", **{**PLAN, **kw})
    p = proj.experiments / f"{eid}.json"
    if tweak:
        e = json.loads(p.read_text())
        tweak(e)
        atomic_write_json(p, e)
    build_experiment(proj, eid, replace=False, slicer=fake_slicer)
    return eid


def edit(proj, rid, fn, folder="experiments"):
    p = proj.root / folder / f"{rid}.json"
    r = json.loads(p.read_text())
    fn(r)
    atomic_write_json(p, r)


def codes(res, result=None):
    return [g.code for g in res.guards if not g.ok and g.result != "info" and (result is None or g.result == result)]


def test_clean_build_is_ready(proj):
    eid = built(proj)
    r = run_check(proj, eid)
    assert r.status == "ready" and codes(r) == [] and "READY" in r.text
    assert load(proj.experiments / f"{eid}.json", "experiment")["status"] == "ready"


def test_owner_stop_blocks(proj):
    eid = built(proj)
    edit(proj, "Q-009", lambda q: q["stops"].append({"reason": "wrong way", "at": "t", "resumed_at": None,
                                                     "resume": None}), "questions")
    r = check_experiment(proj, eid)
    assert r.status == "blocked" and "owner_stopped" in codes(r, "blocked")


def test_full_part_and_over_per_test_time_both_listed(proj):
    eid = built(proj)
    edit(proj, eid, lambda e: e.update(test_kind="full_part"))
    edit(proj, "Q-009", lambda q: q["budget"].update(max_test_minutes=30), "questions")
    r = check_experiment(proj, eid)
    assert r.status == "needs_approval" and {"full_part_required", "per_test_time"} <= set(codes(r))


@pytest.mark.parametrize("budget,code", [({"max_test_g": 9}, "per_test_material"),
                                         ({"max_minutes": 30}, "question_time"),
                                         ({"max_g": 9}, "question_material")])
def test_budget_guards(proj, budget, code):
    eid = built(proj)
    edit(proj, "Q-009", lambda q: q["budget"].update(budget), "questions")
    assert code in codes(check_experiment(proj, eid), "needs_approval")


def test_exact_budget_boundary_fits(proj):
    eid = built(proj)  # estimate 33.9 min, 9.35 g
    edit(proj, "Q-009", lambda q: q["budget"].update(max_minutes=33.9, max_g=9.35), "questions")
    assert check_experiment(proj, eid).status == "ready"


def test_autonomy_level_1_needs_approval(proj):
    eid = built(proj)
    atomic_write_json(proj.project_json, {"autonomy_level": 1})
    assert "autonomy_level" in codes(check_experiment(proj, eid), "needs_approval")


def test_refuted_dependency(proj):
    first = built(proj)
    edit(proj, first, lambda e: e.update(status="answered", owner_verdict={
        "kind": "ranking", "order": [[f"{first}-A"], [f"{first}-B"]], "strength": "clearly", "about_target": True,
        "by": "owner", "at": "t"}, print_runs=[{"id": "PR-001-01", "build_id": "BLD-001-01"}]))
    eid = built(proj, lambda e: e.update(derived_from_result=[first]))
    assert "refuted_dependency" in codes(check_experiment(proj, eid), "needs_approval")


def test_undeclared_difference_blocks_check_and_start(proj):
    eid = built(proj, lambda e: e["build_spec"]["variants"][1]["settings_patch"].update(outer_wall_speed="60"))
    r = check_experiment(proj, eid)
    assert r.status == "blocked" and "undeclared_difference" in codes(r, "blocked") and "outer_wall_speed" in r.text
    with pytest.raises(ValueError, match="undeclared_difference"):
        start(proj, eid)


def test_blocked_again_at_start_after_hand_edit(proj):
    eid = built(proj)
    assert run_check(proj, eid).status == "ready"
    edit(proj, eid, lambda e: e.update(factor={"name": "outer_wall_speed", "values": ["80", "80"], "unit": "mm/s"}))
    with pytest.raises(ValueError, match="undeclared_difference"):
        start(proj, eid)


def test_stale_build_and_no_estimate(proj):
    eid = built(proj)
    edit(proj, eid, lambda e: e["build_spec"]["variants"][1].update(copies=2))
    assert "stale_build" in codes(check_experiment(proj, eid), "rebuild")
    eid2 = built(proj)
    edit(proj, eid2, lambda e: e["builds"][-1].update(estimate=None))
    assert "no_estimate" in codes(check_experiment(proj, eid2), "rebuild")


def test_retry_limit(proj):
    eid = built(proj)
    edit(proj, eid, lambda e: e.update(print_runs=[
        {"id": f"PR-{eid[2:]}-0{i}", "build_id": f"BLD-{eid[2:]}-01", "failed": {"at_fraction": 0.1, "note": "adhesion"}}
        for i in (1, 2)]))
    r = check_experiment(proj, eid)
    assert "retry_limit" in codes(r, "needs_approval") and "adhesion" in r.text


def test_preliminary_plate_mismatch_needs_approval_and_stays_confounded(proj, monkeypatch):
    import lab.loop.realized as realized
    monkeypatch.setattr(realized, "realization", lambda *a: None)  # the fake slicer's G-code is the same file twice
    first = built(proj, values=["250"], expect="")
    edit(proj, first, lambda e: (e["builds"][-1]["measured"].update(
        layer_time_profile=[[z, 36.0] for z, _ in e["builds"][-1]["measured"]["layer_time_profile"]]),
        e.update(print_runs=[{"id": "PR-001-01", "build_id": e["builds"][-1]["id"]}])))
    eid = built(proj, values=["80"], expect="", references=[f"{first}-A"])
    r = check_experiment(proj, eid)
    assert "plate_mismatch" in codes(r, "needs_approval")
    approve(proj, eid, "testing anyway")
    from lab.loop.commands import refresh_derived
    e = refresh_derived(proj, load(proj.experiments / f"{eid}.json", "experiment"))
    assert e["comparison_validity"]["status"] == "confounded"


def test_owner_stop_cannot_be_approved_away(proj):
    eid = built(proj)
    edit(proj, "Q-009", lambda q: q["stops"].append({"reason": "stop", "at": "t", "resumed_at": None,
                                                     "resume": None}), "questions")
    with pytest.raises(ValueError, match="owner_stopped"):
        approve(proj, eid, "please")


def test_approval_covers_only_its_reasons_and_build(proj):
    eid = built(proj)
    edit(proj, "Q-009", lambda q: q["budget"].update(max_test_minutes=30), "questions")
    approve(proj, eid, "worth 34 min")
    assert check_experiment(proj, eid).status == "approved"
    edit(proj, "Q-009", lambda q: q["budget"].update(max_test_g=5), "questions")  # a new reason appears
    assert check_experiment(proj, eid).status == "needs_approval"


def test_approval_does_not_survive_rebuild(proj):
    eid = built(proj)
    edit(proj, "Q-009", lambda q: q["budget"].update(max_test_minutes=30), "questions")
    approve(proj, eid, "worth it")
    edit(proj, eid, lambda e: e["build_spec"].update(witness=False, note="x"))
    build_experiment(proj, eid, replace=True, slicer=fake_slicer)
    with pytest.raises(ValueError, match="per_test_time"):
        start(proj, eid)


def test_check_result_is_kept_on_the_build_for_the_page(proj):
    eid = built(proj)
    r = run_check(proj, eid)
    b = load(proj.experiments / f"{eid}.json", "experiment")["builds"][-1]
    assert b["check"]["status"] == r.status and b["check"]["at"]
    assert {g["code"] for g in b["check"]["guards"]} == {g.code for g in r.guards}


def test_geometry_warnings_show_in_the_check_without_blocking(proj):
    eid = built(proj)
    r = check_experiment(proj, eid)
    warn = [g for g in r.guards if g.code == "geometry_warning" and "parts-too-close" in g.message]
    assert warn and warn[0].result == "info" and "0.1 mm" in warn[0].message
    assert r.status == "ready" and "geometry_warning" in r.text
