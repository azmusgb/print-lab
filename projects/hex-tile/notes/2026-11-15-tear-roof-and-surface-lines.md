# 10 in tile: top-edge ripple, tear roof and face layer lines (13-15 Nov 2026)

Free-form notes, not lab experiment records (no E-numbers, no schema). Design: `faceted_hex` seed 3 at 254 mm, 19 mm
deep, scaled as the locked 6 in tile (0.9215 in plane, 0.8021 thickness). All prints on the X2D, AMS slot 3 unless noted.

## Top-edge wobble and ridge (first 10 in print, `RIFT_10IN_19mm_seed3_batch5`)

- Cause: the sealed hollow roof had a flat ceiling at the top wall's inner face, a 4.6 mm bridge over the rim channel.
  The augura printability check on the closed 3MF solid found it as a 0 deg ceiling.
- Fix: `roof_tear` = 1 cuts the roof hollow's far side back at 45 deg too, so the hollow is tear-shaped and the
  bridge drops to a 0.4 mm sliver. Same tile volume as the scratch patch used for the print (106 514.9 mm3).
- Result: `RIFT_10IN_19mm_seed3_tear_batch5` (6 h 4 min) had no ridge and even lines. Owner judged it better than the
  first 10 in print.

## Faint 45 deg band on the face's top inch

- Seen on the tear print. Hypothesis: sparse infill behind the face skin printing through. Counter-run
  `..._tear_solid_batch5` with 100 % zig-zag infill (grid is refused at 100 %): the band was not visible in the
  photos afterwards. One print, so this is a likely cause and not proven.
- The layer-range modifier (100 % infill only above 190 mm) is ignored by the Bambu Studio command line, so the
  100 % infill is project-wide.

## Visible layer lines on the face

| Print | Layers | Outer wall | Time | Owner's reading |
|---|---|---|---|---|
| `..._tear_solid_batch5` | 0.20 mm | 80 mm/s, 1500 mm/s2 | 6 h 4 min | lines visible |
| `..._tear_solid_016_batch5` | 0.16 mm | 60 mm/s, 1500 mm/s2 | 7 h 39 min actual 7 h 48 | more uniform, lines show more |
| `..._tear_solid_016_smooth_batch5` | 0.16 mm | 40 mm/s, 600 mm/s2, 225 C, 0.45 line | 9 h 21 min | printing 15 Nov, not judged |

- Lines come from layer height and facet lean, not nozzle size: a 0.6 mm nozzle (Bambu range 0.18-0.42 mm layers)
  cannot do better than 0.16 mm and blurs facet edges.
- Even layers read as a regular texture. The glossy Shadow Storm marble (first 10 in print) hid lines; the 6 in tile
  used matte PLA (PlastKyro Dusty Rose, Kexcelled K5). The pink spool in slot 3 is a plain colour and shows them.
- A uniform 9 in scale-down keeps every facet angle, so it does not make the face smoother. A lower `facet_rise`
  would, at the cost of a flatter look.
- Brushed streaks sit near facet boundaries, where a facet leans away from vertical (wider layer ledges).
- Bottom edge tore ragged when lifted off the plate (brim and first layers).

## Open

- Does matte or marble filament at 0.16 mm remove the lines? Not yet tried on the tear tile.
- Do the smooth-profile settings (outer wall 40 mm/s, 600 mm/s2, 225 C, 0.45 line) help on their own? Needs the
  same filament as the 0.16 mm print to compare.
- Bambuddy logs some finished prints as "Aborted / noStatusUpdate".
