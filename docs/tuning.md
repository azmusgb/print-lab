# Printer tuning: what the general guides say, for the hex tile's symptoms

Written 27 Oct 2026. Sources: [Ellis' Print Tuning Guide](https://ellis3dp.com/Print-Tuning-Guide/) (written for
Klipper/Voron printers; only its printer-independent advice is kept here) and OrcaSlicer's built-in calibrations
(installed on the Mac 27 Oct: `/Applications/OrcaSlicer.app`). This is **general tuning advice, not evidence about the
tile**: the tile's own record and lessons are in `.claude/skills/hex-tile/SKILL.md`, and nothing here is proven for
the X2D until a lab experiment tests it. Treat each suggestion below as a hypothesis for a single-factor test.

## Order to tune in

OrcaSlicer (Calibration menu) prints each test on the X2D. Do them **per filament**, in this order, because each one
changes what the next measures:

1. **Dry the filament first** if the spool has been open (AMS humidity was 43–45 % on 27 Oct; Bambuddy's drying presets:
   PLA 45 °C 12 h, PETG 65 °C 12 h). Ellis: wet filament causes "near-unfixable stringing", and no setting fixes it.
2. **Flow rate** (OrcaSlicer: Flow rate, pass 1 then pass 2).
3. **Pressure advance** (OrcaSlicer: Pressure advance, tower or line method). Ellis: tune it **before** retraction;
   it often removes the need for retraction tuning.
4. **Temperature tower**: pick the coolest temperature that still bonds layers.
5. **Retraction test**, only if stringing remains after 1–4. Direct drive (the X2D) starts around 0.5 mm and should stay
   under about 1 mm; choose a value 1–2 steps above where strings disappear.

Record each result as a lab experiment (`test_kind` calibration), so the values the tile prints with are written down
rather than remembered.

## Symptom → what the guides point at

| Tile symptom | General causes (guides) | What to try, as a single-factor test |
|---|---|---|
| **Strings** between the pair or across the gap | Wet filament (first), then too hot, then pressure advance, then retraction | Dry the spool and reprint unchanged; if strings remain, temperature tower, then PA, then retraction |
| **Fine vertical lines** on the face | Ellis "VFAs": belt/pulley/idler teeth (about 2 mm apart), bearings, rails, dirty pulleys | Measure the spacing first. ~2 mm and vertical regardless of the part → printer mechanics (belt tension, clean pulleys), not the model. The skill's height-matching check covers horizontal lines tied to model features |
| **Bands / ridges / "wood grain"** on the face | Extrusion consistency (flow, PA, filament diameter), not mechanics, if they wander off vertical | Flow rate and PA calibration on that spool; compare against a known-good spool |
| **Part off the plate** / early failure | Oils on the plate (wash with dish soap, air dry, hold by edges), first-layer squish, first-layer line width (Ellis uses 120 %), bed temperature (about 60 °C PLA, 80 °C PETG) | Washed plate, same file. Textured PEI needs more squish than smooth. On 27 Oct v73 failed on both the cool plate and the textured plate; plate type and plate cleanliness are separate factors |
| **Pair fused / welded** | Heat soak: Ellis's PLA-overheating fixes are more cooling, door open, bed heater lower or off; longer layer times | Door open (the X2D is enclosed) or chamber kept cool, same model. The skill notes contact area is the main lever; heat is a second factor worth isolating |
| **Corners bulging, seams rough** | Pressure advance | PA calibration |

## What doesn't apply to the X2D

Klipper motor settings (TMC driver tuning), Voron gantry squaring, SuperSlicer-specific steps and macros. Bambu
firmware handles input shaping and vibration calibration itself (Bambuddy's "Vibration calibration: On" default).
