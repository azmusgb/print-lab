# Print lab: design (24 October 2026)

**Owner's problem:** a hex wall tile for a commercial space took 58 versions (v1–v58, 218 files) and still has no
defect-free face. The AI that revised it wrote its own audit: the main failure was stacking several model and settings
changes between test prints, plus misreadings (camera fisheye read as tilt; a 0.4-nozzle print blamed on the 0.6).

**Goal:** a lab that narrows a print defect to its cause in a few controlled, cheap prints, and keeps every version's
model, slicer settings, nozzle, filament, photos and verdict together. The lab grows smarter by turning confirmed
lessons into tested code.

**For:** the owner (decisions, photos, verdicts, from the phone at the printer) and Claude Code on the Mac (analysis,
the next experiment, the new model or settings).

**First case:** the hex wall tile, from v58 and the audit's test plan.

**Not in v1:** generating new parts from a description (build123d comes later); sending prints to the printer (the X2D
stays on Bambu cloud, so the lab hands over a ready 3MF to open in Bambu Studio or Handy); retraining any model.

## What the review found (why the design looks like this)

- **The face has two kinds of facets.** In the upright print orientation, 8 of the 14 front facets point down (mild
  overhang, to -7.8°) and 6 point up (to +8.6°). They switch at about mid-height, which is where the band in the
  latest photo (IMG_0714) sits and where "mid-height lines" appeared in v53–v56 whatever the joins did. Overhang walls
  and step-in walls look different. Leaning the tile back 15° makes every facet face up (+7.2° to +23.6°). No version
  changed this; every version changed tabs, pads, seams or ribs.
- **The slicer may also change speed there.** v56 slows any layer that would take under 8 s (outer wall otherwise
  80 mm/s); as the hex narrows above its widest point, layers shorten. Never tested.
- **Nozzle and profile disagreed.** `hexagon_v56_X2D_0.6nozzle.3mf` was sliced with 0.4 nozzle profiles (0.42 mm
  lines).
- **The tent idea.** Two tiles leaned 15° against each other, backs inward, joined by fins between the backs and a
  short ridge bar, is a braced triangle (stiffer than the 1 mm back-to-back pair that wobbles), keeps every facet
  face-up, puts every contact scar on hidden backs, keeps layers long (no slowdown), and fits about 3 tents of 6"
  tiles on one plate.

These are hypotheses until coupons test them. The lab exists to test them properly.

## Principles

1. **One experimental factor per experiment.** Enforced by the Local AI server, not by the AI's good intentions.
2. **The smallest representative test.** Use the smallest test that can answer the question; full parts only through
   an override.
3. **Measure before guessing.** Geometry and sliced G-code are measured; the AI reasons over numbers.
4. **Orchestrate, don't reinvent.** Existing geometry, 3MF and slicer tools do the computing; the lab's own code is
   the experiment logic, profiles, rules and evidence.
5. **Lessons become code.** A confirmed cause becomes a rule with tests from real files, approved by the owner.
6. **The owner decides.** The AI proposes experiments, overrides and rules; only the owner approves overrides and rules.
7. **Honest confidence.** A result supports a hypothesis; it takes more evidence to call a cause proven.
8. **Keep failure evidence.** A failed tool run never publishes an artefact, but its diagnostics are always kept.

## Architecture

```
 phone ──photos, verdicts, approvals──▶ ┌────────────── Local AI (PC) ──────────────┐
                                        │ /api/lab/*   SQLite tables   DATA_DIR/lab/│
 Claude Code ──▶ print-lab engine ─────▶│ Print lab page · approvals · push · Work  │
 (Mac)           OpenSCAD (current)     └──────▲───────────────▲────────────────────┘
                 Bambu Studio CLI              │               │
                 rules + tests (git)    Bambuddy archive   X2D camera bridge (Pi)
```

- **Local AI holds every record** (source of truth) and enforces the experiment rules. The phone talks only to Local AI.
- **The engine** (`print-lab`, this repo, Python) does the work on the Mac and writes only through `/api/lab/*`,
  authenticated with the Mac key (`X-LocalAI-Mac-Key`), like the Claude board. If the PC is unreachable it queues
  uploads on disk and sends them when it answers.
- **Responsibilities:** OpenSCAD answers "what geometry was specified"; the engine answers "how is it likely to print";
  Bambu Studio answers "how will this printer slice it"; the AI answers "what should we test next"; the owner answers
  "is it good".

### Engine stack

