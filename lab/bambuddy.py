"""Bambuddy (the household's printer manager) as print-lab sees it: read-only. Nothing here ever writes to Bambuddy.

Each build is printed under a lab name like `hex-tile_E-023_BLD-023-01`; parse_lab_name picks that apart so a Bambuddy
print can be linked back to its build. LAB_BAMBUDDY_URL changes the address ("off" disables every call). Bambuddy has
sign-in on, so requests carry print-lab's own read-only API key, from ~/.config/bambuddy/print-lab-key
(LAB_BAMBUDDY_KEY_FILE changes the file). Calls wait at most 5 s and return None on any failure.
"""
import json
import os
import re
import urllib.request
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
    return os.environ.get("LAB_BAMBUDDY_URL", "http://10.0.0.30:8000")


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
