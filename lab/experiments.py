"""Experiments as JSON files: one experimental factor, a test kind, baseline conditions and the server-style checks
(here run locally; Stage 1B moves them to Local AI)."""
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from lab.findings import Finding

TEST_KINDS = ("section_coupon", "orientation_coupon", "fit_coupon", "joint_coupon", "height_strip", "scaled_part",
              "full_part")
BASELINE_ITEMS = ("filament_dried", "vibration_calibration", "nozzle_confirmed", "plate")


@dataclass
class Experiment:
    id: str
    project: str
    question: str
    hypothesis: str
    prediction: str
    why_this_test: str
    test_kind: str
    factor: dict
    controlled: dict = field(default_factory=dict)
    dependent_adjustments: dict = field(default_factory=dict)
    baseline: dict = field(default_factory=dict)
    status: str = "planned"
    blocked_reason: str = ""
    print_runs: list = field(default_factory=list)
    findings: list = field(default_factory=list)
    jobs: list = field(default_factory=list)


def _next(folder: Path, prefix: str, glob: str) -> str:
    nums = [int(m.group(1)) for p in folder.glob(glob) if (m := re.search(rf"{prefix}-?(\d+)", p.name))]
    return f"{prefix}-{(max(nums) + 1 if nums else 1):03d}"


def next_id(project_dir: Path) -> str:
    return _next(Path(project_dir) / "experiments", "E", "E-*.json")


def next_print_run_id(project_dir: Path) -> str:
    return _next(Path(project_dir) / "prints", "PR", "*PR*.3mf")


def save(exp: Experiment, project_dir: Path) -> Path:
    if exp.test_kind not in TEST_KINDS:
        raise ValueError(f"Unknown test kind '{exp.test_kind}'. Use one of: {', '.join(TEST_KINDS)}")
    path = Path(project_dir) / "experiments" / f"{exp.id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(exp), indent=2))
    return path


def load(path: Path) -> Experiment:
    return Experiment(**json.loads(Path(path).read_text()))


def _flatten(d: dict) -> dict:
    out = {}
    for group in ("model", "settings"):
        out.update(d.get(group, {}))
    return out


def differing_factors(before: dict, after: dict, ignore: set[str]) -> list[str]:
    """Model parameters and slicer settings that differ between two versions ({"model": {...}, "settings": {...}})."""
    a, b = _flatten(before), _flatten(after)
    return sorted(k for k in set(a) | set(b) if k not in ignore and a.get(k) != b.get(k))


def check_plan(exp: Experiment, before: dict, after: dict) -> list[Finding]:
    out = []
    allowed = {exp.factor["name"], *exp.dependent_adjustments}
    extra = differing_factors(before, after, ignore=allowed)
    if extra:
        out.append(Finding(rule="stacked-changes", severity="blocking", where=", ".join(extra),
                           why=f"Besides {exp.factor['name']}, this version also changes {', '.join(extra)}. With more "
                               "than one change, the result can't say which one did it.",
                           fix="Put the other changes back, or declare each as a dependent adjustment with its reason.",
                           data={"extra": extra}))
    if exp.test_kind in ("scaled_part", "full_part"):
        out.append(Finding(rule="override-needed", severity="blocking", where=exp.test_kind,
                           why="A scaled or full part needs an approved override: a smaller test must not be able to "
                               "show the effect.",
                           fix="Use a smaller test, or request an override with its seven requirements."))
    missing = [k for k in BASELINE_ITEMS if not exp.baseline.get(k)]
    if missing:
        out.append(Finding(rule="baseline-incomplete", severity="info", where=", ".join(missing),
                           why="Without these baseline conditions the print's result is graded F.",
                           fix="Dry the filament, run the printer's vibration calibration, confirm the nozzle and "
                               "plate, and record them.", data={"missing": missing}))
    return out


def link_slice_job(project_dir: Path, path_3mf: Path, job_id: str) -> str | None:
    """Record a slice job on the print run a lab print file belongs to (from its Metadata/print_lab.json). Returns
    the experiment's id, or None for a file the lab didn't make."""
    import zipfile
    with zipfile.ZipFile(path_3mf) as z:
        if "Metadata/print_lab.json" not in z.namelist():
            return None
        meta = json.loads(z.read("Metadata/print_lab.json"))
    path = Path(project_dir) / "experiments" / f"{meta.get('experiment_id')}.json"
    if not path.exists():
        return None
    exp = json.loads(path.read_text())
    for run in exp.get("print_runs", []):
        if run.get("id") == meta.get("print_run_id"):
            run["slice_job"] = job_id
            path.write_text(json.dumps(exp, indent=2) + "\n")
            return exp["id"]
    return None
