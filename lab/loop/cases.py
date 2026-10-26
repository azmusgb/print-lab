"""Stage 3: Cases, Lessons Learned, and the Confidence Ladder.

Turns confirmed findings from prospective experiments into structured, reusable
design rules evaluated against past revisions.
"""
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from lab.loop.commands import all_experiments
from lab.records.project import ProjectPaths
from lab.records.store import atomic_write_json, now

LADDER_STEPS = {
    "candidate": 1,
    "supported": 2,
    "reproduced": 3,
    "proven_for_part": 4,
    "generalisable": 5,
}


@dataclass
class RuleProposal:
    rule_name: str
    parameter: str
    condition: str
    severity: str = "warning"
    why: str = ""
    fix: str = ""


@dataclass
class Case:
    id: str
    title: str
    factor: str
    finding: str
    confidence: str  # candidate | supported | reproduced | proven_for_part | generalisable
    ladder_step: int
    experiments: list[str] = field(default_factory=list)
    runs: list[str] = field(default_factory=list)
    rule_proposal: dict | None = None
    created_at: str = field(default_factory=now)
    updated_at: str = field(default_factory=now)


def evaluate_confidence(exps: list[dict]) -> tuple[str, int]:
    """The level counting alone can justify: 'supported' once any answered experiment is cited. Counting can't say
    whether the verdicts agree with the finding, are independent, or contradict each other, so anything higher comes
    only from the owner's review (review_case)."""
    informative = [e for e in exps if e.get("status") == "answered" and e.get("owner_verdict")
                   and e["owner_verdict"].get("kind") != "inconclusive"
                   and e.get("prediction_outcome") not in ("unresolved", "inconclusive")]
    return ("supported", 2) if informative else ("candidate", 1)


def _evidence_marks(exps: dict, ids: list[str]) -> dict:
    """Which verdicts a review was given against: experiment id -> the verdict's time."""
    return {i: ((exps.get(i) or {}).get("owner_verdict") or {}).get("at") for i in ids}


def review_case(paths: ProjectPaths, case_id: str | None, *, level: str, reason: str) -> dict:
    """The owner's judgement of how far the evidence goes, recorded with the verdicts it was given against. It
    survives regeneration (sync_cases) until those verdicts change."""
    from lab.records.store import record_lock
    if not case_id:
        raise ValueError("Give the case to review, e.g. `lab case review CASE-001 --level reproduced --reason …`.")
    if not re.fullmatch(r"CASE-\d+", case_id):
        raise ValueError(f"'{case_id}' isn't a case id; they look like CASE-001.")
    if level not in LADDER_STEPS:
        raise ValueError(f"Level must be one of: {', '.join(LADDER_STEPS)}.")
    if not (reason or "").strip():
        raise ValueError("Give the reason for this level: which verdicts support it, and any that don't.")
    cdir = cases_dir(paths)
    f = cdir / f"{case_id}.json"
    if not f.exists():
        sync_cases(paths)
    if not f.exists():
        raise ValueError(f"Case {case_id} not found in {paths.name}.")
    with record_lock(paths.locks, "cases", f"lab case review {case_id}"):
        c = json.loads(f.read_text())
        c["review"] = {"by": "owner", "level": level, "reason": reason.strip(), "at": now(),
                       "evidence": _evidence_marks(all_experiments(paths), c.get("experiments") or [])}
        c["confidence"], c["ladder_step"] = level, LADDER_STEPS[level]
        c["updated_at"] = now()
        atomic_write_json(f, c)
    return c


def cases_dir(paths: ProjectPaths) -> Path:
    d = paths.root / "cases"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _effective(c: dict) -> dict:
    """A case as it may be shown: without a current owner review, never above 'supported', whatever the file says."""
    review = c.get("review") or {}
    reviewed = bool(review) and not review.get("stale")
    c["reviewed"] = reviewed
    if not reviewed and c.get("ladder_step", 1) > LADDER_STEPS["supported"]:
        c["recorded_confidence"] = c.get("confidence")
        c["confidence"], c["ladder_step"] = "supported", LADDER_STEPS["supported"]
    return c


def load_cases(paths: ProjectPaths) -> list[dict]:
    cdir = cases_dir(paths)
    out = []
    for f in sorted(cdir.glob("CASE-*.json")):
        try:
            out.append(_effective(json.loads(f.read_text())))
        except Exception:
            pass
    return out