| Layer | Choice | Notes |
|---|---|---|
| Runtime | Python 3.12 or 3.13, pinned with `uv` | Homebrew's 3.15 is too new for manifold3d wheels |
| Mesh analysis | trimesh (MIT) | normals, sections, ray thickness, mass properties, bounds |
| Booleans, coupons | manifold3d (Apache-2.0) | cutting coupons and test pieces from a model |
| Parametric source | OpenSCAD CLI, current build with the Manifold backend | installed 2021.01 is too old; version recorded per artefact |
| Slicing | Bambu Studio CLI (02.08.02.61 installed) | the only source of slicing truth; same version as manual slicing |
| Bambu project settings | read/write the 3MF's own JSON/config files directly | lib3mf does not understand Bambu's settings |
| 3MF validation | lib3mf (BSD-2) | validate what the engine writes |
| Optional analysis | phyx3d (MIT, TypeScript) behind an adapter, run as a subprocess | must pass a qualifying test first |
| Bambu CLI reference | catesworks/bambu-cli-mcp (MIT, TypeScript) | borrow ideas; every CLI call verified against 02.08 |
| Later CAD backend | build123d + build123d-mcp | not v1 |
| Avoid | MeshLib | non-commercial licence |

### Engine layout

```
print-lab/
  lab/adapters/    openscad · bambu (CLI, settings, gcode.3mf) · phyx3d (optional) · threemf (validate)
  lab/geometry/    mesh · facets · sections · thickness · orientation · coupons
  lab/analysis/    printability · surface_quality · gcode (per-layer Z, time, speeds, accel, fan, seam)
  lab/profiles/    appearance · fit · strength (defect lists, evidence checklists, coupon kinds, orientation weights)
  lab/rules/       one module per rule + its tests
  lab/experiments/ planner (one factor, smallest test, override request) · compare
  lab/api.py       client for Local AI /api/lab/*
  lab/cli.py       lab inspect | orient | coupon | slice | gcode | plan | submit | compare
  lab/mcp.py       analyze_part, recommend_orientation, generate_test, slice_test, inspect_gcode, compare_results
  tests/           pytest; fixtures from real tile versions
```

## Records (Local AI)

New SQLite tables; files (SCAD, STL, 3MF, previews, photos, frames) under `DATA_DIR/lab/`, included in Local AI's
backups. Every row has an id, `createdAt` and links to its parent rows.

| Record | Holds |
|---|---|
| Project | name; profile: purposes (appearance / fit / strength) and measured geometry traits; surface labels (A, B, C, fit); filament (Pi hub spool id); printer and nozzle |
| Version | parent version; SCAD source and parameters; slicer process and filament settings; tool versions; the **diff from its parent** (model parameters and slicer settings that changed) |
| Experiment | version; test kind (see below); question, hypothesis, prediction, "why this test"; the **experimental factor** and its values, the controlled factors, and any dependent adjustments with reasons; status; print runs; cost (time, grams) |
| Print run | id (`PR-019`), experiment, the variant it prints, artefact SHA-256, the matched printer job, start and end |
| Job | an engine tool run (OpenSCAD, Bambu Studio, analysis): command, tool version, input hashes, exit code, stdout, stderr, partial outputs, time; kept whether it succeeded or failed |
| Finding | rule id and version; severity (blocking, warning, info); location (surface, Z range, facets); why; known fix (case link) |
| Evidence | photos with their light set-up; defect marks (photo position, defect type); measurements; camera frames by Z |
| Verdict | per variant and tracked defect: fixed, better, same or worse, plus a 1–5 score; note; whether it matched the prediction |
| Hypothesis | statement, the experiments behind it, confidence: candidate → supported → reproduced → proven for this part → generalisable candidate |
| Override | the full-print request, the 7 requirements (each met or not, with evidence), owner approval and reason, outcome |
| Case | symptom, cause hypothesis and its confidence, the test, the result, what it applies to (geometry, profile), before/after evidence; indexed in memory core |
| Rule | id, version, `print-lab` commit, the case(s) it was promoted from, status (draft, approved, retired), hits and false alarms |

## Part profiles

A project's profile decides which defects matter, what evidence a print needs, what a coupon is and how orientations
are scored.

- **Purposes** (owner declares; can be several): appearance (no visible defects on A surfaces), fit (dimensions and
  clearances), strength (holds a load without cracking or creep).
- **Geometry traits** (measured): facet and overhang angles in the print orientation; wall thickness and
  height-to-thickness ratio; places where the layer outline changes suddenly; layer time by height (after slicing);
  seam candidates; bridges, islands, bed contact; centre of mass and tipping.
