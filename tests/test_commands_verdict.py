import pytest

from lab.loop.commands import record_verdict
from lab.loop.guards import start
from test_guards import built, proj  # noqa: F401  (fixture)


def test_ranking_verdict(proj):
    eid = built(proj)
    e, _ = start(proj, eid)
    out = record_verdict(proj, eid, rank="B>A", strength="clearly", inconclusive=None, accept=None, defects=[], marks=[],
                         witness=None, witness_override=None, anchors=[], not_about_target=False, note="B is cleaner",
                         replace=False, runs=[e["print_runs"][-1]["id"]], lighting="diagnostic")
    assert out["status"] == "answered"
    assert out["owner_verdict"]["kind"] == "ranking"
    assert out["owner_verdict"]["order"] == [[f"{eid}-B"], [f"{eid}-A"]]
    assert out["owner_verdict"]["strength"] == "clearly"


def test_inconclusive_verdict(proj):
    eid = built(proj)
    e, _ = start(proj, eid)
    out = record_verdict(proj, eid, rank=None, strength=None, inconclusive="lighting was bad", accept=None, defects=[],
                         marks=[], witness=None, witness_override=None, anchors=[], not_about_target=False, note=None,
                         replace=False, runs=[e["print_runs"][-1]["id"]], lighting="diagnostic")
    assert out["owner_verdict"]["kind"] == "inconclusive"


def test_failed_run_requires_inconclusive(proj):
    from lab.loop.commands import record_usage
    eid = built(proj)
    e, _ = start(proj, eid)
    rid = e["print_runs"][-1]["id"]
    record_usage(proj, rid, failed_at_pct=10)
    with pytest.raises(ValueError, match="failed before finishing"):
        record_verdict(proj, eid, rank="B>A", strength="clearly", inconclusive=None, accept=None, defects=[], marks=[],
                       witness=None, witness_override=None, anchors=[], not_about_target=False, note=None,
                       replace=False, runs=[rid], lighting="diagnostic")


def test_verdict_requires_real_run(proj):
    eid = built(proj)
    start(proj, eid)
    with pytest.raises(ValueError, match="isn't a print run"):
        record_verdict(proj, eid, rank="B>A", strength="clearly", inconclusive=None, accept=None, defects=[], marks=[],
                       witness=None, witness_override=None, anchors=[], not_about_target=False, note=None,
                       replace=False, runs=["PR-999-99"], lighting="diagnostic")
