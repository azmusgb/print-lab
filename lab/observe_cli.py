"""`lab observe`: record what you saw on a tile, pair, strip or run (spec 2026-10-26-observation-records-design)."""
import argparse
import json
import sys
from pathlib import Path

from lab.cli import project_dir
from lab.records import observations as obs
from lab.records.project import ProjectPaths


def _paths(args) -> ProjectPaths:
    return ProjectPaths(project_dir(args.project))


def _confirm_owner(snapshots: list[dict]) -> bool:
    """Owner reports from the terminal need a person at it: the answer is read from the TTY, never assumed."""
    if not any(s["source"].get("kind") == "owner_report" for s in snapshots):
        return False
    if not sys.stdin.isatty():
        return False
    return input("Are these your own words and your own assessment? (type yes) ").strip().lower() == "yes"


def _check_experiment(paths: ProjectPaths, snapshots: list[dict], eid: str | None = None) -> None:
    from lab.loop.commands import load_experiment
    if not isinstance(snapshots, list) or not all(isinstance(s, dict) and isinstance(s.get("subject"), dict)
                                                  for s in snapshots):
        raise ValueError("Each observation needs its subject.")
    for s in snapshots:
        sid = s["subject"].get("experiment")
        if eid and sid != eid:
            raise ValueError(f"This request is for {eid}, but an observation names {sid}.")
        if sid:
            e = load_experiment(paths, sid)
            run = s["subject"].get("run")
            if run and run not in {r["id"] for r in e.get("print_runs") or []}:
                raise ValueError(f"{run} isn't a print run of {sid}.")


def cmd_observe(args) -> int:
    paths = _paths(args)
    if args.action == "add":
        snapshots = json.loads(Path(args.file).read_text())["snapshots"]
        _check_experiment(paths, snapshots)
        submitted = {"actor": args.as_actor, "channel": "cli", "request_id": args.request_id,
                     "tty_confirmed": args.as_actor == "owner" and _confirm_owner(snapshots)}
        r = obs.record_session(paths, snapshots, submitted=submitted)
        print(f"Recorded {', '.join(r['ids'])} (group {r['group']}).")
    elif args.action == "correct":
        snapshot = json.loads(Path(args.file).read_text())
        _check_experiment(paths, [snapshot])
        submitted = {"actor": args.as_actor, "channel": "cli",
                     "tty_confirmed": args.as_actor == "owner" and _confirm_owner([snapshot])}
        rec = obs.correct(paths, args.id, expected_rev=args.expected_rev, snapshot=snapshot,
                          reason=args.reason or "", submitted=submitted)
        print(f"{rec['id']} is now at revision {obs.latest(rec)['rev']}.")
    elif args.action == "list":
        recs = obs.for_experiment(paths, args.id) if args.id else obs.all_observations(paths)
        if args.json:
            print(json.dumps(recs, indent=2))
        else:
            for r in recs:
                rv = obs.latest(r)
                print(f"{r['id']} rev {rv['rev']}  {rv['subject']['kind']} {rv['subject'].get('label') or ''}  "
                      f"[{rv['source']['kind']}]  {obs.finding([r]) or 'nothing assessed'}")
    elif args.action == "import-verdicts":
        out = obs.import_verdicts(paths, apply=args.apply)
        if not args.apply:
            print(f"dry run: {len(out)} observation(s) would be created from existing verdicts "
                  "(run again with --apply):")
            for x in out:
                print(f"  {x['import_key']}")
        else:
            print(f"Created {sum(len(x['ids']) for x in out)} observation(s); already-imported verdicts skipped.")
    return 0


def register(sub) -> None:
    p = sub.add_parser("observe", help="record what you saw on a tile, pair, strip or run")
    p.add_argument("action", choices=["add", "correct", "list", "import-verdicts"])
    p.add_argument("id", nargs="?", help="for correct: OBS-NNNN; for list: an experiment")
    p.add_argument("--file", help="JSON: {snapshots: [...]} for add; one snapshot for correct")
    p.add_argument("--expected-rev", type=int, help="for correct: the revision you read")
    p.add_argument("--reason", help="for correct: why it changes")
    p.add_argument("--as", dest="as_actor", choices=["owner", "claude"], default="owner",
                   help="who is submitting it (Claude submits as claude)")
    p.add_argument("--request-id", help="for add: an id that makes a retry a no-op")
    p.add_argument("--apply", action="store_true", help="for import-verdicts: create them (default: dry run)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--project", default=argparse.SUPPRESS)
    p.set_defaults(fn=cmd_observe)
