"""The printer's setup log: append-only events, corrections as new events, repairs for damaged lines kept beside it
(spec: Setup log). The current setup is derived; a print run snapshots it."""
import hashlib
import json
import os
import re

from lab.records.project import ProjectPaths
from lab.records.schema import validate
from lab.records.store import RecordError, now, record_lock


def _lines(paths: ProjectPaths) -> list[bytes]:
    return paths.setup_log.read_bytes().splitlines() if paths.setup_log.exists() else []


def _append(path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(obj) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _repairs(paths: ProjectPaths) -> dict[int, dict]:
    out = {}
    if paths.setup_repairs.exists():
        for raw in paths.setup_repairs.read_text().splitlines():
            r = validate(json.loads(raw), "setup_repair", paths.setup_repairs)
            out[r["source_line"]] = r
    return out


def _raw_events(paths: ProjectPaths) -> list[dict]:
    repairs, out = _repairs(paths), []
    for i, raw in enumerate(_lines(paths), 1):
        try:
            out.append(validate(json.loads(raw), "setup_event", paths.setup_log))
        except (json.JSONDecodeError, RecordError) as err:
            r = repairs.get(i)
            if r and r["source_sha256"] == hashlib.sha256(raw).hexdigest():
                out.append(r["replacement_event"])
                continue
            raise RecordError(paths.setup_log, f"line {i}", f"can't be read ({err}). Repair it with "
                                                           f"`lab setup repair --line {i}`; the line itself is never "
                                                           "edited.") from None
    return out


def append_event(paths: ProjectPaths, kind: str, fields: dict, supersedes: str | None = None,
                 replacement: dict | None = None) -> dict:
    with record_lock(paths.printer / ".locks", "id-allocation", f"lab setup log {kind}"):
        events = _raw_events(paths)
        n = max((int(m.group(1)) for e in events if (m := re.match(r"SET-(\d+)", e.get("id", "")))), default=0)
        ev = {"schema": 1, "record_type": "setup_event", "id": f"SET-{n + 1:05d}", "kind": kind, "at": now(),
              "fields": dict(fields)}
        if kind == "correction":
            if not supersedes or supersedes not in {e["id"] for e in events}:
                raise ValueError(f"A correction names the event it replaces; {supersedes!r} isn't in the log.")
            ev.update(supersedes=supersedes, replacement=replacement or {})
        validate(ev, "setup_event", paths.setup_log)
        _append(paths.setup_log, ev)
        return ev


def repair_line(paths: ProjectPaths, line_no: int, replacement: dict, reason: str) -> dict:
    lines = _lines(paths)
    if not 1 <= line_no <= len(lines):
        raise ValueError(f"The setup log has {len(lines)} lines; there's no line {line_no}.")
    raw = lines[line_no - 1]
    try:
        validate(json.loads(raw), "setup_event", paths.setup_log)
        raise ValueError(f"Line {line_no} is readable; correct its facts with a correction event "
                         "(`lab setup log correction --supersedes SET-…`).")
    except (json.JSONDecodeError, RecordError):
        pass
    rid = f"REPAIR-{len(_repairs(paths)) + 1:03d}"
    ev = {"schema": 1, "record_type": "setup_event", "id": f"SET-{line_no:05d}R", "kind": replacement["kind"],
          "at": replacement.get("at") or now(), "fields": replacement.get("fields", {})}
    m = None
    try:
        m = json.loads(raw.decode("utf-8", "replace") + '"}')
    except json.JSONDecodeError:
        pass
    if isinstance(m, dict) and str(m.get("id", "")).startswith("SET-"):
        ev["id"] = m["id"]
    r = {"schema": 1, "record_type": "setup_repair", "repair_id": rid, "source_line": line_no,
         "source_sha256": hashlib.sha256(raw).hexdigest(), "replacement_event": ev, "reason": reason, "at": now()}
    validate(r, "setup_repair", paths.setup_repairs)
    _append(paths.setup_repairs, r)
    return r


def effective_events(paths: ProjectPaths) -> list[dict]:
    """Repairs first, then corrections (each replaces the event it supersedes, keeping that event's time)."""
    events = _raw_events(paths)
    fixes = {e["supersedes"]: e for e in events if e["kind"] == "correction"}
    out = []
    for e in events:
        if e["kind"] == "correction":
            continue
        if e["id"] in fixes:
            c = fixes[e["id"]]
            e = {**e, "kind": c["replacement"].get("kind", e["kind"]), "fields": c["replacement"].get("fields", {}),
                 "note": f"corrected by {c['id']}"}
        out.append(e)
    return out


def current_setup(paths: ProjectPaths, at: str | None = None) -> dict:
    """The latest effective event of each kind, up to `at`."""
    cur: dict[str, dict] = {}
    for e in effective_events(paths):
        if at is None or e["at"] <= at:
            if e["kind"] not in cur or e["at"] >= cur[e["kind"]]["at"]:
                cur[e["kind"]] = e
    return cur
