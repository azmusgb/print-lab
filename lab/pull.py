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

from lab.loop.commands import add_photos, record_verdict
from lab.records.project import ProjectPaths
from lab.records.store import now
from lab.sync import BASE, _call, _context, _key

ROOT = Path(__file__).resolve().parent.parent


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

            if kind == "verdict":
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
                        lighting=payload.get("lighting") or "diagnostic",
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


def pull(pdir: Path, base: str | None = None, timeout: float = 10) -> list[dict]:
    pdir = Path(pdir)
    base = (base or os.environ.get("LAB_LOCALAI_URL") or BASE).rstrip("/")
    key = _key()
    applied = apply_pending(pdir, base, key, timeout)
    if any(r.get("status") == "applied" for r in applied):
        from lab.page import refresh
        refresh(pdir)
        from lab.sync import sync
        sync(pdir, base, timeout)
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
