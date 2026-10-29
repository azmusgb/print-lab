"""Qualification Gate: canonical decision, lineage, stale binding and projection."""
import pytest

from lab import qualification
from lab.page_index import build_index
from loop_fixtures import make_project, minimal_experiment, minimal_question, started


def _part(eid, qid, ref=None):
    e = started(minimal_experiment(eid, qid))
    e["test_kind"] = "full_part"
    e["build_spec"] = {"kind": "full_part"}
    e["status"] = "answered"
    e["reference_variants"] = [f"{ref}-A"] if ref else []
    e["owner_verdict"] = {
        "kind": "acceptance",
        "good_enough": True,
        "blocking_defects": [],
        "print_runs": [e["print_runs"][-1]["id"]],
        "lighting": "installed",
        "note": "good enough",
        "by": "owner",
        "at": "2026-10-29T12:00:00+00:00",
    }
    return e


@pytest.fixture
def qualified_project(tmp_path, monkeypatch):
    q = minimal_question("Q-009", experiments=("E-019", "E-023"))
    ref = _part("E-019", "Q-009")
    cur = _part("E-023", "Q-009", ref="E-019")
    paths = make_project(tmp_path, q, [ref, cur])

    monkeypatch.setattr(qualification.obs, "for_experiment", lambda paths, eid: [{"id": "OBS-0001"}])
    monkeypatch.setattr(
        qualification,
        "comparison_validity",
        lambda *a, **k: {"status": "valid", "reasons": []},
    )
    return paths


def _payload(decision="qualified", **changes):
    p = {
        "decision": decision,
        "reason": "Cleaner production face with no regression.",
        "reference_experiment": "E-019",
        "run_seen": "PR-023-01",
        "build_seen": "BLD-023-01",
        "evidence_reviewed": True,
    }
    p.update(changes)
    return p


def test_qualification_promotes_without_rewriting_experiment(qualified_project):
    before = (qualified_project.experiments / "E-023.json").read_bytes()
    rec = qualification.apply_request(
        qualified_project,
        "E-023",
        _payload(),
        request_id="rq-0123456789abcdef",
    )

    assert rec["id"] == "QUAL-0001"
    assert rec["decision"] == "qualified"
    assert rec["previous_reference"] == "E-019"
    assert rec["run"] == "PR-023-01"
    assert (qualified_project.experiments / "E-023.json").read_bytes() == before

    state = qualification.summary(qualified_project)
    assert state["current_reference"] == "E-023"
    assert state["current"]["id"] == "QUAL-0001"
    assert state["history"] == [rec]


def test_continue_is_audited_but_does_not_promote(qualified_project):
    rec = qualification.apply_request(qualified_project, "E-023", _payload("continue"))
    state = qualification.summary(qualified_project)
    assert rec["decision"] == "continue"
    assert state["current_reference"] is None
    assert state["current"] is None
    assert state["history"][-1]["id"] == "QUAL-0001"


def test_stale_run_or_build_is_refused(qualified_project):
    with pytest.raises(ValueError, match="changed since"):
        qualification.apply_request(
            qualified_project,
            "E-023",
            _payload(run_seen="PR-023-99"),
        )


def test_gate_blocks_without_observation(qualified_project, monkeypatch):
    monkeypatch.setattr(qualification.obs, "for_experiment", lambda paths, eid: [])
    g = qualification.gate(
        qualified_project,
        "E-023",
        "E-019",
        evidence_reviewed=True,
    )
    assert not g["ok"]
    assert "no_observation" in {p["code"] for p in g["problems"]}


def test_page_index_includes_qualification_and_fingerprint_changes(qualified_project):
    before = build_index(qualified_project.root, at="2026-10-29T12:00:00+00:00")
    qualification.apply_request(qualified_project, "E-023", _payload("continue"))
    after = build_index(qualified_project.root, at="2026-10-29T12:00:00+00:00")
    assert after["qualification"]["history"][-1]["decision"] == "continue"
    assert after["fingerprint"] != before["fingerprint"]