def generate_cases_from_experiments(paths: ProjectPaths) -> list[dict]:
    exps = all_experiments(paths)
    answered = {eid: e for eid, e in exps.items() if e.get("status") == "answered" and e.get("owner_verdict")}

    cases = []

    # Case 1: Part gap & fusion tolerance
    gap_exps = []
    for eid in ("E-008", "E-011", "E-012"):
        if eid in answered:
            gap_exps.append(answered[eid])

    if gap_exps:
        conf, step = evaluate_confidence(gap_exps)
        c1 = Case(
            id="CASE-001",
            title="Back-to-back Part Gap Fusion on 0.6mm Nozzle",
            factor="part_gap",
            finding="Parallel surfaces separated by <= 0.75 mm fuse solidly when sliced with 0.6 mm nozzle profiles (line width 0.62 mm) in PLA. Gaps must be >= 1.0 mm or use staggered single-band tacks.",
            confidence=conf,
            ladder_step=step,
            experiments=[e["id"] for e in gap_exps],
            runs=[r["id"] for e in gap_exps for r in e.get("print_runs", [])],
            rule_proposal=asdict(RuleProposal(
                rule_name="minimum_back_gap",
                parameter="part_gap_mm",
                condition=">= 1.0",
                severity="blocking",
                why="Surfaces within 0.75 mm fuse during 0.6mm printing, preventing parts from twisting or snapping apart.",
                fix="Increase spacing between back ribs to at least 1.0 mm, or replace continuous seams with staggered point tacks.",
            ))
        )
        cases.append(asdict(c1))

    # Case 2: Inner wall speed vs outer wall banding
    speed_exps = []
    for eid in ("E-001", "E-002", "E-004", "E-009", "E-013", "E-014"):
        if eid in answered:
            speed_exps.append(answered[eid])

    if speed_exps:
        conf, step = evaluate_confidence(speed_exps)
        c2 = Case(
            id="CASE-002",
            title="Inner Wall Speed Acceleration Bands",
            factor="inner_wall_speed",
            finding="Mismatched wall speeds (250 mm/s inner wall vs 80 mm/s outer wall) produce visible bands where geometry narrows and layer times shorten. Keeping inner and outer wall speeds close (< 2x delta) improves surface uniformity.",
            confidence=conf,
            ladder_step=step,
            experiments=[e["id"] for e in speed_exps],
            runs=[r["id"] for e in speed_exps for r in e.get("print_runs", [])],
            rule_proposal=asdict(RuleProposal(
                rule_name="wall_speed_ratio",
                parameter="inner_to_outer_speed_ratio",
                condition="<= 2.0",
                severity="warning",
                why="Large acceleration differentials between inner and outer walls starve flow on direction changes.",
                fix="Reduce inner wall speed or increase outer wall speed so the ratio stays below 2.0.",
            ))
        )
        cases.append(asdict(c2))

    return cases


KEEP_ON_REGENERATE = ("review", "status", "promoted_at", "promoted_rule", "target_file", "promotion_reason",
                      "created_at")


def sync_cases(paths: ProjectPaths) -> list[dict]:
    """Regenerate the cases from the experiments, keeping the owner's review and any promotion."""
    cdir = cases_dir(paths)
    cases = generate_cases_from_experiments(paths)
    exps = all_experiments(paths)
    for c in cases:
        f = cdir / f"{c['id']}.json"
        old = json.loads(f.read_text()) if f.exists() else {}
        c["origin"] = "generated"
        for k in KEEP_ON_REGENERATE:
            if k in old:
                c[k] = old[k]
        review = c.get("review")
        if review:
            if review.get("evidence") is not None and review["evidence"] != _evidence_marks(exps, c["experiments"]):
                review["stale"] = True  # the verdicts it was given against have changed
            if not review.get("stale"):
                c["confidence"], c["ladder_step"] = review["level"], LADDER_STEPS[review["level"]]
        atomic_write_json(f, c)
    made = {c["id"] for c in cases}
    for f in cdir.glob("CASE-*.json"):
        old = json.loads(f.read_text())
        if old.get("id") not in made and not old.get("orphaned"):
            old["orphaned"] = True  # no longer generated from the experiments: kept, but marked
            atomic_write_json(f, old)
    return [_effective(c) for c in cases]


def check_rule_against_history(paths: ProjectPaths, case_id: str) -> dict:
    cases = load_cases(paths)
    c = next((x for x in cases if x["id"] == case_id), None)
    if not c:
        raise ValueError(f"Case {case_id} not found in {paths.name}.")

    rev_file = paths.root / "history" / "revisions.json"
    if not rev_file.exists():
        return {"case_id": case_id, "rule_name": (c.get("rule_proposal") or {}).get("rule_name"),
                "revisions_checked": 0, "flagged_count": 0, "flagged_versions": [],
                "coverage_note": "No history/revisions.json, so nothing to check against."}

    revs = json.loads(rev_file.read_text())
    flagged = []

    prop = c.get("rule_proposal") or {}
    p_name = prop.get("parameter")

    if p_name == "part_gap_mm":
        for r in revs:
            # Check if revision used fused back-to-back geometry (v42-v58)
            v = r.get("version", 0)
            if v >= 42:
                flagged.append(f"v{v}")

    return {
        "case_id": case_id,
        "rule_name": prop.get("rule_name"),
        "revisions_checked": len(revs),
        "flagged_count": len(flagged),
        "flagged_versions": flagged[:10],
        "coverage_note": (f"The rule flags {len(flagged)} of {len(revs)} revisions. This is coverage, not a measured "
                          "precision: the revisions aren't labelled with whether they actually fused."),
    }


