# Hex tile history audit

## Revisions
- 42 revisions with files: v15–v58
- versions with no files: v43, v45

## Evidence
- A (one change): 2 — v48→v49, v52→v53
- B (two changes): 2 — v41→v42, v47→v48
- C (3–4 changes): 6 — v32→v33, v36→v37, v44→v46, v46→v47, v49→v50, v51→v52
- D (5 or more changes): 15 — v16→v17, v19→v20, v30→v31, v31→v32, v33→v34, v34→v35, v35→v36, v37→v38, v38→v39, v39→v40, v40→v41, v42→v44, v50→v51, v53→v54, v54→v55
- F (what printed is unknown or contradicts the file): 16 — v15→v16, v17→v18, v18→v19, v20→v21, v21→v22, v22→v23, v23→v24, v24→v25, v25→v26, v26→v27, v27→v28, v28→v29, v29→v30, v55→v56, v56→v57, v57→v58

## Persistent defects
- upper-edge ripple: v36, v37, v39, v51, v56
- strings: v29, v51, v54
- pair welded: v46, v47, v48
- supports: v29
- grainy face: v31
- pad ghost lines: v31
- lines along slanted edges: v32
- tipped over: v33
- rough face: v34
- fins hard to remove: v36
- breaks up above widest point: v39
- rough bottom edge: v40
- margins: v40
- lines across face (tabs): v41
- edge ridges: v41
- seam on face corner: v41
- lines across face (pad ends): v49
- ridges near corner: v49
- ridges along edge: v50
- rough edge: v50
- bottom-edge band: v50
- lines across face: v50
- tabs flimsy: v50
- line near edges: v51
- bottom texture: v51
- ribbed face: v54
- mid-height line: v56

## Changes that never touched it
- upper-edge ripple (reported v36, v37, v39, v51, v56): 14 of 18 steps in between changed none of layer_height, orient_for_print, outer_wall_speed, skin — v37→v38, v38→v39, v39→v40, v41→v42, v42→v44, v44→v46, v46→v47, v47→v48, v48→v49, v49→v50, v50→v51, v51→v52, v52→v53, v55→v56

## Not yet tried
- the printer's vibration (resonance) calibration
- a slower speed on the upper half only (height-range modifier)
- matte PLA
- filament confirmed dry before printing
- leaning the tile (the owner asked on 15 Oct; argued against, never tested)

## Next experiment
- EXP-001: does v58 (no join that starts partway up) remove the mid-height line? A height strip across Z 60–100 mm of the 6" pair, v58 against v56, both on the 0.4 nozzle. Why: the line appears from v53, when the upper-edge join began at mid-height, and stays while that join is kept.

Outcomes come from the owner's messages in the chat; none are confirmed yet.
