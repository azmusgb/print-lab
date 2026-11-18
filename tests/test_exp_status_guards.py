"""approve, check and abandon respect the experiment's status (spec: a started, answered or abandoned experiment isn't
approvable or checkable; an answered or abandoned one isn't abandonable)."""
import pytest

from lab.loop.commands import abandon
from lab.loop.guards import approve, check_experiment, run_check
from lab.records.schema import load
from test_guards import built, edit, proj  # noqa: F401  (fixture)


def _needs_approval(proj):
    eid = built(proj)
    edit(proj, eid, lambda e: e.update(test_kind="full_part"))  # a full part always needs approval
    assert check_experiment(proj, eid).status == "needs_approval"
    return eid


def _status(proj, eid):
    return load(proj.experiments / f"{eid}.json", "experiment")["status"]


@pytest.mark.parametrize("status", ["printing", "answered", "abandoned"])
def test_approve_refuses_a_started_or_finished_experiment(proj, status):
    eid = _needs_approval(proj)
    edit(proj, eid, lambda e: e.update(status=status))
    with pytest.raises(ValueError, match=status):
        approve(proj, eid, "ok")
    assert _status(proj, eid) == status


@pytest.mark.parametrize("status", ["printing", "answered", "abandoned"])
def test_check_refuses_a_started_or_finished_experiment(proj, status):
    eid = built(proj)
    edit(proj, eid, lambda e: e.update(status=status))
    with pytest.raises(ValueError, match=status):
        run_check(proj, eid)
    assert _status(proj, eid) == status


@pytest.mark.parametrize("status", ["answered", "abandoned"])
def test_abandon_refuses_a_finished_experiment(proj, status):
    eid = built(proj)
    edit(proj, eid, lambda e: e.update(status=status, abandoned_reason="first"))
    with pytest.raises(ValueError, match=status):
        abandon(proj, eid, "changed my mind")
    e = load(proj.experiments / f"{eid}.json", "experiment")
    assert e["status"] == status and e["abandoned_reason"] == "first"


@pytest.mark.parametrize("status", ["planned", "built", "ready", "needs_approval", "approved", "printing"])
def test_abandon_still_works_before_a_verdict(proj, status):
    eid = built(proj)
    edit(proj, eid, lambda e: e.update(status=status))
    assert abandon(proj, eid, "no longer needed")["status"] == "abandoned"
