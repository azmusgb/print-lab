"""The page's data: one read-only projection of a project's records (the same JSON Stage 1B pushes to Local AI)."""
import json

from lab import page_index
from loop_fixtures import make_project, minimal_experiment, minimal_question, started


def _verdict(order, strength="clearly"):
    return {"kind": "ranking", "print_runs": [], "order": order, "strength": strength, "about_target": True,
            "marks": [], "witness": None, "witness_override": None, "note": "B is smoother", "by": "owner",
            "lighting": "diagnostic",
            "at": "2026-10-25T10:00:00+00:00", "confirmed": True}


def _project(tmp_path):
    e1 = started(minimal_experiment("E-001", "Q-009"), minutes=40, g=12)
    e1["owner_verdict"] = _verdict([["E-001-B"], ["E-001-A"]])
    e1["status"] = "answered"
    e1["builds"][0]["realization"] = {"feature": "Inner wall", "status": "realized_differently", "same_pairs": [],
                                      "differently": ["E-001-A"],
                                      "variants": {"E-001-A": {"requested": 250.0, "realized": 147.0, "coverage": 0.99},
                                                   "E-001-B": {"requested": 80.0, "realized": 80.0, "coverage": 0.99}}}
    e2 = minimal_experiment("E-002", "Q-009")
    e2.update(status="needs_approval", builds=[{"id": "BLD-002-01", "ok": True, "estimate": {"minutes": 63, "g": 19},
                                                "check": {"status": "needs_approval", "at": "2026-10-25T11:00:00+00:00",
                                                          "guards": [{"code": "per_test_time", "ok": False,
                                                                      "result": "needs_approval",
                                                                      "message": "63 / 45 min per test"}]}}])
    e3 = minimal_experiment("E-003", "Q-009")
    e3.update(status="abandoned", abandoned_reason="replaced by E-002")
    e4 = started(minimal_experiment("E-004", "Q-009"))
    q = minimal_question("Q-009", ("E-001", "E-002", "E-003", "E-004"))
    return make_project(tmp_path, q, [e1, e2, e3, e4])


def test_question_shows_spend_next_estimate_stop_and_evidence(tmp_path):
    ix = page_index.build_index(_project(tmp_path).root)
    q = ix["questions"][0]
    assert q["spent"] == {"minutes": 80, "g": 24} and q["budget"]["minutes"] == 180
    assert q["next"] == {"id": "E-002", "minutes": 63, "g": 19}
    assert q["stop"] == {"kind": None, "text": "continue"}
    assert q["evidence"] == {"informative": 1, "uninformative": 0}


def test_experiment_outcome_validity_and_requested_vs_realized(tmp_path):
    ix = page_index.build_index(_project(tmp_path).root)
    e = {x["id"]: x for x in ix["experiments"]}["E-001"]
    assert e["outcome"] == "supported" and e["validity"]["status"] == "valid"
    assert e["variants"][0] == {"id": "E-001-A", "tab": "1A", "requested": 250.0, "realized": 147.0,
                                "as_asked": False, "unit": "mm/s", "grade": None}
    assert e["usage"] == {"minutes": 40, "g": 12, "minutes_source": "estimate", "g_source": "estimate"}


def test_needs_you_lists_actions_with_commands_most_urgent_first(tmp_path):
    ix = page_index.build_index(_project(tmp_path).root)
    needs = ix["needs"]
    assert [n["id"] for n in needs] == ["E-004", "E-002"]  # a print to judge, then an approval; never the abandoned
    assert needs[0]["action"] == "Judge the print" and 'lab exp verdict E-004 --rank "B>A|A>B|A=B"' in needs[0]["command"]
    assert needs[1]["action"] == "Approve or drop" and "63 / 45 min per test" in needs[1]["why"]
    assert needs[1]["command"].startswith("uv run lab exp approve E-002 --reason")


def test_index_carries_originals_fingerprints_and_problems(tmp_path):
    p = _project(tmp_path)
    (p.experiments / "E-099.json").write_text('{"record_type": "experiment"}')
    ix = page_index.build_index(p.root)
    assert ix["schema"] == page_index.SCHEMA and ix["project"] == "hex-tile"
    assert ix["records"]["E-001"]["payload"]["id"] == "E-001" and len(ix["records"]["E-001"]["sha256"]) == 64
    assert [x["file"] for x in ix["problems"]] == ["experiments/E-099.json"]
    assert "E-099" not in {x["id"] for x in ix["experiments"]}
    json.dumps(ix)  # plain JSON, nothing else


def test_the_verdict_command_fits_the_test(tmp_path):
    one = started(minimal_experiment("E-010", "Q-009"))
    one["variants"] = one["variants"][:1]
    full = started(minimal_experiment("E-011", "Q-009"))
    full.update(test_kind="full_part", variants=full["variants"][:1])
    p = make_project(tmp_path, minimal_question("Q-009", ("E-010", "E-011")), [one, full])
    cmds = {n["id"]: n["command"] for n in page_index.build_index(p.root)["needs"]}
    assert "--rank A " in cmds["E-010"] and '--accept "yes|no"' in cmds["E-011"]


