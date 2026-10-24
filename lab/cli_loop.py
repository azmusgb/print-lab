"""The Stage 1A.1 experiment loop commands: migrate, question, exp, setup, photos (spec: Commands)."""
import json
import sys


def _paths(args):
    from lab.cli import project_dir
    from lab.records.project import ProjectPaths
    return ProjectPaths(project_dir(args.project))


def cmd_migrate(args) -> int:
    from lab.records.migrate import migrate_project
    print("\n".join(migrate_project(_paths(args))))
    return 0


def cmd_question(args) -> int:
    from lab.loop import commands, ledger
    from lab.records.store import parse_budget
    paths = _paths(args)
    if args.action == "new":
        qid = commands.new_question(paths, args.id, parse_budget(args.budget) if args.budget else {})
        print(f"Created {qid}")
        return 0
    if args.action in ("stop", "resume") and not args.reason:
        raise ValueError(f"`lab question {args.action}` needs --reason.")
    if args.action == "stop":
        commands.stop_question(paths, args.id, args.reason)
        print(f"Stopped {args.id}. Nothing in it can start until `lab question resume {args.id}`.")
    elif args.action == "resume":
        commands.resume_question(paths, args.id, parse_budget(args.add) if args.add else None, args.reason)
        print(f"Resumed {args.id}.")
    elif args.action == "rebuild":
        report = commands.rebuild_question(paths, args.id)
        print("\n".join(report))
        return 2 if report[-1] == "No derived state updated." else 0
    elif args.action == "status":
        print(commands.question_status(paths, args.id))
    elif args.action == "show":
        q = commands.load_question(paths, args.id)
        exps = commands.all_experiments(paths)
        print(json.dumps({"question": q, "derived": {"spent": ledger.spent(q, exps), "budget": ledger.budget(q),
                                                     "streak": ledger.streak(q, exps),
                                                     "auto_stop": ledger.auto_stop(q, exps),
                                                     "owner_stop": ledger.owner_stopped(q)}}, indent=2))
    return 0


def cmd_exp_verdict(args) -> int:
    from lab.loop.commands import load_experiment, record_verdict
    paths = _paths(args)
    e = load_experiment(paths, args.id)
    if e.get("judge_on"):
        print(f"Judging on: {e['judge_on']}")
    accept = None if args.accept is None else args.accept == "yes"
    e = record_verdict(paths, args.id, rank=args.rank, strength=args.strength, inconclusive=args.inconclusive,
                       accept=accept, defects=args.defects or [], marks=args.mark or [], witness=args.witness,
                       witness_override=args.witness_override, anchors=args.anchor or [],
                       not_about_target=args.not_about_target, note=args.note, replace=args.replace, runs=args.run)
    print(f"{e['id']} answered: outcome {e['prediction_outcome'] or '-'}, comparison {e['comparison_validity']['status']}")
    for r in e["comparison_validity"]["reasons"]:
        print(f"  {r['code']}: {r}")
    return 0


def cmd_exp_usage(args) -> int:
    from lab.loop.commands import record_usage
    pct = float(args.failed_at.rstrip("%")) if args.failed_at else None
    e = record_usage(_paths(args), args.run_id, failed_at_pct=pct, minutes=args.minutes, grams=args.grams)
    print(f"Recorded usage for {args.run_id} ({e['id']}, now {e['status']})")
    return 0


def cmd_exp_plan(args) -> int:
    from lab.loop.builders import plan_experiment
    z0, z1 = (float(x) for x in args.z.split(":"))
    adjust = dict(a.split("=", 1) for a in args.adjust or [])
    eid = plan_experiment(_paths(args), args.question, factor=args.factor, values=args.values.split(","),
                          expect=args.expect, judge_on=args.judge_on, test_kind=args.test_kind, source=args.source,
                          object=args.object, z=(z0, z1), base=args.base, question_text=args.text,
                          hypothesis=args.hypothesis, prediction=args.prediction, why=args.why or "",
                          references=args.reference or [], adjust=adjust, anchor=args.anchor, stepped=args.stepped,
                          tabs=False if args.no_tabs else None)
    print(f"Planned {eid}; build it with `lab exp build {eid}`")
    return 0


def cmd_exp_build(args) -> int:
    from lab.loop.builders import build_experiment
    b = build_experiment(_paths(args), args.id, replace=args.replace)
    est = b["estimate"] or {}
    print(f"{args.id} {b['id']}: {b['artifact']}\n  sliced {b['sliced']}\n  estimate {est.get('minutes')} min, "
          f"{est.get('g')} g; median layer time {b['measured']['layer_time_median_s']} s\n"
          f"Check it with `lab exp check {args.id}`")
    return 0


