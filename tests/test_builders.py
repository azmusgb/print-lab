import json
import shutil
import zipfile
from pathlib import Path

import pytest

from lab.adapters.bambu import read_settings
from lab.jobs import Job, LabToolError
from lab.loop.builders import build_experiment, plan_experiment
from lab.records.schema import load
from lab.records.store import atomic_write_json
from loop_fixtures import PLAN, minimal_question, project_with_sources

SLICED = Path(__file__).parent / "fixtures" / "hex" / "studio_saved_v58_strip.gcode.3mf"


def _job(ok=True):
    return Job(id="job-test-0001", tool="bambu-studio", tool_version="02.08.02.61", command=[], input_sha256={},
               exit_code=0 if ok else 1, stdout="", stderr="" if ok else "boom", ok=ok)


def fake_slicer(path, out_dir, plate, jobs_dir):
    out = Path(out_dir) / (Path(path).name.removesuffix(".3mf") + ".gcode.3mf")
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SLICED, out)
    return out, _job()


def failing_slicer(path, out_dir, plate, jobs_dir):
    raise LabToolError("Bambu Studio couldn't slice it: boom", _job(False))


@pytest.fixture
def proj(tmp_path):
    return project_with_sources(tmp_path)


def test_plan_writes_experiment_then_question(proj):
    eid = plan_experiment(proj, "Q-009", **PLAN)
    e = load(proj.experiments / f"{eid}.json", "experiment")
    assert eid == "E-001" and e["status"] == "planned" and e["provenance"] == "prospective"
    assert [v["id"] for v in e["variants"]] == ["E-001-A", "E-001-B"] and e["variants"][1]["tab"] == "1B"
    assert e["build_spec"]["variants"][1]["settings_patch"] == {"inner_wall_speed": "80"}
    assert e["expect"] == {"better": "E-001-B", "than": "E-001-A", "min_strength": "clearly"}
    assert load(proj.questions / "Q-009.json", "question")["experiments"] == ["E-001"]


def test_plan_leaves_question_unchanged_if_its_write_fails(proj, monkeypatch):
    import lab.loop.builders as b
    real = b.atomic_write_json

    def fail_on_question(path, obj):
        if "questions" in str(path):
            raise OSError("disk")
        real(path, obj)
    monkeypatch.setattr(b, "atomic_write_json", fail_on_question)
    with pytest.raises(OSError):
        plan_experiment(proj, "Q-009", **PLAN)
    assert (proj.experiments / "E-001.json").exists()
    assert load(proj.questions / "Q-009.json", "question")["experiments"] == []


@pytest.mark.parametrize("factor,match", [("inner_wall_speed,outer_wall_speed", "one factor"),
                                          ("wall_color", "isn't on the list")])
def test_plan_refuses_two_factors_and_unknown_factor(proj, factor, match):
    with pytest.raises(ValueError, match=match):
        plan_experiment(proj, "Q-009", **{**PLAN, "factor": factor})


def test_plan_refused_at_level_0(proj):
    atomic_write_json(proj.project_json, {"autonomy_level": 0})
    with pytest.raises(ValueError, match="level 0"):
        plan_experiment(proj, "Q-009", **PLAN)


def test_objects_on_plate_makes_copies(proj):
    eid = plan_experiment(proj, "Q-009", **{**PLAN, "factor": "objects_on_plate", "values": ["2"], "expect": ""})
    e = load(proj.experiments / f"{eid}.json", "experiment")
    assert [v["copies"] for v in e["build_spec"]["variants"]] == [2]


def test_build_records_estimate_profile_plate_and_fingerprints(proj):
    eid = plan_experiment(proj, "Q-009", **PLAN)
    b = build_experiment(proj, eid, replace=False, slicer=fake_slicer)
    assert b["id"] == "BLD-001-01" and b["ok"] and b["estimate"] == {"minutes": 33.9, "g": 9.35}
    assert b["measured"]["layer_time_median_s"] == pytest.approx(18.3, abs=0.3)
    assert b["plate"]["objects"] == ["E-001-A", "E-001-B"]
    assert set(b["inputs"]) >= {"model", "settings", "build_spec_sha256", "builder_version", "builder_fingerprint",
                                "openscad", "bambu_studio"}
    e = load(proj.experiments / f"{eid}.json", "experiment")
    assert e["status"] == "built" and (proj.root / b["artifact"]).exists()
    man = json.loads((proj.prints / "manifest.json").read_text())
    assert man[-1]["build_id"] == "BLD-001-01"


def test_build_again_unchanged_writes_nothing(proj):
    eid = plan_experiment(proj, "Q-009", **PLAN)
    build_experiment(proj, eid, replace=False, slicer=fake_slicer)
    before = (proj.experiments / f"{eid}.json").read_text()
    b = build_experiment(proj, eid, replace=False, slicer=fake_slicer)
    assert b["id"] == "BLD-001-01" and (proj.experiments / f"{eid}.json").read_text() == before


def test_build_spec_change_alone_makes_build_stale(proj):
    eid = plan_experiment(proj, "Q-009", **PLAN)
    build_experiment(proj, eid, replace=False, slicer=fake_slicer)
    p = proj.experiments / f"{eid}.json"
    e = json.loads(p.read_text())
    e["build_spec"]["variants"][1]["copies"] = 2
    atomic_write_json(p, e)
    with pytest.raises(ValueError, match="--replace"):
        build_experiment(proj, eid, replace=False, slicer=fake_slicer)
    b = build_experiment(proj, eid, replace=True, slicer=fake_slicer)
    e = load(p, "experiment")
    assert b["id"] == "BLD-001-02" and [x["id"] for x in e["builds"]] == ["BLD-001-01", "BLD-001-02"]


def test_failed_slice_is_build_failed_with_job_kept(proj):
    eid = plan_experiment(proj, "Q-009", **PLAN)
    with pytest.raises(LabToolError):
        build_experiment(proj, eid, replace=False, slicer=failing_slicer)
    e = load(proj.experiments / f"{eid}.json", "experiment")
    assert e["status"] == "build_failed" and e["builds"][0]["ok"] is False and e["builds"][0]["job"] == "job-test-0001"
    b = build_experiment(proj, eid, replace=True, slicer=fake_slicer)
    assert b["id"] == "BLD-001-02" and load(proj.experiments / f"{eid}.json", "experiment")["status"] == "built"


def test_settings_patch_lands_in_3mf(proj):
    eid = plan_experiment(proj, "Q-009", **{**PLAN, "values": ["80"], "expect": "A=A", "references": []})
    b = build_experiment(proj, eid, replace=False, slicer=fake_slicer)
    s = read_settings(proj.root / b["artifact"])
    assert set(s["inner_wall_speed"]) == {"80"}


def test_per_variant_settings_go_on_their_objects(proj):
    eid = plan_experiment(proj, "Q-009", **PLAN)
    b = build_experiment(proj, eid, replace=False, slicer=fake_slicer)
    with zipfile.ZipFile(proj.root / b["artifact"]) as z:
        ms = z.read("Metadata/model_settings.config").decode()
    assert '<metadata key="inner_wall_speed" value="80"/>' in ms and '<metadata key="inner_wall_speed" value="250"/>' in ms
