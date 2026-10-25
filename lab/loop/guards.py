"""`lab exp check`, `approve` and `start` (spec: Budget and stopping). Every guard is evaluated and every failure
listed; `start` runs the same check on the live state, so a stored 'ready' is only a display."""
from dataclasses import dataclass, field

from lab.loop import ledger
from lab.loop.commands import all_experiments, load_experiment, load_question, refresh_derived, save_experiment
from lab.loop.outcome import comparison_validity, prediction_outcome
from lab.records.project import ProjectPaths, project_settings
from lab.records.store import next_local_id, now, record_lock

BASELINE = ("filament_dried", "vibration_calibration", "nozzle_changed")


@dataclass
class Guard:
    code: str
    ok: bool
    result: str  # "blocked" | "needs_approval" | "rebuild"
    message: str


@dataclass
class CheckResult:
    status: str  # ready | approved | needs_approval | blocked | rebuild
    guards: list[Guard] = field(default_factory=list)
    text: str = ""
    build: dict | None = None
    bundle: list = field(default_factory=list)
    realization: dict | None = None

    def failed(self, result: str | None = None) -> list[Guard]:
        return [g for g in self.guards if not g.ok and (result is None or g.result == result)]


def _n(x) -> str:
    return f"{x:.1f}".rstrip("0").rstrip(".")


def blocking_geometry(findings: list, tabbed: bool) -> list:
    """The findings that block. On a tabbed strip, thin material no higher than the tab is the tab's own text."""
    from lab.loop.tabs import TAB_HEIGHT_MM
    return [f for f in findings if f.severity == "blocking" and f.rule != "nozzle-mismatch"
            and not (tabbed and f.rule == "feature-below-line-width" and f.data["z_max"] <= TAB_HEIGHT_MM)]


def _geometry(paths: ProjectPaths, build: dict, tabbed: bool = False) -> list[str]:
    """Stage 1A blocking findings on each built object (these can't be approved away)."""
    from lab.adapters.threemf import load_object
    from lab.checks import run_checks
    from lab.loop.diff import _objects
    art = paths.root / build["artifact"]
    return [f"{name}: {f.rule}: {f.why}" for name, _ in _objects(art)
            for f in blocking_geometry(run_checks(load_object(art, name), nozzle=0.4), tabbed)]