- **Surface labels:** A (always seen), B (sometimes), C (hidden), fit. Lab-generated SCAD labels its own surfaces;
  otherwise the AI proposes labels and the owner confirms on a coloured preview. Seams and contact scars belong on C.

| Purpose | Evidence | Coupon kind | Orientation weights (starting point) |
|---|---|---|---|
| Appearance | raking-light photos of A surfaces; camera frames to locate | slice of the A surface across the defect region | A-surface quality 40, consistency 20, stability 15, contact damage 10, bed contact 5, time 5, height 5 |
| Fit | caliper measurements at named points; test fit | fit gauge (e.g. the slot at 3 widths) | dimensional accuracy of fit surfaces 35, no supports on fit surfaces 20, stability 15, layer-direction strength 10, time 10, material 10 |
| Strength | load or flex test with a pass weight | the joint or lip alone, in 2–3 orientations | layer-direction strength 35, supports 20, stability 15, accuracy 10, time 10, material 10 |

Weights are hand-set per profile and stay fixed in v1. Results are stored per variant (e.g. 0° 2/5, 10° 4/5, 15° 5/5,
20° 4/5) and the AI can point out patterns ("quality peaks around 15° for this geometry"); it never changes weights by
itself. Revisit once there are enough results across parts.

## Experiment lifecycle

```
planned ─▶ checked ─▶ sliced ─▶ printing ─▶ awaiting verdict ─▶ done ─▶ case (if a cause is confirmed)
   │
   └─▶ blocked (says why and what would unblock it)
```

1. **Planned:** question, hypothesis, prediction, why this test, and one **experimental factor** with its values
   (e.g. orientation: 0, 10, 15, 20°). Everything else is a **controlled factor**, held at the last tested values.
   Changes forced by the factor (plate spacing after rotation, brim, contact structure) are **dependent adjustments**,
   each with its reason; they are not separate hypotheses.
2. **Checked:** the engine runs every approved rule; the server confirms that only the named factor and its declared
   dependent adjustments differ from the last tested version, and that the test kind is allowed (below). A blocking
   finding stops it here.
3. **Sliced:** Bambu Studio makes the 3MF. Each variant gets a print run id; the experiment id, print run id and
   artefact hash go into the 3MF metadata, a manifest JSON beside it, a G-code comment where possible, and the file
   name (`hex-tile_E012_PR019.3mf`). Per-layer G-code data and cost are attached.
4. **Printing:** matched to the real printer job by, in order: 3MF metadata or manifest, the artefact hash, the file
   name, then a manual link. Camera frames at the marked heights and every 10 mm.
5. **Awaiting verdict:** push and the Workshop display ask for photos; the profile's checklist guides them; the owner
   marks defects and gives a verdict per tracked defect.
6. **Done:** `compare_results` lines up the marks with geometry and per-layer data and reports correlation, e.g.:

   ```
   Visible defect          Z ≈ 82 mm
   Geometry event          facet orientation switch, Z = 81.9 mm
   Slicer events ±5 mm     outer-wall speed: none · fan: none · layer-time jump: none · seam move: none
   Geometry correlation    strong        Slicer correlation    weak
   ```

   It records whether the prediction held and moves the hypothesis up the confidence ladder: one passing test →
   supported; a second independent pass (another test kind or size) → reproduced; passing on the real part → proven for
   this part; the same lesson passing on a different geometry → generalisable candidate.

### The smallest representative test, and overrides

Test kinds, smallest first: `section_coupon` (a slice of a surface across the defect region), `orientation_coupon`
(the same slice at several angles on one plate), `fit_coupon`, `joint_coupon`, `height_strip` (a narrow full-height
strip, for effects that build with height), `scaled_part`, `full_part`. Each profile names the kinds that can answer
its defects. The rule is: **use the smallest kind that can answer the question.** `scaled_part` and `full_part` need
an override, which needs all of:

1. **No smaller test can show the effect:** it names one of wobble or ripple at height; whole-part warping; pairs or tents
   separating (or not); bed fit, brim or layout; total print time; tape or mounting. Surface texture, lines, ghosting,
   seams and stringing always start on a coupon.
2. Every other change in the version has passed on a smaller test.
3. Hypothesis, prediction and what will be measured are written before printing.
4. Sizes go 3" → 6" → 10"; skipping a step names the effect that only shows at the larger size.
5. Cost shown: hours, grams, past failures at this size.
6. **The owner approves**; the AI can only request. The reason is stored.
7. The outcome is recorded; the page shows the override success rate against changes tested small first.

## Rules

