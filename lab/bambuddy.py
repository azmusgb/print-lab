"""Bambuddy (the household's printer manager) as print-lab sees it: read-only, except staging (platform amendment
A12). The lab may upload a checked build into Bambuddy's `print-lab` library folder, read it back, and delete a file it
uploaded; it never queues or starts a print. The writes are below `print_log`/`archive`, raise BambuddyError with the
reason, and refuse any Bambuddy version but SUPPORTED_VERSION.

Each build is printed under a lab name like `hex-tile_E-023_BLD-023-01`; parse_lab_name picks that apart so a Bambuddy
print can be linked back to its build. LAB_BAMBUDDY_URL changes the address ("off" disables every call). Bambuddy has
sign-in on, so requests carry print-lab's own read-only API key, from ~/.config/bambuddy/print-lab-key
(LAB_BAMBUDDY_KEY_FILE changes the file). Calls wait at most 5 s and return None on any failure.
"""
import json
import os
import re
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

LAB_NAME = re.compile(r"^(?P<project>[a-z0-9-]+)_(?P<exp>E-\d{3,})_(?P<build>BLD-\d{3,}-\d{2,})$")

STATUS_WORDS = {"completed": "Finished", "failed": "Failed", "cancelled": "Cancelled", "printing": "Printing"}

MAX_TIMEOUT = 5.0


def parse_lab_name(name: str | None) -> dict | None:
    """{"project", "exp", "build"} for a print named like `hex-tile_E-023_BLD-023-01`; None for any other name."""
    m = LAB_NAME.match(name or "")
    return m.groupdict() if m else None


def status_word(status: str | None) -> str:
    """Bambuddy's status as a word for the page: known ones by STATUS_WORDS, others capitalised, None as Unknown."""
    if not status:
        return "Unknown"
    return STATUS_WORDS.get(status, status.capitalize())


def parse_time(s: str | None) -> datetime | None:
    """An ISO timestamp as an aware datetime. Bambuddy's are naive and in UTC, so a naive one is read as UTC; None
    when it's missing or isn't a timestamp."""
    try:
        t = datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def key() -> str | None:
    path = Path(os.environ.get("LAB_BAMBUDDY_KEY_FILE") or Path.home() / ".config/bambuddy/print-lab-key")
    try:
        return path.read_text().strip() or None
    except OSError:
        return None


def base_url() -> str:
    """Bambuddy's address; "off" (or empty) means it is disabled."""
    return os.environ.get("LAB_BAMBUDDY_URL", "http://10.0.0.80:8000")


def _get(path: str, timeout: float):
    """The JSON at `path`, or None when Bambuddy is off, doesn't answer, refuses or sends something unreadable."""
    url = base_url()
    if not url or url == "off":
        return None
    k = key()
    req = urllib.request.Request(f"{url}{path}", headers={"X-API-Key": k} if k else {}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=min(timeout, MAX_TIMEOUT)) as r:
            return json.load(r)
    except Exception:
        return None


def print_log(limit: int = 100, timeout: float = 5.0) -> list[dict] | None:
    """The newest `limit` prints, newest first (by id, since Bambuddy sorts by date); None on any failure or when off."""
    data = _get(f"/api/v1/print-log/?limit={int(limit)}", timeout)
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return None
    return sorted((i for i in items if isinstance(i, dict)), key=lambda i: i.get("id") or 0, reverse=True)


def archive(archive_id: int, timeout: float = 5.0) -> dict | None:
    """One archived print by id; None on any failure or when off."""
    data = _get(f"/api/v1/archives/{int(archive_id)}", timeout)
    return data if isinstance(data, dict) else None


# --- staging (A12): the only writes ---

SUPPORTED_VERSION = "1.3.0"  # checked by the one-tap probe (spec 2026-11-06-one-tap-print-design.md)
STAGING_FOLDER = "print-lab"
WRITE_TIMEOUT = 60.0


class BambuddyError(Exception):
    """A staging call that failed, with Bambuddy's reason when it gave one."""


def _call(method: str, path: str, body: bytes | None = None, ctype: str | None = None,
          timeout: float = WRITE_TIMEOUT) -> bytes:
    url = base_url()
    if not url or url == "off":
        raise BambuddyError("Bambuddy is off (LAB_BAMBUDDY_URL).")
    k = key()
    if not k:
        raise BambuddyError("No Bambuddy API key: put print-lab's key in ~/.config/bambuddy/print-lab-key.")
    headers = {"X-API-Key": k} | ({"Content-Type": ctype} if ctype else {})
    req = urllib.request.Request(f"{url}{path}", data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read() or b"{}").get("detail")
        except Exception:
            detail = None
        raise BambuddyError(f"Bambuddy refused {method} {path}: {e.code} {detail or e.reason}") from None
    except OSError as e:
        raise BambuddyError(f"Bambuddy didn't answer {method} {path}: {e}") from None


def _json(method: str, path: str, **kw):
    try:
        return json.loads(_call(method, path, **kw) or b"null")
    except ValueError:
        raise BambuddyError(f"Bambuddy sent something unreadable for {method} {path}.") from None


def version() -> str:
    """Bambuddy's version; BambuddyError unless it is the one staging was proven against."""
    v = (_json("GET", "/api/v1/updates/version") or {}).get("version")
    if v != SUPPORTED_VERSION:
        raise BambuddyError(f"Bambuddy is {v or 'an unknown version'}; staging is proven on {SUPPORTED_VERSION} only. "
                            "Run the one-tap probe again before changing SUPPORTED_VERSION.")
    return v


def staging_folder() -> int:
    """The id of the `print-lab` library folder. It is made once by hand (the probe made it); the lab never creates
    folders."""
    folders = _json("GET", "/api/v1/library/folders/")
    ids = [f.get("id") for f in folders or [] if isinstance(f, dict) and f.get("name") == STAGING_FOLDER
           and f.get("parent_id") is None]
    if len(ids) != 1:
        raise BambuddyError(f"Bambuddy has {len(ids)} top-level {STAGING_FOLDER!r} folders; it needs exactly one.")
    return int(ids[0])


def upload(path: Path, folder_id: int) -> dict:
    """Upload a file into the folder; Bambuddy's record of it ({"id", "filename", "file_size", …})."""
    path = Path(path)
    boundary = uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{path.name}\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n").encode() + path.read_bytes() + \
        f"\r\n--{boundary}--\r\n".encode()
    rec = _json("POST", f"/api/v1/library/files/?folder_id={int(folder_id)}&generate_stl_thumbnails=false",
                body=body, ctype=f"multipart/form-data; boundary={boundary}")
    if not isinstance(rec, dict) or not isinstance(rec.get("id"), int):
        raise BambuddyError(f"Bambuddy's upload answer has no file id: {str(rec)[:200]}")
    return rec


def download(file_id: int) -> bytes:
    return _call("GET", f"/api/v1/library/files/{int(file_id)}/download")


def library_file(file_id: int) -> dict | None:
    """The library file's record, or None when Bambuddy has no such file (any other failure raises)."""
    try:
        return _json("GET", f"/api/v1/library/files/{int(file_id)}")
    except BambuddyError as e:
        if ": 404 " in str(e):
            return None
        raise


def delete(file_id: int) -> None:
    """Delete a file the lab uploaded (Bambuddy moves it to its trash)."""
    _call("DELETE", f"/api/v1/library/files/{int(file_id)}")
