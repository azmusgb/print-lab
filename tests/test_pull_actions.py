"""`lab pull`: the page's new actions — start (at the tap time), approve (through the guard) and abandon."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from lab import pull
from lab.loop.commands import load_experiment
from test_guards import built, edit, proj  # noqa: F401  (fixture)
from test_pull import FakeLocalAI, _t


def req(rid, kind, eid, payload=None, run_seen=None):
    return {"id": rid, "kind": kind, "experiment": eid, "run_seen": run_seen, "payload": payload or {},
            "at": "2026-10-26T10:00:00Z"}


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


def apply(proj, *reqs):
    with FakeLocalAI(requests=list(reqs)) as fake:
        out = pull.apply_pending(proj.root, _t(fake.base))
        return out, fake


def test_start_request_opens_a_run_at_the_tap_time(proj):
    eid = built(proj)
    tapped = iso(datetime.now(timezone.utc) - timedelta(minutes=12))
    out, fake = apply(proj, req("r1", "start", eid, {"tapped_at": tapped}))
    assert out[0]["status"] == "applied", out
    e = load_experiment(proj, eid)
    assert e["status"] == "printing" and e["print_runs"][-1]["started_at"] == tapped
    assert e["print_runs"][-1].get("started_from") == "page"


def test_start_twice_is_not_two_runs(proj):
    eid = built(proj)
    apply(proj, req("r1", "start", eid))
    out, _ = apply(proj, req("r2", "start", eid))
    assert out[0]["status"] == "applied" and "already started" in out[0]["message"]
    assert len(load_experiment(proj, eid)["print_runs"]) == 1


def test_stale_start_refused(proj):
    eid = built(proj)
    out, _ = apply(proj, req("r1", "start", eid, run_seen="PR-999-01"))
    assert out[0]["status"] == "refused" and "changed since" in out[0]["message"]
    assert load_experiment(proj, eid)["print_runs"] == []


@pytest.mark.parametrize("offset,used", [(timedelta(minutes=30), False), (timedelta(hours=-7), False),
                                         (timedelta(hours=-2), True)])
def test_tap_time_bounds(proj, offset, used):
    eid = built(proj)
    tapped = iso(datetime.now(timezone.utc) + offset)
    apply(proj, req("r1", "start", eid, {"tapped_at": tapped}))
    got = load_experiment(proj, eid)["print_runs"][-1]["started_at"]
    assert (got == tapped) is used


def seen(proj, eid):
    """What the page showed: the build and the guards it asked the owner to approve."""
    from lab.loop.guards import check_experiment
    r = check_experiment(proj, eid)
    return {"build_seen": r.build["id"], "reasons_seen": [x.code for x in r.failed("needs_approval")]}


def test_approve_request_uses_the_guard(proj):
    eid = built(proj)
    edit(proj, "Q-009", lambda q: q["budget"].update(max_test_minutes=30), "questions")
    out, _ = apply(proj, req("r1", "approve", eid, {"reason": "worth 34 min", **seen(proj, eid)}))
    assert out[0]["status"] == "applied", out
    e = load_experiment(proj, eid)
    assert e["status"] == "approved" and e["approval"]["reason"] == "worth 34 min"
    assert e["approval"]["build_id"] == e["builds"][-1]["id"] and e["approval"]["approved_reasons"]


def test_approve_refused_when_nothing_to_approve(proj):
    eid = built(proj)
    out, _ = apply(proj, req("r1", "approve", eid, {"reason": "go"}))
    assert out[0]["status"] == "refused" and "nothing to approve" in out[0]["message"]


def test_owner_stop_still_cannot_be_approved_from_the_page(proj):
    eid = built(proj)
    edit(proj, "Q-009", lambda q: q["stops"].append({"reason": "stop", "at": "t", "resumed_at": None,
                                                     "resume": None}), "questions")
    out, _ = apply(proj, req("r1", "approve", eid, {"reason": "please"}))
    assert out[0]["status"] == "refused" and "owner_stopped" in out[0]["message"]


def test_abandon_needs_a_reason(proj):
    eid = built(proj)
    out, _ = apply(proj, req("r1", "abandon", eid, {"reason": "  "}))
    assert out[0]["status"] == "refused" and "reason" in out[0]["message"]
    assert load_experiment(proj, eid)["status"] != "abandoned"


def test_abandon_request(proj):
    eid = built(proj)
    out, _ = apply(proj, req("r1", "abandon", eid, {"reason": "superseded by v62"}))
    assert out[0]["status"] == "applied"
    e = load_experiment(proj, eid)
    assert e["status"] == "abandoned" and e["abandoned_reason"] == "superseded by v62"


# Security review of b1e30d3: an approval binds to what the page showed; ids from the request are checked.
def test_approve_refused_when_the_guards_changed_since_the_page(proj):
    eid = built(proj)
    edit(proj, "Q-009", lambda q: q["budget"].update(max_test_minutes=30), "questions")
    shown = seen(proj, eid)
    edit(proj, "Q-009", lambda q: q["budget"].update(max_test_g=5), "questions")  # a new reason appears
    out, _ = apply(proj, req("r1", "approve", eid, {"reason": "worth it", **shown}))
    assert out[0]["status"] == "refused" and "changed since" in out[0]["message"]
    assert load_experiment(proj, eid)["status"] != "approved"


def test_approve_needs_what_the_page_showed_and_a_reason(proj):
    eid = built(proj)
    edit(proj, "Q-009", lambda q: q["budget"].update(max_test_minutes=30), "questions")
    out, _ = apply(proj, req("r1", "approve", eid, {"reason": "ok"}), req("r2", "approve", eid, {**seen(proj, eid)}))
    assert [o["status"] for o in out] == ["refused", "refused"]


@pytest.mark.parametrize("bad", ["../../etc/x", "E-1/../E-2", "", None, "Q-009"])
def test_request_ids_are_checked(proj, bad):
    out, _ = apply(proj, req("r1", "abandon", bad, {"reason": "x"}))
    assert out[0]["status"] == "refused" and "experiment id" in out[0]["message"]


@pytest.mark.parametrize("kind,eid,run", [("verdict", "../x", None), ("photos", "E-001", "../../PR"), ("verdict", "E-001", "PR/1")])
def test_verdict_and_photo_ids_are_checked_too(proj, kind, eid, run):
    r = req("r1", kind, eid, {"photos": []})
    r["run"] = run
    out, _ = apply(proj, r)
    assert out[0]["status"] == "refused" and "id" in out[0]["message"]


def test_one_unexpected_failure_is_recorded_and_the_rest_are_processed(proj):
    """A request that raises something other than ValueError (here a source file deleted after the build, which
    start's fingerprint check reads) must not escape: it is recorded as failed with its reason, so it isn't retried
    forever, and the requests sorted after it are still applied."""
    eid = built(proj)
    for src in (proj.root / "sources").iterdir():  # every model file start's fingerprints read
        src.unlink()
    bad = req("r1", "start", eid)
    bad["at"] = "2026-10-26T10:00:00Z"
    later = req("r2", "abandon", eid, {"reason": "superseded"})
    later["at"] = "2026-10-26T10:00:01Z"
    out, fake = apply(proj, bad, later)
    assert [o["id"] for o in out] == ["r1", "r2"], out
    assert out[0]["status"] == "error" and "FileNotFoundError" in out[0]["message"]
    assert "r1" in (proj.root / "requests.jsonl").read_text()
    assert set(fake.results) == {"r1", "r2"}


def test_a_wrongly_typed_payload_does_not_stop_the_pull(proj):
    eid = built(proj)
    wrong = req("r1", "start", eid, ["not", "a", "dict"])
    wrong["at"] = "2026-10-26T10:00:00Z"
    later = req("r2", "abandon", eid, {"reason": "superseded"})
    later["at"] = "2026-10-26T10:00:01Z"
    out, _ = apply(proj, wrong, later)
    assert [o["status"] for o in out] == ["error", "applied"], out


def _raise(exc):
    def f(*a, **k):
        raise exc
    return f


def test_a_transient_os_error_is_not_recorded_so_the_request_is_retried(proj, monkeypatch):
    eid = built(proj)
    monkeypatch.setattr(pull, "_act", _raise(OSError(28, "No space left on device")))
    later = req("r2", "abandon", eid, {"reason": "superseded"})
    later["at"] = "2026-10-26T10:00:01Z"
    out, fake = apply(proj, req("r1", "start", eid), later)
    assert out[0]["id"] == "r1" and out[0]["status"] == "error", out
    assert not (proj.root / "requests.jsonl").exists() or "r1" not in (proj.root / "requests.jsonl").read_text()
    assert "r1" not in fake.results


def test_an_unexpected_error_is_recorded_as_error_not_as_a_refusal(proj, monkeypatch):
    eid = built(proj)
    monkeypatch.setattr(pull, "_act", _raise(KeyError("boom")))
    out, fake = apply(proj, req("r1", "start", eid))
    assert out[0]["status"] == "error" and "KeyError" in out[0]["message"], out
    assert '"status": "error"' in (proj.root / "requests.jsonl").read_text()


def test_every_posted_result_status_is_one_local_ai_accepts(proj, monkeypatch):
    """Local AI takes only applied / refused / duplicate for a request result: an error is posted as a refusal whose
    text says it couldn't be applied, while requests.jsonl keeps `error`."""
    eid = built(proj)
    bad_kind = req("r3", "nonsense", eid)
    refused = req("r4", "abandon", eid, {"reason": "  "})
    ok = req("r5", "abandon", eid, {"reason": "superseded"})
    dup = req("r6", "abandon", eid, {"reason": "again"})
    for i, r in enumerate((bad_kind, refused, ok, dup)):
        r["at"] = f"2026-10-26T10:00:0{i + 1}Z"
    (proj.root / "requests.jsonl").write_text(json.dumps({"id": "r6", "status": "applied"}) + "\n")
    boom = req("r1", "start", eid)
    boom["at"] = "2026-10-26T10:00:00Z"
    real_act = pull._act
    monkeypatch.setattr(pull, "_act", lambda paths, kind, *a, **k: (_ for _ in ()).throw(KeyError("boom"))
                        if kind == "start" else real_act(paths, kind, *a, **k))
    out, fake = apply(proj, boom, bad_kind, refused, ok, dup)
    assert {"error", "refused", "duplicate"} <= {o["status"] for o in out}, out
    assert set(fake.results) == {"r1", "r3", "r4", "r5", "r6"}
    assert {v["status"] for v in fake.results.values()} <= {"applied", "refused", "duplicate"}
    assert fake.results["r1"]["status"] == "refused" and "couldn't be applied: KeyError" in fake.results["r1"]["message"]
    assert '"id": "r1", "status": "error"' in (proj.root / "requests.jsonl").read_text()
