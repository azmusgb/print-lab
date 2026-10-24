# Print lab Stage 1A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A working `lab` command on the Mac that inspects, checks, cuts coupons from, slices and reads the G-code of
the real hex tile, ingests its past revisions into a graded history, and produces the EXP-001 print file.

**Architecture:** A Python package `lab/` in `~/dev/print-lab` that orchestrates existing tools: OpenSCAD renders,
trimesh and manifold3d measure and cut, Bambu Studio's CLI slices, and small modules of our own turn their output into
findings, experiments and history. No Local AI, API or UI in this stage; experiments and history are JSON files in the
repo's `projects/` folder. Every external tool run is a recorded Job.

**Tech Stack:** Python 3.12 (pinned with `uv`), trimesh, manifold3d, numpy, shapely, pytest; OpenSCAD (current
snapshot, Manifold backend); Bambu Studio 02.08.02.61 CLI.

**Spec:** `docs/superpowers/specs/2026-10-24-print-lab-design.md` (Stage 1A row of the build order; sections Engine
stack, Engine layout, Rules, Experiment lifecycle, Past revisions, Errors, Testing).

## Global Constraints

- Python 3.12 via `uv` (`uv python pin 3.12`); never Homebrew's 3.15.
- Bambu Studio CLI: `/Applications/BambuStudio.app/Contents/MacOS/BambuStudio`, version `02.08.02.61`; override with
  `LAB_BAMBU`. It is the only source of slicing truth; the lab never computes walls, cooling or time itself, except
  the per-layer estimate read from G-code.
- OpenSCAD: current snapshot (`brew install --cask openscad@snapshot`), run with `--backend=manifold`; override with
  `LAB_OPENSCAD`. The installed `OpenSCAD-2021.01.app` is not used.
- Printer: Bambu Lab X2D, plate 256 × 256 mm, max height 256 mm (the stricter of its two extruders), 10 mm brim.
- One printed line: 0.42 mm for a 0.4 nozzle, 0.62 mm for a 0.6 nozzle.
- Experiment ids `E-001…`, print run ids `PR-001…`; print file name `hex-tile_E001_PR001.3mf`; the ids and the
  artefact SHA-256 go into the 3MF as `Metadata/print_lab.json` and into a `manifest.json` beside it.
- One experimental factor per experiment (with values), controlled factors, declared dependent adjustments.
- No partial output is ever published as a valid artefact; every tool run's diagnostics are kept as a Job record.
- Raw history evidence (chat exports, raw file copies) stays out of git (`history/*/chat/`, `history/*/raw/`).
- Words shown to the owner follow the spec's writing rules: plain words, the cause and the fix.

## Review Focus

- **A Bambu project with several plates and objects** (every tile 3MF has 3 plates and up to 6 objects): commands
  that take a 3MF must name the object (`--object` substring match) or list them and refuse to guess.
- **A non-watertight or multi-body mesh** (e.g. `export-13.stl`): `inspect` reports it as a finding and still runs the
  other measurements; `coupon` refuses to cut it and says why.
- **A missing or wrong-version tool**: running without OpenSCAD or Bambu Studio, or with another version, stops with
  the install command or the version found, and the failed Job is still written.
- **File names with spaces, `@`, `–` and non-ASCII** (the preset JSONs): every subprocess call passes paths as list
  arguments, and the history inventory reads them.
- **Unrelated projects with the same version numbers in one folder** (`parametric_faceted_hex_wall_tile_mount_v31…`
  next to `hex_wall_tile_v31.scad`): history groups by lineage stem first, then version, so they never merge.

---

## File structure

