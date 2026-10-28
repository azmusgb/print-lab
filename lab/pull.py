"""`lab pull`: fetch and apply pending phone requests (verdicts, photos) from Local AI."""
import fcntl
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from datetime import datetime, timedelta, timezone

from lab.loop.commands import abandon, add_photos, load_experiment, record_verdict
import re

from lab.loop.guards import approve, check_experiment, start

EXP_ID = re.compile(r"E-\d{3,}")  # a request's ids name record files: nothing else gets near the disk
RUN_ID = re.compile(r"PR-\d{3,}-\d{2,}")
from lab.records.project import ProjectPaths
from lab.records.store import now
from lab.sync import BASE, _call, _context, _key, sync_targets

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


def apply_pending(pdir: Path, base: str, key: str, timeout: float = 10) -> list[dict]:
    pdir = Path(pdir)
    lock_file = pdir / ".pull.lock"
    lock_fd = open(lock_file, "a")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
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
                    except Exception:
                        pass

        try:
            st, body = _call(base, "GET", f"/api/lab/{project}/requests?status=pending", key, timeout)
            if st != 200:
                return []
        except (OSError, ValueError):
            return []

        items = body.get("items", body) if isinstance(body, dict) else body
        if not isinstance(items, list):
            return []

        items = sorted(items, key=lambda r: r.get("at", ""))
        results = []

        for req in items:
            req_id = req.get("id")
            if not req_id:
                continue

            if req_id in handled:
                status = "duplicate"
                message = "already handled"
                _call(base, "POST", f"/api/lab/{project}/requests/{req_id}/result", key, timeout,
                      json.dumps({"status": status, "message": message}).encode())
                results.append({"id": req_id, "status": status, "message": message})
                continue

            kind = req.get("kind")
            eid = req.get("experiment")
            run_id = req.get("run")
            payload = req.get("payload") or {}

            bad = (kind in ("verdict", "start", "approve", "abandon") and not (isinstance(eid, str) and EXP_ID.fullmatch(eid))) \
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
                photo_list = payload.get("photos", [])
                try:
                    with tempfile.TemporaryDirectory() as td:
                        tmp_dir = Path(td)
                        files = []
                        tabs = []
                        for p in photo_list:
                            sha = p.get("sha256")
                            tab = p.get("tab")
                            photo_url = f"{base}/api/lab/{project}/incoming/{sha}.jpg"
                            req_obj = urllib.request.Request(photo_url, method="GET",
                                                             headers={"X-LocalAI-Mac-Key": key})
                            with urllib.request.urlopen(req_obj, timeout=timeout, context=_context(base)) as resp:
                                data = resp.read()
                            tmp_path = tmp_dir / f"{sha}.jpg"
                            tmp_path.write_bytes(data)
                            files.append(tmp_path)
                            tabs.append(tab)
                        add_photos(paths, run_id, files, tabs=tabs)
                        status = "applied"
                        message = f"{len(files)} photos added"
                except ValueError as e:
                    status = "refused"
                    message = str(e)
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
                    status, message = "conflict", str(e)
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

            try:
                _call(base, "POST", f"/api/lab/{project}/requests/{req_id}/result", key, timeout,
                      json.dumps({"status": status, "message": message}).encode())
            except Exception:
                pass

            results.append({"id": req_id, "status": status, "message": message})

        return results
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        except OSError:
            pass
        lock_fd.close()


def notify_desktop(message: str, title: str = "Print Lab", subtitle: str = "") -> None:
    """Send a native macOS user notification via AppleScript."""
    try:
        sub_clause = f' subtitle "{subtitle}"' if subtitle else ""
        script = f'display notification "{message}" with title "{title}"{sub_clause}'
        subprocess.run(["osascript", "-e", script], timeout=2.0, capture_output=True)
    except Exception:
        pass


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
        notify_desktop(f"Print {t['run_id']} finished. Ready for verdict; give its minutes from the printer's "
                       "history.", "Print Lab", f"{printing['id']}")
        return {"action": "finished_time_unknown", "experiment": printing["id"], "run": t["run_id"],
                "elapsed_minutes": None, "grams": None}
    try:
        e, t = apply_telemetry(paths, printing["id"], run_id=last_run["id"], base=base)
        notify_desktop(f"Print {t['run_id']} finished! Ready for verdict.", "Print Lab", f"{printing['id']}")
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


def pull(pdir: Path, base: str | None = None, timeout: float = 10) -> list[dict]:
    pdir = Path(pdir)
    targets = sync_targets(base)
    key = _key()
    applied = []
    for t in targets:
        try:
            applied += apply_pending(pdir, t, key, timeout)
        except Exception:
            pass
    seen: dict = {}
    lock_fd = open(pdir / ".pull.lock", "a")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # one pull links at a time; a busy lock skips linking
        try:
            applied += link_new_prints(ProjectPaths(pdir), seen)
        except Exception as e:  # linking must never stop the rest of the pull
            print(f"lab pull: linking Bambuddy prints failed: {e}", file=sys.stderr)
    except OSError:
        pass
    finally:
        lock_fd.close()  # releases the lock
    event = check_active_print(ProjectPaths(pdir), targets[0], timeout)
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
        sync(pdir, base, timeout)
    if event:
        applied.append({
            "id": f"event-{event['run']}",
            "status": "applied",
            "message": (f"Print {event['run']} finished; telemetry usage auto-recorded ({event['elapsed_minutes']} min)"
                        if event["elapsed_minutes"] is not None else
                        f"Print {event['run']} finished; its end time is unknown, so record the printer's minutes"),
        })
    return applied


def plist_text(repo: Path, uv: str) -> str:
    log_path = str(Path.home() / "Library" / "Logs" / "print-lab-pull.log")
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
    if not applied:
        print("No pending requests.")
    for r in applied:
        print(f"{r['id']}: {r['status']} ({r['message']})")
    return 0


def register(sub) -> None:
    s = sub.add_parser("pull", help="fetch and apply pending phone requests (verdicts, photos) from Local AI")
    s.add_argument("--install", action="store_true", help="install launchd agent for 60s pickup")
    s.add_argument("--uninstall", action="store_true", help="uninstall launchd agent")
    s.set_defaults(fn=cmd_pull)
