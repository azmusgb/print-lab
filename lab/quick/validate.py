"""The Q5 start-sequence check: a slice is usable only if its machine initialization holds every command of the lab's
known-good X2D start, and its filament ids are filled. A zero exit status from the slicer is not evidence.

A bare marker such as `^M620 ` is not the check: the good start writes M620 indented and as M620.10 and so on, so a
line-start match counts 0 on a good file (A19 P0 report)."""
import hashlib
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

REFERENCE = Path(__file__).with_name("x2d_start_reference.gcode")


def start_block(gcode: str) -> str | None:
    a, b = gcode.find("; EXECUTABLE_BLOCK_START"), gcode.find("; MACHINE_START_GCODE_END")
    return gcode[a:b] if 0 <= a < b else None


def commands(block: str) -> set[str]:
    out = set()
    for line in block.splitlines():
        code = line.split(";")[0].strip()
        if code:
            out.add(code.split()[0])
    return out


def reference_commands() -> set[str]:
    return commands(REFERENCE.read_text())


@dataclass
class StartCheck:
    ok: bool
    start_block_lines: int = 0
    missing_commands: list[str] = field(default_factory=list)
    filament_ids_empty: bool = True
    reasons: list[str] = field(default_factory=list)


def check_start(gcode: str, reference: set[str] | None = None) -> StartCheck:
    ref = reference_commands() if reference is None else reference
    blk = start_block(gcode)
    res = StartCheck(ok=False)
    if not blk:
        res.reasons.append("the G-code has no machine start block (EXECUTABLE_BLOCK_START to MACHINE_START_GCODE_END)")
        return res
    res.start_block_lines = len(blk.splitlines())
    res.missing_commands = sorted(ref - commands(blk))
    ids = re.findall(r"^; filament_ids = (.*)$", gcode, re.M)
    res.filament_ids_empty = not ids or ids[0].strip().strip('"') == ""
    if res.missing_commands:
        res.reasons.append(f"the start block lacks {len(res.missing_commands)} command(s) of the X2D start "
                           f"({', '.join(res.missing_commands[:6])}{', …' if len(res.missing_commands) > 6 else ''}); "
                           "the printer would not load or prepare the filament")
    if res.filament_ids_empty:
        res.reasons.append("filament_ids is empty, so the project is not a complete X2D project")
    res.ok = not res.reasons
    return res


def machine_start_hash(settings: dict) -> str | None:
    """sha256 of a project's machine_start_gcode setting (None when it has none or it is empty)."""
    v = settings.get("machine_start_gcode")
    if isinstance(v, list):
        v = "\n".join(map(str, v))
    return hashlib.sha256(v.encode()).hexdigest() if v else None


def project_problems(settings: dict | None) -> list[str]:
    """Why a project can't be a Quick Print base: it must carry the X2D start code and filament ids itself."""
    if settings is None:
        return ["the base is not a Bambu Studio project (it has no project_settings.config)"]
    out = []
    if not machine_start_hash(settings):
        out.append("the base project has no machine_start_gcode")
    ids = settings.get("filament_ids")
    if not ids or all(not str(i).strip() for i in (ids if isinstance(ids, list) else [ids])):
        out.append("the base project's filament_ids are empty")
    return out


def sliced_settings(sliced: Path) -> dict | None:
    with zipfile.ZipFile(sliced) as z:
        if "Metadata/project_settings.config" not in z.namelist():
            return None
        return json.loads(z.read("Metadata/project_settings.config"))
