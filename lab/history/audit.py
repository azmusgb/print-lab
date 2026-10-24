"""The history audit: what the past revisions and the owner's reported outcomes say, before any new experiment."""
import json
from collections import Counter, defaultdict
from pathlib import Path

from lab.history.lineage import Transition
from lab.history.revisions import Revision

RIPPLE = "upper-edge ripple"
RIPPLE_FACTORS = {"orient_for_print", "skin", "layer_height", "outer_wall_speed"}
NOT_YET_TRIED = [
    "the printer's vibration (resonance) calibration",
    "a slower speed on the upper half only (height-range modifier)",
    "matte PLA",
    "filament confirmed dry before printing",
    "leaning the tile (the owner asked on 15 Oct; argued against, never tested)",
]
NEXT = ("EXP-001: does v58 (no join that starts partway up) remove the mid-height line? A height strip across "
        "Z 60–100 mm of the 6\" pair, v58 against v56, both on the 0.4 nozzle. Why: the line appears from v53, when "
        "the upper-edge join began at mid-height, and stays while that join is kept.")


def load_outcomes(path: Path) -> list[dict]:
    return json.loads(Path(path).read_text())


def audit_text(revs: list[Revision], trans: list[Transition], outcomes: list[dict]) -> str:
    vs = sorted(r.version for r in revs)
    gaps = sorted({g for t in trans for g in t.gap})
    lines = ["# Hex tile history audit", "", "## Revisions",
             f"- {len(vs)} revisions with files" + (f": v{vs[0]}–v{vs[-1]}" if vs else ""),
             f"- versions with no files: {', '.join(f'v{g}' for g in gaps) or 'none'}", "", "## Evidence"]
    by = Counter(t.grade for t in trans)
    for g, meaning in (("A", "one change"), ("B", "two changes"), ("C", "3–4 changes"), ("D", "5 or more changes"),
                       ("F", "what printed is unknown or contradicts the file")):
        steps = [f"v{t.from_v}→v{t.to_v}" for t in trans if t.grade == g]
        lines.append(f"- {g} ({meaning}): {by.get(g, 0)}" + (f" — {', '.join(steps)}" if steps else ""))
    lines += ["", "## Persistent defects"]
    seen = defaultdict(set)
    for o in outcomes:
        for d in o["defects"]:
            if o["version"] is not None:
                seen[d].add(o["version"])
    for d, vers in sorted(seen.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"- {d}: {', '.join(f'v{v}' for v in sorted(vers))}")
    lines += ["", "## Changes that never touched it"]
    rip = sorted(seen.get(RIPPLE, []))
    if rip:
        span = [t for t in trans if rip[0] <= t.from_v and t.to_v <= rip[-1]]
        untouched = [f"v{t.from_v}→v{t.to_v}" for t in span
                     if not (set(t.scad_changes) | set(t.settings_changes)) & RIPPLE_FACTORS]
        lines.append(f"- {RIPPLE} (reported {', '.join(f'v{v}' for v in rip)}): {len(untouched)} of {len(span)} steps "
                     f"in between changed none of {', '.join(sorted(RIPPLE_FACTORS))}"
                     + (f" — {', '.join(untouched)}" if untouched else ""))
    lines += ["", "## Not yet tried"] + [f"- {x}" for x in NOT_YET_TRIED]
    lines += ["", "## Next experiment", f"- {NEXT}", "",
              "Outcomes come from the owner's messages in the chat; none are confirmed yet."]
    return "\n".join(lines) + "\n"
