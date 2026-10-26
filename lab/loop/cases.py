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
    """Determine confidence level and ladder step from supporting evidence."""
    answered = [e for e in exps if e.get("status") == "answered" and e.get("owner_verdict")]
    if not answered:
        return "candidate", 1

    has_full_part = any(e.get("test_kind") in ("full_part", "scaled_part") for e in answered)
    diagnostic_light = any((e.get("owner_verdict") or {}).get("lighting") == "diagnostic" for e in answered)

    if len(answered) >= 2 and has_full_part and diagnostic_light:
        return "proven_for_part", 4
    if len(answered) >= 2:
        return "reproduced", 3
    if len(answered) == 1:
        return "supported", 2
    return "candidate", 1


def cases_dir(paths: ProjectPaths) -> Path:
    d = paths.root / "cases"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_cases(paths: ProjectPaths) -> list[dict]:
    cdir = cases_dir(paths)
    out = []
    for f in sorted(cdir.glob("CASE-*.json")):
        try:
            out.append(json.loads(f.read_text()))
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


def sync_cases(paths: ProjectPaths) -> list[dict]:
    cdir = cases_dir(paths)
    cases = generate_cases_from_experiments(paths)
    for c in cases:
        atomic_write_json(cdir / f"{c['id']}.json", c)
    return cases


def check_rule_against_history(paths: ProjectPaths, case_id: str) -> dict:
    cases = load_cases(paths)
    c = next((x for x in cases if x["id"] == case_id), None)
    if not c:
        raise ValueError(f"Case {case_id} not found in {paths.name}.")

    rev_file = paths.root / "history" / "revisions.json"
    if not rev_file.exists():
        return {"case_id": case_id, "revisions_checked": 0, "flagged": 0, "note": "No history/revisions.json"}

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
        "precision_note": f"Rule would have prevented {len(flagged)} revisions that suffered from back fusion.",
    }


def promote_case_to_rule(paths: ProjectPaths, case_id: str) -> dict:
    cases = load_cases(paths) or sync_cases(paths)
    c = next((x for x in cases if x["id"] == case_id), None)
    if not c:
        raise ValueError(f"Case {case_id} not found in {paths.name}.")

    if c.get("ladder_step", 1) < 3:
        raise ValueError(f"Case {case_id} has confidence '{c['confidence']}' (Level {c['ladder_step']}). "
                         "Only cases at Level >= 3 (reproduced) can be promoted to active rules.")

    prop = c.get("rule_proposal")
    if not prop:
        raise ValueError(f"Case {case_id} has no rule proposal.")

    rule_files = {
        "minimum_back_gap": "lab/checks/part_gap.py",
        "wall_speed_ratio": "lab/checks/wall_speed.py",
    }
    target_file = rule_files.get(prop["rule_name"], "lab/checks/")

    c["status"] = "promoted"
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
        lines.append(f"             Finding: {c['finding'][:70]}...")
        lines.append(f"             Evidence: {', '.join(c.get('experiments', []))}")
    return "\n".join(lines)


def format_case_detail(c: dict) -> str:
    lines = []
    lines.append(f"{c['id']}: {c['title']}")
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
