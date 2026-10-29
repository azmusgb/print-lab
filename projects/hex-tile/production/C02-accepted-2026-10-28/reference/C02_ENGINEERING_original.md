# C02 — Start here

This is the raised asymmetric tile inspired by your reference: 13 distinct planar facets, five offset interior junctions, a hollow rear and an integral tape land. It is a geometry-validated trial candidate, not a production-qualified part.

## Files

| File | Use |
|---|---|
| `tile.scad` | Standalone editable model. Default output is one upright trial tile. |
| `tile-single.stl` | Start with this one-tile print trial. |
| `tile-pair.stl` | Two independent tiles; evaluate after the single succeeds. |
| `preview.png` | Head-on rendering of the actual face geometry. |
| `ENGINEERING.md` | This short guide. |

The complete design review, parameter table, validation scripts and results are preserved in the separate C02 engineering archive.

## First print

1. Import `tile-single.stl` in millimeters. Keep it upright on its flat lower edge, as supplied; the raised display face stands vertically. Center the tile on your actual usable plate and place it at Z=0. Do not lay the display face onto the bed.
2. Check the upright model dimensions: approximately **152.4 × 19 × 131.982 mm**. Reserve **178.4 × 45 mm** on the bed, including an 8 mm brim and 5 mm additional margin on each side. Allow 136.982 mm usable height including 5 mm headroom. The source assumes a 256 mm cube; change its build-volume parameters for your machine before regenerating outputs.
3. A provisional trial baseline is a 0.4 mm nozzle, 0.45 mm line width, 0.16 mm layers, 0.20 mm first layer, four wall paths and an 8 mm brim. Use your printer's established profile for the exact material. These settings have not been slicer or physically validated for this tile. No G-code is supplied.
4. Inspect layer preview for continuous first-layer contact, the internal upper roof, seams and complete walls. No supports are planned. Investigate any unsupported toolpaths before printing; do not accept support contacts on the display face.
5. Observe lower, middle and upper print regions. After cooling, inspect the face under raking light, measure the outline and rear flatness, and time brim cleanup. Keep the source, mesh, slicer project and process settings with the result.

For the pair, reserve **178.4 × 84 mm** including the same allowances. Use simultaneous layer printing. Each tile is independent; there is no connecting plastic to break away. Equivalent printed quality and a pair duration of approximately nine hours or less remain unverified.

## Mounting and limits

The rear U-shaped land is 17.7 mm wide for 12.7 mm tape. Nominal placements are three 50 mm strips along the bottom/lower sides and two 30 mm strips along the upper sides. Keep the open end of the U upward. Tape product, wall substrate, installed bond strength and service durability are not qualified.

Geometry evidence: one watertight solid per tile, approximately 2.34 mm conservative minimum face-skin separation, and at least 4.09 mm conservative clear-air bound from the rear tape land to the face skin. The air-gap claim excludes integral perimeter and roof shell joints; thermal telegraphing at those joins remains a physical test.

**Not yet established:** slicer acceptance, full-height stability, finished appearance, cleanup time, mounting durability, print duration or repeatability. Qualify these before commercial installation.
