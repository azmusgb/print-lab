import json

from lab.cli import main
from lab.loop.cases import (
    evaluate_confidence,
    format_case_detail,
    format_cases_list,
    generate_cases_from_experiments,
    sync_cases,
)
from loop_fixtures import make_project, minimal_experiment, minimal_question


def test_evaluate_confidence():
    # No answered -> candidate
    e1 = minimal_experiment("E-001")
    assert evaluate_confidence([e1]) == ("candidate", 1)

    # 1 answered -> supported
    e1["status"] = "answered"
    e1["owner_verdict"] = {"kind": "ranking", "order": [["E-001-A"]]}
    assert evaluate_confidence([e1]) == ("supported", 2)

    # More answered experiments, a full part, the diagnostic light: counting still stops at supported; anything
    # higher is the owner's review (blueprint R-05)
    e2 = minimal_experiment("E-002")
    e2["status"] = "answered"
    e2["owner_verdict"] = {"kind": "ranking", "order": [["E-002-A"]], "lighting": "diagnostic"}
    e2["test_kind"] = "full_part"
    assert evaluate_confidence([e1, e2]) == ("supported", 2)


def test_generate_cases(tmp_path):
    e1 = minimal_experiment("E-008")
    e1["status"] = "answered"
    e1["owner_verdict"] = {
        "kind": "ranking",
        "order": [["E-008-A"]],
        "by": "owner",
        "at": "2026-10-25T10:00:00+00:00",
    }
    paths = make_project(tmp_path, minimal_question(), [e1])

    cases = generate_cases_from_experiments(paths)
    assert len(cases) >= 1
    c1 = next(c for c in cases if c["id"] == "CASE-001")
    assert c1["factor"] == "part_gap"
    assert "E-008" in c1["experiments"]
    assert c1["rule_proposal"]["rule_name"] == "minimum_back_gap"


def test_cases_cli(capsys, real_project_copy):
    # A copy of the real hex-tile project (answered E-008, E-011, E-012); `case promote` writes to the copy only
    rc = main(["case", "list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Documented Cases & Confidence Ladder:" in out
    assert "CASE-001" in out

    rc = main(["case", "show", "CASE-001"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "CASE-001: Back-to-back Part Gap Fusion" in out
    assert "Proposed Rule:" in out

    rc = main(["case", "check-rule", "CASE-001"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Rule evaluation for CASE-001" in out
    assert "Revisions checked:" in out

    rc = main(["case", "promote", "CASE-001", "--reason", "x"])
    assert rc == 1  # not reviewed yet
    capsys.readouterr()
    rc = main(["case", "review", "CASE-001", "--level", "reproduced", "--reason", "E-008 and E-012 fused"])
    assert rc == 0
    capsys.readouterr()
    rc = main(["case", "promote", "CASE-001", "--reason", "owner endorses"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "✓ Promoted CASE-001 to active rule" in out
    assert "minimum_back_gap" in out
    assert "promoted" in (real_project_copy / "cases" / "CASE-001.json").read_text()


def test_promote_refuses_candidate(tmp_path):
    import pytest
    from lab.loop.cases import Case, promote_case_to_rule, cases_dir
    from lab.records.store import atomic_write_json
    paths = make_project(tmp_path, minimal_question(), [minimal_experiment()])
    c = {
        "id": "CASE-999",
        "confidence": "candidate",
        "ladder_step": 1,
        "rule_proposal": {"rule_name": "dummy"},
    }
    atomic_write_json(cases_dir(paths) / "CASE-999.json", c)

    with pytest.raises(ValueError, match="needs your review"):
        promote_case_to_rule(paths, "CASE-999", reason="x")
