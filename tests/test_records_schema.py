import pytest

from lab.records.schema import load, validate
from lab.records.store import RecordError, atomic_write_json
from loop_fixtures import minimal_experiment, minimal_question


def test_minimal_records_valid(tmp_path):
    validate(minimal_experiment(), "experiment", tmp_path / "E-009.json")
    validate(minimal_question(), "question", tmp_path / "Q-009.json")


def test_wrong_record_type_refused_before_fields(tmp_path):
    with pytest.raises(RecordError, match="is a question record, not an experiment"):
        validate({"schema": 1, "record_type": "question", "id": "Q-001"}, "experiment", tmp_path / "E-009.json")


def test_bad_field_named_with_path(tmp_path):
    e = minimal_experiment()
    e["variants"][1]["tab"] = 4
    with pytest.raises(RecordError, match=r"variants\[1\]\.tab"):
        validate(e, "experiment", tmp_path / "E-009.json")


def test_unknown_key_refused(tmp_path):
    e = minimal_experiment()
    e["verdcit"] = {}
    with pytest.raises(RecordError, match="unknown field 'verdcit'"):
        validate(e, "experiment", tmp_path / "E-009.json")


@pytest.mark.parametrize("change", [lambda e: e.update(provenance="guessed"),
                                    lambda e: e.update(owner_verdict={"kind": "ranking", "order": [["E-009-B"]],
                                                                      "strength": "very", "by": "owner", "at": "x"}),
                                    lambda e: e.update(schema=2)])
def test_bad_values_refused(tmp_path, change):
    e = minimal_experiment()
    change(e)
    with pytest.raises(RecordError):
        validate(e, "experiment", tmp_path / "E-009.json")


def test_question_stops_shape(tmp_path):
    q = minimal_question()
    q["stops"] = [{"reason": "wrong way", "at": "t", "resumed_at": "t2", "resume": None}]
    with pytest.raises(RecordError, match=r"stops\[0\]\.resume"):
        validate(q, "question", tmp_path / "Q-009.json")


def test_load_reads_and_validates(tmp_path):
    p = tmp_path / "E-009.json"
    atomic_write_json(p, minimal_experiment())
    assert load(p, "experiment")["id"] == "E-009"
