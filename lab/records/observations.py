"""Observation records: what someone saw on a printed tile, pair, strip or run, with who said it, kept apart from
interpretations and corrected only by adding complete revisions.

Spec: docs/superpowers/specs/2026-10-26-observation-records-design.md (rev 2). One file per observation in
projects/<p>/observations/OBS-NNNN.json; interpretations in projects/<p>/interpretations/INT-NNNN.json.
"""
import hashlib
import json
import os
from pathlib import Path

from lab.records.project import ProjectPaths
from lab.records.store import _write_temp, atomic_write_json, now, record_lock

ALLOWED = {
    "tile": ("face", "backing", "mounting", "acceptance"),
    "pair": ("separation", "acceptance"),
    "strip": ("face", "separation", "acceptance"),
    "run": ("acceptance",),
}
VALUES = {
    "face": ("clean", "flawed", "failed"),
    "separation": ("easily", "effort", "no"),
    "backing": ("whole", "marked", "damaged"),
    "mounting": ("fits", "needs_work", "unusable"),
    "acceptance": ("accepted", "accepted_with_defects", "rejected"),
}
STATUSES = ("assessed", "not_assessed", "unknown", "not_applicable")
LIGHTS = ("diagnostic", "room", "installed", "unknown")
SOURCE_KINDS = ("owner_report", "ai_reading", "instrument", "imported_history")
IDENTIFIED = ("confirmed", "assumed", "unidentified")
ACTORS = ("owner", "claude", "import")
CHANNELS = ("phone", "cli", "import")
# Verdicts recorded before this moment had 'diagnostic' filled in when no light was given (removed in ad6009f).
DEFAULT_LIGHT_REMOVED = "2026-10-26T20:00:00+00:00"
LOCK = "observations"


class Conflict(ValueError):
    """A correction was made against a revision that is no longer the latest."""


def folder(paths: ProjectPaths) -> Path:
    return paths.root / "observations"


def _interp_folder(paths: ProjectPaths) -> Path:
    return paths.root / "interpretations"


# ---- validation ---------------------------------------------------------------------------------------------------

def _validate(snapshot: dict) -> None:
    for key in ("subject", "viewing", "outcomes", "source"):
        if not isinstance(snapshot.get(key), dict):
            raise ValueError(f"The observation needs its {key}.")
    s, kind = snapshot["subject"], snapshot["subject"].get("kind")
    if kind not in ALLOWED:
        raise ValueError(f"A subject is a tile, pair, strip or run, not {kind!r}.")
    if s.get("identified") not in IDENTIFIED:
        raise ValueError("Say whether the subject is confirmed, assumed or unidentified.")
    if s.get("identified") == "unidentified" and not s.get("note"):
        raise ValueError("An unidentified subject needs a note saying what is known about it.")
    out = snapshot["outcomes"]
    for name in out:
        if name not in ALLOWED[kind]:
            raise ValueError(f"{name} isn't recorded on a {kind}; on a {kind} you can record "
                             f"{', '.join(ALLOWED[kind])}.")
    for name in ALLOWED[kind]:
        o = out.get(name)
        if not isinstance(o, dict):
            raise ValueError(f"Every revision says something about {name} for a {kind}, even if it's "
                             "'not assessed'.")
        st = o.get("status")
        if st not in STATUSES:
            raise ValueError(f"{name}: status is one of {', '.join(STATUSES)}.")
        if st == "assessed" and o.get("value") not in VALUES[name]:
            raise ValueError(f"{name}: an assessed value is one of {', '.join(VALUES[name])}.")
        if st != "assessed" and o.get("value") is not None:
            raise ValueError(f"{name}: only an assessed outcome has a value.")
        if st == "not_applicable" and not (o.get("note") or "").strip():
            raise ValueError(f"{name}: say why it doesn't apply.")
    if snapshot["viewing"].get("light") not in LIGHTS:
        raise ValueError(f"The light is one of {', '.join(LIGHTS)}.")
    if snapshot["source"].get("kind") not in SOURCE_KINDS:
        raise ValueError(f"The source is one of {', '.join(SOURCE_KINDS)}.")


