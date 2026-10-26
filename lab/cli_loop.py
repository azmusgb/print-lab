"""The Stage 1A.1 experiment loop commands: migrate, question, exp, setup, photos (spec: Commands)."""
import argparse
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
                       not_about_target=args.not_about_target, note=args.note, replace=args.replace, runs=args.run,
                       lighting=args.lighting, grades=args.grade)
    print(f"{e['id']} answered: outcome {e['prediction_outcome'] or '-'}, comparison {e['comparison_validity']['status']}")
    from lab.loop.outcome import criteria_finding, sweep_finding
    if finding := criteria_finding(e) or sweep_finding(e):
        print(f"  finding: {finding}")
    for r in e["comparison_validity"]["reasons"]:
        print(f"  {r['code']}: {r}")
    return 0


def cmd_exp_criteria(args) -> int:
    from lab.loop.commands import set_criteria
    e = set_criteria(_paths(args), args.id, args.add)
    for c in e["criteria"]:
        print(f"{e['id']}: {c['label']} ({' / '.join(c['choices'])})")
    return 0


def cmd_exp_usage(args) -> int:
    from lab.loop.commands import record_usage
    pct = float(args.failed_at.rstrip("%")) if args.failed_at else None
    e = record_usage(_paths(args), args.run_id, failed_at_pct=pct, minutes=args.minutes, grams=args.grams)
    print(f"Recorded usage for {args.run_id} ({e['id']}, now {e['status']})")
    return 0


def cmd_exp_verify(args) -> int:
    from lab.loop.verify import format_verify_text, verify_artifact
    paths = _paths(args)
    res = verify_artifact(paths, args.id, args.file, build_id=args.build)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(format_verify_text(res))
    return 0 if res["ok"] else 1


def cmd_exp_telemetry(args) -> int:
    from lab.loop.telemetry import apply_telemetry, format_telemetry_text, get_run_telemetry
    paths = _paths(args)
    pct = float(args.failed_at.rstrip("%")) if args.failed_at else None
    if args.apply:
        e, t = apply_telemetry(paths, args.id, run_id=args.run, failed_at_pct=pct, force=args.force)
        if args.json:
            print(json.dumps({"experiment": e["id"], "run": t["run_id"], "telemetry": t, "status": e["status"]}, indent=2))
        else:
            print(format_telemetry_text(t))
            print(f"Recorded telemetry usage for {t['run_id']} ({e['id']}, now {e['status']})")
    else:
        t = get_run_telemetry(paths, args.id, run_id=args.run)
        if args.json:
            print(json.dumps(t, indent=2))
        else:
            print(format_telemetry_text(t))
            if not t.get("is_finished"):
                print("Tip: Run `lab exp telemetry <eid> --apply` after the print completes (or `--force` for partial).")
    return 0


def cmd_exp_log(args) -> int:
    import zipfile

    from lab.loop.commands import load_experiment
    from lab.printer import run_log
    from lab.printer.log import heights_from_gcode
    from lab.printer.mqtt import DEFAULT_ENV, listen, load_printer_env
    paths = _paths(args)
    e = load_experiment(paths, args.id)
    runs = e.get("print_runs") or []
    run = next((r for r in runs if r["id"] == args.run), None) if args.run else (runs[-1] if runs else None)
    if args.report:
        if not run or not run.get("printer_log"):
            raise ValueError(f"{args.id} has no printer log yet; run `lab exp log {args.id}` while it prints.")
        print(run_log.report_text(run, (e.get("owner_verdict") or {}).get("marks")))
        return 0
    heights = {}
    build = next((b for b in e.get("builds") or [] if run and b["id"] == run.get("build_id")), None)
    sliced = paths.root / build["sliced"] if build and build.get("sliced") else None
    if sliced and sliced.exists():
        with zipfile.ZipFile(sliced) as z:
            name = next((n for n in z.namelist() if n.endswith(".gcode")), None)
            if name:
                heights = heights_from_gcode(z.read(name).decode("utf-8", "replace"))
    env = load_printer_env(args.env or DEFAULT_ENV)
    print(f"Logging {run['id'] if run else args.id} from {env['host']} until the print ends "
          "(Ctrl-C stops early and keeps what was logged)…")
    try:
        e = run_log.log_run(paths, args.id, env=env, listen=listen, heights=heights, run_id=args.run)
    except (ConnectionError, TimeoutError, OSError) as exc:
        raise ValueError(f"Couldn't log from the printer: {exc}") from exc
    done = next(r for r in e["print_runs"] if r["id"] == (args.run or e["print_runs"][-1]["id"]))
    print(run_log.report_text(done))
    return 0


