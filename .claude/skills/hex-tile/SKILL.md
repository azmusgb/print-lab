---
name: hex-tile
description: Use when working on print-lab's hex-tile project (faceted hexagonal wall tile printed upright as a back-to-back pair on the Bambu X2D). Triggers include: the pair won't separate, is welded or fused, or cracks; lines, bands, ripples or ghosting on the face; strings; a print that came off the plate or turned to spaghetti; choosing the next model version or experiment; and editing the tile's 3MF or SCAD sources.
---

# Hex tile

## Overview

Every design choice on this tile trades three things: **bracing** (the tall, thin pair must hold itself still up to the top), **separation** (the two tiles must come apart whole), and **a clean face** (no feature may change one layer more than another, or touch the skin).

More than 60 versions have explored this already. Read `design-ledger.md` in this folder before proposing any model change, and cite the versions that already tried something like it.

## Proven facts (don't re-test these)

| Fact | Evidence |
|---|---|
| Any continuous join between the backs fuses, even with a 0.10–0.20 mm gap in the model | v42–v48, E-008, E-012, E-014 (gap bridged on 657/660 layers) |
| No join at all lets the top wobble loose | E-011 (v59, 0.5 mm) |
| Small discrete tabs separate; tabs at the same heights leave lines across the face | v40 came apart; v41 lines |
| v58's face geometry prints clean | E-002, E-008, E-012, E-014 |
| Upright is the right orientation; flat or leaned makes contour rings | facets 2–12° |
| 0.65 mm backs crack when a fused join is cut | E-014 |

## Current state

- **v61s** = v58 faces + 1.25 mm backs + 207 staggered tacks, one per 0.6 mm band. Built by `sources/scad/make_v61_tacks.py`.
- **E-019** is the top strip: failed once, came off the plate. **E-020** is the full pair: built, not printed.
- **Nozzle:** the geometry is the 0.6-nozzle variant (`*_0.6nozzle.3mf`, objects `*_06_6in`), printed on the **0.4 nozzle**. It's only slightly thicker inside, and the face is identical.
- **Settings** come from `sources/hexagon_v57_X2D_0.4nozzle_kexcelled.3mf` (the Kexcelled preset, 0.4 nozzle). That base already has a 10 mm outer brim and a 60/55 °C textured PEI plate. Don't suggest "add a brim".
- **Printed so far:** the only full pair printed is E-014.
- **Strips:** "the strip" means a `height_strip` experiment. Check its `build_spec.z`: 106–132 is a high strip; 0–n starts at the bed.
- **Reading a record:** a failed run shows in `print_runs[].failed` and `usage`. The experiment's `status` stays `approved`, so it can be retried; it doesn't mean the run never happened.
- The filament is spool #1, Kexcelled Light Matte Terracotta, lot C6719062. The other five spools are in `filaments.json`; their numbers beyond the labels are untested guesses.

## Before proposing a model change

1. **Look it up first.** Find the nearest past version in the ledger and say what happened to it.
2. **Name the trade-off.** Say which of bracing, separation and face the change affects, and how.
3. **Keep every layer alike.** Any joining feature must appear on every layer at the same complexity: stagger it, or make it continuous. Taper anything that starts or ends.
4. **Keep the skin clear.** Nothing within 1.6 mm of the skin, and nothing attached to the rim near the face.
5. **Check the slice, not just the model.** Run:
   ```
   uv run python .claude/skills/hex-tile/scripts/gap_layers.py prints/sliced/<build>.gcode.3mf
   ```
   It confirms the slicer printed the joining features, and on how many layers.

## Making a variant

- **Derive from a source 3MF; never overwrite one.** Builds pin the file's sha256, and a rewrite, even with identical geometry, marks every build of it stale.
- **Register it.** Add every new file to `sources/sources.json` with `derived_from` and a one-line `change`.
- **Know the coordinates.** In the 3MF, mesh x is the pair's thickness: backs at ±0.5, gap 1.0 mm. z is height, centred on 0, ±66 for the 6".
- **The 6" pair** is mesh objects 3, 7 and 9 (named `*_06_6in`).
- **The SCAD is only approximate.** v57 SCAD with `back_t=0.65 rib_kiss=0.10` reproduces v58 to within about 2% of its volume, not exactly. Edit the v58-derived meshes (trimesh plus manifold3d, both in the venv) rather than regenerating from SCAD.

## Printing (the owner runs these)

- **Approvals and budgets are the owner's.** Tell them the exact `lab question resume …` / `lab exp approve …` lines to run.
- **Starting:** `lab exp start` stamps the current time, so run it only once the print is actually running. If it was started late, correct `started_at` by hand and say so.
- **Failures:** record with `lab exp usage <run> --failed-at <pct> --minutes … --grams …`. The experiment then allows a retry; it doesn't need a new approval.
- **Plate:** wash it with dish soap and hold it by the edges. Let it cool below 30 °C, then flex it to remove the part; never pull the part off.
- **Separating the pair:** snip the inside strings first. Then twist or snap the tiles apart. If you need a knife, run it on the back side only.

## Diagnosing

- **Lines at a regular spacing:** measure the spacing and the heights, then compare them with the model's features at those heights. Candidates: tacks, pad ends, the facet switch at 89.75 mm, and a v58 strip's own start or end. If they match, the feature is the cause (see v41, v49/v50). If they don't, the next single-factor test is wall speed (E-010).
- **Part off the plate early:** tell plate contamination apart from strip shape before changing the model. Re-run on a washed plate, or print a strip that starts at the bed.
- **Tacks still crack the backs:** reduce the tack width before thickening the backs again; contact area is the lever. Regenerate with `make_v61_tacks.py`: argument 4 is width, argument 5 is height.

## Common mistakes

| Mistake | Instead |
|---|---|
| Sweeping the rib or seam gap again | It fused at 0.10, 0.15 and 0.20 mm and wobbled loose at 0.5 mm. Change the kind of join, not the gap. |
| Trusting a high strip for a lightly joined pair | Strips cut from 100 mm and up failed twice (E-011, E-019). Prefer strips that start at the bed, or go to the full part. |
| Stating spool settings as facts | Only the label is known. Mark anything else as untested. |
| Calling a cause proven from photos | Say "likely" until a single-factor test confirms it. |