def _check_attribution(snapshot: dict, submitted: dict) -> None:
    if submitted.get("actor") not in ACTORS or submitted.get("channel") not in CHANNELS:
        raise ValueError("Say who submitted it (owner, claude or import) and how (phone, cli or import).")
    src = snapshot["source"]
    if src["kind"] != "owner_report":
        return
    actor, channel = submitted["actor"], submitted["channel"]
    if actor == "claude":
        raise ValueError("Claude can't file the owner's report; record it as an ai_reading, or as an "
                         "interpretation if it explains a cause.")
    if channel == "phone" and actor == "owner":
        return
    if channel == "cli" and actor == "owner":
        if not submitted.get("tty_confirmed"):
            raise ValueError("An owner report from the terminal needs you to confirm they're your own words and "
                             "your own assessment.")
        return
    if channel == "import":
        if not (src.get("attributed_by") or "").strip():
            raise ValueError("An imported owner report needs attributed_by: the record it came from.")
        return
    raise ValueError("An owner report comes from the owner's phone, the owner at the terminal, or an attributed "
                     "import.")


def _payload_sha(snapshots: list[dict]) -> str:
    return hashlib.sha256(json.dumps(snapshots, sort_keys=True).encode()).hexdigest()


# ---- reading ------------------------------------------------------------------------------------------------------

def load(paths: ProjectPaths, oid: str) -> dict:
    f = folder(paths) / f"{oid}.json"
    if not f.exists():
        raise ValueError(f"{oid} isn't in {paths.name}.")
    return json.loads(f.read_text())


def latest(rec: dict) -> dict:
    return rec["revisions"][-1]


def all_observations(paths: ProjectPaths) -> list[dict]:
    d = folder(paths)
    return [json.loads(f.read_text()) for f in sorted(d.glob("OBS-*.json"))] if d.exists() else []


def for_experiment(paths: ProjectPaths, eid: str) -> list[dict]:
    return [r for r in all_observations(paths) if latest(r)["subject"].get("experiment") == eid]


# ---- writing ------------------------------------------------------------------------------------------------------

def _next_id(d: Path, prefix: str, width: int = 4) -> int:
    nums = [int(f.stem.split("-")[1]) for f in d.glob(f"{prefix}-*.json") if f.stem.split("-")[1].isdigit()]
    return (max(nums) + 1) if nums else 1


def _link_new(d: Path, name: str, record: dict) -> Path:
    path = d / f"{name}.json"
    tmp = _write_temp(d, record)
    try:
        os.link(tmp, path)  # refuses an existing name
    finally:
        tmp.unlink(missing_ok=True)
    return path


def _receipt(ids: list[str], group: str) -> dict:
    return {"ids": ids, "group": group}


def _find_request(paths: ProjectPaths, request_id: str) -> list[dict]:
    return [r for r in all_observations(paths)
            if any((rv.get("submitted") or {}).get("request_id") == request_id for rv in r["revisions"])]


def record_session(paths: ProjectPaths, snapshots: list[dict], *, submitted: dict) -> dict:
    """Create one linked observation per snapshot, all or nothing, under the observations lock. A request_id that was
    already applied returns its receipt (same content) or is refused (different content); nothing is written twice."""
    if not snapshots:
        raise ValueError("Nothing to record.")
    for s in snapshots:
        _validate(s)
        _check_attribution(s, submitted)
    sha = _payload_sha(snapshots)
    request_id = submitted.get("request_id")
    d = folder(paths)
    d.mkdir(parents=True, exist_ok=True)
    with record_lock(paths.locks, LOCK, f"record observations {request_id or ''}".strip()):
        if request_id:
            found = _find_request(paths, request_id)
            if found:
                first = next(rv for rv in found[0]["revisions"] if rv["submitted"].get("request_id") == request_id)
                if first["submitted"].get("payload_sha256") != sha:
                    raise ValueError(f"The request id {request_id} was already used for different content.")
                ids = sorted(r["id"] for r in found)
                return _receipt(ids, first["subject"]["group"])
        keys = [s.get("import_key") for s in snapshots]
        start = _next_id(d, "OBS")
        group = f"G-{start:04d}"
        stamp = now()
        written, ids = [], []
        try:
            for k, s in enumerate(snapshots):
                oid = f"OBS-{start + k:04d}"
                rev = {"rev": 1, "subject": {**s["subject"], "group": group}, "source": s["source"],
                       "submitted": {**{x: submitted.get(x) for x in ("actor", "channel", "request_id")},
                                     "payload_sha256": sha, "recorded_at": stamp},
                       "viewing": s["viewing"], "outcomes": s["outcomes"], "correction": None}
                record = {"schema": 1, "record_type": "observation", "id": oid, "project": paths.name,
                          "import_key": keys[k], "revisions": [rev]}
                written.append(_link_new(d, oid, record))
                ids.append(oid)
        except BaseException:
            for p in written:  # all or nothing
                p.unlink(missing_ok=True)
            raise
    return _receipt(ids, group)


