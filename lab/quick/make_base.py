"""Make a Quick Print base project from a recipe, with no Studio step: a known-good build's complete settings (printer,
nozzle, process, machine, so the X2D start sequence) with the recipe's filament profile put in every slot.

`python -m lab.quick.make_base presets/quick/standard.json` writes presets/quick/<name>.3mf beside the recipe. The
slicer reads only Metadata/project_settings.config from a base, so the file is just that settings file in a valid
3MF. The output is the same bytes every run. Whether the result is fit to print is not decided here: every slice
still has its start sequence checked against the known-good reference (lab.quick.start_check)."""
import argparse
import io
import json
import sys
import zipfile
from pathlib import Path

from lab.adapters.threemf import _CT, _RELS

ROOT = Path(__file__).resolve().parents[2]
# Profile keys that name or inherit a profile rather than set a value; the slots keep what the build had for these,
# except the settings id, which is the point.
SKIP = {"name", "from", "inherits", "filament_extruder_variant"}
KEEP = {  # what the recipe's source must say, so a wrong source is refused, not sliced
    "printer_settings_id": "Bambu Lab X2D 0.4 nozzle",
    "print_settings_id": "0.20mm Standard @BBL X2D",
    "layer_height": 0.2,
}


class RecipeError(Exception):
    """A recipe that can't make a base; the message is for the owner."""


def with_filament(settings: dict, profile: dict) -> tuple[dict, list[str]]:
    """The project settings with the profile's value in every filament slot, and the profile keys the project doesn't
    have (listed, not guessed at)."""
    out, missing = dict(settings), []
    for key, value in profile.items():
        if key in SKIP:
            continue
        if key not in out:
            missing.append(key)
        elif isinstance(out[key], list) and isinstance(value, list) and value:
            out[key] = [value[0]] * len(out[key])
        else:
            out[key] = value
    return out, missing


def build(recipe_path: Path, root: Path = ROOT) -> tuple[bytes, list[str]]:
    """(the base 3MF's bytes, the profile keys the source didn't have). Raises RecipeError."""
    recipe_path = Path(recipe_path)
    try:
        recipe = json.loads(recipe_path.read_text())
        source, filament = root / recipe["from"], root / recipe["filament"]
        profile = json.loads(filament.read_text())
        with zipfile.ZipFile(source) as z:
            settings = json.loads(z.read("Metadata/project_settings.config"))
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as e:
        raise RecipeError(f"{recipe_path.name}: can't read its source or filament ({type(e).__name__}: {e})") from None
    for key, want in KEEP.items():
        got = settings.get(key)
        if str(got) != str(want):
            raise RecipeError(f"{recipe_path.name}: the source has {key} {got!r}, not {want!r}")
    settings, missing = with_filament(settings, profile)
    ids = set(settings.get("filament_settings_id") or [])
    if ids != set(profile.get("filament_settings_id") or ["?"]):
        raise RecipeError(f"{recipe_path.name}: the filament didn't reach every slot ({sorted(ids)})")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in (("[Content_Types].xml", _CT), ("_rels/.rels", _RELS),
                           ("Metadata/project_settings.config", json.dumps(settings, indent=4))):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    return buf.getvalue(), missing


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("recipe", nargs="+", type=Path, help="a presets/quick/<name>.json recipe")
    args = ap.parse_args(argv)
    for recipe in args.recipe:
        try:
            data, missing = build(recipe)
        except RecipeError as e:
            print(e, file=sys.stderr)
            return 1
        out = recipe.with_suffix(".3mf")
        out.write_bytes(data)
        print(f"{out}: {len(data)} bytes" + (f"; not in the source, left out: {', '.join(missing)}" if missing else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