def _kv(pairs) -> dict:
    out = {}
    for p in pairs or []:
        k, _, v = p.partition("=")
        try:
            out[k] = json.loads(v)
        except ValueError:
            out[k] = v
    return out


def cmd_setup(args) -> int:
    from lab.loop import setup_log
    paths = _paths(args)
    if args.action == "log":
        ev = setup_log.append_event(paths, args.kind, _kv(args.set), supersedes=args.supersedes,
                                    replacement={"kind": args.replacement_kind, "fields": _kv(args.set)}
                                    if args.kind == "correction" else None)
        print(f"Logged {ev['id']} {ev['kind']}")
    elif args.action == "repair":
        r = setup_log.repair_line(paths, args.line, {"kind": args.replacement_kind, "fields": _kv(args.set),
                                                     "at": args.at}, args.reason)
        print(f"Recorded {r['repair_id']} for line {args.line}")
    else:
        for kind, ev in sorted(setup_log.current_setup(paths).items()):
            print(f"{kind:<24} {ev['at']}  {json.dumps(ev['fields'])}  ({ev['id']})")
    return 0


def cmd_exp_check(args) -> int:
    from lab.loop.guards import run_check
    r = run_check(_paths(args), args.id)
    print(r.text)
    return 0 if r.status in ("ready", "approved") else 2


def cmd_exp_approve(args) -> int:
    from lab.loop.guards import approve
    e = approve(_paths(args), args.id, args.reason)
    print(f"Approved {e['approval']['build_id']} for: {', '.join(e['approval']['approved_reasons'])}. "
          f"Start it with `lab exp start {args.id}` when you send it.")
    return 0


def cmd_exp_start(args) -> int:
    from lab.loop.guards import start
    e, warn = start(_paths(args), args.id)
    for w in warn:
        print(w)
    run = e["print_runs"][-1]
    print(f"{e['id']} printing as {run['id']} ({run['build_id']})")
    return 0


def cmd_exp_abandon(args) -> int:
    from lab.loop.commands import abandon
    abandon(_paths(args), args.id, args.reason)
    print(f"{args.id} abandoned.")
    return 0


def cmd_exp_observe(args) -> int:
    from lab.loop.commands import observe
    observe(_paths(args), args.id, {"type": args.type, "variant": args.variant, "assessment": args.assessment,
                                    "confidence": args.confidence})
    print(f"Observation added to {args.id} (unconfirmed; never counts as your verdict).")
    return 0


def cmd_capability(args) -> int:
    from lab.loop import capabilities
    if args.action == "run":
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            r = capabilities.run_capability(args.name, Path(d))
        print(f"{r['name']}: {'PASSED' if r['passed'] else 'FAILED'} on Bambu Studio {r['bambu_studio']}\n"
              f"  {json.dumps(r['evidence'])}")
        return 0 if r["passed"] else 2
    for name, r in sorted(capabilities.results().items()):
        print(f"{name:<45} {'passed' if r['passed'] else 'FAILED'}  {r['at']}")
    return 0


