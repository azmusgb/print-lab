# Rift 10 in hex tile, 70° back-to-back pair, version 1.0

Locked 2026-11-23 at the owner's request ("Yes, lock it"). Do not edit in place: a change is a new version folder (v1.1, v2.0).

Two 10 in RIFT tiles leaning back at 70°, back to back, on one shared hybrid breakaway support (HBS: fins, tabs, cradles,
feet, anchors). Printed on the X2D as `RIFT10_PAIR70_CLEAN_X2D_WITH_HBS`.

**Why this version:** it is the only 10 in pair that has printed to the end more than once (3 of 6 attempts).
No owner verdict on its finish is recorded anywhere (Bambuddy holds none, the lab history stops at 24 Oct), so this is
the best evidence on hand, not an accepted production recipe like C02.

## Print record (Bambuddy, X2D)

| Archive | Started (UTC) | Result | Hours |
|---|---|---|---|
| 90 | 2026-11-18 00:32 | completed | 22.1 |
| 91 | 2026-11-18 22:45 | completed | 21.3 |
| 92 | 2026-11-19 20:27 | failed | 0.2 |
| 93 | 2026-11-19 20:38 | completed | 25.5 |
| 94 | 2026-11-20 22:31 | failed | 24.2 |
| 104 | 2026-11-23 14:28 | failed | 0.7 |

Bambuddy's slicer estimate for archives 90 and 93 is 74 760 s (20 h 46 min). The full log of every PAIR70 print,
including the 1.32 mm plate variant C (1 completed of 8), is in `evidence/bambuddy_print_log.json`.

## Recipe

| | |
|---|---|
| Printer | Bambu Lab X2D, 0.4 mm nozzle, Textured PEI plate |
| Process | `RIFT pair70 hbs 0.16mm @BBL X2D 0.4 nozzle` (0.16 mm layers, 3 walls, 100 % infill, 5 mm brim), Studio preset saved 17 Nov 14:55, before the first print |
| Filament | PLA, PlastKyro PLA Matte Dusty Rose |
| Model | `model/RIFT10_PAIR70_CLEAN_X2D_WITH_HBS.stl` (17 Nov 19:30, before the first print) |

**What is not captured:** Bambuddy kept no copy of the G-code for archives 90, 91 or 93, and no sliced file from 17–20 Nov
is on disk. The recipe is the model and process preset that existed before those prints; the filament preset and
by-hand plate changes are unconfirmed.

**To reprint:** open `model/RIFT10_PAIR70_CLEAN_X2D_WITH_HBS.3mf` in Studio, import the process preset, pick the Dusty Rose
filament on the slot you load, Textured PEI, and slice. Expect roughly 19 h 50 min to 20 h 46 min depending on the
filament preset. **Export the sliced plate before printing** and add it as v1.1 evidence.

## Files

| Path | What it is |
|---|---|
| `model/RIFT10_PAIR70_CLEAN_X2D_WITH_HBS.stl` | Pair + HBS mesh, the printed geometry |
| `model/RIFT10_PAIR70_CLEAN_X2D_WITH_HBS.3mf` | Studio project with that mesh and the pair70 process (re-saved 23 Nov 09:28; filament slots there are Generic/SUNLU, re-pick before slicing) |
| `presets/RIFT pair70 hbs 0.16mm @BBL X2D 0.4 nozzle.json` | Process preset (Studio user copy, same bytes as the preset library copy) |
| `presets/PlastKyro PLA Matte Dusty Rose @BBL X2D 0.4 nozzle.json` | Dusty Rose filament preset from 28 Oct, predates the prints |
| `presets/PlastKyro PLA Matte - Dusty Rose CALIBRATED RIFT @BBL X2D 0.4 nozzle.json` | Calibrated Dusty Rose preset made 21 Nov, after the three good prints; used by the later 19h50m slice |
| `evidence/printer_camera_end_archive90.jpg`, `..._archive93.jpg` | Printer camera at the end of two completed prints (384×216) |
| `evidence/bambuddy_print_log.json` | Every PAIR70 print Bambuddy logged, as read 23 Nov |
| `SHA256SUMS` | Checksums of the files here, plus the large files below |

Kept out of git (size), recorded by hash in `SHA256SUMS`; originals are in `~/Downloads`:
`RIFT10_PAIR70_CLEAN_X2D_WITH_HBS_PLA_19h50m.gcode` (26 MB, GUI slice of 21 Nov, after the good prints) and
`RIFT10_PAIR70_CLEAN_X2D_WITH_HBS.obj.zip` (69 MB).

Check with `shasum -a 256 -c SHA256SUMS` (run from this folder; the large files only if present).

## Still to establish

- Owner's verdict on the finish of a completed pair (photos, defects, breakaway).
- Why the 20 Nov print failed at 24.2 h and the 23 Nov print at 0.7 h (printer or plate, not yet checked).
- A captured sliced file for the next good print.
