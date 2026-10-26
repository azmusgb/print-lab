# v62r — modern v40 rim-tab pair

## Goal

Keep the current v60b125 tile geometry and 1.25 mm backs, but replace the failed v61s interior tack field with the only pair-join topology that has actually separated successfully: v40-style breakaway tabs on the solid back rim.

## Geometry

- Base: `hexagon_v60b125_X2D_0.6nozzle.3mf`
- Pair gap: **0.4 mm** (v40 proven value)
- Breakaway tab cross-section: **0.6 × 0.6 mm**
- Maximum nominal tab pitch along each rim side: **12 mm**
- Default 6-inch placement: **7 tabs/side, 42 total**
- Actual adjacent-center spacing on the default layout: about **10.5–10.9 mm**
- Tab overlap into each back: **0.3 mm**
- Approximate contact per tile: **15.1 mm²**
- Back thickness: unchanged at **1.25 mm**
- Front/body geometry: unchanged from v60b125
- Slicer settings: unchanged by the generator

## What is different from v40/v41

v40 proved that rim tabs could hold a 6-inch pair and still let it come apart. v41 then exposed the face-line failure mode when many tabs began or ended at the same Z heights.

v62r keeps the v40 mechanical topology but makes the placement **layer-aware** for the current 0.20 mm layer height:

- opposite slanted sides are shifted out of phase along the rim;
- top and bottom tabs use deliberately different insets inside the 2 mm solid rim, moving their Z centers onto different layer bands;
- the generator measures tab start/stop events and refuses the layout if more than **two** occur on one 0.20 mm layer.

That does not prove the face will be perfect—the real Bambu slice remains authoritative—but it removes the obvious v41-style synchronized row from the model geometry before slicing.

## What is different from v61s / E-020

v61s cut a 1.0 mm central gap and placed 207 isolated tack posts in the interior back field, intentionally staying 4 mm away from the solid rim. E-020 showed loose extrusions consistent with that interior bridge/tack topology failing to land reliably.

v62r removes that topology entirely. The connection is made only at the solid rim, where v40 proved the mechanical concept.

## Generate and test on the Mac

From `~/dev/print-lab` on branch `feat/v62-rim-tabs`:

```bash
uv run pytest -q tests/test_v62_rim_tabs.py

uv run python projects/hex-tile/sources/scad/make_v62_rim_tabs.py \
  projects/hex-tile/sources/hexagon_v60b125_X2D_0.6nozzle.3mf \
  projects/hex-tile/sources/hexagon_v62r_X2D_0.6nozzle.3mf
```

Expected default generator summary includes:

```text
v62r tabs=42 (7/side) gap=0.40mm tab=0.60mm actual_pitch<=10.89mm contact/tile=15.1mm2 max_events/layer<=2 watertight=True
```

The real-source pytest generates a temporary v62r from the tracked v60b125 3MF and verifies the archive, linked mesh objects, watertight output, tab count/pitch, and layer-event guard.

## Required validation before printing

1. Run the real-source test above.
2. Inspect the generated 3MF with the normal Print Lab geometry checks.
3. Slice with the exact installed Bambu Studio version (`02.08.02.61` for the current project record).
4. Confirm the G-code contains the rim tabs and that no old continuous ribs/seams still bridge the pair gap.
5. Inspect layer-time/toolpath events around tab elevations; model-level staggering is not a substitute for G-code evidence.
6. Record a new **prospective** experiment before any physical print.
7. Use the smallest representative breakaway test only if it can stand reliably. E-011/E-019 showed that tall lightly joined strips can detach; a full pair may therefore be the representative geometry, but still requires normal full-part/budget approval.

## Prospective experiment after validation

Do **not** create this record until the generated source exists and the real Bambu slice has passed the checks above. The intended next experiment is under Q-003 and should preserve the prediction before printing:

- factor: `model_version` bundle (`v62r`)
- test kind: `full_part` if a strip is rejected as non-representative because of the E-011/E-019 strip failures
- hypothesis: **v40-style rim tabs restore reliable supported landings and breakaway separation; layer-staggering avoids v41's synchronized face line while the 1.25 mm backs survive separation**
- prediction: **the pair remains upright to completion, both fronts are good enough from 60 cm, and the two tiles separate by hand without cracking either back**
- judge on: **print completion/stability, both visible faces, and separation/back integrity**

Because Q-003 is already beyond its normal autonomous time envelope and a full pair is a full-part test, the normal `lab exp check`/explicit approval path must remain in force. Do not enlarge the question budget merely to hide that exception.

## Intended verdict

A successful result requires all three:

- pair remains stable through the full height,
- both visible faces remain clean at normal viewing distance,
- tiles separate by hand without cracking the backs.
