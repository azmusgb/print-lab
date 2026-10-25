"""Per-experiment criteria: an experiment's own per-strip questions (spec 2026-10-25 phone verdicts, design 1)."""
import json

import pytest

from lab.loop.commands import load_experiment, record_verdict, set_criteria
from lab.records.schema import load
from lab.records.store import RecordError
from loop_fixtures import make_project, minimal_experiment, minimal_question, started

PRINT = "print=Printed cleanly?:clean,flawed,failed"
APART = "apart=Twists apart by hand?:yes,hard,no"


@pytest.fixture
def proj(tmp_path):
    return make_project(tmp_path, minimal_question(), [started(minimal_experiment())])


def V(proj, eid="E-009", **kw):
    args = dict(rank=None, strength=None, inconclusive=None, accept=None, defects=[], marks=[], witness=None,
                witness_override=None, anchors=[], not_about_target=False, note=None, replace=False, runs=None)
    args.update(kw)
    return record_verdict(proj, eid, **args)


def test_criteria_are_saved_in_order(proj):
    e = set_criteria(proj, "E-009", [PRINT, APART])
    assert e["criteria"] == [{"key": "print", "label": "Printed cleanly?", "choices": ["clean", "flawed", "failed"]},
                             {"key": "apart", "label": "Twists apart by hand?", "choices": ["yes", "hard", "no"]}]
    assert load_experiment(proj, "E-009")["criteria"] == e["criteria"]


def test_criteria_refused_after_a_verdict(proj):
    V(proj, rank="B>A", strength="clearly")
    with pytest.raises(ValueError, match="already has a verdict"):
        set_criteria(proj, "E-009", [PRINT])


@pytest.mark.parametrize("spec", ["print=Printed cleanly?:clean", "=Label?:a,b", "print:clean,flawed",
                                  "Print=Label?:a,b", "print=Label?:a,b,c,d,e"])
def test_criteria_spec_needs_two_choices_and_a_key(proj, spec):
    with pytest.raises(ValueError, match="key=Label"):
        set_criteria(proj, "E-009", [spec])


def test_criteria_keys_are_unique(proj):
    with pytest.raises(ValueError, match="twice"):
        set_criteria(proj, "E-009", [PRINT, "print=Again?:a,b"])


def test_schema_accepts_criteria_and_rejects_bad_shape(proj, tmp_path):
    e = set_criteria(proj, "E-009", [PRINT])
    e["criteria"] = [{"key": "print", "label": "Printed cleanly?"}]
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(e))
    with pytest.raises(RecordError):
        load(bad, "experiment")


# --- Task 2: the criteria verdict, its finding and the page index ---------------------------------------------

from lab import page_index
from lab.loop import ledger
from lab.loop.outcome import criteria_finding

GRADES = "12A=print:clean,apart:no;12B=print:clean,apart:yes;12C=print:flawed,apart:yes"


@pytest.fixture
def e012(tmp_path):
    e = started(minimal_experiment("E-012", "Q-009"))
    e["variants"].append({"id": "E-012-C", "tab": "12C", "factor_value": 300})
    e["expect"] = None
    p = make_project(tmp_path, minimal_question(experiments=("E-012",)), [e])
    set_criteria(p, "E-012", [PRINT, APART])
    return p


def test_criteria_verdict_by_tab(e012):
    e = V(e012, "E-012", grades=GRADES)
    assert e["owner_verdict"]["kind"] == "criteria"
    assert e["owner_verdict"]["grades"]["E-012-B"] == {"print": "clean", "apart": "yes"}
    assert e["owner_verdict"]["lighting"] == "diagnostic"
    assert e["prediction_outcome"] is None


def test_criteria_verdict_accepts_the_stored_dict(e012):
    stored = {"E-012-A": {"print": "clean", "apart": "no"}, "E-012-B": {"print": "clean", "apart": "yes"},
              "E-012-C": {"print": "flawed", "apart": "yes"}}
    assert V(e012, "E-012", grades=stored)["owner_verdict"]["grades"] == stored


@pytest.mark.parametrize("text,missing", [("12A=print:clean,apart:no;12B=print:clean,apart:yes", "12C"),
                                          ("12A=print:clean,apart:no;12B=print:clean;12C=print:clean,apart:no",
                                           "12B: Twists apart by hand?")])
def test_criteria_verdict_needs_every_strip_and_criterion(e012, text, missing):
    with pytest.raises(ValueError, match=missing):
        V(e012, "E-012", grades=text)


def test_criteria_verdict_refuses_unknown_choice(e012):
    with pytest.raises(ValueError, match="yes, hard, no"):
        V(e012, "E-012", grades=GRADES.replace("apart:no", "apart:maybe"))


def test_criteria_verdict_does_not_move_the_streak(e012):
    from lab.loop.commands import load_question
    V(e012, "E-012", grades=GRADES)
    q, e = load_question(e012, "Q-009"), load_experiment(e012, "E-012")
    assert ledger.streak(q, {"E-012": e}) == 0 and ledger.outcomes(q, {"E-012": e}) == []


def test_criteria_finding_sentence(e012):
    e = V(e012, "E-012", grades=GRADES)
    assert criteria_finding(e) == ("12A: printed clean, didn't come apart. 12B: printed clean, came apart. "
                                   "12C: printed flawed, came apart.")


def test_index_carries_criteria_and_run(e012):
    ix = page_index.build_index(e012.root)
    entry = next(x for x in ix["experiments"] if x["id"] == "E-012")
    assert entry["criteria"] == load_experiment(e012, "E-012")["criteria"] and entry["run"] == "PR-012-01"


def test_needs_you_command_for_criteria(e012):
    ix = page_index.build_index(e012.root)
    entry = next(x for x in ix["experiments"] if x["id"] == "E-012")
    assert entry["needs"]["command"].startswith('uv run lab exp verdict E-012 --grade "12A=print:')
