"""A19 P0: which candidate settings change a real Bambu Studio slice, and the start-block validator's verdicts.

Read-only on every host: it writes only under the output directory it is given. It slices with the lab's own adapter
(`lab.adapters.bambu`) and builds projects with `lab.adapters.threemf.write_print_3mf` from a base project's embedded
settings. Run: uv run python docs/superpowers/specs/quick-print-p0/settings_probe.py <base.3mf> <good.gcode.3mf> <out_dir>"""
import json
import re
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import trimesh

from lab.adapters import bambu, threemf

START_COMMANDS = ("M620", "M620.10", "M620.11", "M620.17", "M621", "M622", "M623", "G29", "M1002", "M109", "M190", "T0")


def start_block(gcode: str) -> str | None:
    a, b = gcode.find("; EXECUTABLE_BLOCK_START"), gcode.find("; MACHINE_START_GCODE_END")
    return gcode[a:b] if 0 <= a < b else None


def commands(block: str) -> dict:
    out: dict = {}
    for line in block.splitlines():
        line = line.split(";")[0].strip()
        if line:
            out[line.split()[0]] = out.get(line.split()[0], 0) + 1
    return out


def verdict(gcode: str, reference_cmds: dict) -> dict:
    """The candidate validator: the start block exists, holds every command the known-good start holds (any count >= 1),
    and the project's filament ids are filled. Whitespace-insensitive, so ' M620 S0A' counts."""
    blk = start_block(gcode)
    missing = sorted(set(reference_cmds) - set(commands(blk or "")))
    ids = re.findall(r"^; filament_ids = (.*)$", gcode, re.M)
    return {"start_block_lines": len((blk or "").splitlines()), "missing_commands": missing,
            "filament_ids_empty": not ids or ids[0].strip('"') == "", "ok": bool(blk) and not missing and bool(ids) and ids[0].strip('"') != ""}


def plate_gcode(sliced: Path) -> str:
    with zipfile.ZipFile(sliced) as z:
        return z.read("Metadata/plate_1.gcode").decode("utf-8", "replace")


def facts(gcode: str) -> dict:
    layers = re.findall(r"^; total layer number: (\d+)", gcode, re.M)
    feats = {}
    for m in re.finditer(r"^; FEATURE: (.+)$", gcode, re.M):
        feats[m.group(1).strip()] = feats.get(m.group(1).strip(), 0) + 1
    return {"layers": int(layers[0]) if layers else None, "features": feats}


def model() -> trimesh.Trimesh:
    base = trimesh.creation.box(extents=(20, 20, 6)); base.apply_translation([0, 0, 3])
    top = trimesh.creation.box(extents=(40, 20, 4)); top.apply_translation([0, 0, 8])
    return trimesh.util.concatenate([base, top])


def slice_with(base: Path, patch: dict, out: Path, name: str) -> dict:
    proj = out / f"{name}.3mf"
    threemf.write_print_3mf(base, [("probe", model(), (128.0, 128.0))], proj, {"probe": name}, settings_patch=patch)
    sliced, job = bambu.slice_with_job(proj, out / "sliced", 1, out / "jobs")
    g = plate_gcode(sliced)
    return {"name": name, "patch": patch, "exit_ok": job.ok, "gcode_bytes": len(g), **facts(g), "gcode": g}


def main(base: Path, good: Path, out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    ref = commands(start_block(plate_gcode(good)) or "")
    cases = [("baseline", {}), ("layer_0.12", {"layer_height": "0.12"}), ("layer_0.28", {"layer_height": "0.28"}),
             ("walls_2", {"wall_loops": "2"}), ("walls_4", {"wall_loops": "4"}),
             ("top_3", {"top_shell_layers": "3"}), ("top_7", {"top_shell_layers": "7"}),
             ("bottom_2", {"bottom_shell_layers": "2"}), ("bottom_6", {"bottom_shell_layers": "6"}),
             ("infill_10", {"sparse_infill_density": "10%"}), ("infill_40", {"sparse_infill_density": "40%"}),
             ("pattern_gyroid", {"sparse_infill_pattern": "gyroid"}), ("pattern_grid", {"sparse_infill_pattern": "grid"}),
             ("support_on", {"enable_support": "1"}), ("support_off", {"enable_support": "0"}),
             ("brim_none", {"brim_type": "no_brim"}), ("brim_outer", {"brim_type": "outer_only", "brim_width": "5"}),
             # top layers below the profile's shell thickness, and the edges of each range
             ("top_3_thick0", {"top_shell_layers": "3", "top_shell_thickness": "0"}),
             ("edge_layer_0.04", {"layer_height": "0.04"}), ("edge_layer_0.01", {"layer_height": "0.01"}),
             ("edge_layer_0.6", {"layer_height": "0.6"}), ("edge_walls_0", {"wall_loops": "0"}),
             ("edge_walls_20", {"wall_loops": "20"}), ("edge_infill_0", {"sparse_infill_density": "0%"}),
             ("edge_infill_100", {"sparse_infill_density": "100%"}), ("edge_infill_150", {"sparse_infill_density": "150%"}),
             ("edge_pattern_bogus", {"sparse_infill_pattern": "nonsense"}), ("edge_brim_width_100", {"brim_type": "outer_only", "brim_width": "100"})]
    rows = []
    for name, patch in cases:
        try:
            r = slice_with(base, patch, out, name)
            g = r.pop("gcode")
            r["start_check"] = verdict(g, ref)
            rows.append(r)
        except Exception as e:  # a slice that fails is a result too
            rows.append({"name": name, "patch": patch, "error": str(e)[:300]})
    (out / "settings_probe.json").write_text(json.dumps(rows, indent=1))
    for r in rows:
        print(r["name"], r.get("layers"), r.get("start_check", {}).get("ok"), r.get("error", ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])))
