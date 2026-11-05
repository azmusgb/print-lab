# Fusion to lab: from a parameter change to a planned experiment

Date: 2026-11-05 · Status: **proposed** (approved when the owner merges this PR) · Builds on: the Fusion Parameters Panel
(print-lab #25)

## Problem

The hex tiles are now modelled parametrically in Fusion ("Rift simplified v3"), and the Parameters Panel can export and
`lab inspect` a design. The path stops there:

1. **A Fusion design can't become an experiment.** `lab exp plan --source` takes a registered `sources/*.3mf` and an
   object name; the panel makes a loose STL. Today the step between is done by hand (copy a 3MF, swap the mesh, edit
   `sources/sources.json`, hash it), and the hand path is where v73 went wrong: an STL sliced with loose presets had no
   X2D start G-code and printed in air (27 Oct).
2. **The panel lets you pick values the tile's own rules forbid.** edge_depth 6 leaves a 1.2 mm skin-to-land gap
   against the 1.6 mm rule; nothing says so until someone works it out.
3. **`lab inspect` blocks on lettering.** The 0.6 mm RAHE/RIFT cut makes `feature-below-line-width` report blocking
   slivers at 92–108 mm. They vanish when the cut is rolled back (checked 5 Nov), so the severity misleads.
4. **The panel doesn't say what the lab is waiting for.** The next step (e.g. "E-026 needs your approval") is only in
   `lab status`.

Out of scope: Pi Hub's `/lab` page (baseline step 6 and A7, another track), approving, starting or sending prints, and
any change to experiment rules or guards.

## Design

### 1. Send to lab: a Fusion design becomes a registered source

A **Send to lab** action in the panel's Print-lab section, beside the existing check:

- **Inputs:** the project (as now), a **base** chosen from that project's registered 3MF sources (default: the newest
  one whose objects match the design's family, e.g. `RIFT_10IN_batch5_shadow_storm.3mf`), an **object name**
  (default from the Fusion document, e.g. `RIFT_simplified_v3`), and an optional one-line note.
- **What it does**, in a new `lab` command so the panel stays a thin caller and the step is testable without Fusion:
  `lab variant add --project P --mesh FILE.stl --base sources/B.3mf --name N --params params.json [--note …]`
  1. Loads the STL and turns it upright (the panel's `upright.py` turn, moved into `lab/geometry/` and reused by both).
  2. Writes `sources/<N>.3mf` with `write_print_3mf(base, [(N, mesh, (0, 0))], …)` (`lab/adapters/threemf.py`): the
     base's full project settings, one object on plate 1. **Refuses if the file exists** (sources are never
     overwritten; a rewrite would mark every build of it stale).
  3. Writes `sources/<N>.params.json`: the Fusion document name and version, and every user parameter's expression and
     value.
  4. Appends to `sources/sources.json`: `path`, `sha256`, `source: "derived"`, `derived_from: <base>`, and `change`
     written from the parameter diff against the base's own `.params.json` when it has one ("edge_depth 9 → 7.5 mm;
     geometry from Fusion 'Rift simplified v3' v12"), else "geometry from Fusion '<doc>' v<n>; settings from <base>".
  5. Runs `lab inspect` on the new source and prints the findings, then the exact next command:
     `uv run lab exp plan <Q> … --source sources/<N>.3mf --object <N> --base <base>`.
- **Why a 3MF from a base, not an STL:** builds take settings from `--base` anyway, but a source that is itself a full
  project can be opened and sliced in Studio as is, and can never be sliced from loose presets.
- **Guard:** before registering, check the written file round-trips: `load_object(new, N)` returns a mesh within
  0.01 mm³ of the STL's volume and the same bounds after the upright turn.

### 2. Design-rule limits in the panel

- A tracked rules file per project, `projects/<p>/design-rules.json`: each rule names a parameter, a limit as a Fusion
  expression over other parameters (e.g. edge_depth ≥ `skin_axial + 1.6 mm + …`, written out in PR 2 from the model's
  geometry), the reason in one line, and its source (hex-tile skill rule, owner note, or experiment).
- The panel evaluates each limit with Fusion's own expression evaluator and shows a quiet warning under the field when
  a value breaks it ("min 6.5 mm: 1.6 mm air gap between skin and land"). It never blocks: the owner may want to test
  past a rule.
- PR 2's tests derive the edge_depth floor by measuring the gap in the model at several values, not by trusting the
  5 Nov hand calculation (6.5 mm).

### 3. Engraving is a note, not a blocker

- In `lab/checks/feature_width.py`, a thin region that is a **shallow cut into an outer surface** is reported once as
  `info` (rule `engraving`, "lettering or marks: check they read in the slice preview"), not as
  `feature-below-line-width`.
- Classification is prototyped first on the C02-T STL and the Fusion export: a thin piece of a layer's section counts
  as engraving when it lies within 1 mm of that section's outer boundary and the section's area changes by less than
  the cut's area between neighbouring layers. If no rule separates lettering from real thin walls on the existing
  fixtures, this item stops at a written finding and the severity stays as it is.
- Acceptance: the RIFT export with lettering gives no blocking finding; the existing thin-wall fixtures in
  `tests/test_checks.py` still block.

### 4. What the lab is waiting for

- A one-line, read-only strip at the top of the panel from `lab status --json --no-printer`: the active question, the
  experiment waiting on the owner, and the exact command to run (copy button). Refreshed when the panel opens and after
  a check or Send to lab; never on a timer.

### 5. Parameter history

- Because each Fusion source keeps its `.params.json`, the panel shows which registered source the open design matches
  (all parameters equal) or differs from, and the ledger can list Fusion variants by parameter. No new storage beyond
  item 1.

## PRs

1. #25, the panel as it is (open).
2. `lab variant add` + Send to lab (item 1): tests for the 3MF round-trip, the refusal to overwrite, the
   `sources.json` entry and the change line; a live run from Fusion on a scratch project.
3. Design-rule limits (item 2), with the hex-tile rules file.
4. Engraving classification (item 3), prototype first.
5. Waiting-for strip and parameter history (items 4 and 5).

Each PR: `uv run pytest` (fast suite) green, and the panel exercised live in Fusion with the result reported.

## Risks

- **Settings drift:** a source carries the base's settings at the time it was made. Builds still take settings from
  `--base`, so this only matters when someone opens the source in Studio; the `change` line names the base.
- **Wrong orientation:** a design exported flat and registered upright would print on its face. The round-trip guard
  and the inspect run (which reports height) catch it before planning.
- **Repo size:** each source 3MF is a few MB; the same as today's hand-made variants.
