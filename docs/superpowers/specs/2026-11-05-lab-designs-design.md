# The lab designs: generated models that are printable by construction

Date: 2026-11-05 · Status: **proposed** (approved when the owner merges this PR) · Amends: the print lab design
(`2026-10-24-print-lab-design.md`), decision D1 ("the lab first; generating parts later") and its "Not in v1:
generating new parts from a description (build123d comes later)". Builds on: Fusion to lab (`2026-11-05-fusion-to-lab-design.md`).

## Problem

The lab records, checks and compares designs that someone has already made. Every lesson it holds arrives after a
print: the hollow roof (5 Nov) came from photos of a finished tile, a section analysis by hand, and a fix in Fusion.
The owner wants the lab to **create** models, not only critique them:

1. **Lessons don't flow forward.** The 1.6 mm skin rule, "every layer alike", the hollow roof and the top-wall shell
   count live in the skill, `design-rules.json` and the ledger. A new design meets them only if its author remembers.
2. **One design at a time.** Each variant is hand-made in OpenSCAD or Fusion. Exploring a family (sizes, depths, facet
   layouts) costs a session per variant.
3. **Nothing is scored before the owner sees it.** `lab inspect`, the slice and (PR #40) the risk predictor run after a
   design is registered, not while choosing between ideas.

Out of scope: sending prints, approving, the `/lab` page (Pi Hub, A7), and changing experiment rules or guards.

## Design

### 1. Families: generators, not files

A **family** is a Python module in `lab/design/families/` built on build123d. It defines:

- `PARAMS`: each parameter's name, unit, default, range and one-line meaning (the same shape as Fusion's user
  parameters, so a `params.json` from Fusion and one from a family read alike);
- `build(params, seed) -> Part`: deterministic; the same parameters and seed give the same solid to 0.001 mm³;
- `orientation`: how the part stands on the bed (the hex tile: upright, a flat side down).

A design is `(family, version, params, seed)`. Its id is a hash of those four, so a verdict on one design can be
traced to everything that shares its parameters.

The first family, **`faceted_hex`**, reproduces "Rift simplified v6" (Fusion, 5 Nov): corner_diameter, edge_depth,
facet_rise, skin_axial, perimeter_wall, land_width, land_thickness, roof_wall, the U tape land with the open top, and
the RAHE/RIFT lettering. The facet layout is the seeded part: a seed picks the interior peak points (count, position
and height within `facet_rise`) and triangulates them to the hex outline.

### 2. Lab rules as constraints, not reviews

A tracked file per project, `projects/<p>/design-constraints.json`, holds the rules a generator must obey, each with
its source (the same sources `design-rules.json` cites). A family reads the constraints and builds within them;
`design-rules.json` stays as the panel's warnings for hand designs.

The hex tile's first constraints, all from existing evidence:

| Constraint | Source |
|---|---|
| Nothing joins or touches within 1.6 mm of the skin | hex-tile skill |
| Skin, walls, land and roof plate at least two printed lines (0.9 mm) | `lab/checks/feature_width.py` |
| No region behind the face wider than the wall loops (hollow roof) | E-026 hypothesis; 5 Nov section analysis |
| A top wall no thicker than the top plus bottom shell layers | 5 Nov analysis (0.8 mm of infill under a 2.4 mm wall) |
| Lettering inside the land with at least 1 mm clear of its edges | Fusion lettering, 5 Nov |

A constraint that can't be expressed in the generator is checked after building (item 3) and marked so.

### 3. The gate: scored before anyone looks

`lab design make --family F --params P.json --seeds N` builds each candidate, then for each:

1. validity: one closed solid (manifold3d), bounds and volume;
2. `lab inspect` on the upright mesh;
3. a slice with the project's base 3MF settings (as `lab variant add` does);
4. the slice risk predictor (PR #40), run as a library function, not the agent: risk bands with heights;
5. cost: print minutes and grams from the slice.

Candidates that fail 1 or 2 are dropped with a reason. The rest are written to `designs/<family>/<id>/` (outside
`sources/` until chosen): `model.step`, `model.stl`, `params.json`, `gate.json`, `render.png`.

### 4. The gallery: the owner chooses

One page per `make` run: each candidate's render, print time, grams, risk bands (a small height strip) and its
parameter differences from the family default. It's a private Artifact while this is local; on Pi Hub later (A7).
Choosing a candidate runs `lab variant add` with it, so it becomes a registered source exactly as Send to lab does
(sha256, `derived_from`, `change` naming the family, version, seed and parameter diff). Planning and printing are
unchanged.

### 5. Fusion stays the hand tool

Fusion remains where the owner shapes a single design by hand. Both directions use files the lab already reads:

- **Family to Fusion:** a STEP and `params.json`, opened in Fusion for hand work (as a base feature, not parametric).
- **Fusion to lab:** Send to lab, unchanged. A Fusion design whose parameters match a family's can be rebuilt by the
  family and compared: same volume to within 0.1%.

### 6. What this is not yet

The **wall composer** (one relief split across many tiles whose edges meet) and **design from a photo or sketch**
are the reason to build families, but each needs the family and gate working first. They get their own specs once
items 1 to 4 have run on real prints.

## Dependency

**build123d** joins the project's dependencies: it builds B-rep solids headless, exports STEP and STL, and is what the
installed build123d MCP server runs, so a family can be developed interactively there and run in the lab unchanged.
It is installed into the lab's venv with a pinned version.

## PRs

1. This spec.
2. `lab/design/` with the family interface and `faceted_hex` at Rift v6's parameters, seed fixed to v6's layout.
   Acceptance: within 0.1% of the volume of `sources/Rift_simplified_v5_save5.3mf` (64 323.4 mm³), same bounds within
   0.05 mm, two shells (the hollow roof); a test builds it from `params.json`.
3. `design-constraints.json` and the constraint checks; tests with one passing and one failing case per constraint.
4. `lab design make` with the gate (item 3), a 12-seed run of `faceted_hex`, and the gallery page from it.
5. Choosing a candidate (`lab variant add` from a design).

Each PR: `uv run pytest` green, and the generated parts measured, not assumed.

## Risks

- **Seeded facets that look worse than hand ones.** The gallery is the check: the owner picks, the generator only
  proposes. Seeds that keep being rejected tell us which ranges to narrow.
- **Constraints frozen too early.** Each constraint names its source; a verdict that contradicts one updates or
  retires it, the same rule the skill applies to its lessons table.
- **Fusion and family drift.** The 0.1% comparison in item 5 catches it, and the family's version is in every id.
- **Slicing many candidates is slow** (about a minute each). `make` runs them one after another in the background and
  records partial results, so twelve seeds finish unattended.