```
pyproject.toml                 uv project; console script `lab = lab.cli:main`
lab/__init__.py
lab/jobs.py                    run_tool(): one external command -> Job record (kept on success and failure)
lab/findings.py                Finding dataclass + severity ordering
lab/adapters/openscad.py       find + render SCAD -> STL
lab/adapters/bambu.py          find CLI, read/patch 3MF settings, list objects, slice, extract plate G-code
lab/adapters/threemf.py        load a named object from a 3MF; write a 3MF with Metadata/print_lab.json
lab/geometry/mesh.py           load_mesh(), MeshFacts
lab/geometry/facets.py         front facets, elevations, switch heights
lab/geometry/sections.py       per-layer outline stats, outline jumps, thin-feature scan
lab/geometry/orientation.py    lean(), score_orientations()
lab/geometry/coupons.py        height_strip(), plate_layout()
lab/analysis/gcode.py          per-layer Z, time estimate, outer-wall speed, fan, seam
lab/checks/__init__.py         run_checks() over the four Stage 1A checks
lab/checks/mesh_validity.py
lab/checks/overhang_flip.py    rule `overhang-flip-on-A`
lab/checks/feature_width.py    rule `feature-below-line-width`
lab/checks/bed_fit.py          rule `bed-fit`
lab/checks/nozzle_mismatch.py  rule `nozzle-mismatch` (needed by history and slice)
lab/experiments.py             Experiment model, one-factor check, ids, save/load
lab/history/inventory.py       fingerprints, lineage stems, version guesses, duplicates
lab/history/revisions.py       per-revision facts (SCAD params, mesh facts, 3MF settings)
lab/history/lineage.py         transitions, diffs, evidence grades
lab/history/audit.py           audit report text from history JSON + outcomes
lab/cli.py                     argparse front end
projects/hex-tile/             project folder: history/, experiments/, prints/, jobs/
tests/fixtures/hex/            copies of real tile files (listed in Task 1)
tests/...                      one test module per lab module
```

---

### Task 1: Project scaffold, tools and fixtures

**Files:**
- Create: `pyproject.toml`, `lab/__init__.py`, `tests/conftest.py`, `tests/test_tools.py`, `tests/fixtures/hex/*`,
  `README.md`

**Interfaces:**
- Produces: `tests/conftest.py` fixtures `hex_dir: Path` (= `tests/fixtures/hex`) and markers `slow` (needs OpenSCAD
  or Bambu Studio), registered in `pyproject.toml`.

- [ ] **Step 1: Install tools**

```bash
brew install uv && brew install --cask openscad@snapshot
cd ~/dev/print-lab && uv init --package --name lab --python 3.12 . && uv python pin 3.12
uv add trimesh manifold3d numpy shapely scipy networkx && uv add --dev pytest
```

- [ ] **Step 2: Copy fixtures** from `~/Downloads` into `tests/fixtures/hex/`: `hex_pair_v53_6in.stl`,
  `hex_pair_v47_6in.stl`, `hex_tile_v31_6in.stl`, `hex_tile_v33_6in.stl`, `hex_wall_tile_v57.scad`,
  `hexagon_v56_X2D_0.6nozzle.3mf`, `hexagon_v57_X2D_0.4nozzle.3mf`, `hexagon_v58_X2D_0.6nozzle.3mf`,
  `Hex Tile v55 0.20mm @BBL X2D.json`. **Prerequisite (owner):** download `hex_wall_tile_v58.scad` and
  `hexagon_v58_X2D_0.4nozzle.3mf` from the chat session into `~/Downloads`, then copy them too. Until then, tasks that
  need v58 at 0.4 skip with the message "v58 0.4 files not downloaded yet".

- [ ] **Step 3: Write `tests/test_tools.py::test_tools_present`** (marked `slow`): asserts the OpenSCAD binary reports
  a version starting with `2025` or later and the Bambu binary's `--help` first line contains `02.08.02.61`.

- [ ] **Step 4: Run** `uv run pytest -q` → Expected: `1 passed` (or skipped without `-m slow`).

- [ ] **Step 5: Commit** `git add -A && git commit -m "Scaffold print-lab: uv project, tools, real tile fixtures"`

### Task 2: Jobs and findings

**Files:**
- Create: `lab/jobs.py`, `lab/findings.py`, `tests/test_jobs.py`

**Interfaces:**
- Produces: `run_tool(args: list[str], *, inputs: list[Path], outputs: list[Path], jobs_dir: Path, tool: str,
  tool_version: str | None = None, timeout: int = 1800) -> Job`;
  `Job(id: str, tool, tool_version, command: list[str], input_sha256: dict[str,str], exit_code: int, stdout: str,
  stderr: str, outputs_present: list[str], ok: bool, started: str, ended: str)`, written to `jobs_dir/<id>.json`
  whether it succeeded or failed. `ok` is `exit_code == 0` and every declared output exists.
- Produces: `class LabToolError(Exception)` with `.job`, raised by adapters when `job.ok` is false.
- Produces: `Finding(rule: str, severity: Literal["blocking","warning","info"], where: str, why: str, fix: str,
  data: dict)`; `worst(findings) -> str | None`.

