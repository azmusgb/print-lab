import json
import shutil
from pathlib import Path

import pytest

from lab.records.migrate import migrate_project
from lab.records.project import ProjectPaths
from lab.records.schema import load
from lab.loop.plate import layer_time_profile, median_layer_time

REAL = Path(__file__).parent.parent / "projects" / "hex-tile"


@pytest.fixture(scope="module")
def migrated(tmp_path_factory):
    if not (REAL / "prints" / "sliced" / "hex-tile_E004_PR006.gcode.3mf").exists():
        pytest.skip("sliced prints not present on this machine")
    root = tmp_path_factory.mktemp("lab") / "projects" / "hex-tile"
    shutil.copytree(REAL, root, ignore=shutil.ignore_patterns(".locks", "questions", "sources", "experiments"))
    shutil.copytree(Path(__file__).parent / "fixtures" / "migration", root / "experiments")  # the records before 1A.1
    paths = ProjectPaths(root)
    migrate_project(paths)
    return paths


def exp(paths, n):
    return load(paths.experiments / f"E-{n:03d}.json", "experiment")


def test_migration_creates_q001_and_validates(migrated):
    q = load(migrated.questions / "Q-001.json", "question")
    assert q["question"] == "What causes the bands on v58's face?"
    assert q["experiments"] == ["E-001", "E-002", "E-003", "E-004"]
    assert [p["id"] for p in q["plans"]] == ["P-001", "P-002"]
    for e in q["experiments"]:
        assert load(migrated.experiments / f"{e}.json", "experiment")["question"] == "Q-001"


def test_provenance(migrated):
    assert [exp(migrated, i)["provenance"] for i in (1, 2, 3, 4)] == ["migrated"] * 2 + ["prospective"] * 2


def test_e001_strength_unknown_and_e002_analysis_post_hoc(migrated):
    v = exp(migrated, 1)["owner_verdict"]
    assert v["order"] == [["E-001-B"], ["E-001-A"]] and v["strength"] is None and v["about_target"] is None
    e2 = exp(migrated, 2)
    assert e2["analysis"][0]["provenance"] == "post_hoc"
    assert e2["owner_verdict"]["order"] == [["E-002-A"], ["E-001-B"]] and e2["reference_variants"] == ["E-001-B"]


def test_e004_prospective_plan(migrated):
    e = exp(migrated, 4)
    assert e["expect"] == {"better": "E-002-A", "than": "E-004-A", "min_strength": "clearly"}
    assert e["reference_variants"] == ["E-002-A"] and e["status"] == "printing"
    assert e["print_runs"][0]["id"] == "PR-006" and e["print_runs"][0]["setup"]["nozzle"] == "0.4/0.4mm"


def test_layer_times_measured(migrated):
    m1 = exp(migrated, 1)["builds"][1]["measured"]["layer_time_median_s"]
    m2 = exp(migrated, 2)["builds"][-1]["measured"]["layer_time_median_s"]
    assert m1 == pytest.approx(34.8, abs=0.5) and m2 == pytest.approx(18.4, abs=0.5)
    assert exp(migrated, 4)["builds"][-1]["plate"]["objects"] == ["v58 strip Z60-72 (1 of 2)", "v58 strip Z60-72 (2 of 2)"]


def test_sources_copied_with_provenance(migrated):
    s = json.loads((migrated.sources / "sources.json").read_text())
    assert {x["path"] for x in s} == {"sources/hexagon_v56_X2D_0.6nozzle.3mf", "sources/hexagon_v57_X2D_0.4nozzle.3mf",
                                      "sources/hexagon_v58_X2D_0.6nozzle.3mf"}
    assert all(x["source"] == "migration_fixture" and len(x["sha256"]) == 64 for x in s)


def test_nothing_lost(migrated):
    assert exp(migrated, 1)["legacy"]["print_runs"][1]["result"]["owner_words"].startswith("the ribbed back")


def test_migration_is_idempotent(migrated):
    assert migrate_project(migrated) == ["already migrated"]


def test_median_layer_time_window():
    prof = [[0.2, 10.0], [1.0, 20.0], [2.0, 30.0], [3.0, 40.0]]
    assert median_layer_time(prof) == 25.0 and median_layer_time(prof, (1.0, 2.0)) == 25.0
    assert layer_time_profile("") == []
