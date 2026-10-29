# HEX TILE v77: design package

Written 27 Oct 2026 against the outcome-based tile specification ("Perfected faceted hex wall tile", §1–38).

**Status: GEOMETRICALLY VALIDATED and SLICER VALIDATED. Not physically tested.** See §E.

| File | What it is |
|---|---|
| `sources/scad/HEX_TILE_v77.scad` | **A.** Final source: standalone and parametric, with guards |
| `sources/scad/validate_v77.py` | Mesh-level validator, independent of the SCAD's own asserts |
| `sources/HEX_TILE_v77.stl` | Production pair export (defaults) |
| `sources/HEX_TILE_v77_X2D_textured.3mf` | Slicer project: v77 pair + the v74 X2D settings, unchanged |
| `sources/HEX_TILE_v77_gusset.stl` / `..._gusset_X2D_textured.3mf` | Same with the C3 top gusset (experiment B) |

All are registered in `sources/sources.json` with sha256, `derived_from` and `change`.

---

## B. Design rationale

### Starting point: what 70+ versions established

The tile has a fixed architecture problem: a 152 × 132 mm faceted plate only 11.6 mm deep. Printed face-up, the
5–9° facets would come out as stacked contour terraces. Printed face-down, the face isn't flat. So it prints
**upright, standing on one flat edge**, which turns the facets into near-vertical walls built from clean perimeters.
The cost is stability: alone, a tile stands on a 4–5 mm wide footprint at roughly 30:1 height to width.

The ledger and experiments settled these points (evidence labels from `design-ledger.md`):

- **Bracing:** a lone tile, or a pair with no join, lets the top wobble. The upper-edge ripple appeared in v36,
  v37, v39, v51 and v56; E-011 broke loose with zero contact. Printing **back to back as a pair** doubles the
  footprint and lets each tile brace the other.
- **Separation:** continuous or full-height contact welds the pair (owner: v46–v48, v58 E-012, v61s E-020
  "SUPER hard"). Gaps ≤ 0.75 mm fuse (CASE-001). Small **cuttable rim joins across a 2.0 mm gap** (v70 → v75)
  are the latest topology. Owner on v70: "worked way better than the slew of recent ones". At pitch 12 it was
  "hard to separate", so v75 moved to pitch 13.
- **Face:** anything within about 1.4 mm of the skin ghosts through (v31 pads, v50 lips). Features that start or
  stop on a few layers leave lines (v41 tabs, v49/v50 pad ends), so joins are staggered with a cap on transitions
  per layer.
- **Bed edge:** a chamfer on the bed edge undercut the first layer, and four prints tore off above the brim (v73 →
  v74). The bed edge stays square.

### What v77 changes, and why

v77 is v75 plus exactly three changes. Each one is tied to a requirement and can be tested on its own (§30).

| # | Change | Requirement | Expected effect | Side effects (§33) |
|---|---|---|---|---|
| C1 | `edge_depth` 4.1 → **4.6** | §9: ≥ 1.6 mm face isolation. **v73–v76 had 1.22 mm and fail §9**; only v72 (1.2 mm skin) passed. | Isolation 1.22 → 1.72 mm (bound), 1.90 mm measured | Overall depth 11.08 → 11.58 mm. Bed footprint 351 mm² per tile (v72 recorded 301 mm²). C1 + C2 together add 4.4 g per pair against v73's slice. Side wall 0.5 mm taller, not significant at 6 in. |
| C2 | Flange 15 → **18 mm**; outer edge buried `rim/2` inside the outline | §8: tape placement slack clear of the cut join stubs (outer 2 mm) | Tape land 13.0 → **16.0 mm** for 12.7 mm tape (1.65 mm slack each side; v75 had 0.15) | More flange mass, all on hidden rear surfaces. Burying the edge also removed 4 zero-area export slivers (§23). |
| C3 | `top_closure = "gusset"` option, **default off** | §12 upper-edge stability; §35 layer uniformity | Slicer: removes a **12.2 → 9.7 s layer-time drop at Z 114.2 mm**, where the five-edge flange ends abruptly. Ties the upper rim back to the flange. | +0.8 cm³ per tile, +6 min per pair. Leaves a 19.4 mm open centre at the top edge, so it won't close the top. Grows at 45°, so it needs no support. |

