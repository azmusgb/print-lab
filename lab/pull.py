"""`lab pull`: fetch and apply pending phone requests (verdicts, photos) from Local AI."""
import hashlib
import http.client
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

if sys.platform == "win32":
    import msvcrt

    def _flock_nb(f):
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)

    def _funlock(f):
        try:
            os.lseek(f.fileno(), 0, os.SEEK_SET)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
else:
    import fcntl

    def _flock_nb(f):
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _funlock(f):
        try:
            fcntl.flock(f, fcntl.LOCK_UN)
        except OSError:
            pass

from datetime import datetime, timedelta, timezone

from lab.loop.commands import abandon, add_photos, load_experiment, record_verdict
import re

from lab.loop.guards import approve, check_experiment, start

EXP_ID = re.compile(r"E-\d{3,}")  # a request's ids name record files: nothing else gets near the disk
RUN_ID = re.compile(r"PR-\d{3,}-\d{2,}")
from lab.records.project import ProjectPaths
from lab.records.store import now
from lab.sync import RemoteError, Target, _call, _error, _open, localai_base, targets

ROOT = Path(__file__).resolve().parent.parent


def verdict_lighting(payload: dict) -> str | None:
    """The light the owner judged under, as sent; None when the phone didn't say (never assumed diagnostic)."""
    return payload.get("lighting") or None


TAP_WINDOW = timedelta(hours=6)  # a phone's tap time is used only if it is this recent and not in the future


def _tap_time(raw) -> str | None:
    """The page's tap time as the start, when it is plausible; else None (the Mac's clock is used)."""
    try:
        t = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        return None
    n = datetime.now(timezone.utc)
    return t.astimezone(timezone.utc).isoformat() if n - TAP_WINDOW <= t <= n + timedelta(minutes=1) else None


def _act(paths: ProjectPaths, kind: str, eid: str, run_seen, payload: dict) -> str:
    """The page's buttons, applied with the CLI's own functions (lab exp start / approve / abandon)."""
    if kind == "start":
        e = load_experiment(paths, eid)
        latest = (e.get("print_runs") or [{}])[-1].get("id")
        if run_seen and run_seen != latest:
            raise ValueError(f"{eid} changed since the page was loaded (its latest run is {latest or 'none'}); reload and try again.")
        e, warn = start(paths, eid, started_at=_tap_time(payload.get("tapped_at")), started_from="page")
        run = e["print_runs"][-1]
        return " ".join([f"{eid} printing as {run['id']}", *warn]) if not warn or "already" not in warn[0] else warn[0]
    reason = str(payload.get("reason") or "").strip()
    if kind == "approve":
        # The approval binds to what the page showed: the same build and the same guards, as the CLI's approval binds
        # to the build the check passed. Anything different means the owner approved something else.
        if not reason:
            raise ValueError(f"Approving {eid} needs a reason.")
        r = check_experiment(paths, eid)
        if r.status != "needs_approval":
            approve(paths, eid, reason)  # raises the CLI's own words: blocked, owner stopped, nothing to approve
        now_reasons = sorted(x.code for x in r.failed("needs_approval"))
        build_now = (r.build or {}).get("id")
        if payload.get("build_seen") != build_now or sorted(payload.get("reasons_seen") or []) != now_reasons:
            raise ValueError(f"{eid} changed since the page was loaded (build {build_now or 'none'}, "
                             f"to approve: {', '.join(now_reasons) or 'nothing'}); reload and look again.")
        e = approve(paths, eid, reason)
        return f"Approved {e['approval']['build_id']} for: {', '.join(e['approval']['approved_reasons'])}."
    if not reason:
        raise ValueError(f"Dropping {eid} needs a reason.")
    abandon(paths, eid, reason)
    return f"{eid} abandoned."


ONE_TAP_WINDOW = timedelta(days=7)  # Pi Hub stamps the tap with its own clock; a week covers a Mac asleep for days
BUILD_ID = re.compile(r"BLD-\d{3,}-\d{2,}")