def correct(paths: ProjectPaths, oid: str, *, expected_rev: int, snapshot: dict, reason: str,
            submitted: dict) -> dict:
    """Add a complete revision. Refused as a Conflict when the latest revision isn't expected_rev."""
    _validate(snapshot)
    _check_attribution(snapshot, submitted)
    if not (reason or "").strip():
        raise ValueError("A correction needs its reason.")
    with record_lock(paths.locks, LOCK, f"correct {oid}"):
        rec = load(paths, oid)
        cur = latest(rec)["rev"]
        if cur != expected_rev:
            raise Conflict(f"{oid} is at revision {cur}, not {expected_rev}: someone changed it since you read it.")
        stamp = now()
        group = latest(rec)["subject"].get("group")
        rec["revisions"].append({
            "rev": cur + 1, "subject": {**snapshot["subject"], "group": group}, "source": snapshot["source"],
            "submitted": {**{x: submitted.get(x) for x in ("actor", "channel", "request_id")},
                          "payload_sha256": _payload_sha([snapshot]), "recorded_at": stamp},
            "viewing": snapshot["viewing"], "outcomes": snapshot["outcomes"],
            "correction": {"reason": reason.strip(), "by": submitted.get("actor"), "at": stamp}})
        atomic_write_json(folder(paths) / f"{oid}.json", rec)
        _flag_dependents(paths, oid, cur + 1, latest(rec)["subject"].get("experiment"))
    return rec


def _flag_dependents(paths: ProjectPaths, oid: str, new_rev: int, eid: str | None) -> None:
    d = _interp_folder(paths)
    for f in sorted(d.glob("INT-*.json")) if d.exists() else []:
        it = json.loads(f.read_text())
        if any(c.get("observation") == oid and c.get("rev", 0) < new_rev for c in it.get("cites") or []):
            it["needs_review"] = True
            atomic_write_json(f, it)
    cdir = paths.root / "cases"
    for f in sorted(cdir.glob("CASE-*.json")) if cdir.exists() and eid else []:
        c = json.loads(f.read_text())
        if eid in (c.get("experiments") or []) and c.get("review"):
            c["review"]["needs_review"] = True
            atomic_write_json(f, c)


# ---- interpretations ----------------------------------------------------------------------------------------------

def interpret(paths: ProjectPaths, *, claim: str, by: str, cites: list[dict]) -> str:
    if not (claim or "").strip() or not cites:
        raise ValueError("An interpretation needs its claim and the observations it rests on.")
    d = _interp_folder(paths)
    d.mkdir(parents=True, exist_ok=True)
    with record_lock(paths.locks, LOCK, "interpret"):
        iid = f"INT-{_next_id(d, 'INT'):04d}"
        _link_new(d, iid, {"schema": 1, "record_type": "interpretation", "id": iid, "claim": claim.strip(),
                           "by": by, "cites": cites, "status": "hypothesis", "needs_review": False, "at": now()})
    return iid


def load_interpretation(paths: ProjectPaths, iid: str) -> dict:
    return json.loads((_interp_folder(paths) / f"{iid}.json").read_text())


# ---- importing existing verdicts ----------------------------------------------------------------------------------

_FACE = {"clean": "clean", "flawed": "flawed", "failed": "failed"}
_APART = {"yes": "easily", "hard": "effort", "no": "no"}


def _graded(value, table) -> dict:
    if value is None or value == "-":
        return {"status": "not_assessed", "value": None, "note": None}
    if value in table:
        return {"status": "assessed", "value": table[value], "note": None}
    return {"status": "unknown", "value": None, "note": f"recorded as {value!r}"}


def _light(v: dict) -> tuple[str, str | None]:
    light = v.get("lighting")
    if light == "diagnostic" and (v.get("at") or "") < DEFAULT_LIGHT_REMOVED:
        return "unknown", "recorded as diagnostic while that was the default"
    return (light if light in LIGHTS else "unknown"), None


