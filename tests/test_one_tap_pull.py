"""One tap to print, the lab's half (A12 plan P2): `lab pull` stages a ready or approved build once the printer has been
idle 10 minutes, and records Pi Hub's Start (`one_tap` requests) on the run (spec S6)."""
from datetime import datetime, timedelta, timezone

from lab.loop.commands import load_experiment
from lab.loop.guards import start
from lab.loop.linking import link_entries
from lab.loop.stage import stage_waiting
from lab.records.schema import load
from test_guards import built, proj  # noqa: F401  (fixture)
from test_pull_actions import apply, iso, req
from test_stage import FakeBambuddy

NOW = datetime.now(timezone.utc)


def one_tap(eid, build, minutes_ago=3, by="Bill's iPhone", **kw):
    r = req("rq-1", "one_tap", eid, {"tapped_at": iso(NOW - timedelta(minutes=minutes_ago)), "build": build,
                                     "queue_item": 41, "library_file": 7} | kw)
    return {**r, "by": by}


def build_id(proj, eid):
    return load(proj.experiments / f"{eid}.json", "experiment")["builds"][-1]["id"]


def log(status="completed", minutes_ago=30, name="other"):
    return [{"id": 9, "print_name": name, "status": status,
             "completed_at": (NOW - timedelta(minutes=minutes_ago)).replace(tzinfo=None).isoformat()}]


# --- S6: Pi Hub's Start recorded on the run ---

def test_one_tap_opens_the_run_at_the_tap_and_says_who_started_it(proj):
    eid = built(proj)
    b = build_id(proj, eid)
    out, _ = apply(proj, one_tap(eid, b))
    assert out[0]["status"] == "applied" and "started from Pi Hub (Bill's iPhone)" in out[0]["message"], out
    run = load_experiment(proj, eid)["print_runs"][-1]
    assert run["started_by"] == "pi-hub one-tap" and run["started_from"] == "one-tap"
    assert run["one_tap"] == {"device": "Bill's iPhone", "queue_item": 41, "library_file": 7,
                              "tapped_at": run["started_at"]}
    assert run["started_at"] == (NOW - timedelta(minutes=3)).replace(microsecond=0).isoformat()


def test_a_print_the_log_linked_first_is_marked_not_doubled(proj):
    eid = built(proj)
    b = build_id(proj, eid)
    link_entries(proj, [{"id": 70, "print_name": f"{proj.name}_{eid}_{b}", "status": "printing",
                         "started_at": (NOW - timedelta(minutes=3)).replace(tzinfo=None).isoformat()}], lambda a: None)
    assert len(load_experiment(proj, eid)["print_runs"]) == 1
    out, _ = apply(proj, one_tap(eid, b))
    e = load_experiment(proj, eid)
    assert out[0]["status"] == "applied" and len(e["print_runs"]) == 1
    assert e["print_runs"][0]["started_by"] == "pi-hub one-tap" and e["print_runs"][0]["bambuddy"]["print"] == 70


def test_the_same_start_twice_is_one_run(proj):
    eid = built(proj)
    b = build_id(proj, eid)
    apply(proj, one_tap(eid, b))
    out, _ = apply(proj, {**one_tap(eid, b), "id": "rq-2"})
    assert "already marked" in out[0]["message"] and len(load_experiment(proj, eid)["print_runs"]) == 1


def test_a_start_of_another_build_is_refused(proj):
    eid = built(proj)
    start(proj, eid)
    out, _ = apply(proj, one_tap(eid, "BLD-999-01"))
    assert out[0]["status"] == "refused" and "lab exp link" in out[0]["message"]
    assert "started_by" not in load_experiment(proj, eid)["print_runs"][-1]


def test_a_start_without_its_facts_is_refused(proj):
    eid = built(proj)
    b = build_id(proj, eid)
    for i, bad in enumerate(({"queue_item": "41"}, {"library_file": None}, {"build": "nope"})):
        r = one_tap(eid, b)
        out, _ = apply(proj, {**r, "id": f"rq-{i}", "payload": r["payload"] | bad})
        assert out[0]["status"] == "refused", bad
    out, _ = apply(proj, {**one_tap(eid, b, minutes_ago=60 * 24 * 8), "id": "rq-old"})
    assert out[0]["status"] == "refused" and "last week" in out[0]["message"]
    assert load_experiment(proj, eid)["print_runs"] == []


# --- staging on idle ---

def ready(proj):
    eid = built(proj)
    from lab.loop.guards import run_check
    assert run_check(proj, eid).status == "ready"
    return eid


def test_a_ready_build_is_staged_once_the_printer_has_been_idle_ten_minutes(proj):
    eid = ready(proj)
    fake, failed = FakeBambuddy(), {}
    out = stage_waiting(proj, log(minutes_ago=11), failed, client=fake)
    assert [e["status"] for e in out] == ["applied"] and "ready to start from Pi Hub" in out[0]["message"]
    assert load(proj.experiments / f"{eid}.json", "experiment")["builds"][-1]["staged"]["library_file"] == 1
    assert stage_waiting(proj, log(minutes_ago=12), failed, client=fake) == []  # already staged: nothing again


def test_nothing_is_staged_while_printing_or_just_finished_or_unknown(proj):
    ready(proj)
    fake = FakeBambuddy()
    assert stage_waiting(proj, log(status="printing", minutes_ago=0), {}, client=fake) == []
    assert stage_waiting(proj, log(minutes_ago=5), {}, client=fake) == []
    assert stage_waiting(proj, None, {}, client=fake) == []
    assert fake.calls == []


def test_a_built_but_unchecked_experiment_is_not_staged(proj):
    built(proj)
    fake = FakeBambuddy()
    assert stage_waiting(proj, log(), {}, client=fake) == [] and fake.calls == []


def test_a_failed_stage_waits_an_hour_before_trying_again(proj):
    eid = ready(proj)
    failed = {}
    out = stage_waiting(proj, log(), failed, client=FakeBambuddy(corrupt=True))
    assert out[0]["status"] == "error" and "isn't the checked build" in out[0]["message"]
    b = build_id(proj, eid)
    assert b in failed
    fake = FakeBambuddy()
    assert stage_waiting(proj, log(), failed, client=fake) == [] and fake.calls == []
    failed[b] -= 3601
    assert stage_waiting(proj, log(), failed, client=fake)[0]["status"] == "applied" and b not in failed


def test_an_empty_print_log_counts_as_idle(proj):
    ready(proj)
    assert stage_waiting(proj, [], {}, client=FakeBambuddy())[0]["status"] == "applied"
