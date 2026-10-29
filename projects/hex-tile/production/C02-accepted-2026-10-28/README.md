# C02 hex tile — production acceptance, 28 Oct 2026

**Status: accepted by the owner.** This folder is locked (see the end). Do not edit or delete it; copy files out to work on them.

> Owner, 28 Oct 2026, after printing the C02 pair: **"BEST ONE YES - AMAZING - ITS A KEEPER"**

## What was accepted

C02: a raised, asymmetric faceted 6-inch hex wall tile, printed **upright as two independent tiles** (no joins, nothing to separate).

| | |
|---|---|
| Size | 152.4 mm corner to corner × 131.98 mm tall × 19 mm deep (9 mm rim + 10 mm facet rise) |
| Shell | 2.4 mm face skin, 2.4 mm perimeter walls, 45° internal roof (no overhangs) |
| Back | hollow, with a U-shaped tape land 17.7 mm wide, open at the top (for 12.7 mm foam tape) |
| Bed contact | 9 mm × 76.2 mm flat edge per tile (686 mm²) |
| Accepted print | Bambuddy archive #30, job `C02_Independent_Pair_-_Qualification`, 28 Oct 03:04–06:11 UTC, 3 h 08 min actual, 660 layers, no pauses |

## Print recipe (reconstructed — read the note)

| Setting | Value |
|---|---|
| Printer | Bambu Lab X2D, 0.4 / 0.4 mm nozzles, left (main) nozzle, AMS slot A1 |
| Process | **stock `0.20mm Standard @BBL X2D`** — 0.20 mm layers, 2 walls, 15 % grid infill, stock speeds |
| Filament | **stock `Bambu PLA Matte @BBL X2D 0.4 nozzle`**, 220 °C; spool colour #AF7933 |
| Plate | **Textured PEI**, 55 °C |
| Brim | outer brim (width not captured; reconstruction uses the stock 5 mm) |
| Model | `model/tile-pair.stl` (two tiles facing the same way, ~20 mm apart) |

**How the recipe was established:** the owner sliced in Bambu Studio and the plate file was not saved. Bambuddy recorded the slicer's estimate as **10 500 s (2 h 55 min 00 s)**. Studio's last project was the reviewer's original `C02_PAIR_QUALIFICATION.3mf`, which contained an invalid infill-pattern value, and Studio's selected presets afterwards were the stock ones above. Re-slicing the same pair with those stock presets gives **2 h 55 min 38 s** (the slow qualification settings give 7 h 04 min; the lab's v70 preset 3 h 52 min). So the recipe is a strong inference, not a captured file. The brim and any by-hand plate changes are unconfirmed.

**To reprint:** open `model/tile-pair.stl` (or `slicing/C02_PAIR_QUALIFICATION_fixed.3mf`) in Studio, select the stock process and filament above, Textured PEI, outer brim. **Export the plate-sliced file before printing** and add it to the lab's records. Compare against `slicing/C02_pair_KEEPER_reconstructed_stock020Standard.gcode.3mf`.

## Files

| Path | What it is |
|---|---|
| `model/tile.scad` | C02 source, OpenSCAD. Identical in the original C02 folder and the reviewer's selected-design package. Default output: one trial tile. |
| `model/tile-single.stl`, `model/tile-pair.stl` | The exported meshes from the C02 folder. (A later `tile.stl` re-export matched `tile-single.stl` within 0.0005 mm but had 16 zero-area triangles, so it is not kept.) |
| `model/preview.png` | Rendering of the face. |
| `slicing/C02_pair_KEEPER_reconstructed_stock020Standard.gcode.3mf` | Claude's CLI slice of the pair with the stock recipe: mesh, all settings and G-code. 2 h 55 min 38 s, 121 g. Reference, not the owner's file. |
| `slicing/C02_PAIR_QUALIFICATION_fixed.3mf`, `slicing/C02_SINGLE_QUALIFICATION_fixed.3mf` | The reviewer's qualification projects (slow, 100 % infill) with the infill-pattern name corrected (`rectilinear` → `zig-zag`). **Not** the accepted recipe; kept because the accepted print was set up from the original of the pair project. |
| `presets/*__resolved_stock.json` | The stock Bambu process, filament and printer profiles, fully resolved, from Bambu Studio's bundled profiles. |
| `presets/Bambu Lab X2D 0.4 nozzle.bbscfg` | Owner's exported printer config bundle (28 Oct). |
| `presets/owner_process_presets_library.zip` | Owner's exported process-preset library (28 Oct); does not record which preset the plate used. |
| `evidence/photos/IMG_1032–1038.HEIC` | Owner's photos of the accepted pair. |
| `evidence/printer_camera_end_of_print.jpg` | Printer camera at the end of the print: both tiles full height and upright. |
| `evidence/bambuddy_archive_30.json` | Bambuddy's record of the print. |
| `reference/` | C02 engineering notes (original and qualification) and the reviewer's full engineering archive. |
| `SHA256SUMS` | Checksums of every file here. |

## Notes from the photos (AI reading, not the owner's words)

Faces smooth matte with crisp facet edges; no visible band in the top 8–12 mm where the roof meets the skin. Backs flat and clean. The bed edge carries the Textured PEI diamond imprint (other edges smooth). One tile has a small chip at a lower corner of the edge, probably from brim removal. A few hair-thin strings.

## Still to establish

- **Repeatability:** one accepted print so far. Print the recipe again, archiving the sliced file, before calling it production.
- Brim width actually used; brim cleanup time.
- Mounting: tape product, wall substrate and long-term hold are untested.

## Lock

Every file and folder here has the macOS user-immutable flag (`chflags uchg`), so it cannot be changed, renamed or deleted — not even with `rm -rf` — until unlocked. To unlock deliberately:

```
chflags -R nouchg ~/dev/print-lab/projects/hex-tile/production/C02-accepted-2026-10-28
```

Check the files with `shasum -a 256 -c SHA256SUMS` from inside this folder.