def _one_tap(paths: ProjectPaths, eid: str, payload: dict, by) -> str:
    """Pi Hub's Start of a staged build (one tap to print, S6): open the run as `lab exp start` would, at the tap time,
    and mark who started it. The print has already begun, so if the print log linked it first (a run is open on the
    same build), that run is marked instead of opening a second."""
    from lab.records.store import record_lock
    from lab.loop.commands import save_experiment
    build, item, lfile = payload.get("build"), payload.get("queue_item"), payload.get("library_file")
    if not (isinstance(build, str) and BUILD_ID.fullmatch(build)):
        raise ValueError("A one-tap start must name its build.")
    if not all(isinstance(x, int) and not isinstance(x, bool) and x > 0 for x in (item, lfile)):
        raise ValueError("A one-tap start must name its queue item and library file.")
    try:
        t = datetime.fromisoformat(str(payload.get("tapped_at")))
    except ValueError:
        t = None
    n = datetime.now(timezone.utc)
    if t is None or t.tzinfo is None or not n - ONE_TAP_WINDOW <= t <= n + timedelta(minutes=1):
        raise ValueError("A one-tap start must carry Pi Hub's tap time from the last week.")
    tapped = t.astimezone(timezone.utc).isoformat(timespec="seconds")
    e = load_experiment(paths, eid)
    warn = []
    if e["status"] != "printing":
        e, warn = start(paths, eid, started_at=tapped, started_from="one-tap")
    with record_lock(paths.locks, eid, f"lab pull: one-tap {eid}"):
        e = load_experiment(paths, eid)
        run = (e.get("print_runs") or [{}])[-1]
        if run.get("build_id") != build:
            raise ValueError(f"{eid}'s latest run is on {run.get('build_id') or 'no build'}, not {build}; "
                             "link the print by hand with `lab exp link`.")
        if run.get("started_by"):
            return f"{eid} {run['id']} was already marked as started from Pi Hub."
        run["started_by"] = "pi-hub one-tap"
        run.setdefault("started_from", "one-tap")
        run["one_tap"] = {"device": str(by or "")[:80] or None, "queue_item": item, "library_file": lfile,
                          "tapped_at": tapped}
        save_experiment(paths, e)
    return " ".join([f"{eid} printing as {run['id']}, started from Pi Hub" + (f" ({by})" if by else "") + ".", *warn])


def _post_result(target: Target, project: str, req_id: str, status: str, message: str, timeout: float) -> None:
    """Tell the target what happened. A failure is printed and left: the request is on disk as handled, so the next
    run answers it `duplicate` and the target stops showing it as pending."""
    try:
        st, body = _call(target, "POST", f"/api/lab/{project}/requests/{req_id}/result", timeout,
                         json.dumps({"status": status, "message": message}).encode())
        if st != 200:
            print(f"lab pull: {target.name} wouldn't take the result for {req_id}: {_error(body, st)}", file=sys.stderr)
    except Exception as e:  # one result post never stops the loop
        print(f"lab pull: couldn't tell {target.name} the result for {req_id} ({getattr(e, 'reason', None) or e})",
              file=sys.stderr)


SHA_RE = re.compile(r"[0-9a-f]{64}")  # a photo's name is the SHA-256 of its bytes; nothing else reaches a URL or path
MAX_PHOTOS = 50  # Pi Hub's caps
MAX_TAB = 16
MAX_PHOTO_BYTES = 8 * 1024 * 1024
LOCAL_FAIL = "Couldn't add the photos on the Mac: "


def _apply_photos(paths: ProjectPaths, project: str, run_id, payload: dict, target: Target,
                  timeout: float) -> tuple[str, str]:
    """Check the request's shape, download each photo (size-capped, hash-checked), add them to the run.
    Returns (status, message); a download failure raises OSError/HTTPError for the caller to turn into `error`."""
    photos = payload.get("photos")
    if not isinstance(photos, list) or not 1 <= len(photos) <= MAX_PHOTOS:
        return "refused", f"A photos request needs 1 to {MAX_PHOTOS} photos."
    for p in photos:
        if not (isinstance(p, dict) and isinstance(p.get("sha256"), str) and SHA_RE.fullmatch(p["sha256"])
                and (p.get("tab") is None or (isinstance(p["tab"], str) and len(p["tab"]) <= MAX_TAB))):
            return "refused", f"A photo in the request isn't a SHA-256 name with an optional tab of up to {MAX_TAB} characters."
    try:
        with tempfile.TemporaryDirectory() as td:
            files, tabs = [], []
            for p in photos:
                sha = p["sha256"]
                req_obj = urllib.request.Request(f"{target.base}/api/lab/{project}/incoming/{sha}.jpg", method="GET",
                                                 headers={target.header: target.key})
                with _open(req_obj, timeout, target.context) as resp:
                    data = resp.read(MAX_PHOTO_BYTES + 1)
                if len(data) <= MAX_PHOTO_BYTES and getattr(resp, "length", None):
                    # a body shorter than its Content-Length is a dropped connection, not a bad photo: retry, don't refuse
                    raise http.client.IncompleteRead(data, resp.length)
                if len(data) > MAX_PHOTO_BYTES:
                    return "refused", f"A photo is over {MAX_PHOTO_BYTES // (1024 * 1024)} MB."
                if hashlib.sha256(data).hexdigest() != sha:
                    return "refused", f"A photo didn't match its name ({sha[:12]}), so none were added."
                tmp_path = Path(td) / f"{sha}.jpg"
                try:
                    tmp_path.write_bytes(data)
                except OSError as e:
                    return "error", f"{LOCAL_FAIL}{e}"[:200]
                files.append(tmp_path)
                tabs.append(p.get("tab"))
            try:
                add_photos(paths, run_id, files, tabs=tabs)
            except OSError as e:  # sips missing, disk full: local, kept as `error` so it is retried and not lost
                return "error", f"{LOCAL_FAIL}{e}"[:200]
            return "applied", f"{len(files)} photos added"
    except ValueError as e:
        return "refused", str(e)