A rule is a Python module with test cases from real project files. A finding carries severity, location, why and the
known fix. A blocking finding stops an experiment at "checked".

**Seed rules (v1):**

| Rule | Severity | Origin | Checks |
|---|---|---|---|
| `overhang-flip-on-A` | warning | this review | A-surface facets switch between facing down and facing up in the print orientation |
| `layer-shape-jump` | warning | audit lesson | the layer outline changes abruptly (tabs, pad ends, joins starting mid-height) |
| `feature-below-line-width` | blocking | audit mistake 11 | a feature thinner than one printed line |
| `slowdown-on-A` | warning | this review | sliced layer time crosses the slowdown threshold while printing an A surface |
| `ghost-gap` | warning | v31–v33 | an internal feature closer than 1.5 mm behind a thin skin |
| `fused-gap` | warning | v42–v46 | a gap between parts small enough to squash shut |
| `nozzle-mismatch` | blocking | audit mistake 10 | file name, slicer profile and the printer's nozzle disagree |
| `bed-fit` | blocking | audit mistake 6 | part plus brim exceeds the plate |
| `stacked-changes` | blocking | audit mistake 12 | a version changes more than one experimental factor since the last test, beyond declared dependent adjustments (also enforced by the server) |

### Learning

- **Cases first:** every done experiment whose hypothesis reached *supported* or higher becomes or updates a case. Most
  lessons stay cases: searchable, cited, not code.
- **Promote a case to a rule** only when it is worth automating: the check can be computed from the model, settings or
  G-code, and the case is *proven for this part* or better. Claude proposes "Promote case → rule?" as a pull request in
  `print-lab`; its tests must flag the original defect's files and pass the clean ones. It shows in Print lab with the
  proving photos and merges only after the owner approves.
- **Rule scores:** each finding is later marked useful or false alarm by the verdict; a rule wrong more than half the
  time over 10 or more findings is proposed for retirement.
- **Case search:** `analyze_part` searches cases first, by defect type, profile and geometry features.

## Print lab page (Local AI)

A registry view `printLab`, a Projects tab "Print lab". Uses Local AI's `--ds-*` tokens and Figtree, dark and light.
Phone first.

- **Project page, in order:** name and profile; **the open question** set large as a sentence, with its status
  ("Coupon printing · 38 min left") and a short **Why this test?** (the measured reason, e.g. "The face switches from
  slight overhang to upward-facing near Z 82 mm; no slicer speed or fan change happens there.") with Show evidence; **the evidence wipe** (before and after photos overlaid, a drag handle between
  them, defect marks pinned to both) — the page's one memorable element; verdict buttons (Fixed, Better, Same, Worse)
  only when a verdict is due; Mark a defect; the size ladder (Coupon, 3", 6", 10"); the notebook (one row per
  experiment, spine in the filament's colour); what the checks found.
- **Desktop:** notebook on the left (~360 px), question, wipe and verdict on the right.
- **Colour:** only one addition to the design system: each experiment's accent is its spool's real colour (Pi hub).
  Verdict colours are fixed: good = fixed, attention = better, muted = same, bad = worse.
- **Override sheet:** "Print the full 6" pair?" with the 7 requirements, each met or not with evidence; cost above
  **Approve full print**, which stays disabled until all but the owner's approval are met.
- **New rule sheet:** the rule in plain words, the photo that proved it, the tests it passes, **Add rule** / **Not yet**.
- **Photos:** taken from the phone with the profile's checklist on screen (raking light at a low angle from one side,
  fixed distance, reference card in frame); tap to mark a defect and pick its type from the profile's list.
- **Words:** buttons say what happens (Record verdict, Print the coupon, Approve full print). Empty: "No open question.
  Ask the lab what to test next." Errors say the cause and the fix ("The slicer couldn't open v58: 2 non-manifold
  edges near the top-left pad. Regenerate it.").

## Integrations