def register(sub) -> None:
    s = sub.add_parser("migrate", help="move the hand-written E-001..E-004 into Stage 1A.1 records (once)")
    s.add_argument("--project", default="hex-tile")
    s.set_defaults(fn=cmd_migrate)

    q = sub.add_parser("question", help="questions: new, status, show, stop, resume, rebuild")
    q.add_argument("action", choices=["new", "status", "show", "stop", "resume", "rebuild"])
    q.add_argument("id", help="the question's ID (for `new`: the question's text)")
    q.add_argument("--budget", help="for new: e.g. 3h,100g")
    q.add_argument("--add", help="for resume: budget to add, e.g. 60m,30g")
    q.add_argument("--reason")
    q.add_argument("--project", default="hex-tile")
    q.set_defaults(fn=cmd_question)

    cp = sub.add_parser("capability", help="prove a slicer mechanism with a real slice: run NAME, list")
    cp.add_argument("action", choices=["run", "list"])
    cp.add_argument("name", nargs="?")
    cp.set_defaults(fn=cmd_capability)

    st = sub.add_parser("setup", help="the printer's setup log: log, repair, show")
    st.add_argument("action", choices=["log", "repair", "show"])
    st.add_argument("kind", nargs="?", help="filament_dried, vibration_calibration, nozzle_changed, spool_loaded, "
                                            "correction, ...")
    st.add_argument("--set", action="append", help="KEY=VALUE")
    st.add_argument("--supersedes", help="for a correction: the event it replaces")
    st.add_argument("--replacement-kind", help="for a correction or repair: the event's kind")
    st.add_argument("--line", type=int)
    st.add_argument("--at")
    st.add_argument("--reason")
    st.add_argument("--project", default="hex-tile")
    st.set_defaults(fn=cmd_setup)

    exp = sub.add_parser("exp", help="experiments: verdict, usage")
    es = exp.add_subparsers(dest="exp_action", required=True)
    pl = es.add_parser("plan", help="plan an experiment in a question (one factor)")
    pl.add_argument("question")
    pl.add_argument("text", help="what this experiment asks")
    pl.add_argument("--factor", required=True)
    pl.add_argument("--values", required=True, help="comma-separated, one variant each (A, B, ...)")
    pl.add_argument("--expect", default="", help="'B>A:clearly' or 'A=B'")
    pl.add_argument("--judge-on", default="bands")
    pl.add_argument("--test-kind", default="height_strip")
    pl.add_argument("--source", required=True, help="sources/<file>.3mf")
    pl.add_argument("--object", required=True)
    pl.add_argument("--z", required=True, help="from:to in mm")
    pl.add_argument("--base", required=True, help="sources/<file>.3mf whose settings to use")
    pl.add_argument("--hypothesis", required=True)
    pl.add_argument("--prediction", required=True)
    pl.add_argument("--why")
    pl.add_argument("--reference", action="append", help="a variant from an earlier experiment to compare with")
    pl.add_argument("--adjust", action="append", help="KEY=VALUE, a declared dependent adjustment")
    pl.add_argument("--anchor", help="reprint an earlier variant (e.g. E-005-A) on this plate as a control")
    pl.add_argument("--stepped", action="store_true", help="step the values up one strip, with a reversed twin")
    pl.add_argument("--no-tabs", action="store_true", help="no version-ID tabs")
    pl.add_argument("--project", default="hex-tile")
    pl.set_defaults(fn=cmd_exp_plan)
    bd = es.add_parser("build", help="build and slice an experiment's plate")
    bd.add_argument("id")
    bd.add_argument("--replace", action="store_true")
    bd.add_argument("--project", default="hex-tile")
    bd.set_defaults(fn=cmd_exp_build)
    for name, fn, help_ in (("check", cmd_exp_check, "check a build against every guard"),
                            ("start", cmd_exp_start, "record that you sent the print (re-checks first)")):
        c = es.add_parser(name, help=help_)
        c.add_argument("id")
        c.add_argument("--project", default="hex-tile")
        c.set_defaults(fn=fn)
    ap = es.add_parser("approve", help="approve a build that needs it (never an owner stop)")
    ap.add_argument("id")
    ap.add_argument("--reason", required=True)
    ap.add_argument("--project", default="hex-tile")
    ap.set_defaults(fn=cmd_exp_approve)
    ab = es.add_parser("abandon", help="stop an experiment on purpose")
    ab.add_argument("id")
    ab.add_argument("--reason", required=True)
    ab.add_argument("--project", default="hex-tile")
    ab.set_defaults(fn=cmd_exp_abandon)
    ob = es.add_parser("observe", help="an AI observation (kept apart from verdicts)")
    ob.add_argument("id")
    ob.add_argument("--type", required=True)
    ob.add_argument("--variant")
    ob.add_argument("--assessment", required=True)
    ob.add_argument("--confidence", type=float)
    ob.add_argument("--project", default="hex-tile")
    ob.set_defaults(fn=cmd_exp_observe)
    v = es.add_parser("verdict", help="record your verdict on a printed experiment")
    v.add_argument("id")
    v.add_argument("--rank", help="best first, e.g. 'B>A'; 'A=B' for no meaningful difference")
    v.add_argument("--strength", choices=["slightly", "clearly", "a lot"])
    v.add_argument("--inconclusive", metavar="REASON")
    v.add_argument("--accept", choices=["yes", "no"])
    v.add_argument("--defects", nargs="*")
    v.add_argument("--mark", action="append", help="VARIANT:mm up the strip, e.g. A:6")
    v.add_argument("--witness", choices=["normal", "abnormal", "inconclusive"])
    v.add_argument("--witness-override", metavar="REASON")
    v.add_argument("--anchor", action="append", help="ANCHOR=EARLIER:same|different|inconclusive[:strength]")
    v.add_argument("--not-about-target", action="store_true")
    v.add_argument("--note")
    v.add_argument("--replace", action="store_true")
    v.add_argument("--run", action="append")
    v.add_argument("--project", default="hex-tile")
    v.set_defaults(fn=cmd_exp_verdict)
    u = es.add_parser("usage", help="what a print run used, or how far a failed print got")
    u.add_argument("run_id")
    u.add_argument("--failed-at", metavar="PCT")
    u.add_argument("--minutes", type=float)
    u.add_argument("--grams", type=float)
    u.add_argument("--project", default="hex-tile")
    u.set_defaults(fn=cmd_exp_usage)