def check_experiment(paths: ProjectPaths, exp_id: str) -> CheckResult:
    from lab.loop.builders import input_fingerprints
    from lab.loop.diff import actual_differences, undeclared
    e = load_experiment(paths, exp_id)
    q = load_question(paths, e["question"])
    exps = all_experiments(paths)
    settings = project_settings(paths)
    tol = settings["plate_time_tolerance_pct"]
    build = e["builds"][-1] if e.get("builds") else None
    est = (build or {}).get("estimate") or {}
    g: list[Guard] = []

    def add(code, ok, result, message):
        g.append(Guard(code, bool(ok), result, message))

    st = ledger.owner_stopped(q)
    add("owner_stopped", not st, "blocked",
        f"you stopped {q['id']}: {st['reason']}; only `lab question resume {q['id']}` lifts it" if st else "question active")
    auto = ledger.auto_stop(q, exps, tol)
    add("auto_stopped", not auto, "needs_approval", auto["message"] if auto else "no automatic stop")
    add("full_part_required", e["test_kind"] not in ("scaled_part", "full_part"), "needs_approval",
        f"a {e['test_kind']} always needs your approval" if e["test_kind"] in ("scaled_part", "full_part")
        else "diagnostic test type")
    lvl = settings["autonomy_level"]
    add("autonomy_level", lvl >= 2, "needs_approval",
        f"{paths.name} is at autonomy level {lvl}" if lvl < 2 else f"autonomy level {lvl}")
    refuted = [d for d in e.get("derived_from_result") or [] if d in exps and
               prediction_outcome(exps[d], comparison_validity(exps[d], exps, tol)) == "refuted"]
    add("refuted_dependency", not refuted, "needs_approval",
        f"relies on a conclusion that {', '.join(refuted)} refuted" if refuted else "no contradicted reasoning")
    if not build or not build.get("ok"):
        add("no_estimate", False, "rebuild", f"{exp_id} has no successful build; run `lab exp build {exp_id}`")
        return _finish(e, g, None, q, exps, tol, est)
    add("no_estimate", bool(est.get("minutes") is not None), "rebuild",
        "estimate present" if est else "the build has no sliced estimate; rebuild it")
    if e.get("build_spec"):
        from lab.loop import builders
        fp = input_fingerprints(paths, e)
        changed = [k for k in fp if (build.get("inputs") or {}).get(k) != fp[k]]
        code_only = changed and set(changed) <= {"builder_fingerprint", "builder_version"}
        artifact = build.get("artifact") and (paths.root / build["artifact"]).exists()
        if code_only and artifact and builders.same_output(paths, e, build):
            add("stale_build", True, "rebuild", f"the builder code changed, but it writes an identical print file "
                                               f"for {build['id']}")
        else:
            add("stale_build", not changed, "rebuild",
                f"changed since {build['id']}: {', '.join(changed)}; `lab exp build {exp_id} --replace`" if changed
                else "inputs unchanged since the build")
    bundle, real = [], None
    if not build.get("artifact") or not (paths.root / build["artifact"]).exists():
        add("undeclared_difference", False, "rebuild",
            f"{build['id']}'s print file is missing, so the one-factor check can't run; rebuild it")
    else:
        bad, bundle = undeclared(actual_differences(paths, e, build, exps), e)
        add("undeclared_difference", not bad, "blocked",
            "; ".join(f"{d['where']} {d['key']} differs ({d['a']} vs {d['b']})" for d in bad)
            + " — declare it as a dependent adjustment or fix the plan" if bad else "only the declared factor differs")
        geo = _geometry(paths, build, tabbed=bool((e.get("build_spec") or {}).get("tabs")))
        add("geometry_blocking", not geo, "blocked", "; ".join(geo) if geo else "no blocking geometry findings")
        from lab.loop import realized
        real = realized.realization(paths, e, build, exps)
        if real:
            vs = ", ".join(f"{v}: {x['realized']:g} mm/s over {round(x['coverage'] * 100)}%"
                           + (f" (asked {x['requested']:g})" if x["requested"] is not None else "")
                           for v, x in real["variants"].items())
            msg = {"realized": f"realized as asked ({vs})",
                   "realized_differently": f"realized differently ({vs}); the evidence is about the printed values",
                   "not_realized": f"no material difference in the G-code ({vs}); the experiment would test nothing",
                   "single": f"one variant only ({vs})"}[real["status"]]
            add("factor_not_realized", real["status"] != "not_realized", "blocked", msg)
    if est:
        mt, gt = float(q["budget"]["max_test_minutes"]), float(q["budget"]["max_test_g"])
        add("per_test_time", est["minutes"] <= mt, "needs_approval", f"{_n(est['minutes'])} / {_n(mt)} min per test")
        add("per_test_material", est["g"] <= gt, "needs_approval", f"{_n(est['g'])} / {_n(gt)} g per test")
        s, b = ledger.spent(q, exps), ledger.budget(q)
        add("question_time", s["minutes"] + est["minutes"] <= b["minutes"] + 1e-9, "needs_approval",
            f"{_n(s['minutes'])} + {_n(est['minutes'])} / {_n(b['minutes'])} min for {q['id']}")
        add("question_material", s["g"] + est["g"] <= b["g"] + 1e-9, "needs_approval",
            f"{_n(s['g'])} + {_n(est['g'])} / {_n(b['g'])} g for {q['id']}")
    failed = [r for r in e.get("print_runs") or [] if r.get("failed")]
    add("retry_limit", len(failed) < 2, "needs_approval",
        "two attempts failed: " + "; ".join(f"{r['id']} at {round(r['failed']['at_fraction'] * 100)}%"
                                             + (f" ({r['failed']['note']})" if r['failed'].get('note') else "")
                                             for r in failed) if len(failed) >= 2 else f"{len(failed)} / 2 failed attempts")
    reasons = comparison_validity(e, exps, tol)["reasons"]
    mism = [r for r in reasons if r["code"] in ("layer_time_mismatch", "reference_unmeasurable",
                                                "reference_not_printed")]
    add("plate_mismatch", not mism, "needs_approval",
        "; ".join(f"layer time {r['this_s']} s vs {r['other_s']} s on {r['variant']}'s plate (over {tol}%)"
                  if r["code"] == "layer_time_mismatch" else f"{r['variant']}'s plate can't be compared ({r['code']})"
                  for r in mism) + "; approving lets it print, but the comparison stays confounded" if mism
        else "plate timing matches the compared plates")
    res = _finish(e, g, build, q, exps, tol, est)
    res.bundle, res.realization = bundle, real
    return res