| Source | Use |
|---|---|
| Bambuddy archive (Pi) | a print whose file name holds the experiment id moves it to printing; its end moves it to awaiting verdict; grams and time; manual link as fallback |
| X2D camera bridge (Pi) | frames during lab prints at marked heights and every 10 mm; for locating, never for judging (fisheye) |
| Push and Inbox | "Coupon E-012 is done: rate it", override requests, new rules |
| Workshop display | "Lab print done: rate it on your phone" through display messages |
| Memory core (#376) | experiments, verdicts and cases in the journal; the lab's own case search until #376 lands |
| Claude board | the engine posts its proposed next experiment as a finding |
| Work timeline | each experiment is a run of kind "lab" |
| Agent World | lab prints show in the Workshop garage; a Lab district later (not v1) |

## Errors

- A failed OpenSCAD or Bambu Studio run blocks the experiment and shows the tool's error in plain words. **No partial
  output is ever published as a valid artefact, but the failure evidence is always kept** as a Job record: command,
  tool version, input hashes, exit code, stdout, stderr, the partial outputs that exist, and when it failed (with
  "View full log").
- The PC unreachable: the engine queues uploads and retries.
- A print that can't be matched by metadata, hash or file name: the page offers "This is the print" on the experiment.
- An analysis provider that fails (e.g. phyx3d): its findings are left out and marked missing; the core analysis runs.

## Testing

- **Engine (pytest):** fixtures from real tile versions (v30, v53, v56, v57, v58). `overhang-flip-on-A` finds the
  switch at Z ≈ 82 mm on v56; `feature-below-line-width` catches v57's joins; the G-code reader is tested on a real
  sliced v56; coupon generation produces closed, printable meshes; every rule has a flagged and a clean case.
- **Local AI:** unit tests for `/api/lab/*`, the one-factor check, test-kind policy and the override requirements;
  a browser suite `print-lab-ui.mjs` (plan, verdict, defect marking, override and rule sheets; axe; visual baselines).
- **End to end:** the engine against a throwaway Local AI server, with the tile and a fake print event.
- **phyx3d qualifying test:** on v56 it must report the same facet switch height as `facets.py` (±2 mm) before its
  findings are shown.

## Build order

Each stage is usable on its own; the tile goes through the lab from stage 1.

| # | Stage | Delivers |
|---|---|---|
| 1A | Useful engine (no Local AI yet) | `lab inspect / orient / coupon / slice / gcode` on the real tile; four checks (mesh validity, facet orientation, minimum feature width, bed fit); experiments as local JSON files; Job records for every tool run. **EXP-001:** does orientation affect the band? An orientation coupon plate at 0, 10, 15 and 20°, everything else controlled. **EXP-002:** does slicer slowdown affect the band? At EXP-001's best angle: normal slowdown vs slowdown off |
| 1B | Records and enforcement | `/api/lab/*` and the Local AI tables; the server checks (one factor, test kind, overrides); the local JSON experiments imported; the remaining 5 seed rules |
| 2 | Print lab page | phone verdicts, defect marking, the evidence wipe, why this test, ladder, notebook, override approvals |
| 3 | Learning and cases | the confidence ladder, cases, case search, promote case → rule as PRs, rule scores, memory-core indexing |
| 4 | Print links | print run ids in 3MF metadata and manifests, Bambuddy matching (metadata, hash, name, manual), camera frames, display and push prompts, Work runs |
| 5 | Extras | phyx3d adapter and qualifying test, a weekly check for new Bambu Studio / phyx3d / bambu-cli-mcp releases (posted to the Claude board), the tent version of the tile designed in the lab |

1A comes first so the geometry and Bambu automation are proven on the real tile before any API is built around them.

## Decisions taken

| # | Decision | Chosen |
|---|---|---|
| D1 | First scope | the lab first; generating parts later |
| D2 | Who drives | Claude Code on the Mac; the lab itself enforces the rules |
| D3 | Test size | the smallest representative test; scaled and full parts need a 7-requirement override the owner approves |
| D4 | Evidence | phone raking-light photos decide; camera frames locate |
| D5 | Profiles | purpose + measured geometry decide defects, evidence, coupons and scoring |
| D6 | Knowledge | rules in code with tests; AI review on top; lessons become approved rules; case library |
| D7 | Where | engine in this repo on the Mac; records and the owner's page in Local AI |
| D8 | v1 scope | everything, delivered in the 5 stages above |
| D9 | Engine approach | orchestrate trimesh, manifold3d, OpenSCAD, Bambu Studio; phyx3d optional behind an adapter |
| D10 | Repo | new private repo `azmusgb/print-lab`; Local AI knows only the `/api/lab/*` contract |
| D11 | Experiment unit | one experimental factor (with values), controlled factors, and declared dependent adjustments |
| D12 | Confidence | candidate → supported → reproduced → proven for this part → generalisable candidate |
| D13 | Knowledge growth | results become cases; only proven, computable lessons are promoted to rules (owner-approved) |
| D14 | Profile weights | hand-set and fixed in v1; results recorded, never auto-tuned |
| D15 | Failures | no partial artefacts published; every tool run's diagnostics kept |
| D16 | Print identity | experiment and print run ids in 3MF metadata, manifest, G-code comment and file name; matched in that order, then manual |
