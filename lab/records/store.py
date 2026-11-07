"""Plain-file records: atomic JSON writes, per-record locks and collision-free IDs (spec: Commands)."""
import json
import os
import re
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl


class RecordError(ValueError):
    """A record that can't be read, or a record that's busy. The message says which file and what to do."""

    def __init__(self, path: Path | str, field: str | None, message: str):
        self.path, self.field, self.message = Path(path), field, message
        where = f"{Path(path).name}" + (f" ({field})" if field else "")
        super().__init__(f"{where}: {message}")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_temp(folder: Path, obj: dict) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=folder, prefix=".tmp-", suffix=".json", delete=False) as f:
        json.dump(obj, f, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    return Path(f.name)


def atomic_write_json(path: Path, obj) -> None:
    """Write to a temporary file in the same folder, then replace: a crash never leaves half a record."""
    path = Path(path)
    tmp = _write_temp(path.parent, obj)
    try:
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def read_json(path: Path) -> dict:
    path = Path(path)
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise RecordError(path, None, f"isn't valid JSON (line {e.lineno}, column {e.colno}: {e.msg}). "
                                      "Fix the file by hand; the lab never repairs a record itself.") from None


@contextmanager
def record_lock(lock_dir: Path, record_id: str, command: str, timeout_s: float = 10.0):
    """Hold <lock_dir>/<id>.lock while changing a record. The OS frees it if the command dies."""
    lock_dir = Path(lock_dir)
    lock_dir.mkdir(parents=True, exist_ok=True)
    path = lock_dir / f"{record_id}.lock"
    meta_path = lock_dir / f"{record_id}.lock.meta"
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    deadline = time.monotonic() + timeout_s
    locked = False
    try:
        while True:
            try:
                if sys.platform == "win32":
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except BlockingIOError:
                pass
            except OSError as e:
                # On Windows, msvcrt.locking raises OSError(errno=EACCES or EDEADLK) when locked
                if sys.platform == "win32" and e.errno in (13, 36):
                    pass
                else:
                    raise
            if time.monotonic() >= deadline:
                held = {}
                for p in (path, meta_path):
                    try:
                        held = json.loads(p.read_text() or "{}")
                        if held:
                            break
                    except (OSError, json.JSONDecodeError):
                        pass
                raise RecordError(path, None, f"{record_id} is being changed by `{held.get('command', '?')}` "
                                              f"(PID {held.get('pid', '?')}, since {held.get('started_at', '?')}). "
                                              "Wait for it to finish and try again.") from None
            time.sleep(0.1)
        info = json.dumps({"pid": os.getpid(), "command": command, "started_at": now()}).encode()
        os.ftruncate(fd, 0)
        os.write(fd, info)
        if sys.platform == "win32":
            try:
                meta_path.write_bytes(info)
            except OSError:
                pass
        yield
    finally:
        if sys.platform == "win32":
            meta_path.unlink(missing_ok=True)
            if locked:
                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
        os.close(fd)  # closing the descriptor releases the flock on Unix


def create_record(lock_dir: Path, folder: Path, prefix: str, make_record: Callable[[str], dict], width: int = 3,
                  validate: Callable[[dict], object] | None = None) -> tuple[str, Path]:
    """Choose the next unused <prefix>-NNN and create its complete record, under id-allocation.lock. The record is
    linked into place only once fully written, so a crash leaves no record at all."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    with record_lock(lock_dir, "id-allocation", f"create {prefix}"):
        nums = [int(m.group(1)) for p in folder.glob(f"{prefix}-*.json")
                if (m := re.fullmatch(rf"{prefix}-(\d+)\.json", p.name))]
        new_id = f"{prefix}-{(max(nums) + 1 if nums else 1):0{width}d}"
        record = make_record(new_id)
        if validate:
            validate(record)
        path = folder / f"{new_id}.json"
        tmp = _write_temp(folder, record)
        try:
            os.link(tmp, path)  # fails if the name exists
        finally:
            tmp.unlink(missing_ok=True)
    return new_id, path


def next_local_id(record: dict, key: str, prefix: str) -> str:
    """The next ID for a list inside a record (BLD-004-NN, PR-004-NN); call it while holding that record's lock."""
    nums = [int(m.group(1)) for item in record.get(key) or []
            if (m := re.fullmatch(rf"{re.escape(prefix)}-(\d+)", str(item.get("id", ""))))]
    return f"{prefix}-{(max(nums) + 1 if nums else 1):02d}"


def parse_budget(text: str) -> dict:
    """'180m,100g', '3h', '2h30m', '100g' -> {"minutes", "g"}. Every number needs a unit."""
    out = {"minutes": None, "g": None}
    for part in [p.strip() for p in text.split(",") if p.strip()]:
        if m := re.fullmatch(r"(?:(\d+(?:\.\d+)?)h)?(?:(\d+(?:\.\d+)?)m)?", part):
            if not (m.group(1) or m.group(2)):
                raise ValueError(f"'{part}' has no units. Write time as 3h, 180m or 2h30m and material as 100g.")
            out["minutes"] = float(m.group(1) or 0) * 60 + float(m.group(2) or 0)
        elif m := re.fullmatch(r"(\d+(?:\.\d+)?)g", part):
            out["g"] = float(m.group(1))
        else:
            raise ValueError(f"'{part}' has no units. Write time as 3h, 180m or 2h30m and material as 100g.")
    return {k: (int(v) if isinstance(v, float) and v.is_integer() else v) for k, v in out.items()}
