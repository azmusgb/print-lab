"""Observation records (spec docs/superpowers/specs/2026-10-26-observation-records-design.md, rev 2)."""
import json
import threading

import pytest

from lab.records import observations as obs
from loop_fixtures import make_project, minimal_experiment, minimal_question, started

ALL = ("face", "separation", "backing", "mounting", "acceptance")


def na(note="not looked at"):
    return {"status": "not_assessed", "value": None, "note": None}


def assessed(value, note=None):
    return {"status": "assessed", "value": value, "note": note}


def subject(kind, **kw):
    base = {"kind": kind, "experiment": "E-009", "run": "PR-009-01", "build": "BLD-009-01", "variant": "E-009-A",
            "label": "9A", "tile": None, "identified": "confirmed", "note": None}
    return {**base, **kw}


def snap(kind, outcomes=None, **subj):
    allowed = obs.ALLOWED[kind]
    out = {k: na() for k in allowed}
    out.update(outcomes or {})
    return {"subject": subject(kind, **subj), "viewing": {"light": "room"}, "outcomes": out,
            "source": {"kind": "owner_report", "words": "as seen", "evidence": [], "occurred_at": None,
                       "attributed_by": "phone_session"}}


PHONE = {"actor": "owner", "channel": "phone"}


@pytest.fixture
def paths(tmp_path):
    return make_project(tmp_path, minimal_question(), [started(minimal_experiment("E-009"))])


def session(paths, request_id="req-1", snapshots=None, submitted=PHONE):
    snapshots = snapshots or [snap("pair", {"separation": assessed("effort")}),
                              snap("tile", {"face": assessed("clean")}, tile="left"),
                              snap("tile", {"face": assessed("flawed", "ridge at 14 mm")}, tile="right")]
    return obs.record_session(paths, snapshots, submitted={**submitted, "request_id": request_id})


# 1. subject-valid fields
@pytest.mark.parametrize("kind, bad", [("tile", "separation"), ("pair", "face"), ("run", "face")])
def test_an_outcome_the_subject_cant_have_is_refused(paths, kind, bad):
    s = snap(kind)
    s["outcomes"][bad] = assessed("clean" if bad == "face" else "effort")
    with pytest.raises(ValueError, match=f"{bad}.*{kind}"):
        obs.record_session(paths, [s], submitted={**PHONE, "request_id": "r"})


def test_a_snapshot_missing_an_allowed_outcome_is_refused(paths):
    s = snap("pair")
    del s["outcomes"]["acceptance"]
    with pytest.raises(ValueError, match="acceptance"):
        obs.record_session(paths, [s], submitted={**PHONE, "request_id": "r"})


# 2. linked observations stay separate
def test_a_session_makes_linked_observations_that_dont_touch_each_other(paths):
    receipt = session(paths)
    recs = [obs.load(paths, i) for i in receipt["ids"]]
    assert len({r["revisions"][0]["subject"]["group"] for r in recs}) == 1
    kinds = sorted(obs.latest(r)["subject"]["kind"] for r in recs)
    assert kinds == ["pair", "tile", "tile"]
    pair = next(r for r in recs if obs.latest(r)["subject"]["kind"] == "pair")
    assert obs.latest(pair)["outcomes"]["separation"]["value"] == "effort"


# 3. missing answers
def test_not_applicable_needs_a_reason_and_nothing_defaults(paths):
    s = snap("pair", {"separation": {"status": "not_applicable", "value": None, "note": None}})
    with pytest.raises(ValueError, match="why"):
        obs.record_session(paths, [s], submitted={**PHONE, "request_id": "r"})
    s["outcomes"]["separation"]["note"] = "the pair failed to print"
    r = obs.record_session(paths, [s], submitted={**PHONE, "request_id": "r"})
    o = obs.latest(obs.load(paths, r["ids"][0]))["outcomes"]
    assert o["separation"] == {"status": "not_applicable", "value": None, "note": "the pair failed to print"}
    assert o["acceptance"]["status"] == "not_assessed"


def test_an_assessed_outcome_needs_a_known_value(paths):
    s = snap("pair", {"separation": {"status": "assessed", "value": "sort of", "note": None}})
    with pytest.raises(ValueError, match="separation"):
        obs.record_session(paths, [s], submitted={**PHONE, "request_id": "r"})


# 4. owner attribution
def test_an_owner_report_from_the_cli_needs_the_terminal_confirmation(paths):
    with pytest.raises(ValueError, match="your own words"):
        session(paths, submitted={"actor": "owner", "channel": "cli"})
    r = session(paths, submitted={"actor": "owner", "channel": "cli", "tty_confirmed": True})
    assert r["ids"]


