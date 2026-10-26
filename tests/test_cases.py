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

    # 2 answered -> reproduced
    e2 = minimal_experiment("E-002")
    e2["status"] = "answered"
    e2["owner_verdict"] = {"kind": "ranking", "order": [["E-002-A"]]}
    assert evaluate_confidence([e1, e2]) == ("reproduced", 3)

    # 2 answered with full_part and diagnostic lighting -> proven_for_part
    e2["test_kind"] = "full_part"
    e2["owner_verdict"]["lighting"] = "diagnostic"
    assert evaluate_confidence([e1, e2]) == ("proven_for_part", 4)


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


def test_cases_cli(capsys):
    # Real hex-tile project has answered E-008, E-011, E-012
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
