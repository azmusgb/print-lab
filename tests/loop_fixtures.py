"""Shared record fixtures for the Stage 1A.1 tests."""
import copy


def minimal_question(qid="Q-009", experiments=("E-009",)):
    return {"schema": 1, "record_type": "question", "id": qid, "project": "hex-tile",
            "question": "What causes the bands?", "status": "active", "autonomy_level": 2,
            "budget": {"max_test_minutes": 45, "max_test_g": 25, "max_minutes": 180, "max_g": 100},
            "experiments": list(experiments), "plans": [], "stops": []}


def minimal_experiment(eid="E-009", qid="Q-009"):
    n = eid.split("-")[1].lstrip("0")
    return copy.deepcopy({
        "schema": 1, "record_type": "experiment", "id": eid, "project": "hex-tile", "question": qid,
        "provenance": "prospective", "question_text": "Do slower inner walls reduce the bands?",
        "hypothesis": "Fast inner walls starve the outer wall.", "prediction": "B is clearly smoother.",
        "test_kind": "height_strip", "factor": {"name": "inner_wall_speed", "values": [250, 80], "unit": "mm/s"},
        "judge_on": "bands", "expect": {"better": f"{eid}-B", "than": f"{eid}-A", "min_strength": "clearly"},
        "status": "planned",
        "variants": [{"id": f"{eid}-A", "tab": f"{n}A", "factor_value": 250},
                     {"id": f"{eid}-B", "tab": f"{n}B", "factor_value": 80}],
        "builds": [], "print_runs": [], "owner_verdict": None})


def started(e, minutes=40.0, g=12.0, z=(60, 72)):
    """The experiment built (one build with an estimate) and started (one print run)."""
    n = e["id"][2:]
    e["build_spec"] = {"kind": "height_strip", "z": list(z)}
    e["builds"] = [{"id": f"BLD-{n}-01", "ok": True, "estimate": {"minutes": minutes, "g": g},
                    "measured": {"layer_time_median_s": 18.0, "layer_time_profile": [[0.2 * i, 18.0] for i in range(1, 61)]}}]
    e["print_runs"] = [{"id": f"PR-{n}-01", "build_id": f"BLD-{n}-01", "started_at": "2026-10-25T09:00:00+00:00",
                        "setup": {}, "usage": None, "failed": None, "photos": []}]
    e["status"] = "printing"
    return e


def make_project(tmp_path, question, exps, name="hex-tile"):
    from lab.records.project import ProjectPaths
    from lab.records.store import atomic_write_json
    paths = ProjectPaths(tmp_path / "projects" / name)
    for e in exps:
        atomic_write_json(paths.experiments / f"{e['id']}.json", e)
    atomic_write_json(paths.questions / f"{question['id']}.json", question)
    return paths


def project_with_sources(tmp_path, question=None):
    """A project with Q-009 and the v58/v57 sources, ready for `exp plan`."""
    import shutil
    from pathlib import Path
    fx = Path(__file__).parent / "fixtures" / "hex"
    paths = make_project(tmp_path, question or minimal_question(experiments=()), [])
    paths.sources.mkdir(parents=True, exist_ok=True)
    for n in ("hexagon_v58_X2D_0.6nozzle.3mf", "hexagon_v57_X2D_0.4nozzle.3mf"):
        shutil.copy2(fx / n, paths.sources / n)
    return paths


PLAN = dict(factor="inner_wall_speed", values=["250", "80"], expect="B>A:clearly", judge_on="bands",
            test_kind="height_strip", source="sources/hexagon_v58_X2D_0.6nozzle.3mf", object="v58_06_6in",
            z=(60.0, 72.0), base="sources/hexagon_v57_X2D_0.4nozzle.3mf", question_text="Do slower inner walls help?",
            hypothesis="Fast inner walls starve the outer wall.", prediction="B (80) is clearly smoother.",
            why="One setting, two strips on one plate.", references=[], adjust={})