def test_claude_cant_file_an_owner_report(paths):
    with pytest.raises(ValueError, match="ai_reading"):
        session(paths, submitted={"actor": "claude", "channel": "cli", "tty_confirmed": True})


def test_an_imported_owner_report_needs_the_record_it_came_from(paths):
    s = snap("pair")
    s["source"]["attributed_by"] = None
    with pytest.raises(ValueError, match="attributed_by"):
        obs.record_session(paths, [s], submitted={"actor": "import", "channel": "import", "request_id": None})


# 5. complete snapshots and corrections
def test_a_correction_is_a_complete_snapshot_and_keeps_the_old_revision(paths):
    rid = session(paths)["ids"][0]
    new = snap("pair", {"separation": assessed("easily")})
    del new["outcomes"]["acceptance"]
    with pytest.raises(ValueError, match="acceptance"):
        obs.correct(paths, rid, expected_rev=1, snapshot=new, reason="misread", submitted=PHONE)
    new = snap("pair", {"separation": assessed("easily")})
    rec = obs.correct(paths, rid, expected_rev=1, snapshot=new, reason="misread", submitted=PHONE)
    assert [r["rev"] for r in rec["revisions"]] == [1, 2]
    assert rec["revisions"][0]["outcomes"]["separation"]["value"] == "effort"
    assert rec["revisions"][1]["correction"]["reason"] == "misread"


def test_a_correction_flags_interpretations_that_cite_the_old_revision(paths):
    rid = session(paths)["ids"][0]
    iid = obs.interpret(paths, claim="tacks too strong", by="claude", cites=[{"observation": rid, "rev": 1}])
    obs.correct(paths, rid, expected_rev=1, snapshot=snap("pair", {"separation": assessed("easily")}),
                reason="misread", submitted=PHONE)
    assert obs.load_interpretation(paths, iid)["needs_review"] is True


# 6. expected_rev
def test_a_correction_against_an_old_revision_is_a_conflict(paths):
    rid = session(paths)["ids"][0]
    obs.correct(paths, rid, expected_rev=1, snapshot=snap("pair", {"separation": assessed("easily")}),
                reason="a", submitted=PHONE)
    with pytest.raises(obs.Conflict):
        obs.correct(paths, rid, expected_rev=1, snapshot=snap("pair", {"separation": assessed("no")}),
                    reason="b", submitted=PHONE)
    assert len(obs.load(paths, rid)["revisions"]) == 2


# 7. retries
def test_the_same_request_twice_returns_the_same_receipt(paths):
    a = session(paths, "req-7")
    b = session(paths, "req-7")
    assert a == b and len(list(obs.folder(paths).glob("OBS-*.json"))) == 3


def test_a_reused_request_id_with_different_content_is_refused(paths):
    session(paths, "req-8")
    with pytest.raises(ValueError, match="already used"):
        session(paths, "req-8", snapshots=[snap("pair", {"separation": assessed("no")})])


def test_concurrent_deliveries_of_one_request_make_one_set(paths):
    results, errors = [], []

    def go():
        try:
            results.append(session(paths, "req-9"))
        except Exception as e:  # noqa: BLE001
            errors.append(e)
    threads = [threading.Thread(target=go) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors and len({json.dumps(r, sort_keys=True) for r in results}) == 1
    assert len(list(obs.folder(paths).glob("OBS-*.json"))) == 3


def test_a_retry_after_a_crash_finds_what_was_saved(paths, monkeypatch):
    real = obs._receipt
    monkeypatch.setattr(obs, "_receipt", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("crash after save")))
    with pytest.raises(RuntimeError):
        session(paths, "req-10")
    monkeypatch.setattr(obs, "_receipt", real)
    r = session(paths, "req-10")
    assert len(r["ids"]) == 3 and len(list(obs.folder(paths).glob("OBS-*.json"))) == 3


# 8. import
def _with_criteria_verdict(tmp_path, at="2026-10-26T02:43:41+00:00", light="diagnostic"):
    e = started(minimal_experiment("E-012"))
    e["status"] = "answered"
    e["criteria"] = [{"key": "print", "label": "Printed?", "choices": ["clean", "flawed", "failed"]},
                     {"key": "apart", "label": "Apart?", "choices": ["yes", "hard", "no"]}]
    e["owner_verdict"] = {"kind": "criteria", "grades": {"E-012-A": {"print": "clean", "apart": "no"},
                                                         "E-012-B": {"print": "clean", "apart": "no"}},
                          "lighting": light, "by": "owner", "at": at, "note": "fused", "print_runs": ["PR-012-01"]}
    return make_project(tmp_path, minimal_question(), [e])