def cmd_case(args) -> int:
    from lab.loop.cases import check_rule_against_history, format_case_detail, format_cases_list, load_cases, sync_cases
    paths = _paths(args)
    if args.action == "export":
        cases = sync_cases(paths)
        if args.json:
            print(json.dumps(cases, indent=2))
        else:
            print(f"Exported {len(cases)} cases to {paths.root / 'cases'}")
            print(format_cases_list(cases))
        return 0
    if args.action == "list":
        cases = load_cases(paths) or sync_cases(paths)
        if args.json:
            print(json.dumps(cases, indent=2))
        else:
            print(format_cases_list(cases))
        return 0
    if args.action == "show":
        cases = load_cases(paths) or sync_cases(paths)
        c = next((x for x in cases if x["id"] == args.id), None)
        if not c:
            raise ValueError(f"Case {args.id} not found in {paths.name}.")
        if args.json:
            print(json.dumps(c, indent=2))
        else:
            print(format_case_detail(c))
        return 0
    if args.action == "check-rule":
        res = check_rule_against_history(paths, args.id)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"Rule evaluation for {args.id} ({res.get('rule_name')}):")
            print(f"  Revisions checked: {res['revisions_checked']}")
            print(f"  Flagged:           {res['flagged_count']} ({', '.join(res['flagged_versions'])})")
            print(f"  Impact:            {res['precision_note']}")
        return 0
    if args.action == "promote":
        from lab.loop.cases import promote_case_to_rule
        res = promote_case_to_rule(paths, args.id)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"✓ Promoted {res['case_id']} to active rule '{res['rule_name']}':")
            print(f"  Confidence: {res['confidence']} (Level {res['ladder_step']} of 5)")
            print(f"  Condition:  {res['condition']}")
            print(f"  Rule File:  {res['rule_file']}")
            print("  Effect:     Active in `lab inspect`, `lab checks`, and `lab plan`")
        return 0
    return 0


def cmd_exp_plan(args) -> int:
    from lab.loop.builders import plan_experiment
    judged = None
    if args.around is not None:
        from lab.loop.builders import JUDGED_HALF_MM, size_strip
        if args.test_kind == "speed_sweep":  # sizing measures one strip alone; a sweep's time is the whole plate's
            raise ValueError("Give a speed sweep its strip height with --z FROM:TO (e.g. --z 60:72); --around sizes one "
                             "strip alone, and a sweep's time is the whole plate's.")
        z0, z1 = size_strip(_paths(args), args.source, args.object, args.around, args.target_minutes, args.base)
        judged = (args.around - JUDGED_HALF_MM, args.around + JUDGED_HALF_MM)
        print(f"Strip Z {z0:g}–{z1:g} mm fits {args.target_minutes:g} min around {args.around:g} mm")
    elif args.z:
        z0, z1 = (float(x) for x in args.z.split(":"))
    else:
        raise ValueError("Give --z FROM:TO, or --around Z (with --target-minutes) to size the strip.")
    adjust = dict(a.split("=", 1) for a in args.adjust or [])
    eid = plan_experiment(_paths(args), args.question, factor=args.factor, values=args.values.split(","),
                          expect=args.expect, judge_on=args.judge_on, test_kind=args.test_kind, source=args.source,
                          object=args.object, z=(z0, z1), base=args.base, question_text=args.text,
                          hypothesis=args.hypothesis, prediction=args.prediction, why=args.why or "",
                          references=args.reference or [], adjust=adjust, anchor=args.anchor, stepped=args.stepped,
                          tabs=False if args.no_tabs else None, judged=judged)
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


def cmd_exp_send(args) -> int:
    from lab.loop import send as sending
    r = sending.send(_paths(args), args.id, app=args.app,
                     opener=(lambda app, path: None) if args.dry_run else sending._open)
    print(f"{'Would open' if args.dry_run else 'Opened'} {r['file']} in {r['app']} ({r['build']}, the build the check "
          f"passed).\nIn {r['app']}: pick the X2D, set filament 1 to the right AMS tray, press Print. Don't slice it "
          f"again: that prints different G-code.\nOnce it's printing: uv run lab exp start {args.id}")
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