def _finish(e, guards, build, q, exps, tol, est) -> CheckResult:
    blocked = [x for x in guards if not x.ok and x.result == "blocked"]
    rebuild = [x for x in guards if not x.ok and x.result == "rebuild"]
    approval = [x for x in guards if not x.ok and x.result == "needs_approval"]
    a = e.get("approval")
    covered = bool(a and build and a["build_id"] == build["id"] and a["artifact_sha256"] == build.get("artifact_sha256")
                   and {x.code for x in approval} <= set(a["approved_reasons"]))
    status = ("blocked" if blocked else "rebuild" if rebuild else
              ("approved" if covered else "needs_approval") if approval else "ready")
    s = ledger.spent(q, exps)
    lines = [f"{e['id']} CHECK", "", "Build"]
    lines.append(f"  {build['id']}  {_n(est.get('minutes', 0))} min  {_n(est.get('g', 0))} g" if build else "  none")
    b = ledger.budget(q)
    lines += ["", "Question budget", f"  Used        {_n(s['minutes'])} / {_n(b['minutes'])} min, "
                                     f"{_n(s['g'])} / {_n(b['g'])} g"]
    if est:
        lines.append(f"  After test  {_n(s['minutes'] + est['minutes'])} / {_n(b['minutes'])} min, "
                     f"{_n(s['g'] + est['g'])} / {_n(b['g'])} g")
    lines += ["", "Guards"] + [f"  {'✓' if x.ok else '✗'} {x.code:<22} {x.message}" for x in guards]
    lines += ["", "Result", f"  {status.upper().replace('_', ' ')}"]
    if not covered:
        for x in blocked + rebuild + approval:
            lines.append(f"  • {x.code}: {x.message}")
    return CheckResult(status=status, guards=guards, text="\n".join(lines), build=build)


def run_check(paths: ProjectPaths, exp_id: str) -> CheckResult:
    """`lab exp check`: the check, then the status it implies (ready / needs approval / approved)."""
    r = check_experiment(paths, exp_id)
    with record_lock(paths.locks, exp_id, f"lab exp check {exp_id}"):
        e = load_experiment(paths, exp_id)
        new = {"ready": "ready", "approved": "approved", "needs_approval": "needs_approval"}.get(r.status)
        if e["status"] in ("built", "ready", "needs_approval", "approved") and new and e["status"] != new:
            e["status"] = new
        if r.build:
            b = next(x for x in e["builds"] if x["id"] == r.build["id"])
            if r.bundle:
                b.update(factor_scope="bundle", bundle_differences=r.bundle)
            if r.realization:
                b["realization"] = r.realization
            b["check"] = {"status": r.status, "at": now(),  # a display for the page; `start` always re-checks
                          "guards": [{"code": g.code, "ok": g.ok, "result": g.result, "message": g.message}
                                     for g in r.guards]}
        save_experiment(paths, e)
    return r


def approve(paths: ProjectPaths, exp_id: str, reason: str) -> dict:
    r = check_experiment(paths, exp_id)
    if r.status in ("blocked", "rebuild"):
        raise ValueError("Can't approve: " + "; ".join(f"{x.code}: {x.message}" for x in r.failed()
                                                         if x.result != "needs_approval"))
    if r.status != "needs_approval":
        raise ValueError(f"{exp_id} is {r.status}; there's nothing to approve.")
    with record_lock(paths.locks, exp_id, f"lab exp approve {exp_id}"):
        e = load_experiment(paths, exp_id)
        e["approval"] = {"build_id": r.build["id"], "artifact_sha256": r.build.get("artifact_sha256"),
                         "approved_reasons": [x.code for x in r.failed("needs_approval")], "by": "owner",
                         "at": now(), "reason": reason}
        e["status"] = "approved"
        return save_experiment(paths, e)


def start(paths: ProjectPaths, exp_id: str) -> tuple[dict, list[str]]:
    """Record that the owner sent the print: re-check the live state, snapshot the setup, open a print run."""
    from lab.loop.setup_log import current_setup
    e = load_experiment(paths, exp_id)
    if e["status"] == "printing":
        return e, [f"{exp_id} already started ({e['print_runs'][-1]['id']}); nothing written."]
    if e["status"] not in ("built", "ready", "needs_approval", "approved"):
        raise ValueError(f"{exp_id} is {e['status']}; only a built experiment can be started. "
                         "To print it again, plan a repeat.")
    r = check_experiment(paths, exp_id)
    if r.status not in ("ready", "approved"):
        raise ValueError(f"Can't start {exp_id}:\n" + "\n".join(f"  {x.code}: {x.message}" for x in r.failed()))
    setup = current_setup(paths)
    missing = [k for k in BASELINE if k not in setup]
    with record_lock(paths.locks, exp_id, f"lab exp start {exp_id}"):
        e = load_experiment(paths, exp_id)
        run = {"id": next_local_id(e, "print_runs", f"PR-{exp_id[2:]}"), "build_id": r.build["id"],
               "started_at": now(), "setup": {k: {"id": v["id"], "at": v["at"], "fields": v["fields"]}
                                              for k, v in setup.items()},
               "baseline_missing": missing, "usage": None, "failed": None, "photos": []}
        e["print_runs"].append(run)
        e["status"] = "printing"
        e = save_experiment(paths, refresh_derived(paths, e))
    warn = [f"Not in the setup log: {', '.join(missing)}. Recorded as missing on {run['id']}."] if missing else []
    return e, warn