def apply_pending(pdir: Path, target: Target, timeout: float = 10) -> list[dict]:
    pdir = Path(pdir)
    lock_file = pdir / ".pull.lock"
    lock_fd = open(lock_file, "a")
    try:
        _flock_nb(lock_fd)
    except (BlockingIOError, OSError):
        lock_fd.close()
        return []

    try:
        paths = ProjectPaths(pdir)
        project = pdir.name
        handled = set()
        requests_file = pdir / "requests.jsonl"
        if requests_file.exists():
            for line in requests_file.read_text().splitlines():
                if line.strip():
                    try:
                        handled.add(json.loads(line)["id"])
                    except (ValueError, KeyError, TypeError) as e:
                        print(f"lab pull: skipped an unreadable line in requests.jsonl ({e})", file=sys.stderr)

        try:
            st, body = _call(target, "GET", f"/api/lab/{project}/requests?status=pending", timeout)
        except (OSError, ValueError) as e:
            raise RemoteError(f"{target.name} didn't answer ({getattr(e, 'reason', None) or e})"[:200]) from e
        if st != 200:
            raise RemoteError(_error(body, st))

        items = body.get("items", body) if isinstance(body, dict) else body
        if not isinstance(items, list):
            raise RemoteError(f"{target.name} sent a pending list this Mac can't read")

        items = sorted(items, key=lambda r: r.get("at", ""))
        results = []

        for req in items:
            req_id = req.get("id")
            if not req_id:
                continue

            if req_id in handled:
                status = "duplicate"
                message = "already handled"
                _post_result(target, project, req_id, status, message, timeout)
                results.append({"id": req_id, "status": status, "message": message})
                continue

            kind = req.get("kind")
            eid = req.get("experiment")
            run_id = req.get("run")
            payload = req.get("payload") or {}

            bad = (kind in ("verdict", "start", "approve", "abandon", "qualification", "one_tap") and not (isinstance(eid, str) and EXP_ID.fullmatch(eid))) \
                or (run_id is not None and not (isinstance(run_id, str) and RUN_ID.fullmatch(run_id)))
            if bad:
                status, message = "refused", f"Not an experiment id or run id: {str(eid)[:40]!r}, {str(run_id)[:40]!r}."
            elif kind == "verdict":
                try:
                    record_verdict(
                        paths,
                        eid,
                        rank=payload.get("rank"),
                        strength=payload.get("strength"),
                        inconclusive=payload.get("inconclusive"),
                        accept=None,
                        defects=[],
                        marks=[],
                        witness=None,
                        witness_override=None,
                        anchors=[],
                        not_about_target=False,
                        note=payload.get("note"),
                        replace=bool(payload.get("replace", False)),
                        runs=[run_id] if run_id else None,
                        lighting=verdict_lighting(payload),
                        grades=payload.get("grades"),
                    )
                    status = "applied"
                    message = f"{eid} answered"
                except ValueError as e:
                    status = "refused"
                    message = str(e)
            elif kind == "photos":
                try:
                    status, message = _apply_photos(paths, project, run_id, payload, target, timeout)
                except urllib.error.HTTPError as e:
                    status, message = "error", f"HTTP {e.code}"
                except (OSError, http.client.HTTPException) as e:  # URLError, timeout, closed or short connection
                    status, message = "error", str(getattr(e, "reason", None) or e)[:200] or type(e).__name__
                if status == "error":  # not recorded and no result posted: the request is retried on the next run
                    what = message if message.startswith(LOCAL_FAIL) else f"not fetched ({message})"
                    print(f"lab pull: {target.name}: photos for {req_id} {what}", file=sys.stderr)
                    results.append({"id": req_id, "status": status, "message": message})
                    continue
            elif kind == "observation":
                from lab.observe_cli import _check_experiment
                from lab.records import observations as obs
                try:
                    snapshots = payload.get("snapshots") or []
                    _check_experiment(paths, snapshots, eid)
                    r = obs.record_session(paths, snapshots,
                                           submitted={"actor": "owner", "channel": "phone", "request_id": req_id})
                    status, message = "applied", f"Recorded {', '.join(r['ids'])}"
                except ValueError as e:
                    status, message = "refused", str(e)
            elif kind == "observation_correction":
                from lab.observe_cli import _check_experiment
                from lab.records import observations as obs
                try:
                    _check_experiment(paths, [payload.get("snapshot") or {}], eid)
                    rec = obs.correct(paths, payload.get("observation"), expected_rev=payload.get("expected_rev"),
                                      snapshot=payload.get("snapshot") or {}, reason=payload.get("reason") or "",
                                      submitted={"actor": "owner", "channel": "phone", "request_id": req_id})
                    status, message = "applied", f"{rec['id']} is now at revision {obs.latest(rec)['rev']}"
                except obs.Conflict as e:
                    status, message = "refused", f"conflict: {e}"
                except ValueError as e:
                    status, message = "refused", str(e)
            elif kind == "qualification":
                from lab.qualification import apply_request as apply_qualification, message as qualification_message
                try:
                    rec = apply_qualification(paths, eid, payload, request_id=req_id)
                    status, message = "applied", qualification_message(rec)
                except ValueError as e:
                    status, message = "refused", str(e)
            elif kind == "one_tap":
                try:
                    status, message = "applied", _one_tap(paths, eid, payload, req.get("by"))
                except ValueError as e:
                    status, message = "refused", str(e)
            elif kind in ("start", "approve", "abandon"):
                try:
                    status, message = "applied", _act(paths, kind, eid, req.get("run_seen"), payload)
                except ValueError as e:
                    status, message = "refused", str(e)
            else:
                status = "refused"
                message = f"unknown request kind {kind}"

            record_entry = {"id": req_id, "status": status, "message": message, "at": now()}
            with open(requests_file, "a") as f:
                f.write(json.dumps(record_entry) + "\n")
            handled.add(req_id)

            _post_result(target, project, req_id, status, message, timeout)

            results.append({"id": req_id, "status": status, "message": message})

        return results
    finally:
        _funlock(lock_fd)
        lock_fd.close()