def test_import_keeps_scope_is_repeatable_and_doesnt_trust_old_defaults(tmp_path):
    p = _with_criteria_verdict(tmp_path)
    plan = obs.import_verdicts(p, apply=False)
    assert len(plan) == 2 and not list(obs.folder(p).glob("OBS-*.json"))
    made = obs.import_verdicts(p, apply=True)
    again = obs.import_verdicts(p, apply=True)
    assert sum(len(m["ids"]) for m in made) == 2 and len(made) == 1 and again == []  # one group per verdict
    recs = [obs.latest(obs.load(p, f.stem)) for f in sorted(obs.folder(p).glob("OBS-*.json"))]
    assert {r["subject"]["kind"] for r in recs} == {"strip"}
    assert all(r["subject"]["identified"] == "assumed" for r in recs)
    assert all(r["source"]["kind"] == "imported_history" for r in recs)
    assert all(r["viewing"]["light"] == "unknown" for r in recs)  # 'diagnostic' recorded while it was the default
    assert recs[0]["outcomes"]["face"] == {"status": "assessed", "value": "clean", "note": None}
    assert recs[0]["outcomes"]["separation"]["value"] == "no"


def test_import_keeps_a_light_recorded_after_the_default_was_removed(tmp_path):
    p = _with_criteria_verdict(tmp_path, at="2026-10-27T10:00:00+00:00", light="room")
    obs.import_verdicts(p, apply=True)
    r = obs.latest(obs.load(p, sorted(obs.folder(p).glob("OBS-*.json"))[0].stem))
    assert r["viewing"]["light"] == "room"


# 9. precedence
def test_observations_override_the_verdicts_finding_and_follow_corrections(tmp_path):
    from lab import page_index
    p = _with_criteria_verdict(tmp_path)
    x = page_index.build_index(p.root)["experiments"][0]
    assert x["finding_source"] == "legacy_verdict"
    obs.import_verdicts(p, apply=True)
    first = sorted(obs.folder(p).glob("OBS-*.json"))[0].stem
    fixed = obs.latest(obs.load(p, first))
    fixed = {k: fixed[k] for k in ("subject", "viewing", "outcomes", "source")}
    fixed["outcomes"]["separation"] = assessed("effort")
    obs.correct(p, first, expected_rev=1, snapshot=fixed, reason="pried apart after all", submitted=PHONE)
    x = page_index.build_index(p.root)["experiments"][0]
    assert x["finding_source"] == "observations"
    assert "came apart with effort" in x["finding"]
    assert x["outcome"] is None  # a criteria verdict still isn't a prediction test


@pytest.mark.parametrize("bad", ["../../experiments/E-009", "OBS-1/../../x", "OBS-", "obs-0001", None, 7])
def test_ids_that_arent_observation_ids_are_refused_before_any_file_is_touched(paths, bad):
    with pytest.raises(ValueError, match="isn't an observation id"):
        obs.load(paths, bad)
    with pytest.raises(ValueError, match="isn't an observation id"):
        obs.correct(paths, bad, expected_rev=1, snapshot=snap("pair"), reason="r", submitted=PHONE)


def test_interpretation_ids_are_checked_too(paths):
    with pytest.raises(ValueError, match="isn't an interpretation id"):
        obs.load_interpretation(paths, "../observations/OBS-0001")


# ---- review of 736c977 --------------------------------------------------------------------------------------------

def test_a_retry_after_a_crash_part_way_through_a_session_writes_the_rest(paths, monkeypatch):
    real, calls = obs._link_new, {"n": 0}

    def dies_on_second(d, name, record):
        calls["n"] += 1
        if calls["n"] == 2:
            raise SystemExit("killed")  # stands in for a hard kill: the cleanup below is skipped
        return real(d, name, record)
    monkeypatch.setattr(obs, "_link_new", dies_on_second)
    monkeypatch.setattr(obs, "_cleanup", lambda written: None)  # a killed process cleans nothing up
    with pytest.raises(SystemExit):
        session(paths, "req-20")
    monkeypatch.setattr(obs, "_link_new", real)
    r = session(paths, "req-20")
    assert len(r["ids"]) == 3 and len(obs.all_observations(paths)) == 3
    assert len({obs.latest(x)["subject"]["group"] for x in obs.all_observations(paths)}) == 1


def test_a_retried_correction_returns_the_record_and_a_changed_one_is_refused(paths):
    rid = session(paths)["ids"][0]
    sub = {**PHONE, "request_id": "corr-1"}
    s = snap("pair", {"separation": assessed("easily")})
    a = obs.correct(paths, rid, expected_rev=1, snapshot=s, reason="misread", submitted=sub)
    b = obs.correct(paths, rid, expected_rev=1, snapshot=s, reason="misread", submitted=sub)
    assert a == b and len(b["revisions"]) == 2
    with pytest.raises(ValueError, match="already used"):
        obs.correct(paths, rid, expected_rev=2, snapshot=snap("pair", {"separation": assessed("no")}),
                    reason="x", submitted=sub)


