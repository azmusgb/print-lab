import json
import shutil

from lab.findings import Finding, worst
from lab.jobs import run_tool


def test_job_success_written(tmp_path):
    job = run_tool(["/bin/echo", "hi"], inputs=[], outputs=[], jobs_dir=tmp_path, tool="echo")
    assert job.ok and job.exit_code == 0 and job.stdout == "hi\n"
    assert json.loads((tmp_path / f"{job.id}.json").read_text())["stdout"] == "hi\n"


def test_job_failure_kept(tmp_path):
    job = run_tool(["/bin/sh", "-c", "echo bad >&2; exit 3"], inputs=[], outputs=[], jobs_dir=tmp_path, tool="sh")
    assert job.ok is False and job.exit_code == 3 and job.stderr == "bad\n"
    assert (tmp_path / f"{job.id}.json").exists()


def test_missing_output_not_ok(tmp_path):
    out = tmp_path / "never.stl"
    job = run_tool(["/bin/echo"], inputs=[], outputs=[out], jobs_dir=tmp_path, tool="echo")
    assert job.ok is False and job.outputs_present == []


def test_paths_with_spaces(tmp_path, hex_dir):
    src = tmp_path / "Hex Tile v55 0.20mm @BBL X2D.json"
    shutil.copy(hex_dir / "Hex Tile v55 0.20mm @BBL X2D.json", src)
    job = run_tool(["/bin/cat", str(src)], inputs=[src], outputs=[], jobs_dir=tmp_path, tool="cat")
    assert job.ok and '"name"' in job.stdout
    assert len(job.input_sha256[str(src)]) == 64


def test_worst_severity():
    f = lambda s: Finding(rule="r", severity=s, where="", why="", fix="", data={})
    assert worst([f("info"), f("blocking"), f("warning")]) == "blocking"
    assert worst([]) is None
