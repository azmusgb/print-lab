---
name: rift-tile-print
description: Use for the RIFT single hex wall tile (faceted_hex seed 3, c9f530ce03f2) at 6 in or 10 in printed upright on the Bambu X2D - building a matched-scale 6 in / 10 in pair, Fusion MCP inspection and draft analysis, slicing with the Bambu Studio CLI, checking the G-code for bridges and floating shells, and queueing the print on Bambuddy with an AMS slot. Also use for the wall-mount version (ribs, mounting bosses, keyhole slots, the 15.24 mm tile), measuring the tile in its standing orientation, and questions about face layer lines, flipping or tilting the tile, the tear roof, the "floating cantilever" warning, or sending the 10 in tile to print. Not for the back-to-back pair (use hex-tile).
---

# RIFT tile: build, check, slice, queue

One tile printed standing on its flat edge. The 6 in tile is the locked reference (`faceted_hex` seed 3 scaled in Bambu Studio: 0.9215 in plane, 0.8021 thickness). The 10 in is generated at 254 mm and scaled the same way, so the two sit edge to edge on a wall with matching depth and wall thickness. The back-to-back pair project is `hex-tile`; this skill is the single-tile workflow.

## Facts that decide outcomes

- **The tear roof goes at the top of the print.** `roof_tear` cuts the roof hollow at one end only. That end must be at the top. Flipping the tile puts the untorn hollow at the top and gives a flat 4.9 mm bridge (the ridge, and Bambu Studio's "floating cantilever" warning). Never recommend a flip without slicing it first; the flip was recommended once and was wrong.
- **A 180 degree in-plane rotation or a flip does not help the face.** The tile is a dome: the lower half faces down and the upper half faces up in any orientation.
- **Layer lines come from layer height x tan(facet lean).** Median lean is about 2.3 to 2.6 degrees, so the step is about 0.01 mm per layer at 0.16 mm. Filament finish (matte, marble) is the biggest lever; nozzle size and "lower fan" are not. Whether matte or marble hides the lines is untested. Say so, and offer a coupon pair instead of claiming it.
- **Run builds from the repo root** of the checkout or worktree you are in (`uv run python`). `roof_tear` has been on `main` since PR #82.
- **Never start a print, and queue only when asked.** A queue item uses `manual_start: true`; the owner clears the plate and presses Start.
- **Tile frame vs bed.** Tile x is corner to corner (±127), y flat to flat (±109.985, vertical in the print), z depth (0 to 15.24, open back at z 0). Bed X = 109.270 − z, Y = 128.000 − x, Z = 109.985 + y, so the build direction is tile +y. Convert every slicer event back to tile coordinates before judging it.

## 1. Build the matched tile

```
cd /Users/billrahe/dev/print-lab   # or your worktree
uv run python .claude/skills/rift-tile-print/scripts/build_matched_tile.py <out>/RIFT_10IN_seed3_tear_matched6in_tileframe.stl
```

Writes the STL and a STEP beside it and prints validity, volume (expect about 106.5 cm3, 247 planar faces), lean statistics and downward-facing area. Parameters are the 6 in tile's scale (`kx`, `kz`) applied to the 10 in values; the script asserts they sit inside the generator's bounds. The earlier 19 mm / 154.6 cm3 tile is a different, deeper model, not a bug.

## 2. Fusion (MCP server `fusion`, 127.0.0.1:27182)

Read `references/fusion-notes.md` before scripting. Short version: import the STEP, not the STL (a mesh convert gives 844 triangle faces; STEP gives a clean planar B-rep). Scripts fail while a command dialog is open and roll back entirely on any exception. Draft analysis needs a body and `createInput([body], directionEntity)` takes a Python list. Fusion exports 3MF in inches. Do not delete the owner's analyses; deleting a timeline feature resets the occurrence transform, so re-apply it and take a snapshot.

## 3. Project 3MF and slice

```
uv run python .claude/skills/rift-tile-print/scripts/build_project_3mf.py <outdir> <smooth_base.3mf> <6in_project.3mf>
```

Stands the unflipped tile, swaps its mesh into `object_4.model` of the smooth base 3MF and copies slot 2's filament values from the printed 6 in project. Check the printed `filament ids`, `nozzle temp`, `layer`, `infill` against the table below. Then slice:

```
/Applications/BambuStudio.app/Contents/MacOS/BambuStudio --slice 1 --outputdir <outdir>/out --export-3mf <outdir>/<name>.gcode.3mf <outdir>/<name>.3mf
```

Settings of the queued print: 0.16 mm layers, 100 % zig-zag infill (the layer-range modifier is ignored by the CLI, so it is project-wide), 3 classic walls inner then outer, outer wall 40 mm/s at 600 mm/s2, 0.45 mm line, back seam, 30 mm outer-only brim, Kexcelled K5 PLA Matte Light Matte Terracotta at 210 C (flow 0.96). Result: 7 h 28 min, 128.21 g, 1375 layers, max z 220.04 mm.

## 4. Check the G-code before queueing

```
grep -c '^; FEATURE: Bridge' <outdir>/out/plate_1.gcode
grep -E '^; FEATURE: (Overhang wall|Floating vertical shell)' <outdir>/out/plate_1.gcode | sort | uniq -c
grep -E '^; (total filament weight|estimated printing time|total layer number|max_z_height)' <outdir>/out/plate_1.gcode
```

Expected for the unflipped tile: one 2.5 mm bridge at about z 217.96 (the tear sliver), and "floating vertical shell" markers only at the foot and cap layers. A flat bridge near 4.9 mm at the top means the tile is flipped or the tear roof is missing; fix the model, don't dismiss the warning.

## 5. Upload and queue on Bambuddy

Read `references/bambuddy-queue.md` for the exact calls and keys. The mapping is `ams_mapping: [1]` for slot 2 (index = slot minus 1). Confirm the spool in that slot matches the slice's filament before queueing: compare the AMS tray reading with the owner's photo or inventory, since tray colour, slice header colour and inventory colour often differ and that is metadata only.

## 6. Mount model: ribs, bosses, keyholes

```
uv run python .claude/skills/rift-tile-print/scripts/add_mount_bosses.py <out>.stl --key-y0 105.0
uv run python .claude/skills/rift-tile-print/scripts/mesh_to_project_3mf.py <base.3mf> <out>.stl <out_project>.3mf
```

Two 28 x 16 mm bosses at x ±45 on 1.8 mm vertical ribs, kept 1.6 mm below the inner skin, each with a teardrop keyhole (1.8 mm lip, 5.0 mm pocket). Slice it, then run the section 4 greps and list every bridge, overhang and floating-shell event in tile coordinates.

- **A flat boss underside is a bridge in a standing print.** The first model had one (about 406 + 438 mm of bridge at z 102). Each boss now has a 50 degree gusset down to its rib. Check every added feature's underside against 45 degrees, not just its attachment.
- **`--key-y0` ties the rib top to the rim roof.** The rib climbs at 45 degrees from y = 105.0 and fuses 0.3 mm into the roof wall, which keeps 3.5 mm from the visible face. Without it the ribs stop short and are anchored only at the bottom wall.
- **The 36 % sliced-area step at 16.24 mm print height is the inner edge of the 16.3 mm back land flange** (`land_width`). The plain tile has it too; ribs and bosses don't cause it.
- **Known residue** in the gusseted candidate: 2 bridges of 81 mm at the keyhole pocket tips, 16 small overhang segments, 68 floating-shell markers with the cause not isolated, +18.3 g and about 1.5 h over the plain tile. Keyhole strength and the face finish are untested; say so and suggest a hang test and a coupon.

## Report

Lead with what was built or checked, then what was queued only if asked, and what the owner must do (clear plate, press Start). Include the slot, time and grams. Say plainly what is untested (marble vs matte, lines hidden or not). Do not claim a quality improvement without a test print.
