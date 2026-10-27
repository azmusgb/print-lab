---
name: hex-tile
description: Use when working on print-lab's hex-tile project (faceted hexagonal wall tile printed upright as a back-to-back pair on the Bambu X2D). Triggers include: the pair won't separate, is welded or fused, or cracks; lines, bands, ripples or ghosting on the face; strings; a print that came off the plate or turned to spaghetti; choosing the next model version or experiment; and editing the tile's 3MF or SCAD sources.
---

# Hex tile

## Overview

Every design choice on this tile trades three things: **bracing** (the tall, thin pair must hold itself still up to the top), **separation** (the two tiles must come apart whole), and **a clean face** (no feature may change one layer more than another, or touch the skin).

More than 60 versions have explored this already. Read `design-ledger.md` in this folder before proposing any model change, and cite the versions that already tried something like it, with the ledger's evidence labels (owner, AI-photo, inferred).

## What the record supports

Nothing below is proven. Each line says how far the evidence goes; don't present it more strongly.

| Lesson | Status | Evidence and limits |
|---|---|---|
| Continuous or full-height contact between the backs welds the pair | observation, repeated | owner: v46–v48 "cant separate", "almost welded", "almost fused"; v58 ribs E-012 "cant even pull them apart". Gaps 0.10–0.20 mm only; contact area alone doesn't predict force |
| No join at all lets the top wobble loose | one result | E-011 (v59, 0.5 mm), a high strip, not a full tile |
| Pairs came apart before the ribs | AI-photo only | v41 tabs, v49 and v51 edge-only kiss seams seen apart in photos; how easy is not recorded |
| Features at a few fixed heights leave face lines | hypothesis | v41 tab lines, v49/v50 pad-end lines; positions matched, never tested alone |
| v58's face prints clean | owner, several prints | E-002, E-008, E-012, E-014 (lab filament, 0.4 nozzle settings) |
| Filament affects the face | untested | yellow → grey → pink → white → terracotta across versions; every cross-version comparison is confounded |

## Current state

- **E-020 (v61s):** accepted for the 26 Oct deadline *with defects* (separation "SUPER hard", one back torn).
- **E-021/E-022 (v61s + v62k strips):** ridged faces, cause unresolved (Q-004). E-021 stopped at 1 h 27 min on the printer.
- **Next: E-023**, v51 reprinted as it was (owner said yes, 26 Oct): the last design seen apart with a mostly clean face. Then the same in Kexcelled terracotta, to separate filament from design.
- **Nozzle:** every file, including `*_0.6nozzle`, is set up for 0.4/0.4. Ask the owner what is fitted before relying on it.
- **Settings** for v57 onward come from `sources/hexagon_v57_X2D_0.4nozzle_kexcelled.3mf`. v51 carries its own settings in its 3MF.
- **Reading a record:** a failed run shows in `print_runs[].failed` and `usage`; `status` stays open for a retry.
- **Quotes:** owner words come from experiment verdicts or `history/hex-tile/chat/owner-notes.md`. Never turn an AI-photo reading into a quote.
- The lab's filament is spool #1, Kexcelled Light Matte Terracotta, lot C6719062. Numbers beyond the labels on the other spools are untested guesses.

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

General printer tuning (drying, flow, pressure advance, temperature, retraction; OrcaSlicer's calibrations; symptom → cause
from Ellis' guide) is in `docs/tuning.md`. It is general advice, not tile evidence: test it like any other factor.

- **Lines at a regular spacing:** measure the spacing and the heights, then compare them with the model's features at those heights. Candidates: tacks, pad ends, the facet switch at 89.75 mm, and a v58 strip's own start or end. If they match, the feature is the cause (see v41, v49/v50). If they don't, the next single-factor test is wall speed (E-010).
- **Part off the plate early:** tell plate contamination apart from strip shape before changing the model. Re-run on a washed plate, or print a strip that starts at the bed.
- **Tacks still crack the backs:** reduce the tack width before thickening the backs again; contact area is the lever. Regenerate with `make_v61_tacks.py`: argument 4 is width, argument 5 is height.

## Common mistakes

| Mistake | Instead |
|---|---|
| Sweeping the rib gap again | Full-height ribs fused at 0.10–0.20 mm and wobbled loose at 0.5 mm (strip). Change the kind or amount of contact first. |
| Trusting a high strip for a lightly joined pair | Strips cut from 100 mm and up failed twice (E-011, E-019). Prefer strips that start at the bed, or go to the full part. |
| Stating spool settings as facts | Only the label is known. Mark anything else as untested. |
| Calling a cause proven from photos | Say "likely" until a single-factor test confirms it. |
