"""Record integrity: a slice job link leaves the experiment valid, and one unreadable record never lets the page or
`lab status` show a question's spend and stop state as if they were complete."""
import json
import zipfile

import pytest

from lab import page_index
from lab.experiments import link_slice_job
from lab.loop import commands
from lab.records.store import RecordError
from lab.status import build_status, format_status_text
from loop_fixtures import make_project, minimal_experiment, minimal_question, started


def _lab_file(tmp_path, eid, run_id):
    p = tmp_path / "x.3mf"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("Metadata/print_lab.json", json.dumps({"experiment_id": eid, "print_run_id": run_id}))
    return p


def test_slice_job_link_leaves_the_project_readable(tmp_path):
    e = started(minimal_experiment("E-009"))
    paths = make_project(tmp_path, minimal_question("Q-009", ("E-009",)), [e])
    assert link_slice_job(paths.root, _lab_file(tmp_path, "E-009", "PR-009-01"), "job-1") == "E-009"
    # `question status`, `exp check` and `question rebuild` all read every record through load()
    assert commands.all_experiments(paths)["E-009"]["print_runs"][0]["slice_job"] == "job-1"
    assert page_index.build_index(paths.root)["problems"] == []
    assert (paths.locks / "E-009.lock").exists()  # taken under the record's lock, like every other mutation


def test_slice_job_link_refuses_an_unreadable_experiment_and_leaves_it_alone(tmp_path):
    e = started(minimal_experiment("E-009"))
    e["surprise"] = 1  # an unknown field: the record fails validation
    paths = make_project(tmp_path, minimal_question("Q-009", ("E-009",)), [])
    path = paths.experiments / "E-009.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(e))
    before = path.read_text()
    with pytest.raises(RecordError, match="unknown field 'surprise'"):
        link_slice_job(paths.root, _lab_file(tmp_path, "E-009", "PR-009-01"), "job-1")
    assert path.read_text() == before


def _broken_project(tmp_path):
    good = started(minimal_experiment("E-001"), minutes=40, g=12)
    bad = started(minimal_experiment("E-002"), minutes=60, g=20)
    paths = make_project(tmp_path, minimal_question("Q-009", ("E-001", "E-002")), [good])
    bad["print_runs"][0]["slice_job"] = {"not": "a string"}  # fails validation
    (paths.experiments / "E-002.json").write_text(json.dumps(bad))
    return paths


def test_question_with_an_unreadable_experiment_does_not_report_totals(tmp_path):
    paths = _broken_project(tmp_path)
    ix = page_index.build_index(paths.root)
    q = ix["questions"][0]
    assert [p["file"] for p in ix["problems"]] == ["experiments/E-002.json"]
    assert q["spent"] is None and q["reserved"] is None
    assert q["stop"]["kind"] == "unknown" and "E-002" in q["stop"]["text"] and q["stop"]["text"] != "continue"
    assert q["streak"] is None and q["evidence"] is None and q["next"] is None


def test_status_does_not_print_incomplete_spend_as_fact(tmp_path):
    paths = _broken_project(tmp_path)
    text = format_status_text(build_status(paths.root, include_printer=False))
    assert "continue" not in text and "Time 40" not in text
    assert "unknown" in text.lower()
