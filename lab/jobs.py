"""Every external tool run is a Job: kept on disk whether it worked or not (never publish partial output)."""
import hashlib
import json
import secrets
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class Job:
    id: str
    tool: str
    tool_version: str | None
    command: list[str]
    input_sha256: dict[str, str]
    exit_code: int
    stdout: str
    stderr: str
    outputs_present: list[str] = field(default_factory=list)
    ok: bool = False
    started: str = ""
    ended: str = ""


class LabToolError(Exception):
    """A tool run that failed; .job holds its full record."""

    def __init__(self, message: str, job: Job):
        super().__init__(message)
        self.job = job


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_tool(args: list[str], *, inputs: list[Path], outputs: list[Path], jobs_dir: Path, tool: str,
             tool_version: str | None = None, timeout: int = 1800, cwd: Path | None = None) -> Job:
    """Run one command (never through a shell) and write its Job record to jobs_dir/<id>.json."""
    jobs_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    job = Job(id=f"job-{stamp}-{secrets.token_hex(2)}", tool=tool, tool_version=tool_version,
              command=[str(a) for a in args], input_sha256={str(p): sha256(Path(p)) for p in inputs},
              exit_code=-1, stdout="", stderr="", started=_now())
    try:
        r = subprocess.run(job.command, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        job.exit_code, job.stdout, job.stderr = r.returncode, r.stdout, r.stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        job.stderr = f"{type(e).__name__}: {e}"
    job.ended = _now()
    job.outputs_present = [str(p) for p in outputs if Path(p).exists()]
    job.ok = job.exit_code == 0 and len(job.outputs_present) == len(outputs)
    (jobs_dir / f"{job.id}.json").write_text(json.dumps(asdict(job), indent=2))
    return job