- [ ] **Step 1: Write failing tests** `test_job_success_written` (runs `["/bin/echo","hi"]`, asserts `ok`, stdout
  `"hi\n"`, JSON file exists), `test_job_failure_kept` (runs `["/bin/sh","-c","echo bad >&2; exit 3"]`, asserts
  `ok is False`, `exit_code == 3`, stderr `"bad\n"`, JSON exists), `test_missing_output_not_ok` (declared output that
  is never created → `ok is False`, `outputs_present == []`), `test_paths_with_spaces` (input file
  `"Hex Tile v55 0.20mm @BBL X2D.json"` copied to tmp is hashed and passed as one argument to `/bin/cat`).
- [ ] **Step 2: Run** `uv run pytest tests/test_jobs.py -v` → FAIL (module missing).
- [ ] **Step 3: Implement** with `subprocess.run(args, capture_output=True, text=True, timeout=...)`; id =
  `job-<UTC yyyymmddThhmmss>-<4 hex>`; never `shell=True`.
- [ ] **Step 4: Run** → 4 passed.
- [ ] **Step 5: Commit** `"Jobs: every tool run kept as a record, success or failure"`

### Task 3: OpenSCAD and Bambu adapters

**Files:**
- Create: `lab/adapters/openscad.py`, `lab/adapters/bambu.py`, `lab/adapters/threemf.py`,
  `tests/test_adapters.py`

**Interfaces:**
- Consumes: `run_tool`, `LabToolError` (Task 2).
- Produces:
  - `openscad_binary() -> tuple[Path, str]` (path, version); raises `LabToolError`-free `FileNotFoundError` with
    text `"OpenSCAD not found. Install it: brew install --cask openscad@snapshot"`.
  - `render(scad: Path, out_stl: Path, defines: dict[str, float|int|str|bool], jobs_dir: Path) -> Job` (adds
    `--backend=manifold`, `-D k=v` per define).
  - `bambu_binary() -> tuple[Path, str]`; error text names the expected path and version `02.08.02.61`.
  - `read_settings(path_3mf: Path) -> dict` (parsed `Metadata/project_settings.config`).
  - `list_objects(path_3mf: Path) -> list[ObjectInfo]` with `ObjectInfo(id: str, name: str, plate: int)` from
    `Metadata/model_settings.config`.
  - `load_object(path_3mf: Path, name_contains: str) -> trimesh.Trimesh` in `threemf.py`; raises `ValueError` listing
    the object names when zero or several match.
  - `write_print_3mf(base_3mf: Path, meshes: list[tuple[str, trimesh.Trimesh, tuple[float,float]]], out: Path,
    meta: dict) -> str` (returns SHA-256): keeps the base project's `Metadata/project_settings.config`, replaces the
    model with the given named meshes placed at (x, y) on plate 1, adds `Metadata/print_lab.json` = `meta`.
  - `slice_3mf(path_3mf: Path, out_dir: Path, plate: int, jobs_dir: Path) -> Path` → path of the sliced
    `.gcode.3mf`; `extract_gcode(sliced: Path, plate: int) -> str`.

- [ ] **Step 1: Write failing tests**: `test_read_settings_v56` (`nozzle_diameter == ["0.4","0.4"]`,
  `outer_wall_line_width == "0.42"`), `test_list_objects_v57` (names include `hex_pair_v57_3in`, `_6in`, `_10in`),
  `test_load_object_ambiguous` (`"hex_pair"` raises `ValueError` whose message lists the names),
  `test_load_object_6in_watertight` (v57 0.4, `"6in"` → watertight mesh, extents ≈ 22.2 × 152.4 × 132.0 ± 0.5 in
  some axis order), `test_write_print_3mf_roundtrip` (write two box meshes with `meta={"experiment_id":"E-001"}`,
  re-open: `print_lab.json` equal, two objects, settings file byte-identical to the base),
  `test_missing_openscad_message` (with `LAB_OPENSCAD=/nonexistent` the error text contains `brew install --cask
  openscad@snapshot`), slow `test_render_cube` (renders `cube(10);` → STL extents 10 × 10 × 10, Job ok), slow
  `test_slice_v57_3in` (plate 1 of v57 0.4 → `.gcode.3mf` exists, `extract_gcode` contains `; CHANGE_LAYER`).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Slice command: `[bambu, "--slice", str(plate), "--outputdir", str(out_dir),
  "--export-3mf", "<stem>.gcode.3mf", str(path_3mf)]`; read G-code from `Metadata/plate_<n>.gcode` in the result.
  3MF reading with `zipfile` + `xml.etree`; meshes via `trimesh.load(..., force="scene")` filtered by object name.