Kept from v75 unchanged: facet topology (11 points, 14 facets), 1.68 mm skin (4 × 0.42 mm walls), 0.6 mm face
chamfer, 2.0 mm rim, the square bed edge, and the whole join system (36 per pair, 2.0 mm gap, 1.0 × 0.6 mm roots,
0.6 × 0.4 mm necks, ≤ 2 root and ≤ 3 total transitions per layer).

Removed from the source as dead or legacy: `separated`, `wall` and `tabs` outputs, `back_edge_chamfer`,
`chamfer_bed_edge` (the square bed edge is now fixed behaviour) and `include_top_flange` (a full top band starts as
an unsupported bridge, so it isn't offered).

### Why this configuration meets the requirements

- **Visible face (§3–4):** same facets and skin as the v58/v70 faces that printed clean. Nothing rear is closer
  than 1.6 mm (proved in the SCAD, measured on the mesh). Joins sit in the solid rim, 3.7 mm behind the face plane.
- **Mounting (§8, §18):** a continuous five-edge flange, 18 × 1.2 mm, that is one flat plane: 5,777 mm² at Z = 0
  and no stray faces just above it. The 16 mm tape land is 100% solid on 48k samples. Mounting load runs into the
  rim walls rather than into the skin.
- **Separation (§15):** joins are cut, not snapped. The neck is the only thin section, mid-gap, so where it fails
  doesn't depend on how hard the parts bonded. A cut stub reaches at most 1.2 mm past the back plane, at the outer
  rim and outside the tape land. The guard requires foam tape ≥ 1.5 mm (the default assumes 1.6 mm) so the stubs
  never touch the wall.
- **Multi-tile (§13):** the pair *is* the multi-tile unit. `chain` (3 pairs) passes bed fit and transition caps
  but stays **experimental**. Earlier strips printed noticeably worse with two objects on the plate (E-004, layer
  time 35 s vs 18 s) and ridged on a shared plate (E-021/22, unresolved).

---

## C. Parameter table

| Parameter | Default | Units | Purpose | Valid range (enforced) | Dependencies |
|---|---|---|---|---|---|
| `size_in` | 6 | in | Corner-to-corner width | 3–10 (10 in fails join pitch and bed fit) | R, AP, joins, bed fit |
| `edge_depth` | 4.6 | mm | Side-wall depth at perimeter | > 0; isolation ≥ 1.6 | face_isolation, root_face_distance, depth |
| `rim` | 2.0 | mm | Solid perimeter wall width; joins live here | 1.5 – AP/4; > join insets | tape_land, joins, cavity |
| `skin` | 1.68 | mm | Face skin (depth-wise) | ≥ 3 × line_width; isolation ≥ 1.6 | face_isolation |
| `relief_scale` | 1.0 | – | Facet relief multiplier | > 0 | depth, isolation proof needs relief ≥ 0 |
| `front_chamfer` | 0.6 | mm | Face-perimeter chamfer (not bed edge) | 0 – min(rim, edge_depth); root distance ≥ 1.6 | root_face_distance |
| `flange_width` | 18 | mm | Rear tape band width from outline | > rim, ≤ AP/2; land ≥ tape + 2 × margin | tape_land, gusset |
| `flange_t` | 1.2 | mm | Flange thickness | ≥ 2 layers and ≥ 2 lines; > root_overlap | face_isolation |
| `top_closure` | none | – | `none` / `gusset` | enum | gusset_angle |
| `gusset_angle` | 45 | ° | Gusset lower-edge angle above horizontal | 40–90 | gusset_center_gap |
| `tape_width` | 12.7 | mm | Foam tape width | land ≥ width + 2 × margin | – |
| `tape_thickness` | 1.6 | mm | Thinnest tape allowed | ≥ stub + clearance (1.5) | stub guard |
| `tape_margin_min` | 1.0 | mm | Placement slack per side | – | tape land guard |
| `min_face_isolation` | 1.6 | mm | Spec §9 limit | – | isolation guards |
| `pair_gap` | 2.0 | mm | Back-to-back gap | 1.0–3.0 (CASE-001) | stub, pair_width, neck |
| `root_width` / `root_height` | 1.0 / 0.6 | mm | Join root | root_width > neck_width, ≤ 1.2; height ≤ 1, whole layers | events, rim fit |
| `neck_width` / `neck_height` / `neck_length` | 0.6 / 0.4 / 0.4 | mm | Cuttable neck | width ≥ line; height ≥ layer, ≤ root; length < gap | stub |
| `root_overlap` | 0.3 | mm | Root embed into rim | 0 – flange_t | root_face_distance |
| `tab_pitch` | 13 | mm | Max join spacing | actual pitch ≤ value; transition caps | N joins, events |
| `layer_height` / `first_layer_height` | 0.2 / 0.2 | mm | Must match slicer | > 0; roots/necks whole layers | join snapping |
| `root_event_limit` / `all_event_limit` | 2 / 3 | count/layer | Face-line guard | – | joins |
| `batch_*_event_limit` | 6 / 9 | count/layer | Same for chain | chain_count ≤ 3 at defaults | chain |
| `chain_count` / `chain_gap` | 3 / 6 | – / mm | Pairs per plate (experimental) | integer 1–8; events; bed fit | layout |
| `bed_width/depth/height` | 256 | mm | Build volume | > 0 | fit guard |
| `planned_brim` / `bed_margin` | 10 / 5 | mm | Fit allowances (conservative; slice uses 5.5 mm brim) | ≥ 0 | fit guard |

---

## D. Validation report

**OpenSCAD 2026.10.11, Manifold backend.** All 7 outputs and both gusset variants render with exit 0 and no warnings.
Echo for the default:

```
v77 | pair | tile 152.4 x 131.982 x 11.584 mm
Face isolation 1.72 mm (min 1.6) | join roots to face 3.7 mm
Flange 18 x 1.2 mm | tape land 16 mm for 12.7 mm tape | top_closure none
Joins 36/pair, max pitch 12.8441 mm, worst stub 1.2 mm | transitions/layer root 2, all 3
Plate footprint 45.1681 x 172.4 mm with brim | height 131.982 mm
```

**Guards tested by breaking them.** Each of these failed with its own message: `edge_depth=4.1` (isolation 1.22),
`flange_width=15` (land 13 < 14.7), `pair_gap=0.5`, `tape_thickness=1.0`, `size_in=11`, `skin=1.0`,
`chain_count=4` (transition burst), `tab_pitch=6`, `gusset_angle=30` and an unknown output.

**Mesh checks** (`validate_v77.py`, 22/22 pass):

| Check | Result |
|---|---|
| Watertight / winding / degenerate faces | single, pair, installed and gusset: all watertight, consistent, 0 zero-area faces |
| Connected solids | single 1, installed 1, pair 1 (joined by 36 joins, genus 35); joins total 27 mm³ |
| Bounding box | 152.400 × 131.982 × 11.584 mm (tile); pair 25.168 × 152.4 × 131.982 |
| Volume | 35,970 mm³ per tile; 71,967 mm³ per pair |
| Bed contact | tile 351 mm², pair 701 mm²; ≥ 95% of the Z = 0.3 section (no undercut); 1 first-layer island |
| Mounting plane | 5,777 mm² coplanar at Z = 0; 0 down-facing faces just above it |
| Tape land | 16.0 mm; 100.00% solid over 48,133 samples on the five flanged edges |
| Face isolation | SCAD proof: ≥ 1.72 mm everywhere (relief ≥ 0). Mesh: **min 1.905 mm** vertical (37,207 rays), **1.904 mm** true 3-D |
| Build volume | pair + 10 mm brim + 5 mm margin fits 256³ (45 × 172 × 132 mm) |

**Lab checks** (`lab inspect`, 0.4 nozzle): closed, 1 piece, centre of mass at 63.9 mm. Two warnings, both inherited
from v75 and left alone under change control:

- `overhang-flip` at 65.75 mm: the facets lean out below mid-height and back above it. This is the established
  facet pattern; v58 faces printed clean with it.
- `parts-too-close` 0.4 mm: in the top layer of each root, the two root arms end 0.4 mm apart. The slicer will
  probably fill that gap, so the effective neck may be 3 layers instead of 2. This is a candidate cause of
  "hard to separate" (v74/v75) and is the first separation experiment below.

**Slicer** (Bambu Studio CLI via `lab slice`; v74 project settings unchanged: X2D 0.4, v70 process, Kexcelled K5
Matte Terracotta 210 °C, Textured PEI, 5.5 mm outer brim):

| | Time | Filament | Layers | Joins printed |
|---|---|---|---|---|
| v77 (default) | 3 h 56 min | 83.07 g | 660 | 65 / 660 layers cross the gap |
| v77 + gusset | 4 h 02 min | 84.77 g | 660 | – |
| v73 (reference, from registry) | 3 h 34 min | 78.7 g | 660 | 111 / 660 |

The start block matches E-022 line for line apart from the bed-mesh probe area (v73's first slice lacked it and
printed in air). Upper layer times: default 12.2 s → **9.7 s at Z 114.2** (flange end); gusset stays 12.2 → 11.6 s
all the way to Z 127.

**Not validated by any of this:** whether it prints standing up to the top, ripple, face lines, how separation feels,
how the stubs come out, tape adhesion on the printed flange, and repeatability.

### Risk register (§35)

| Risk | Cause | Expected consequence | Mitigation | Residual uncertainty | Validation required |
|---|---|---|---|---|---|
| Upper-edge ripple | Tall thin pair; top region has least bracing; flange ends abruptly at 114 mm | Ripple near the upper corners | Pair + rim joins to the top (v70); gusset option | High: persistent defect (5 versions), never single-factor tested | Exp. B: pair vs pair+gusset, same plate settings |
| Face line at 114 mm | 20% layer-time drop at the flange end | Horizontal band near the top | Gusset removes the step | Medium: the same step existed at 117 mm in v70–v75; no line was reported there, but nobody looked | Inspect Z 110–118 on Exp. A; compare with B |
| Hard separation | Neck may print as 3 layers (arms 0.4 mm apart) | Knife work > 1 min, stress whitening | Cut, don't twist; neck mid-gap | Medium (v75 at pitch 13 unprinted) | Exp. A timing; then Exp. C on neck geometry |
| Tear-off above the brim | Narrow footprint, tall part | Failed print | Square bed edge (v74), deeper footprint (C1), brim | Low to medium | Exp. A, all layers |
| Face telegraphing | Rear features near the skin | Ghost lines | ≥ 1.72 mm proven, 1.90 mm measured | Low | Raking-light inspection |
| Stub interference | Cut stubs 1.2 mm past the back plane | Tile rocks on the wall | Stubs sit outside the tape land; tape ≥ 1.5 mm guard | Low | Mount on glass with the chosen tape; check for rocking |
| Process bands | Inner/outer wall speed 250/80 = 3.1× (CASE-002 rule: ≤ 2×) | Sheen bands | Not changed here (process, not geometry) | Medium | Separate process experiment after A |
| Multi-pair plates | Longer layer times / shared plate (E-004, E-021/22) | Worse face | `chain` marked experimental | High | Only after A/B pass |

---

## E. Production-readiness assessment

| Level | Status | Evidence |
|---|---|---|
| GEOMETRICALLY VALIDATED | **Yes** | Renders, 22/22 mesh checks, guards proven to fire, isolation proved and measured |
| SLICER VALIDATED | **Yes, for X2D 0.4 / Textured PEI / v70 presets only** | Bambu Studio slice, start block verified, joins present on 65 layers |
| PHYSICALLY TESTED | **No** | No v77 print exists |
| REPEATABILITY VALIDATED | **No** | – |
| PRODUCTION READY | **No** | Requires the above |

### Path to production (one change per experiment, §30)

- **A. v77 baseline pair** (`HEX_TILE_v77_X2D_textured.3mf`, unchanged). Answers whether C1 + C2 keep v75's
  behaviour and meet §9 and §8 in print. C1 and C2 are bundled because both are spec-mandated and touch no face
  geometry, so A can't attribute a face change to either one alone. Acceptance: completes; no tear-off; face clean
  at arm's length under raking light; separation ≤ 1 min with a hobby blade, no whitening; tile sits flat on glass
  with tape. Record per §31 with `lab exp plan … --source sources/HEX_TILE_v77_X2D_textured.3mf`.
- **B. Gusset** (`top_closure=gusset`), same plate settings. Single factor: the top closure. Predicted: less
  upper-corner ripple; no band at Z 114. Make it the default only if B ≥ A on the face and the top.
- **C. Separation**, only if A is hard to cut: open the root arms so the neck stays 2 layers (`neck_length` 0.4 →
  0.8), on `release_test` coupons first.
- **Repeatability:** three consecutive good pairs of the winning configuration, same spool and setup log, before
  calling it PRODUCTION READY.
