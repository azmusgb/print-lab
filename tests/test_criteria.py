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
