# Print lab: the speed sweep (one plate, one speed per strip)

Written 24 Oct 2026 for the owner's review. **Status: draft, not started.**

## Goal

Find which wall speeds put bands on v58's face, in one print. Today each experiment compares two values. A sweep
prints 3 to 6 values side by side and asks one question: from which speed do the bands start?

## Why not a stepped tower

An OrcaSlicer-style tower changes speed with height. In Bambu Studio 02.08.02.61 that works for the inner wall but
not for the outer wall, which is what makes the tile's face. The lab's own capability tests showed this:

- CAP-BAMBU-HEIGHT-RANGE-inner_wall_speed passed (60 → 120 mm/s switched at 6.2 mm).
- CAP-BAMBU-HEIGHT-RANGE-outer_wall_speed failed: the outer wall eased from 67 to 109 mm/s over many layers.

A stepped outer-wall tower would blur exactly the bands we want to see.

Per-object speeds do work (`outer_wall_speed` and `inner_wall_speed` are `per_object_verified` in `lab/factors.json`).
So a sweep is N separate short strips on one plate, each with its own speed. They share the plate's time per layer,
the printer's state and the spool, so the only thing that differs is the speed.

## What `lab source` already settles

- **Speeds above the flow cap are pointless.** Bambu Studio caps every wall at
  `filament_max_volumetric_speed / mm3_per_mm` (GCode.cpp around line 6161, noted in
  `capabilities/02.08.02.61-source.json`).
  - With the Kexcelled profile's 12 mm³/s and 0.42 × 0.2 mm lines, that is about 147 mm/s. This is why 250 mm/s
    inner walls printed at 147.
  - A sweep therefore refuses values above the cap at plan time: it says what the cap is and why. Raising the cap is
    a different factor (`filament_max_volumetric_speed`) and its own experiment.
- **The outer-wall ramp isn't the "smooth speed discontinuity" setting.** That setting only smooths overhang areas
  within a layer. So the sweep makes no assumption about ramps between layers. Each strip is one object at one speed,
  and the realized-speed check reads what was really printed.

## Design

1. **Plan.** `lab exp plan Q-003 "Which outer-wall speeds band?" --test-kind speed_sweep --factor outer_wall_speed
   --values 40,60,80,100,120,140 --around 66 --source … --base …`
   - Only `per_object_verified` speed factors are allowed. Each value must be at or under the flow cap.
   - Between 3 and 6 values.
   - Each strip is sized around the chosen height, as height strips are today (judged band ±2 mm, edge margins grown
     until the strip is representative), so the strips are identical apart from their speed.
2. **Plate.**
   - The strips stand in a row in ascending speed, mirrored on a repeat print, the same rule experiments use now.
   - Each strip's ID tab shows its speed ("60", "100") instead of "5A", so a photo needs no key.
   - The witness wall is added only when the sweep is compared with another plate.
3. **Check.** All the existing guards apply.
   - The one-factor check confirms the strips differ only in the swept setting.
   - The realized-speed check reads each strip's printed speed from the G-code. It blocks if two strips printed the
     same speed, and it shows any strip the slicer changed.
   - The usual budgets apply. Six strips around Z 66 come to about 60–70 min, so a sweep normally needs your
     approval.
4. **Verdict.** You grade each strip: `lab exp verdict E-009 --grade 40=clean,60=clean,80=faint,100=banded,…`.
   - The grades are clean, faint or banded, named by speed or by tab.
   - The verdict also records the light, as now. Only a diagnostic-light verdict counts.
5. **Outcome.**
   - **Without a prediction:** the result is the finding "clean up to 60 mm/s, bands from 100". It is recorded as
     evidence that later experiments can build on. It doesn't count towards the uninformative streak, as
     acceptance verdicts don't.
   - **With a prediction** (`--expect "bands>=100"`):
     - **supported:** every strip at or above 100 is banded, and every strip below is clean.
     - **refuted:** a strip below 100 is banded, or one at or above is clean.
     - **unresolved:** "faint" grades leave it unclear.
6. **Page.** A sweep card shows one chip per strip with three things: the speed asked, the speed printed (when the
   slicer changed it) and your grade, coloured clean, faint or banded. The finding appears as one line.

## Testing

- **Plan:**
  - A value above the flow cap is refused, and the message names the cap.
  - A plate-wide factor is refused.
  - Fewer than 3 or more than 6 values are refused.
- **Build (fake slicer):**
  - N strips with one speed each and identical meshes.
  - Tabs carry the speeds.
  - The order is mirrored on a repeat print.
- **Check:** two strips that print the same speed block.
- **Verdict and outcome:** each row of the outcome rules above. A sweep without a prediction never moves the
  streak.
- **Real slice (slow test):** a 4-value outer-wall sweep shows four distinct outer-wall speeds in the G-code.

## Out of scope

Stepped towers; pressure advance and flow calibration (later presets); printing the sweep for you (starting prints
is level 3).

## Open questions for the owner

1. Which speeds for the first sweep? I recommend 40, 60, 80, 100, 120 and 140 mm/s on the outer wall around Z 66,
   where the bands were seen. Your profile's 80 mm/s is in the middle of that range.
2. Should it be on Q-001 (what causes the bands) or a new question? I recommend Q-001, so its results build on
   E-002 to E-005.