def _applescript_text(text: str) -> str:
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"') + '"'


def notify_desktop(message: str, title: str = "Print Lab", subtitle: str = "") -> None:
    """A native macOS notification via AppleScript. Only for Pi Hub not answering: every other notice goes to the phone
    through Pi Hub (verdict_notice), which can't carry news of itself (platform step 5, D2)."""
    try:
        sub_clause = f" subtitle {_applescript_text(subtitle)}" if subtitle else ""
        script = f"display notification {_applescript_text(message)} with title {_applescript_text(title)}{sub_clause}"
        subprocess.run(["osascript", "-e", script], timeout=2.0, capture_output=True)
    except Exception:
        pass


NOTICE_MAX_AGE = 3600  # seconds a phone notice Pi Hub hasn't taken is still worth sending


def verdict_notice(event: dict, now_ts: float | None = None) -> dict:
    """The phone notice for a finished print (check_active_print's event): sent through Pi Hub, which keeps quiet hours.
    A tap opens the lab at that experiment's verdict sheet."""
    from lab.sync import HUB_URL
    exp, run = event["experiment"], event["run"]
    body = (f"Print {run} finished." if event.get("elapsed_minutes") is not None else
            f"Print {run} finished. Give its minutes from the printer's history.")
    return {"kind": "verdict", "title": f"{exp} is ready for a verdict", "body": body,
            "click": f"{HUB_URL}/lab?e={exp}&do=judge", "dedupe": f"verdict-{run}", "at": int(now_ts or time.time())}