def test_an_abandoned_experiment_needs_nothing_even_if_its_last_check_blocked(tmp_path):
    e = minimal_experiment("E-012", "Q-009")
    e.update(status="abandoned", builds=[{"id": "BLD-012-01", "ok": True, "estimate": {"minutes": 9, "g": 1},
                                          "check": {"status": "blocked", "at": "2026-10-25T01:00:00+00:00",
                                                    "guards": [{"code": "geometry_blocking", "ok": False,
                                                                "result": "blocked", "message": "3 pieces"}]}}])
    p = make_project(tmp_path, minimal_question("Q-009", ("E-012",)), [e])
    assert page_index.build_index(p.root)["needs"] == []


# The owner's 26 Oct review of the lab page.

def test_a_running_print_says_when_it_is_due_and_reports_no_usage_yet(tmp_path):
    ix = page_index.build_index(_project(tmp_path).root, at="2026-10-25T09:10:00+00:00")
    need = next(n for n in ix["needs"] if n["id"] == "E-004")
    e = {x["id"]: x for x in ix["experiments"]}["E-004"]
    assert need["due_at"] == e["due_at"] == "2026-10-25T09:40:00+00:00"
    assert need["why"].startswith("Printing until about ") and "Then look at: bands" in need["why"]
    assert e["usage"] is None  # the estimate isn't usage until the print ends


def test_a_print_past_its_estimate_is_ready_to_judge(tmp_path):
    ix = page_index.build_index(_project(tmp_path).root, at="2026-10-25T10:00:00+00:00")
    need = next(n for n in ix["needs"] if n["id"] == "E-004")
    assert need["why"].startswith("Look at: bands")


def test_an_acceptance_verdict_carries_its_defects(tmp_path):
    full = started(minimal_experiment("E-011", "Q-009"))
    full.update(test_kind="full_part", variants=full["variants"][:1], status="answered", owner_verdict={
        "kind": "acceptance", "good_enough": True, "blocking_defects": ["hard to separate"], "lighting": "installed",
        "print_runs": ["PR-011-01"], "note": "faces good", "by": "owner", "at": "2026-10-26T13:48:01+00:00"})
    p = make_project(tmp_path, minimal_question("Q-009", ("E-011",)), [full])
    v = page_index.build_index(p.root)["experiments"][0]["verdict"]
    assert v["good_enough"] is True and v["defects"] == ["hard to separate"]


# ---- run-bound figures and labelled usage (blueprint R-11, R-16, R-17; F-07, F-08) -----------------------------

def _rebuilt_while_printing(tmp_path):
    e = started(minimal_experiment("E-009"), minutes=60.0, g=20.0)
    e["builds"][0]["realization"] = {"variants": {"E-009-A": {"requested": 250, "realized": 250}}}
    e["builds"].append({"id": "BLD-009-02", "ok": True, "estimate": {"minutes": 90.0, "g": 30.0},
                        "realization": {"variants": {"E-009-A": {"requested": 250, "realized": 999}}}})
    e["print_runs"][0]["started_at"] = "2026-10-25T09:00:00+00:00"
    return make_project(tmp_path, minimal_question(), [e])


def test_a_running_print_shows_its_own_builds_figures_after_a_rebuild(tmp_path):
    p = _rebuilt_while_printing(tmp_path)
    x = page_index.build_index(p.root)["experiments"][0]
    assert x["due_at"] == "2026-10-25T10:00:00+00:00"  # 60 min from BLD-009-01, not 90 from BLD-009-02
    assert x["estimate"] == {"minutes": 60.0, "g": 20.0}
    assert x["variants"][0]["realized"] == 250
    assert x["shown_build"] == "BLD-009-01"


def test_a_running_print_is_reserved_not_used(tmp_path):
    p = _rebuilt_while_printing(tmp_path)
    x = page_index.build_index(p.root)["experiments"][0]
    assert x["usage"] is None
    assert x["reserved"] == {"minutes": 60.0, "g": 20.0}


def test_usage_says_which_figures_were_observed_and_which_are_estimates(tmp_path):
    e = started(minimal_experiment("E-009"), minutes=60.0, g=20.0)
    e["print_runs"][0]["usage"] = {"actual_minutes": 51.0, "actual_g": None, "usage_source": "printer_log",
                                   "completion_fraction": None}
    p = make_project(tmp_path, minimal_question(), [e])
    u = page_index.build_index(p.root)["experiments"][0]["usage"]
    assert u == {"minutes": 51.0, "g": 20.0, "minutes_source": "observed", "g_source": "estimate"}
