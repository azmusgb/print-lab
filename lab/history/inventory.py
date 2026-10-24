"""Fingerprint every file in a folder of past work and say which design lineage and version each belongs to."""
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from lab.jobs import sha256

KINDS = {".scad": "scad", ".stl": "stl", ".3mf": "3mf", ".json": "json", ".gcode": "gcode", ".png": "image",
         ".jpg": "image", ".jpeg": "image", ".heic": "image"}
# A lineage is a set of exact name stems (the part of the name before _v<N>, lower-case, spaces as _).
LINEAGES = {"hex-tile": {"hex_wall_tile", "hexagon_wall_tile", "hexagon_wall_tile_pair", "hex_pair", "hex_tile",
                         "hexagon", "generic_pla_hex_tile", "bambu_pla_matte_hex_tile"}}

_VERSION = re.compile(r"(?:^|[_ \-–])v(\d+)(?=[_ .\-–@]|$)", re.I)
_SIZE = re.compile(r"[_ \-–](\d+)in(?=[_ .\-–]|$)", re.I)
_NOZZLE = re.compile(r"(0\.[46])\s*nozzle", re.I)


@dataclass
class Artifact:
    path: str
    sha256: str
    size: int
    mtime: str
    kind: str
    stem: str
    lineage: str | None
    version: int | None
    size_in: int | None
    nozzle: str | None
    duplicate_of: str | None = None


def _stem(name: str) -> str:
    base = name.split(".")[0]
    m = _VERSION.search(base)
    stem = base[: m.start()] if m else base
    return re.sub(r"[\s\-–]+", "_", stem.strip()).lower().strip("_")


def describe(path: Path) -> Artifact:
    name = path.name
    stem = _stem(name)
    lineage = next((k for k, stems in LINEAGES.items() if stem in stems), None)
    if stem == "hexagon" and not re.search(r"_x2d", name, re.I):  # bare 'hexagon' is too generic on its own
        lineage = None
    v, s, n = _VERSION.search(name), _SIZE.search(name), _NOZZLE.search(name)
    st = path.stat()
    return Artifact(path=str(path), sha256=sha256(path), size=st.st_size,
                    mtime=datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(timespec="seconds"),
                    kind=KINDS.get(path.suffix.lower(), "other"), stem=stem, lineage=lineage,
                    version=int(v.group(1)) if v else None, size_in=int(s.group(1)) if s else None,
                    nozzle=n.group(1) if n else None)


def inventory(folder: Path) -> list[Artifact]:
    """Every regular file in folder (not recursive), oldest first; identical content is marked as a duplicate of the
    first file that has it."""
    arts = sorted((describe(p) for p in Path(folder).iterdir() if p.is_file() and not p.name.startswith(".")),
                  key=lambda a: (a.mtime, a.path))
    return dedupe(arts)


def dedupe(arts: list[Artifact]) -> list[Artifact]:
    """Mark each file whose content an earlier file in this list already has. Run it on the project's own files so
    an unrelated older copy elsewhere in the folder never hides a project file."""
    first: dict[str, str] = {}
    for a in arts:
        a.duplicate_of = None
        if a.sha256 in first:
            a.duplicate_of = first[a.sha256]
        else:
            first[a.sha256] = a.path
    return arts