def cmd_photos(args) -> int:
    from lab.loop.commands import add_photos
    out = add_photos(_paths(args), args.run_id, args.files)
    for p in out:
        print(f"Added {p['path']} ({p['source']}, taken {p['captured_at']})")
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

    ph = sub.add_parser("photos", help="add photos to a print run (converted to JPEG, kept outside git)")
    ph.add_argument("action", choices=["add"])
    ph.add_argument("run_id")
    ph.add_argument("files", nargs="+")
    ph.add_argument("--project", default="hex-tile")
    ph.set_defaults(fn=cmd_photos)

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
    pl.add_argument("--z", help="from:to in mm")
    pl.add_argument("--around", type=float, help="size the strip around this model height")
    pl.add_argument("--target-minutes", type=float, default=45)
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
    cr = es.add_parser("criteria", help="the experiment's own per-strip questions, set before its verdict")
    cr.add_argument("id")
    cr.add_argument("--add", action="append", required=True,
                    help="key=Label?:choice,choice, e.g. 'apart=Twists apart by hand?:yes,hard,no'")
    cr.add_argument("--project", default="hex-tile")
    cr.set_defaults(fn=cmd_exp_criteria)
    se = es.add_parser("send", help="open the checked build's sliced file in Bambu Connect, to print it unchanged")
    se.add_argument("id")
    se.add_argument("--app", default="Bambu Connect", help="the app to open it in (default: Bambu Connect)")
    se.add_argument("--dry-run", action="store_true", help="say which file it would open, and open nothing")
    se.add_argument("--project", default="hex-tile")
    se.set_defaults(fn=cmd_exp_send)
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
    v.add_argument("--grade", help="for a speed sweep: each strip by its speed, e.g. 40=clean,60=faint,100=banded; "
                   "for an experiment with criteria: each strip by its tab, e.g. '12A=print:clean,apart:no;12B=…' "
                   "(- for a criterion that can't be judged)")
    v.add_argument("--lighting", default="diagnostic", help="the light you judged under: diagnostic (raking, side "
                   "by side), or e.g. room; only the diagnostic light can support or refute a prediction")
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
    vf = es.add_parser("verify", help="verify a candidate 3MF file matches the approved build artifact before printing")
    vf.add_argument("id", help="experiment ID")
    vf.add_argument("file", help="candidate 3MF or G-code file")
    vf.add_argument("--build", help="specific build ID to verify against")
    vf.add_argument("--json", action="store_true")
    vf.add_argument("--project", default=argparse.SUPPRESS)
    vf.set_defaults(fn=cmd_exp_verify)
    tl = es.add_parser("telemetry", help="live printer telemetry and usage auto-fill for a print run")
    tl.add_argument("id", help="experiment ID")
    tl.add_argument("--run", help="specific run ID (defaults to latest)")
    tl.add_argument("--apply", action="store_true", help="record telemetry usage to the experiment run")
    tl.add_argument("--force", action="store_true", help="allow applying partial usage while still printing")
    tl.add_argument("--failed-at", metavar="PCT", help="record failure at this percentage (1-99)")
    tl.add_argument("--json", action="store_true")
    tl.add_argument("--project", default=argparse.SUPPRESS)
    tl.set_defaults(fn=cmd_exp_telemetry)

    lg = es.add_parser("log", help="record what the printer reports (fans, chamber, temperatures) layer by layer "
                       "while a run prints; read-only")
    lg.add_argument("id", help="experiment ID")
    lg.add_argument("--run", help="specific run ID (defaults to latest)")
    lg.add_argument("--env", help="file with PRINTER_HOST, BAMBU_SERIAL, BAMBU_TOKEN (default "
                    "~/.config/print-lab/printer.env, chmod 600)")
    lg.add_argument("--report", action="store_true", help="show the logged events, lined up with your marks")
    lg.add_argument("--project", default=argparse.SUPPRESS)
    lg.set_defaults(fn=cmd_exp_log)

    cs = sub.add_parser("case", help="Stage 3: case library, confidence ladder, and rule evaluation")
    cs.add_argument("action", choices=["list", "show", "export", "check-rule", "promote"])
    cs.add_argument("id", nargs="?", help="case ID, e.g. CASE-001")
    cs.add_argument("--json", action="store_true")
    cs.add_argument("--project", default=argparse.SUPPRESS)
    cs.set_defaults(fn=cmd_case)