def test_a_missing_expected_rev_is_a_bad_request_not_a_conflict(paths):
    rid = session(paths)["ids"][0]
    with pytest.raises(ValueError, match="expected_rev") as e:
        obs.correct(paths, rid, expected_rev=None, snapshot=snap("pair"), reason="r", submitted=PHONE)
    assert not isinstance(e.value, obs.Conflict)


def test_concurrent_imports_create_each_observation_once_in_one_group_per_verdict(tmp_path):
    p = _with_criteria_verdict(tmp_path)
    threads = [threading.Thread(target=lambda: obs.import_verdicts(p, apply=True)) for _ in range(3)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    recs = obs.all_observations(p)
    assert len(recs) == 2 and len({obs.latest(r)["subject"]["group"] for r in recs}) == 1


def test_a_replaced_verdict_isnt_imported_beside_the_old_one(tmp_path):
    from lab.loop.commands import load_experiment, save_experiment
    p = _with_criteria_verdict(tmp_path)
    obs.import_verdicts(p, apply=True)
    e = load_experiment(p, "E-012")
    e["owner_verdict"]["at"] = "2026-10-27T09:00:00+00:00"
    save_experiment(p, e)
    plan = obs.import_verdicts(p, apply=False)
    assert plan == [] and len(obs.all_observations(p)) == 2
    assert "E-012" in obs.import_skipped(p)


def test_a_correction_makes_reviews_of_its_experiment_stale(paths):
    from lab.loop.cases import cases_dir, load_cases
    from lab.records.store import atomic_write_json
    atomic_write_json(cases_dir(paths) / "CASE-001.json",
                      {"id": "CASE-001", "title": "t", "factor": "x", "finding": "f", "confidence": "reproduced",
                       "ladder_step": 3, "experiments": ["E-009"],
                       "review": {"by": "owner", "level": "reproduced", "reason": "r", "at": "t"}})
    rid = session(paths)["ids"][0]
    obs.correct(paths, rid, expected_rev=1, snapshot=snap("pair", {"separation": assessed("easily")}),
                reason="misread", submitted=PHONE)
    c = load_cases(paths)[0]
    assert c["review"]["stale"] is True and c["confidence"] == "supported"


def test_an_ai_reading_names_the_ai(paths):
    s = snap("pair")
    s["source"] = {"kind": "ai_reading", "words": "two backs", "evidence": [], "occurred_at": None,
                   "attributed_by": None}
    with pytest.raises(ValueError, match="by"):
        obs.record_session(paths, [s], submitted={"actor": "claude", "channel": "cli", "request_id": None})
    s["source"]["by"] = "claude-opus-5-5, session 5e49"
    assert obs.record_session(paths, [s], submitted={"actor": "claude", "channel": "cli", "request_id": None})["ids"]


def test_a_retry_with_extra_client_fields_is_the_same_request(paths):
    a = session(paths, "req-30")
    snaps = [snap("pair", {"separation": assessed("effort")}),
             snap("tile", {"face": assessed("clean")}, tile="left"),
             snap("tile", {"face": assessed("flawed", "ridge at 14 mm")}, tile="right")]
    for s in snaps:
        s["draft_saved_at"] = "2026-10-27T10:00:01Z"
    assert obs.record_session(paths, snaps, submitted={**PHONE, "request_id": "req-30"}) == a


def test_a_broken_record_is_reported_and_doesnt_stop_the_others(paths):
    session(paths, "req-40")
    (obs.folder(paths) / "OBS-0099.json").write_text("{not json")
    (obs.folder(paths) / "OBS-0098.json").write_text('{"id": "OBS-0098"}')
    assert len(obs.all_observations(paths)) == 3
    assert sorted(obs.problems(paths)) == ["OBS-0098", "OBS-0099"]
    assert session(paths, "req-41", snapshots=[snap("pair")])["ids"]


def test_findings_merge_observed_and_legacy_variants(tmp_path):
    from lab import page_index
    p = _with_criteria_verdict(tmp_path)
    s = snap("strip", {"face": assessed("flawed")}, experiment="E-012", run="PR-012-01", build="BLD-012-01",
             variant="E-012-A", label="12A")
    obs.record_session(p, [s], submitted={**PHONE, "request_id": "r-merge"})
    x = page_index.build_index(p.root)["experiments"][0]
    assert x["finding_source"] == "mixed"
    assert "12A: face flawed" in x["finding"] and "12B" in x["finding"]
