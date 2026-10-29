# C02 — Selected geometry and qualification setup

**Use the 3MF as an editable project and slice it in Bambu Studio. It contains no G-code.** This is the selected design for qualification; commercial production readiness still requires physical and repeated-print acceptance.

## Four files

| File | Purpose |
|---|---|
| `tile.scad` | Complete standalone C02 source, unchanged from the geometry-validated model. |
| `C02_SINGLE_QUALIFICATION.3mf` | Selected single-tile geometry, orientation and embedded process settings. Start here. |
| `C02_PAIR_QUALIFICATION.3mf` | Two independent copies using the same setup; qualify after the single passes. |
| `ENGINEERING.md` | This guide. Full analysis and original evidence are in the separate engineering archive. |

## Design decision

Keep C02's raised asymmetric face, hollow rear, 9 mm rim depth, 19 mm maximum depth, 2.4 mm axial skin and 17.7 mm U-shaped tape land. No new braces, tacks or pair ties are introduced. Both projects preserve the orientation in the supplied preflight. The pair has 20 mm raw clearance along the tile-depth axis, with nominal 4 mm between 8 mm brims. Its geometry plus brim and 5 mm margins fits the specified 256 mm bed.

The supplied preflight was independently inspected: matching mesh, one watertight component, continuous display contours, and internal roof-shell paths over 15% grid near the top. Those internal paths do not demonstrate a floating display face. They do identify a support/heat transition, while the actual inner-wall and floating-shell paths also use high motion settings. The selected setup addresses these two concerns together; a successful print would qualify the whole setup, not isolate which setting produced the result.

## Selected settings

| Setting | Value |
|---|---|
| Printer | Bambu Lab X2D, 0.4 / 0.4 mm nozzles; original assignment retained |
| Process name | C02 Qualification 0.20mm - Dense Shell |
| Layer / first layer | 0.20 / 0.20 mm |
| Walls / generator / order | 3 / Classic / inner then outer, unchanged |
| Filament | Supplied stock Bambu PLA Matte profile: 220 °C, flow 1.006 |
| Plate | Textured PEI, 55 °C |
| Brim | 8 mm outer; requested object gap 0 mm |
| Modeled-volume fill | 100% Rectilinear; serialized Studio value `zig-zag` |
| Outer / inner wall speed | 40 / 150 mm/s |
| Internal solid / gap fill speed | 100 / 100 mm/s |
| Floating-shell speed | 80 mm/s absolute; diagnostic remains enabled |
| Top-surface speed | 50 mm/s |
| Default / outer / inner acceleration | 2,000 / 500 / 1,500 mm/s² |
| Travel speed / acceleration | 500 mm/s / 3,000 mm/s² |
| Top-surface acceleration | 1,000 mm/s² |

First-layer motion, material temperature, flow multiplier, volumetric cap, cooling, machine macros, wall widths and bridge settings retain the supplied values. No new temperature or flow calibration diagnosis is assumed.

The supplied preflight's nominal bead reconstruction shows one connected model footprint, but about 0.27 mm minimum separation between brim and model paths. Its 0.1 mm brim-gap setting and 0.2 mm elephant-foot compensation therefore must not be described as a continuous stability base. The selected setup requests zero brim gap and retains the 0.2 mm compensation to protect the lower edge. This reduces the requested release gap; **it does not prove the resliced brim will fuse to the tile**. Check the actual Preview and physical attachment. The tile's broad base remains the primary bed-contact geometry.

The later CLI follow-up reports approximately **0.18 mm residual nominal gap** in the corrected slice. Treat any visible separation as a detached brim; do not assume first-layer spreading closes it or credit it as bonded support.

**100% fill applies only inside the modeled plastic regions. The rear cavity remains an actual open void in the mesh.** The intent is to remove sparse grid as the roof-shell foundation. It adds material/heat and does not remove the roof's geometric mass increase; its visual benefit is a testable expectation, not an established result.

## Open, slice, inspect, print

1. Open the single 3MF **as a project**, using its embedded settings. Selecting the old v70 process afterward would replace the selected settings. Confirm the process name and the table above.
2. Retain upright placement and size. The supplied tiny negative Z rounding offset is about 0.000023 mm; ensure the part sits on the bed. Do not rotate the display face onto the bed or scale the tile.
3. Slice. The original delivery used an invalid infill enum, `rectilinear`; both projects are corrected to `zig-zag`. The supplied CLI follow-up reports that this single-key correction allows both to slice: approximately **3 h 35 min / 75.8 g single** and **7 h 04 min / 151.6 g pair**. These are externally reported estimates, not a native slice performed in this runtime. The uploaded stock preflight's **1 h 59 min / 72.52 g estimate does not apply to this changed setup**. Confirm your own fresh estimates. The pair target remains approximately nine hours or less.
4. In Preview, inspect the first layer, the lower closure around 1.4–2 mm, and the upper closure around 124–132 mm. Confirm full fill where the former sparse grid was, supported internal paths and intact outer contours. Keep the floating-shell detector enabled; assess the actual support and paths rather than requiring the role label to disappear. Supports remain off. Inspect any reported new warning before printing.
5. Print one tile with normal printer calibration behavior preserved. Record lower/middle/upper motion, completion, dimensions, rear flatness, edge quality and cleanup. Inspect the whole face under diffuse and raking light, paying particular attention to the upper 8–12 mm. Do not repair or sand a failed display surface into acceptance.
6. After the single passes, slice and qualify the pair with the same embedded settings. Use simultaneous layer printing. Check pair finish, time and cleanup independently before repeated production runs.

## Evidence and limits

The two uploaded preflights are byte-identical and match SHA-256 `b783587668a2aa116356328630039c762a7b030f82deca1e85b6453b0a54384e`. The embedded mesh matches C02 to approximately 0.0000034 mm after alignment. Geometry and settings were verified directly, rather than accepted from the CLI summary.

The revised projects retain the exact embedded mesh and contain no stale slice cache. XML/JSON, relationships, instance count and bounds were checked. The corrected infill enum was independently checked against Bambu's source; the user's CLI follow-up reports successful slicing of the corrected settings. The resulting fixed/sliced projects were not attached for independent inspection here, and no C02 physical print result has been supplied. No absence of banding, stable full-height motion, clean removal, adhesive durability, repeatability or commercial suitability is asserted.

The CAD rear-land clear-air bound remains approximately 4.10 mm and the conservative minimum skin separation approximately 2.34 mm. This air-gap statement excludes the integral perimeter/roof shell joins; it does not prove thermal isolation there. The native projects preserve that geometry.

Use 12.7 mm tape on the designated U-land, open end upward. Exact adhesive, wall coating, environmental durability and installation loads remain qualification items.
