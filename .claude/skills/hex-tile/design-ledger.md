# Hex tile design ledger

Reconciled 26 Oct 2026 from every source on the Mac. The full working file, with sources, is
`history/hex-tile/chat/reconciled-2026-10-26.md` (local only, not in git).

## How to read this ledger

- **owner:** the owner's own words, quoted exactly. v29–v56 come only from `history/hex-tile/chat/owner-notes.md`,
  a transcription of the cloud chat; the original isn't on disk.
- **AI-photo:** an AI's reading of a photo. It is not a verdict and never becomes one by being repeated.
- **inferred:** a conclusion that no source states.
- Write "not recorded" when nothing was said. Never fill a gap from memory or from a design note.
- Status of a lesson: observation → hypothesis → supported (under stated conditions) → rule. Only the owner's
  verdicts on controlled prints move a lesson past "hypothesis".

## How the two tiles of a pair were joined

| Version | Join | Separation | Face | Filament (by photo colour, inferred) |
|---|---|---|---|---|
| v34–v38 | Single tile; snap-off fins (v34), then a brace frame (v38) | owner v36: "the fins are hard to pull off the back" | v36 AI-photo: ripple near the top edge | yellow (v36) |
| v39 | Pair, 0.4 mm gap, 12 tiny tabs | not recorded; AI-photo: the pair still joined | owner: "3" was perfect --- 6" was far from it" | grey |
| v40 | Tabs every ≤12 mm | not recorded ("better! 6" tiles printed" is about printing) | owner: "front face could use a bit more polish" | – |
| v41 | v40 tabs, 10" | not recorded; AI-photo: one tile's back on its own, so apart | owner: "lines are on all four prints" | pink |
| v42–v46 | Continuous hairline seam round the edge, 0.4 mm gap | owner v46: "cant separate the pair once printed" | owner v46: "def better" | – |
| v47 | Gap 1.0 mm, seam only joins | owner: "the two are almost welded together" | – | – |
| v48 | Seam on slanted edges only, pry slots | owner: "its almost fused together" | – | – |
| v49 | Kiss seam, stops 0.15 mm short | not recorded; AI-photo: a single back, so apart | AI-photo: two lines across the face at pad ends | grey |
| v50 | v49 seam, pointed pad tops | not recorded | owner: "front margins have a bit of print/finish issues"; picked "Lines across the face" | – |
| **v51** | Kiss seam 0.15 mm on the **edges only**, pry slot, no ribs | **not recorded**; AI-photo: two separate backs | owner: "defects - 6"" only. AI-photo: big face areas clean; ripple near a top corner; strings; a line 3 mm in from the edges | pink |
| v53–v54 | Upper seams fused from mid-height, lower kiss | not recorded | owner: "bad!" (v53 or v54); v54: "way worse than prior versions" | pink |
| v56 | as v53 | not recorded | owner: "ugh"; mid-height line | white |
| v57/v58 | Closed backs + full-height ribs stopping 0.10–0.20 mm short | owner E-012: "i cant even pull them apart withougt breaaking them", "one i pried / other i used a utility knife to seperate" | owner E-008: "looks really good" (inferred to be E-008); E-014: "faces are pretty good" | terracotta |
| v59 | Ribs 0.5 mm short (no contact) | – | E-011: faces broke loose from the strip base; owner: "Not good" | terracotta |
| v61s | 207 tacks, fused into both 1.25 mm backs | owner E-020: "was SUPER hard to seperate them"; AI-photo: one back torn | owner E-020: "face was good and no extra artifaces" | terracotta |
| v62k | Kiss tacks (fused into one back, 0.15 mm short of the other) | E-021/E-022: not recorded | owner E-021: "really bad in person", "both sides bad" (both strips, including v61s) | terracotta |

## What the record supports

- **Observation:** every pair seen apart in photos predates the ribs (v41 tabs; v49 and v51 edge-only kiss seams).
  No source says how easy any of them was.
- **Observation:** every join with continuous or full-height contact was reported welded or very hard to separate
  (v46–v48, v58 ribs, v61s tacks).
- **Hypothesis:** the amount of contact matters more than the modelled gap. Supported by v46–v48 and E-012; not
  tested directly, and contact area alone doesn't predict separation force.
- **Hypothesis:** features at a few fixed heights leave lines across the face (v41 tabs, v49/v50 pad ends).
  Supported by line positions matching feature heights; no single-factor test.
- **Unresolved:** E-021/E-022 ridges. Both strips (v61s and v62k) ridged on a shared two-pair plate, while E-020
  (v61s alone) didn't. The kiss tacks aren't needed for the ridges but may contribute. Candidates: plate sharing,
  run conditions (chamber auto-cooling `M142`), filament, printer state. None tested.
- **Untracked factor:** filament changed from yellow to grey, pink, white and finally Kexcelled terracotta across
  versions. Any comparison across those versions is confounded by filament.
- **Acceptance:** E-020 was accepted for the 26 Oct deadline *with defects*: separation "SUPER hard" and one back
  torn. It is not a repeatable product.

## What has put lines or ripples on the face (hypotheses unless noted)

| Suspected cause | Versions | Working rule |
|---|---|---|
| Anything attached to or within ~1.4 mm of the skin ghosts through | v31 pads (owner: "the edges of the back pads where creating lines"), v50 lips | Keep ≥1.6 mm air from the skin |
| A feature that starts or ends abruptly changes the layer time | v49/v50 pad ends, v41 tabs | Taper feature ends; keep layers alike |
| The top of a tall thin wall wobbles → ripple near the upper corners | v36, v37, v39, v51, v56 | Brace up to the top |
| Printer setup | E-002 | Drying + vibration calibration preceded the "much better" faces (owner E-002) |
| Inner/outer wall speed jump | E-003/E-005/E-010 | Unresolved; never tested |

## Plate and process events

- E-014: owner: "bottom fused with the plate so the bottom side detached from the tile". Cause not established.
- E-019: the strip came off at layer 14; E-011's high strip also failed. A strip cut from high up is not the same
  object as the top of a full tile, so neither result says what a full pair would do.
- E-021: the printer recorded FAILED at 1 h 27 min of 1 h 46 min (Bambuddy #13); the lab had no failure. Whether
  the strips reached full height is not recorded.
- Nozzle: every file, including those named `*_0.6nozzle`, is set up for a 0.4/0.4 nozzle. v56 may be the only
  print that used 0.6 presets chosen in Studio.