def flush_notices(notices: list, timeout: float = 10, now_ts: float | None = None) -> list:
    """Posts queued phone notices to Pi Hub's /api/notify/print-lab with the lab key, oldest first. Returns those still
    to send: the first one Pi Hub didn't take and the rest. One refused as invalid (400), or older than an hour, is
    dropped. With no hub key this Mac isn't set up for Pi Hub, so they're dropped too."""
    from lab.sync import _call, hub_target
    now_ts = now_ts or time.time()
    fresh = [n for n in notices if isinstance(n, dict) and now_ts - (n.get("at") or 0) <= NOTICE_MAX_AGE]
    if not fresh:
        return []
    try:
        hub = hub_target()
    except (OSError, ValueError) as e:
        print(f"lab pull: phone notice waiting ({e})", file=sys.stderr)
        return fresh
    if hub is None:
        return []
    for i, n in enumerate(fresh):
        body = json.dumps({k: n[k] for k in ("kind", "title", "body", "click", "dedupe") if n.get(k)}).encode()
        try:
            st, said = _call(hub, "POST", "/api/notify/print-lab", timeout, body)
        except (urllib.error.URLError, OSError, http.client.HTTPException, ValueError):
            return fresh[i:]
        if st == 400:
            print(f"lab pull: Pi Hub refused a phone notice as invalid: {_error(said, st)}", file=sys.stderr)
        elif not 200 <= st < 300:
            return fresh[i:]
    return []


def check_active_print(paths: ProjectPaths, base: str | None = None, timeout: float = 5.0) -> dict | None:
    """Check if an active in-flight print has finished, and auto-record telemetry usage."""
    from lab.loop.commands import all_experiments
    from lab.loop.telemetry import apply_telemetry, get_run_telemetry, mark_finished_unknown

    exps = all_experiments(paths)
    printing = next((e for e in exps.values() if e.get("status") == "printing"), None)
    if not printing:
        return None

    runs = printing.get("print_runs") or []
    if not runs:
        return None

    last_run = runs[-1]
    usage = last_run.get("usage")
    if usage and usage.get("usage_source") in ("telemetry", "manual", "printer_log", "finished_unknown", "bambuddy"):
        return None

    try:
        t = get_run_telemetry(paths, printing["id"], run_id=last_run["id"], base=base)
    except ValueError:
        return None
    if t["is_finished"] and t["elapsed_minutes"] is None:
        mark_finished_unknown(paths, printing["id"], last_run["id"])
        return {"action": "finished_time_unknown", "experiment": printing["id"], "run": t["run_id"],
                "elapsed_minutes": None, "grams": None}
    try:
        e, t = apply_telemetry(paths, printing["id"], run_id=last_run["id"], base=base)
        return {
            "action": "telemetry_applied",
            "experiment": printing["id"],
            "run": t["run_id"],
            "elapsed_minutes": t["elapsed_minutes"],
            "grams": t["estimate_g"],
        }
    except ValueError:
        return None


def link_new_prints(paths: ProjectPaths, seen: dict | None = None) -> list[dict]:
    """Link Bambuddy prints newer than the last one seen (plus linked ones still awaiting their end), saving the
    newest id only once linking is done. Bambuddy off or failing: nothing happens and the saved id stays.
    Limits: the print log is read 100 entries deep, so more than 100 new prints between pulls leaves the oldest
    unlinked; the first run (no state file) scans the newest 100; and a reset or deleted state file can re-link a
    print the owner had unlinked (it is new again by id). Skipped prints are not reported.
    TODO: the spec's "no longer in Bambuddy" state for a linked print deleted from Bambuddy isn't implemented yet."""
    from lab import bambuddy
    from lab.loop.commands import all_experiments
    from lab.loop.linking import link_entries
    from lab.records.store import atomic_write_json
    try:
        entries = bambuddy.print_log()
    except Exception:
        entries = None
    if entries is None:
        return []
    if seen is not None:
        seen["entries"] = entries  # the caller rebuilds the outside list from this, without a second request
    state = paths.root / "bambuddy-seen.json"
    try:
        last_id = int(json.loads(state.read_text())["last_id"])
    except (OSError, ValueError, KeyError, TypeError):
        last_id = 0
    waiting = {r["bambuddy"]["print"] for e in all_experiments(paths).values() for r in e.get("print_runs") or []
               if (r.get("bambuddy") or {}).get("print") is not None and not r["bambuddy"].get("snapshot_at")}
    due = sorted((x for x in entries if x.get("id") is not None and (x["id"] > last_id or x["id"] in waiting)),
                 key=lambda x: x["id"])
    plans: dict = {}

    def planned(archive_id):
        if archive_id not in plans:
            a = bambuddy.archive(archive_id) if archive_id is not None else None
            plans[archive_id] = (a or {}).get("print_time_seconds")
        return plans[archive_id]
    events = link_entries(paths, due, planned)
    newest = max([last_id, *(x["id"] for x in entries if x.get("id") is not None)])
    if newest != last_id or not state.exists():
        atomic_write_json(state, {"last_id": newest})
    say = {"linked": "linked to", "created": "opened a run on", "snapshot": "ended; evidence saved on",
           "skipped": "not linked:"}
    return [{"id": f"link-{ev['print']}", "status": "applied",
             "message": ev["message"] or f"Bambuddy print #{ev['print']} {say[ev['action']]} "
                                         f"{ev['experiment']} {ev['run'] or ''}".strip()}
            for ev in events if ev["action"] != "skipped"]