- [ ] **Step 4: Run** `uv run pytest tests/test_adapters.py -v -m "slow or not slow"` → all pass.
- [ ] **Step 5: Commit** `"Adapters: OpenSCAD render, Bambu Studio settings, objects and slicing, 3MF in and out"`

### Task 4: Mesh facts, facets and sections

**Files:**
- Create: `lab/geometry/mesh.py`, `lab/geometry/facets.py`, `lab/geometry/sections.py`, `tests/test_geometry.py`

**Interfaces:**
- Produces:
  - `load_mesh(path: Path, object: str | None = None) -> trimesh.Trimesh` (STL directly; 3MF via `load_object`).
  - `mesh_facts(m) -> MeshFacts(extents: tuple, volume_cm3: float, area_cm2: float, watertight: bool, bodies: int,
    bed_contact_mm2: float, com_z: float)`. Print orientation = as stored (Z up, bed at min Z).
  - `front_facets(m, max_tilt_deg: float = 25.0) -> list[Facet]` with `Facet(normal, area_mm2, centroid_z,
    elevation_deg, side: "+x"|"-x"|"+y"|"-y")`: front directions are ± the thinnest horizontal axis of the bounding
    box; a face is a front facet when its normal is within `max_tilt_deg` of one of them. Coplanar triangles are
    merged into one facet (`trimesh.graph.facets` plus single triangles).
  - `facet_switches(facets) -> list[Switch]` with `Switch(side, z_mm, down_area_mm2, up_area_mm2)`: heights where,
    on one side, the area-weighted facets change from elevation < −0.5° below to > +0.5° above (or the reverse).
  - `layer_outlines(m, layer_h: float = 0.2) -> list[Layer]` with `Layer(z, perimeter_mm, area_mm2, islands)`.
  - `outline_jumps(layers, min_jump_mm: float = 30.0) -> list[tuple[float, float]]` (z, perimeter change).
  - `thin_regions(m, line_w: float, layer_h: float = 0.2) -> list[tuple[float, float]]` (z, area_mm2 of material
    that disappears when each layer polygon is eroded by `line_w/2` then dilated back).

- [ ] **Step 1: Write failing tests**: `test_mesh_facts_v53` (6" pair STL: watertight, 1 body, extents contain 132.0
  ± 0.5 as Z), `test_front_facets_both_sides_v53` (sides found are the two ± directions of the thin axis; each side
  ≥ 10 facets), `test_facet_switch_near_mid_height_v53` (each side has a switch with `55 <= z <= 77` for the 132 mm
  pair), `test_synthetic_switch` (a 2-facet test wall, lower facet tilted −5°, upper +5°, joined at z = 10 → one
  switch at 10 ± 0.2), `test_outline_jump_v53_mid` (≥ 1 jump with `60 <= z <= 72`, the v53 join start),
  `test_no_outline_jumps_v47_above_5mm` (v47 6" pair: no jump above z = 5), `test_thin_regions_v57` (v57 0.4 6" pair:
  thin area > 0 for `line_w=0.42` in ≥ 50 % of layers above z = 1) and `test_thin_regions_clean_box` (a 10 mm box →
  none).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** with `m.section_multiplane` + `shapely` (`unary_union`, `buffer`).
- [ ] **Step 4: Run** → pass.
- [ ] **Step 5: Commit** `"Geometry: mesh facts, front facets and switch heights, per-layer outlines, thin features"`

### Task 5: The four Stage 1A checks and nozzle mismatch

**Files:**
- Create: `lab/checks/__init__.py`, `lab/checks/mesh_validity.py`, `lab/checks/overhang_flip.py`,
  `lab/checks/feature_width.py`, `lab/checks/bed_fit.py`, `lab/checks/nozzle_mismatch.py`, `tests/test_checks.py`