def _plan_imports(paths: ProjectPaths) -> list[tuple[str, dict]]:
    from lab.loop.commands import all_experiments
    have = {r.get("import_key") for r in all_observations(paths)}
    out = []
    for eid, e in sorted(all_experiments(paths).items()):
        v = e.get("owner_verdict") or {}
        if v.get("kind") not in ("criteria", "acceptance"):
            continue
        runs = v.get("print_runs") or []
        run = runs[0] if len(runs) == 1 else None
        build = next((r.get("build_id") for r in e.get("print_runs") or [] if r["id"] == run), None)
        light, light_note = _light(v)
        source = {"kind": "imported_history", "words": v.get("note") or "", "evidence": [], "occurred_at": None,
                  "attributed_by": f"verdict {eid} at {v.get('at')}, by: {v.get('by')}"}
        viewing = {"light": light, **({"note": light_note} if light_note else {})}
        if v["kind"] == "criteria":
            for var in e.get("variants") or []:
                g = (v.get("grades") or {}).get(var["id"])
                if g is None:
                    continue
                key = f"verdict:{eid}:{v.get('at')}:{var['id']}"
                if key in have:
                    continue
                out.append((key, {
                    "import_key": key,
                    "subject": {"kind": "strip", "experiment": eid, "run": run, "build": build, "variant": var["id"],
                                "label": var.get("tab"), "tile": None, "identified": "assumed", "note": None},
                    "source": source, "viewing": viewing,
                    "outcomes": {"face": _graded(g.get("print"), _FACE), "separation": _graded(g.get("apart"), _APART),
                                 "acceptance": {"status": "not_assessed", "value": None, "note": None}}}))
        else:
            key = f"verdict:{eid}:{v.get('at')}:{run or 'run'}"
            if key in have:
                continue
            ok, defects = v.get("good_enough"), v.get("blocking_defects") or []
            acc = ("accepted_with_defects" if defects else "accepted") if ok else ("rejected" if ok is False else None)
            out.append((key, {
                "import_key": key,
                "subject": {"kind": "run", "experiment": eid, "run": run, "build": build, "variant": None,
                            "label": run, "tile": None, "identified": "assumed" if run else "unidentified",
                            "note": None if run else "the verdict names no single run"},
                "source": source, "viewing": viewing,
                "outcomes": {"acceptance": {"status": "assessed", "value": acc, "note": "; ".join(defects) or None}
                             if acc else {"status": "unknown", "value": None, "note": "no acceptance recorded"}}}))
    return out


def import_verdicts(paths: ProjectPaths, *, apply: bool) -> list[dict]:
    """Observations from existing criteria and acceptance verdicts, at their original scope. A dry run unless
    apply; already-imported verdicts (by import_key) are skipped, so it can run any number of times."""
    plan = _plan_imports(paths)
    if not apply:
        return [{"import_key": k, "subject": s["subject"], "outcomes": s["outcomes"]} for k, s in plan]
    made = []
    for key, s in plan:
        r = record_session(paths, [s], submitted={"actor": "import", "channel": "import", "request_id": None})
        made.append({"import_key": key, "ids": r["ids"]})
    return made


# ---- findings -----------------------------------------------------------------------------------------------------

_WORDS = {
    "face": {"clean": "printed clean", "flawed": "face flawed", "failed": "failed to print"},
    "separation": {"easily": "came apart easily", "effort": "came apart with effort", "no": "didn't come apart"},
    "backing": {"whole": "back whole", "marked": "back marked", "damaged": "back damaged"},
    "mounting": {"fits": "mounts", "needs_work": "mounting needs work", "unusable": "can't be mounted"},
    "acceptance": {"accepted": "accepted", "accepted_with_defects": "accepted with defects", "rejected": "rejected"},
}


def finding(recs: list[dict]) -> str | None:
    """'12A: printed clean, came apart with effort. …' from the latest revisions, with sources that aren't the
    owner's own words marked."""
    parts = []
    for r in sorted(recs, key=lambda x: x["id"]):
        rv = latest(r)
        words = [_WORDS[k][o["value"]] for k, o in rv["outcomes"].items() if o["status"] == "assessed"]
        words += [f"{k} couldn't be told" for k, o in rv["outcomes"].items() if o["status"] == "unknown"]
        if not words:
            continue
        s = rv["subject"]
        name = s.get("label") or s.get("variant") or s["kind"]
        if s["kind"] == "tile" and s.get("tile"):
            name = f"{name} {s['tile']}"
        src = rv["source"]["kind"]
        tag = "" if src == "owner_report" else f" ({src.replace('_', ' ')})"
        parts.append(f"{name}: {', '.join(words)}{tag}.")
    return " ".join(parts) or None