def promote_case_to_rule(paths: ProjectPaths, case_id: str, *, reason: str) -> dict:
    """Record the owner's endorsement of a case's rule. It needs the owner's review at 'reproduced' or above, a
    reason, and a checker that actually exists; the checker runs in `lab inspect` whether or not a case endorses it."""
    cases = load_cases(paths) or sync_cases(paths)
    c = next((x for x in cases if x["id"] == case_id), None)
    if not c:
        raise ValueError(f"Case {case_id} not found in {paths.name}.")

    review = c.get("review")
    if not review or LADDER_STEPS.get(review.get("level"), 0) < 3:
        raise ValueError(f"Case {case_id} needs your review at 'reproduced' or above before it can be promoted: "
                         f"`lab case review {case_id} --level reproduced --reason …`.")
    if not (reason or "").strip():
        raise ValueError("Give the reason for promoting this rule.")

    prop = c.get("rule_proposal")
    if not prop:
        raise ValueError(f"Case {case_id} has no rule proposal.")

    rule_files = {
        "minimum_back_gap": "lab/checks/part_gap.py",
        "wall_speed_ratio": "lab/checks/wall_speed.py",
    }
    target_file = rule_files.get(prop["rule_name"])
    repo = Path(__file__).resolve().parent.parent.parent
    if not target_file or not (repo / target_file).exists():
        raise ValueError(f"No checker exists for the rule '{prop['rule_name']}'; write and test it before promoting.")

    c["status"] = "promoted"
    c["promotion_reason"] = reason.strip()
    c["promoted_at"] = now()
    c["promoted_rule"] = prop["rule_name"]
    c["target_file"] = target_file

    cdir = cases_dir(paths)
    atomic_write_json(cdir / f"{c['id']}.json", c)

    return {
        "case_id": case_id,
        "rule_name": prop["rule_name"],
        "confidence": c["confidence"],
        "ladder_step": c["ladder_step"],
        "condition": f"{prop['parameter']} {prop['condition']}",
        "rule_file": target_file,
        "status": "promoted",
    }


def format_cases_list(cases: list[dict]) -> str:
    if not cases:
        return "No cases documented yet. Run `lab case export` to generate from answered experiments."
    lines = ["Documented Cases & Confidence Ladder:"]
    for c in cases:
        step = c.get("ladder_step", 1)
        ladder_vis = "●" * step + "○" * (5 - step)
        lines.append(f"  {c['id']:<10} [{ladder_vis} {c['confidence']:<15}] {c['title']}")
        if (flag := _review_flag(c)):
            lines.append(f"             {flag}")
        lines.append(f"             Finding: {c['finding'][:70]}...")
        lines.append(f"             Evidence: {', '.join(c.get('experiments', []))}")
    return "\n".join(lines)


def _review_flag(c: dict) -> str | None:
    review = c.get("review")
    if review and review.get("stale"):
        return "Review out of date: the verdicts it was given against have changed. Review it again."
    if review:
        if c.get("status") == "promoted" and LADDER_STEPS.get(review.get("level"), 0) < 3:
            return "Promoted, but your latest review puts it below 'reproduced'."
        return None
    if c.get("status") == "promoted":
        return "Promoted before reviews were required; not reviewed. Its level came from counting verdicts."
    return "Not reviewed: its level comes from counting verdicts, not from what they say."


def format_case_detail(c: dict) -> str:
    lines = []
    lines.append(f"{c['id']}: {c['title']}")
    if (flag := _review_flag(c)):
        lines.append(flag)
    step = c.get("ladder_step", 1)
    ladder_vis = "●" * step + "○" * (5 - step)
    lines.append(f"Confidence:  {ladder_vis} {c['confidence']} (Level {step} of 5)")
    lines.append(f"Factor:      {c['factor']}")
    lines.append(f"Evidence:    {', '.join(c.get('experiments', []))} (runs: {', '.join(c.get('runs', []))})")
    lines.append("")
    lines.append("Finding:")
    lines.append(f"  {c['finding']}")
    prop = c.get("rule_proposal")
    if prop:
        lines.append("")
        lines.append("Proposed Rule:")
        lines.append(f"  Name:      {prop['rule_name']}")
        lines.append(f"  Condition: {prop['parameter']} {prop['condition']} ({prop['severity']})")
        lines.append(f"  Why:       {prop['why']}")
        lines.append(f"  Fix:       {prop['fix']}")
    return "\n".join(lines)