**Interfaces:**
- Consumes: Task 4 functions, `read_settings`, `Finding`.
- Produces: `run_checks(m: trimesh.Trimesh, *, nozzle: float, settings: dict | None = None,
  file_name: str | None = None) -> list[Finding]`; each check is `check(m, ctx) -> list[Finding]` with
  `ctx = CheckContext(nozzle, line_w, settings, file_name)`; `line_w` = 0.42 for 0.4, 0.62 for 0.6.
  Rule ids and severities exactly: `mesh-validity` (blocking when not watertight or bodies > 2), `overhang-flip-on-A`
  (warning), `feature-below-line-width` (blocking), `bed-fit` (blocking), `nozzle-mismatch` (blocking).
  `bed-fit` adds 10 mm brim on every side and checks the footprint, rotated by the object's placement, against
  256 × 256 and height ≤ 256. `nozzle-mismatch` compares a `0.4|0.6` in the file name, `nozzle_diameter` and the
  line width in settings.
- Every finding's `why` and `fix` are plain sentences, e.g. for `feature-below-line-width`: why "Parts of this model
  are thinner than one printed line (0.42 mm), so the slicer will leave them out or print them as nubs.", fix "Make
  them at least 0.45 mm wide for a 0.4 nozzle (0.65 mm for a 0.6)."

