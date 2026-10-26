# Hex tile design ledger

Sources: the change notes at the top of each `sources/scad/hex_wall_tile_v*.scad`, `history/outcomes.json` (the
owner's words per version), and `experiments/E-*.json`. Quote the owner's words; don't paraphrase them into a
stronger claim.

## How the two tiles of a pair were joined

| Version | Join between the backs | Separation (owner's words) | Face cost |
|---|---|---|---|
| v34–v38 | Single tile; snap-off fins (v34), then a brace frame (v38) on tiny tabs | v36: "the fins are hard to pull off the back" | v33 "tipped over" without fins; upper-edge ripple v36–v37 |
| v39 | Pair, 0.4 mm gap, 12 tiny tabs | twisted apart | 6": tab spacing grew with size, "breaks up above widest point"; 3" "perfect" |
| **v40** | Tabs every ≤12 mm round the rim on every size | **came apart** ("better! 6" tiles printed") | v41: "lines are on all four prints" — tabs at the same heights changed those layers' toolpath |
| v42–v46 | One continuous hairline seam round the edge, 0.4 mm gap | v46: "cant separate the pair once printed" | clean |
| v47 | Gap 0.4 → 1.0 mm, seam only joins | "the two are almost welded together" | clean |
| v48 | Seam on the slanted edges only, pry slots top/bottom | "its almost fused together" | clean |
| v49–v51 | "Kiss" seam: stops 0.15 mm short of the partner | no welding complaint recorded | v49/v50 lines from pad ends, not the seam |
| v53–v54 | Upper slanted seams fused, lower kiss | not recorded | v54 "ribbed face … way worse than prior versions" |
| v57/v58 | Closed backs + full-height ribs stopping 0.10–0.15 mm short | E-008 "fused too much"; E-014 cracked when cut apart | faces clean (E-002, E-008, E-012, E-014) |
| v59 | Ribs 0.5 mm short (no contact) | — | E-011: faces broke loose from the strip base, "Not good" |
| v58 g015/g020 | Ribs 0.15 / 0.20 mm short | E-012: all fused | — |
| v60b125 | v58 with 1.25 mm backs (0.65 before) | never printed | — |
| v61t | Ribs and seams → 124 tacks, bunched at the same heights | abandoned before printing: repeats v41's layout | — |
| v61s | Ribs and seams → 207 tacks, one per 0.6 mm band, 1.25 mm backs | E-019 strip came off the plate at layer 14; E-020 full pair built | under test |

**What this proves:** any continuous contact fuses, whatever gap the model leaves below about 0.4 mm, because
the squashed lines bridge it. v58's ribs and seams were 1,697 mm² of contact; E-014 bridged the gap on 657 of
660 layers. No contact at all lets the top wobble loose (E-011). Discrete tabs are the only join that ever
separated (v39/v40). Their one problem was face lines when the tabs sat at the same heights (v41).

## What has put lines or ripples on the face

| Cause | Versions | Rule |
|---|---|---|
| Anything attached to the skin, or within ~1.4 mm of it, ghosts through | v31 pads, v50 lips | Keep ≥1.6 mm air from the skin (`back_gap`, `pad_gap`); nothing joins the rim near the face |
| A feature that starts or ends abruptly changes the layer time → a line across the face | v49/v50 pad ends, v41 tabs | Taper feature ends over many layers; keep every layer the same complexity |
| The top of a tall thin wall wobbles → ripple near the upper corners | v36, v37, v39, v51, v56 | Brace the full height: a single tile needs fins or a brace; a pair braces itself only if it is joined up to the top |
| Printer setup | E-002 | Drying + vibration calibration made the faces "much better" (both now in the setup log) |
| Inner/outer wall speed jump | E-003/E-005/E-010 | Unresolved; E-010 speed sweep never approved |

Lying the tile flat or leaning it doesn't help: the facets are 2–12° from the back, so they print as wide
contour rings. Upright is right for this face.

## Plate and process events

- E-014: "bottom fused with the plate so the bottom side detached from the tile". The part was most likely removed warm or pulled off.
- E-019: the strip came off at layer 14, after the plate had been handled to remove E-014. The brim was already 10 mm outer-only, the same as E-012's strips, which stayed on.
- High strips of a pair that isn't fused every layer have failed twice: E-011 (v59) and E-019 (v61s). Strips of fused v58 (E-008 from 80 mm, E-012) printed fine. The two possible causes, plate contamination and an unjoined base, haven't been told apart.
