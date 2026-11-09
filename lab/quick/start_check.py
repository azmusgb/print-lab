"""Q5: a slice without the X2D start sequence is refused, whatever the slicer's exit code.

The whole initialization is compared with a reference taken from a known-good build, not one marker: the ordered
command sequence of the start block, the project's `machine_start_gcode` hash and the filament ids. (A naive `^M620` is
wrong: the real commands are indented.) The 27 Oct air-print was a 12-line start block against 404."""
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

REFERENCE = Path(__file__).resolve().parents[2] / "presets" / "quick" / "x2d-start-reference.json"


def start_block(gcode: str) -> str | None:
    a, b = gcode.find("; EXECUTABLE_BLOCK_START"), gcode.find("; MACHINE_START_GCODE_END")
    return gcode[a:b] if 0 <= a < b else None


def command_sequence(block: str) -> list[str]:
    """Each command word in order, comments and indentation ignored; consecutive repeats kept once."""
    out: list[str] = []
    for line in block.splitlines():
        code = line.split(";", 1)[0].strip()
        if code and (not out or out[-1] != code.split()[0]):
            out.append(code.split()[0])
    return out


def _header(gcode: str, key: str) -> str | None:
    m = re.search(rf"^; {key} = (.*)$", gcode, re.M)
    return m.group(1).strip() if m else None


def machine_start_sha256(gcode: str) -> str | None:
    v = _header(gcode, "machine_start_gcode")
    return hashlib.sha256(v.encode()).hexdigest() if v is not None else None


def reference_from_gcode(gcode: str) -> dict:
    block = start_block(gcode)
    if not block:
        raise ValueError("No start block in that G-code")
    return {"commands": command_sequence(block), "machine_start_sha256": machine_start_sha256(gcode),
            "block_lines": len(block.splitlines())}


def load_reference(path: Path = REFERENCE) -> dict:
    ref = json.loads(Path(path).read_text())
    if not ref.get("commands") or not ref.get("machine_start_sha256"):
        raise ValueError(f"{path} isn't a start reference")
    return ref


def accepted_machine_starts(reference: dict) -> set[str]:
    """The reference's own `machine_start_gcode` hash plus any other revision recorded as known-good."""
    return {reference["machine_start_sha256"], *(e["machine_start_sha256"] for e in reference.get("also_known_good", []))}


@dataclass
class StartCheck:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    block_lines: int = 0


def _is_subsequence(want: list[str], have: list[str]) -> list[str]:
    """The commands of `want` not found, in order, within `have`."""
    it = iter(have)
    return [c for c in want if c not in it]


def check_gcode(gcode: str, reference: dict) -> StartCheck:
    reasons: list[str] = []
    block = start_block(gcode)
    if not block:
        return StartCheck(False, ["The G-code has no start block"])
    lines = len(block.splitlines())
    missing = _is_subsequence(reference["commands"], command_sequence(block))
    if missing:
        reasons.append(f"Start block is missing {len(missing)} of {len(reference['commands'])} commands the X2D "
                       f"start sequence has, starting with {', '.join(missing[:6])}")
    if lines < reference.get("block_lines", 0) * 0.9:
        reasons.append(f"Start block has {lines} lines against {reference['block_lines']} in the known-good file")
    if machine_start_sha256(gcode) not in accepted_machine_starts(reference):
        reasons.append("The printer's start G-code isn't the known-good one")
    ids = _header(gcode, "filament_ids")
    if not ids or not ids.strip('";'):
        reasons.append("The project has no filament ids")
    return StartCheck(not reasons, reasons, lines)