- [ ] **Step 1: Write failing tests**: `test_v57_joins_flagged` (v57 0.4 6": `feature-below-line-width` present),
  `test_v53_overhang_flip` (warning present, `data["switches"]` non-empty), `test_v56_nozzle_mismatch`
  (`hexagon_v56_X2D_0.6nozzle.3mf` settings → blocking `nozzle-mismatch`), `test_v57_04_no_nozzle_mismatch`,
  `test_bed_fit_10in_straight_fails` (a 254 × 31.5 × 220 box at 0° → blocking), `test_bed_fit_10in_45deg_ok` (same box
  rotated 45° → no finding), `test_non_watertight_reported_not_crashing` (a box with one face removed: `mesh-validity`
  blocking, the other checks still return lists).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → pass.
- [ ] **Step 5: Commit** `"Checks: mesh validity, overhang flip, feature width, bed fit, nozzle mismatch"`

### Task 6: G-code reader

**Files:**
- Create: `lab/analysis/gcode.py`, `tests/test_gcode.py`, `tests/fixtures/gcode/tiny.gcode`

**Interfaces:**
- Produces: `read_layers(gcode: str) -> list[LayerInfo]` with `LayerInfo(index: int, z: float, est_time_s: float,
  outer_wall_speeds_mm_s: list[float], fan_pct: float | None, seam_xy: tuple[float, float] | None)`;
  `events_near(layers, z: float, window: float = 5.0) -> dict` with keys `outer_wall_speed_change`, `fan_change`,
  `layer_time_jump` (bool each, with the heights).
- Parsing rules (Bambu G-code): new layer on `; CHANGE_LAYER`; Z from `; Z_HEIGHT: <z>`; feature from `; FEATURE: <name>`;
  feed from `F` (mm/min → mm/s); fan from `M106 S<0–255>` (→ %); seam = first extruding point of the first
  `Outer wall` in the layer; time = sum of segment length / current feed (acceleration ignored; documented as an
  estimate). A layer-time jump is a change > 30 % between neighbouring layers.

- [ ] **Step 1: Write failing tests** against `tiny.gcode` (3 hand-written layers: layer 2 outer wall at F6000 vs
  F4800 elsewhere; fan S255 then S128 at layer 3): `test_layers_counted` (3), `test_speeds` (layer 2 has 100.0),
  `test_fan` (layer 3 50 %), `test_events_near` (speed change found within 5 mm of layer 2's z), and slow
  `test_real_slice_v57_3in` (layers > 300; every layer has a z; times all > 0).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → pass.
- [ ] **Step 5: Commit** `"G-code: per-layer z, time estimate, outer-wall speed, fan, seam"`

### Task 7: Orientation and coupons

**Files:**
- Create: `lab/geometry/orientation.py`, `lab/geometry/coupons.py`, `tests/test_coupons.py`

**Interfaces:**
- Consumes: `front_facets`, `mesh_facts`.
- Produces:
  - `lean(m, angle_deg: float, axis: Literal["x","y"]) -> trimesh.Trimesh`: rotates about the bed-level axis along
    the tile's long horizontal direction, then drops to z = 0.
  - `score_orientations(m, angles: list[float], profile: str = "appearance") -> list[OrientationScore]` with
    `OrientationScore(angle, a_surface, stability, height_mm, score)`; appearance weights from the spec (A-surface
    quality 40, consistency 20, stability 15, contact damage 10, bed contact 5, time 5, height 5), with contact damage
    and time fixed at their full value in Stage 1A (no support and no slicing here); `a_surface` = 1 when the minimum
    front-facet elevation is ≥ +5°, scaled linearly down to 0 at −10°; `stability` = clamp(base depth / COM height
    × 4, 0, 1).
  - `height_strip(m, z0: float, z1: float) -> trimesh.Trimesh`: `manifold3d` intersection with a box spanning the
    full X/Y extent from z0 to z1, translated to z = 0; raises `ValueError("The mesh isn't closed, so a coupon can't
    be cut from it. Fix the model first (mesh-validity).")` when not watertight.
  - `plate_layout(parts: list[tuple[str, trimesh.Trimesh]], gap: float = 15.0) -> list[tuple[str, trimesh.Trimesh,
    tuple[float, float]]]`: places parts in a row along Y, centred on the plate, and raises `ValueError` naming the
    overflow when the row with brims exceeds 256 mm.

- [ ] **Step 1: Write failing tests**: `test_strip_closed_and_height` (v53 6": `height_strip(60, 100)` watertight, Z
  extent 40 ± 0.05), `test_strip_refuses_open_mesh`, `test_lean_15_all_facets_up` (v53 6" leaned 15°: min front
  elevation ≥ +5° on the side facing up), `test_scores_prefer_lean` (angles `[0, 10, 15, 20]` on v53: 0° has the
  lowest `a_surface`; scores list keeps the input order), `test_plate_layout_two_strips_fit`,
  `test_plate_layout_overflow_message`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → pass.
- [ ] **Step 5: Commit** `"Orientation scores, lean, height-strip coupons and plate layout"`

### Task 8: Experiments

**Files:**
- Create: `lab/experiments.py`, `tests/test_experiments.py`

**Interfaces:**
- Produces:
  - `Experiment` dataclass, saved as `projects/<project>/experiments/E-NNN.json`: `id`, `project`, `question`,
    `hypothesis`, `prediction`, `why_this_test`, `test_kind` (one of `section_coupon`, `orientation_coupon`,
    `fit_coupon`, `joint_coupon`, `height_strip`, `scaled_part`, `full_part`), `factor: {name, values, unit}`,
    `controlled: dict`, `dependent_adjustments: dict[str, str]` (name → reason), `baseline: dict` (keys
    `filament_dried`, `vibration_calibration`, `nozzle_confirmed`, `plate`), `status` (`planned`, `checked`,
    `sliced`, `printing`, `awaiting_verdict`, `done`, `blocked`), `blocked_reason`, `print_runs: list`,
    `findings: list`, `jobs: list[str]`.
  - `next_id(project_dir) -> str` (`E-001` first), `next_print_run_id(project_dir) -> str` (`PR-001` first).
  - `differing_factors(before: dict, after: dict, ignore: set[str]) -> list[str]` over flattened model parameters +
    slicer settings.
  - `check_plan(exp, before: dict, after: dict) -> list[Finding]`: blocking `stacked-changes` when
    `differing_factors` minus `{factor.name}` minus `dependent_adjustments` keys is non-empty; blocking
    `override-needed` for `scaled_part`/`full_part`; info `baseline-incomplete` listing missing baseline items (the
    print would be graded F).

- [ ] **Step 1: Write failing tests**: `test_ids_sequence`, `test_roundtrip_json`, `test_one_factor_ok`
  (`layer_height` declared, only it differs → no blocking), `test_stacked_changes_blocked` (also `outer_wall_speed`
  differs → blocking naming it), `test_dependent_adjustment_allowed` (`brim_width` declared as dependent → allowed),
  `test_full_part_needs_override`, `test_baseline_incomplete_info`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → pass.
- [ ] **Step 5: Commit** `"Experiments: one factor, test kinds, baseline, ids"`

### Task 9: History inventory and revisions

**Files:**
- Create: `lab/history/inventory.py`, `lab/history/revisions.py`, `tests/test_history_inventory.py`

**Interfaces:**
- Consumes: `read_settings`, `list_objects`, `load_mesh`, `mesh_facts`, `front_facets`, `facet_switches`,
  `outline_jumps`, `layer_outlines`.
- Produces:
  - `inventory(folder: Path) -> list[Artifact]` with `Artifact(path, sha256, size, mtime, kind: "scad"|"stl"|"3mf"|
    "json"|"gcode"|"image"|"other", stem: str, version: int | None, size_in: int | None, nozzle: str | None,
    duplicate_of: str | None)`. `stem` is the file name with the version, size, nozzle and copy suffixes removed and
    lower-cased (so `hex_wall_tile`, `hex_pair`, `hexagon` and `hex_tile` map to lineage `hex-tile` through
    `LINEAGES = {"hex-tile": ["hex_wall_tile", "hex_pair", "hex_tile", "hexagon"]}`, while
    `parametric_faceted_hex_wall_tile_mount` stays separate).
  - `revisions(artifacts, lineage: str) -> list[Revision]` with `Revision(version, artifacts: list[str],
    scad_params: dict, settings: dict | None, nozzle_profile: str | None, mesh: dict[str, dict])` where `mesh` maps
    size (`"6in"`) to `mesh_facts` + `facet_switches` + `outline_jumps` (above z = 5). SCAD params are read from
    `^name = value;` lines, normalised (`1.400` → `1.4`, booleans, strings).
  - Written to `projects/hex-tile/history/{inventory,revisions}.json`.

- [ ] **Step 1: Write failing tests** on a tmp folder built from the fixtures plus two copies under other names and a
  `parametric_faceted_hex_wall_tile_mount_v31.stl` dummy: `test_duplicates_collapsed`, `test_lineage_separates_mount`,
  `test_version_and_size_parsed` (`hex_pair_v53_6in.stl` → 53, 6), `test_scad_params_normalised` (v57: `rib_w ==
  0.45`, `closed_back is True`), `test_revision_v56_settings_nozzle` (`nozzle_profile == "0.4"` although the name says
  0.6), `test_unicode_names_read` (the preset JSON with spaces and `@`).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → pass.
- [ ] **Step 5: Commit** `"History: inventory with duplicates and lineages, per-revision facts"`

### Task 10: Lineage, evidence grades and the audit report

**Files:**
- Create: `lab/history/lineage.py`, `lab/history/audit.py`, `projects/hex-tile/history/outcomes.json`,
  `tests/test_history_lineage.py`

**Interfaces:**
- Consumes: `Revision` (Task 9).
- Produces:
  - `transitions(revs) -> list[Transition]` with `Transition(from_v, to_v, scad_changes: dict, settings_changes:
    dict, nozzle_change: bool, factors: int, grade: "A"|"B"|"C"|"D"|"F")`. Grade: F when either side's printed
    configuration is unknown or contradicts its file name (`nozzle-mismatch`); else A for 1 factor, B for 2, C for
    3–4, D for 5 or more. A missing version (no files, e.g. v45) is a gap, not a transition.
  - `outcomes.json`: one entry per row of the "Owner-reported outcomes" table in
    `history/hex-tile/chat/owner-notes.md`: `{at, version, size, nozzle, owner_words, defects, confirmed: false}`.
    `confirmed` stays false until the owner confirms in Stage 2.
  - `audit_text(revs, transitions, outcomes) -> str`: sections "Revisions" (count, lineages, gaps), "Evidence"
    (transitions by grade), "Persistent defects" (defect → versions where reported), "Changes that never touched it"
    (for the upper-edge ripple: transitions between first and last report that changed no factor in `{orientation,
    skin, layer_height, outer_wall_speed}`), "Not yet tried" (fixed list from the spec: vibration calibration,
    upper-half speed modifier, matte PLA, confirmed-dry filament, orientation), "Next experiment" (EXP-001 from the
    spec with its why).

- [ ] **Step 1: Write failing tests**: `test_grade_one_factor_A`, `test_grade_v56_F`, `test_gap_v45`,
  `test_audit_sections_present` (all six headings), `test_audit_lists_ripple_versions` (v36, v37, v39, v51, v56).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → pass.
- [ ] **Step 5: Commit** `"History: transitions, evidence grades, outcomes and the audit report"`

### Task 11: The `lab` command

**Files:**
- Create: `lab/cli.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: everything above.
- Produces the commands (all accept `--project hex-tile`, default from `LAB_PROJECT`):
  - `lab inspect <file> [--object S] [--nozzle 0.4]` → mesh facts, front-facet summary, switches, outline jumps and
    findings, as text; `--json` prints the same as JSON.
  - `lab orient <file> [--object S] --angles 0,10,15,20` → the score table.
  - `lab coupon <file> [--object S] --kind height_strip --z 60:100 --out <stl>`.
  - `lab slice <3mf> --plate N` → sliced path + time and grams from the sliced 3MF metadata.
  - `lab gcode <sliced.gcode.3mf> --plate N [--near Z]` → per-layer summary and events near Z.
  - `lab plan <experiment.json>` → runs `check_plan`, sets `checked` or `blocked`, prints findings.
  - `lab history ingest <folder>` / `lab history audit` / `lab history timeline`.
  - Exit code 0 on success, 2 on blocking findings, 1 on tool errors (message from the error; Job id printed).

- [ ] **Step 1: Write failing tests** with `subprocess.run(["uv","run","lab",...])` on fixtures: `test_inspect_text`
  (contains "Front facets" and the switch height), `test_inspect_ambiguous_object` (exit 1, lists names),
  `test_plan_blocked_exit_2`, `test_history_audit_runs` (after ingest of the fixture folder).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** with `argparse` subcommands. **Step 4: Run** → pass.
- [ ] **Step 5: Commit** `"lab command: inspect, orient, coupon, slice, gcode, plan, history"`

### Task 12: Run it on the real tile and produce EXP-001

**Files:**
- Create: `projects/hex-tile/experiments/E-001.json`, `projects/hex-tile/prints/hex-tile_E001_PR001.3mf`,
  `projects/hex-tile/prints/manifest.json`, `projects/hex-tile/history/audit.md`

**Interfaces:**
- Consumes: the `lab` command.

- [ ] **Step 1: Ingest** `uv run lab history ingest ~/Downloads` → `inventory.json` and `revisions.json` written; then
  `uv run lab history audit > projects/hex-tile/history/audit.md`. Check by eye: v56 graded F, v42→v44 graded D or
  worse, the ripple listed on v36, v37, v39, v51 and v56.
- [ ] **Step 2: Inspect v58 and v56** (`lab inspect … --object 6in`): v58 shows no outline jump above 5 mm; v56 shows
  the mid-height jump.
- [ ] **Step 3: Write `E-001.json`**: question "Does v58 remove the mid-height line?", test kind `height_strip`,
  factor `{name: "model_version", values: ["v56", "v58"]}` with dependent adjustment `nozzle_profile: "v56 was
  printed on the 0.6; both strips print on the 0.4 so only the model differs"`, controlled = the v55 0.4 process and
  filament settings, baseline items as given by the owner, why = "The line appears from v53, when the join began at
  mid-height; v58 has no join that starts partway up."
- [ ] **Step 4: Cut** both strips at Z 60–100 from the 6" pairs, lay them out, write
  `hex-tile_E001_PR001.3mf` on the v58 0.4 project's settings with `print_lab.json` and `manifest.json`, run `lab plan`
  (expect `checked`), `lab slice --plate 1` and `lab gcode --near 66`: record time, grams and the events near the
  join height in the experiment.
- [ ] **Step 5: Commit** `"EXP-001: v56 vs v58 height strips, sliced and checked"` and hand the 3MF to the owner.

---

## Self-review notes

- Spec coverage for Stage 1A: inspect/orient/coupon/slice/gcode (Tasks 3, 4, 6, 7, 11); four checks plus nozzle
  mismatch (Task 5); local experiment JSON with one factor, test kinds, baseline (Task 8); Job records (Task 2);
  history ingest/audit/timeline (Tasks 9, 10, 11); EXP-001 (Task 12). EXP-002 (full 6" pair, needs an override) and
  EXP-003 follow EXP-001's result and are not code. The remaining five seed rules, `/api/lab/*`, phyx3d and the page
  are later stages, as the spec's build order says.
- Review Focus items are pinned: several objects (Task 3 `test_load_object_ambiguous`, Task 11
  `test_inspect_ambiguous_object`); non-watertight (Task 5, Task 7 `test_strip_refuses_open_mesh`); missing tool
  (Task 3 `test_missing_openscad_message`, Task 2 failure kept); unusual names (Task 2 `test_paths_with_spaces`,
  Task 9 `test_unicode_names_read`); unrelated lineages (Task 9 `test_lineage_separates_mount`).
