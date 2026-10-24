"""The Stage 1A.1 experiment loop commands: migrate, question, exp, setup, photos (spec: Commands)."""
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
    import json
    from lab.loop import commands, ledger
    paths = _paths(args)
    if args.action == "status":
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
                          references=args.reference or [], adjust=adjust)
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


def register(sub) -> None:
    s = sub.add_parser("migrate", help="move the hand-written E-001..E-004 into Stage 1A.1 records (once)")
    s.add_argument("--project", default="hex-tile")
    s.set_defaults(fn=cmd_migrate)

    q = sub.add_parser("question", help="questions: status, show")
    q.add_argument("action", choices=["status", "show"])
    q.add_argument("id")
    q.add_argument("--project", default="hex-tile")
    q.set_defaults(fn=cmd_question)

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
    pl.add_argument("--project", default="hex-tile")
    pl.set_defaults(fn=cmd_exp_plan)
    bd = es.add_parser("build", help="build and slice an experiment's plate")
    bd.add_argument("id")
    bd.add_argument("--replace", action="store_true")
    bd.add_argument("--project", default="hex-tile")
    bd.set_defaults(fn=cmd_exp_build)
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
