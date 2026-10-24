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