STATE_FILE = ".pull-state.json"  # per project, outside git: each target's last outcome, so a standing failure prints once


def _load_state(pdir: Path) -> dict:
    try:
        st = json.loads((Path(pdir) / STATE_FILE).read_text())
        return st if isinstance(st, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(pdir: Path, state: dict) -> None:
    from lab.records.store import atomic_write_json
    try:
        if _load_state(pdir) != state:
            atomic_write_json(Path(pdir) / STATE_FILE, state)
    except OSError as e:  # a log nicety never stops a pull
        print(f"lab pull: couldn't save {STATE_FILE} ({e})", file=sys.stderr)


# The launchd agent runs straight from this checkout, so a new commit here is print-lab's deploy (amendment A3). Only the
# code that runs counts as uncommitted changes: projects/ and history/ change with every print.
CODE_PATHS = ("lab", "pyproject.toml", "uv.lock")
MAC_WATCH = (".claude", "localai-chat", "mac-watch.py")  # under the home folder, found when a pull runs


def checkout_release(repo: Path | None = None, runner=subprocess.run) -> dict | None:
    """{"commit", "dirty"} for the checkout `lab` runs from, or None when it isn't a readable git checkout."""
    repo = repo or ROOT
    try:
        head = runner(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
        status = runner(["git", "-C", str(repo), "status", "--porcelain", "--", *CODE_PATHS],
                        capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    commit = head.stdout.strip().lower()
    if head.returncode != 0 or status.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", commit):
        return None
    return {"commit": commit, "dirty": bool(status.stdout.strip())}


def report_release(last: dict | None, runner=subprocess.run, watch: Path | None = None,
                   repo: Path | None = None) -> dict | None:
    """Queues release:print-lab through mac-watch's outbox (it sends it to Pi Hub with the mac deploy key) when the
    checkout differs from `last`, the release last queued. Returns what to remember: the new release once queued; else
    `last` plus the failure, so the release is tried again next run but a standing failure prints once. No mac-watch
    installed: nothing to do."""
    last = last if isinstance(last, dict) else {}
    now = checkout_release(repo, runner)
    watch = Path(os.environ.get("LAB_MAC_WATCH") or watch or Path.home().joinpath(*MAC_WATCH))
    if now is None or now == {k: last.get(k) for k in ("commit", "dirty")} or not watch.is_file():
        return last or None
    try:
        out = runner([sys.executable, str(watch), "--queue-release", "print-lab", now["commit"],
                      "1" if now["dirty"] else "0"], capture_output=True, text=True, timeout=30)
        failure = None if out.returncode == 0 else (out.stderr or "").strip()[:200] or f"exit {out.returncode}"
    except (OSError, subprocess.TimeoutExpired) as e:
        failure = str(e) or type(e).__name__
    if failure:
        if last.get("failed") != failure:
            print(f"lab pull: mac-watch didn't queue the release report: {failure}", file=sys.stderr)
        return {**last, "failed": failure}
    print(f"Release report queued: print-lab {now['commit'][:7]}{' + local changes' if now['dirty'] else ''}")
    return now


OUTAGE_ALERT_AFTER = 15 * 60  # seconds a target must keep failing before the Mac says so


def track_outages(down: dict, now_state: dict, now: float, notify=None) -> dict:
    """Each failing target's first failure time; one desktop alert once it has failed for OUTAGE_ALERT_AFTER,
    and one when it answers again. A brief blip (a Pi restart) stays in the log only."""
    notify = notify or notify_desktop
    down = down if isinstance(down, dict) else {}
    out = {}
    for name, outcome in now_state.items():
        was = down.get(name) if isinstance(down.get(name), dict) else None
        if outcome == "ok":
            if was and was.get("alerted"):
                notify(f"{name} is answering again; lab requests and syncs are flowing.", "Print Lab")
            continue
        since = was.get("since") if was and isinstance(was.get("since"), (int, float)) else now
        alerted = bool(was and was.get("alerted"))
        if not alerted and now - since >= OUTAGE_ALERT_AFTER:
            minutes = int((now - since) // 60)
            notify(f"{name} hasn't answered for {minutes} minutes, so phone requests aren't reaching the Mac. "
                   f"Last error: {outcome}"[:240], "Print Lab")
            alerted = True
        out[name] = {"since": since, "alerted": alerted}
    return out


def pull(pdir: Path, base: str | None = None, timeout: float = 10) -> list[dict]:
    pdir = Path(pdir)
    applied = []
    state = _load_state(pdir)
    last = state.get("targets") if isinstance(state.get("targets"), dict) else {}
    now_state: dict = {}
    for t in targets(base):
        name = t[0] if isinstance(t, tuple) else t.name
        now_state[name] = "ok"
        try:
            if isinstance(t, tuple):
                raise RemoteError(t[1])
            applied += apply_pending(pdir, t, timeout)
        except Exception as e:  # one target's trouble never stops the others
            message = str(e) or type(e).__name__
            now_state[name] = message
            entry = {"id": name, "status": "error", "message": message}
            if last.get(name) == message:  # the same failure as last run: still returned, but not printed again
                entry["repeat"] = True
            else:
                print(f"lab pull: {name}: {message}", file=sys.stderr)
            applied.append(entry)
    _save_state(pdir, {**state, "targets": now_state, "down": track_outages(state.get("down"), now_state, time.time())})
    seen: dict = {}
    lock_fd = open(pdir / ".pull.lock", "a")
    try:
        _flock_nb(lock_fd)  # one pull links at a time; a busy lock skips linking
        try:
            applied += link_new_prints(ProjectPaths(pdir), seen)
        except Exception as e:  # linking must never stop the rest of the pull
            print(f"lab pull: linking Bambuddy prints failed: {e}", file=sys.stderr)
    except (BlockingIOError, OSError):
        pass
    finally:
        _funlock(lock_fd)
        lock_fd.close()  # releases the lock
    if seen.get("entries") is not None:  # staging needs the print log this pull read: idle for 10 minutes
        from lab.loop.stage import stage_waiting
        failed = dict(_load_state(pdir).get("stage_failed") or {})
        try:
            staged = stage_waiting(ProjectPaths(pdir), seen["entries"], failed)
        except Exception as e:  # staging must never stop the rest of the pull
            staged = [{"id": "stage", "status": "error", "message": f"staging failed: {e}"}]
        for ev in staged:
            if ev["status"] == "error":
                print(f"lab pull: {ev['message']}", file=sys.stderr)
        applied += staged
        _save_state(pdir, {**_load_state(pdir), "stage_failed": failed})
    event = check_active_print(ProjectPaths(pdir), localai_base(base), timeout)  # telemetry is Local AI's
    entries = seen.get("entries")
    outside_changed = False
    if entries is not None and (pdir / "page.json").exists():
        from lab.page import outside_prints
        from lab.page_index import build_index
        try:  # refresh only when the list differs from the saved one: an unchanged pull leaves page.json alone
            saved = json.loads((pdir / "page.json").read_text()).get("outside") or []
            linked = {r["print"]["id"] for e in build_index(pdir)["experiments"] for r in e["runs"] if r.get("print")}
            outside_changed = outside_prints(entries, linked) != saved
        except (OSError, ValueError):
            pass
    if any(r.get("status") == "applied" for r in applied) or event or outside_changed:
        from lab.page import refresh
        refresh(pdir, entries)
        from lab.sync import sync
        if base is None:
            sync(pdir, timeout=timeout)
        else:
            sync(pdir, base, timeout)
    state = _load_state(pdir)
    notices = (state.get("notices") or []) + ([verdict_notice(event)] if event else [])
    if notices:
        _save_state(pdir, {**state, "notices": notices})  # kept before sending, so a crash can't lose it
        _save_state(pdir, {**state, "notices": flush_notices(notices, timeout)})
    if event:
        applied.append({
            "id": f"event-{event['run']}",
            "status": "applied",
            "message": (f"Print {event['run']} finished; telemetry usage auto-recorded ({event['elapsed_minutes']} min)"
                        if event["elapsed_minutes"] is not None else
                        f"Print {event['run']} finished; its end time is unknown, so record the printer's minutes"),
        })
    return applied


LOG_MAX_BYTES = 1_048_576  # 1 MiB


def _log_path() -> Path:
    return Path.home() / "Library" / "Logs" / "print-lab-pull.log"


def rotate_log(path: Path | None = None, max_bytes: int = LOG_MAX_BYTES) -> bool:
    """Keep the pull log under max_bytes by moving it to .log.1 when it grows past the cap."""
    p = _log_path() if path is None else Path(path)
    try:
        if p.stat().st_size > max_bytes:
            p.replace(p.with_suffix(".log.1"))
            return True
    except OSError:
        pass
    return False


def plist_text(repo: Path, uv: str) -> str:
    log_path = str(_log_path())
    data = {
        "Label": "com.printlab.pull",
        "ProgramArguments": [uv, "run", "--project", str(repo), "lab", "pull"],
        "StartInterval": 60,
        "RunAtLoad": True,
        "StandardOutPath": log_path,
        "StandardErrorPath": log_path,
    }
    return plistlib.dumps(data).decode()


def install(repo: Path | None = None, uv: str | None = None, agent_dir: Path | None = None, runner=None) -> Path:
    if uv is None:
        uv = shutil.which("uv")
    if not uv:
        raise ValueError("uv isn't on PATH.")
    if repo is None:
        repo = ROOT
    if agent_dir is None:
        agent_dir = Path.home() / "Library" / "LaunchAgents"
    if runner is None:
        runner = subprocess.run

    agent_dir = Path(agent_dir)
    agent_dir.mkdir(parents=True, exist_ok=True)
    plist_path = agent_dir / "com.printlab.pull.plist"
    text = plist_text(repo, uv)
    plist_path.write_text(text)
    runner(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist_path)],
           check=True, capture_output=True, text=True)
    return plist_path


def uninstall(agent_dir: Path | None = None, runner=None) -> None:
    if agent_dir is None:
        agent_dir = Path.home() / "Library" / "LaunchAgents"
    if runner is None:
        runner = subprocess.run

    plist_path = Path(agent_dir) / "com.printlab.pull.plist"
    if plist_path.exists():
        runner(["launchctl", "bootout", f"gui/{os.getuid()}", str(plist_path)],
               capture_output=True, text=True)
        plist_path.unlink(missing_ok=True)


def cmd_pull(args) -> int:
    from lab.cli import ROOT, project_dir
    pdir = project_dir(args.project)
    if getattr(args, "install", False):
        try:
            p = install(repo=ROOT)
            print(f"Installed com.printlab.pull to {p}")
            return 0
        except Exception as e:
            print(f"Failed to install launchd agent: {e}", file=sys.stderr)
            return 1
    if getattr(args, "uninstall", False):
        try:
            uninstall()
            print("Uninstalled com.printlab.pull")
            return 0
        except Exception as e:
            print(f"Failed to uninstall launchd agent: {e}", file=sys.stderr)
            return 1
    applied = pull(pdir)
    shown = [r for r in applied if not r.get("repeat")]  # a failure already printed last run stays out of the log
    state = _load_state(pdir)
    idle = not applied
    if idle and not state.get("idle"):
        print("No pending requests.")
    for r in shown:
        print(f"{r['id']}: {r['status']} ({r['message']})")
    _save_state(pdir, {**state, "idle": idle, "release": report_release(state.get("release"))})
    rotate_log()
    return 1 if any(r["status"] == "error" for r in applied) else 0


def register(sub) -> None:
    s = sub.add_parser("pull", help="fetch and apply pending phone requests (verdicts, photos) from Pi Hub")
    s.add_argument("--install", action="store_true", help="install launchd agent for 60s pickup")
    s.add_argument("--uninstall", action="store_true", help="uninstall launchd agent")
    s.set_defaults(fn=cmd_pull)
