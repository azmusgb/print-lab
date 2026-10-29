"""Where a project's records live, and its settings (project.json)."""
from dataclasses import dataclass
from pathlib import Path

from lab.records.store import read_json

DEFAULT_BUDGET = {"max_test_minutes": 45, "max_test_g": 25, "max_minutes": 180, "max_g": 100}


@dataclass(frozen=True)
class ProjectPaths:
    root: Path

    def __post_init__(self):
        object.__setattr__(self, "root", Path(self.root))

    @property
    def name(self) -> str: return self.root.name
    @property
    def questions(self) -> Path: return self.root / "questions"
    @property
    def experiments(self) -> Path: return self.root / "experiments"
    @property
    def runs(self) -> Path: return self.root / "runs"
    @property
    def production(self) -> Path: return self.root / "production"
    @property
    def prints(self) -> Path: return self.root / "prints"
    @property
    def sliced(self) -> Path: return self.root / "prints" / "sliced"
    @property
    def jobs(self) -> Path: return self.root / "jobs"
    @property
    def photos(self) -> Path: return self.root / "photos"
    @property
    def sources(self) -> Path: return self.root / "sources"
    @property
    def presets(self) -> Path: return self.root / "presets"
    @property
    def locks(self) -> Path: return self.root / ".locks"
    @property
    def printer(self) -> Path: return self.root.parent.parent / "printer"
    @property
    def setup_log(self) -> Path: return self.printer / "setup.jsonl"
    @property
    def setup_repairs(self) -> Path: return self.printer / "setup-repairs.jsonl"
    @property
    def project_json(self) -> Path: return self.root / "project.json"


def project_settings(paths: ProjectPaths) -> dict:
    s = {"autonomy_level": 2, "plate_time_tolerance_pct": 10, "plate_time_tolerance_source": "provisional",
         "budget": dict(DEFAULT_BUDGET), "production_plate": None}
    if paths.project_json.exists():
        got = read_json(paths.project_json)
        s.update({k: v for k, v in got.items() if k != "budget"})
        s["budget"].update(got.get("budget") or {})
    return s
