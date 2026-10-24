# Print lab Stage 1A.1: the experiment loop (24 October 2026)

**Builds on:** `2026-10-24-print-lab-design.md` (the approved Print lab design) and Stage 1A, merged 24 Oct.

**Goal:** turn a question about a print into controlled, budgeted test prints and recorded answers, with Claude Code
preparing the next test on its own inside limits the owner sets, and every record honest about what it knows.

**Why now:** the first day of real experiments showed what the lab lacked.

- E-001's file claimed "about an hour" and sliced to 2 h 52 min; nothing checked it.
- Every print file was built by a throwaway script; every result was hand-written JSON with new fields each time.
- Telling the strips apart in photos needed geometry reasoning; nothing on the print said which was which.
- The baseline steps (drying, vibration calibration) were never done or recorded, and E-002's planned change
  (doing them) silently didn't happen.
- **E-002 printed one strip alone; E-001 printed the same strip beside another.** Layer time 18 s against 35 s, owner
  verdict "much better". The plate itself was an uncontrolled variable, and nothing recorded it.

**Stage map.** 1A.1 (this spec) is the experiment loop. 1A.2 is diagnosis (candidate causes, defect-height matching
against G-code, band score from photos, repeat prints, filament checks, version-pinned Bambu Studio settings
reference, kinds of knowledge). 1A.3 is self-learning (cases into rules, learned priors, the owner's eye, remembered
settings, preference-based tuning with BoTorch `PairwiseGP`). 1A.1's records are designed so 1A.2 and 1A.3 can
reason and learn from them. Stage 1B moves the records into Local AI.

## Decisions taken

| Topic | Decision |
|---|---|
| Autonomy | Levels per project: 0 observe, 1 recommend, **2 diagnostic autonomy (default; hex tile)**, 3 print autonomy (later; not possible while the printer is in cloud mode), 4 production autonomy (not enabled). At level 2 the lab plans, builds, slices and checks test pieces on its own; the owner starts every print and judges every result. |
| Budgets (defaults) | Per test 45 min and 25 g. Per question 180 min and 100 g. At most 2 next-test plans prepared ahead; only the one the latest verdict selects is built. |
| Verdicts | Experiments: a ranking of the variants (a pair is a ranking of two; "no meaningful difference" puts them in one group) with strength slightly / clearly / a lot, or *inconclusive*. Full and scaled parts: an acceptance verdict, good enough yes / no with blocking defects. |
| Good enough (hex tile) | No visible banding, ripples, seams, support scars or other distracting surface defects from about 60 cm in the room's normal light, including the worst realistic window light, and no visible defect from 1 m or farther in any normal viewing condition. **If a defect draws the eye before you go looking for it, it fails; if you must know where to look and use the diagnostic light to find it, it can pass.** |
| Lighting | Comparisons of strips are judged under the diagnostic light (low, raking, fixed set-up). Acceptance is judged in real installed conditions, ideally at one named check spot. A trace only the diagnostic light shows is recorded, never a failure. |
| Storage | Plain JSON files in the repo are the Stage 1A source of truth: one file per question, one per experiment, an append-only setup log. **Experiment files are evidence; question totals and states are derived and can always be rebuilt.** Photos stay out of git. |
| New dependencies | None. Geometry stays trimesh, manifold3d and shapely; slicing stays Bambu Studio 02.08.02.61. |

## Records

Every record carries `"schema": 1` and `"record_type"` (`question`, `experiment`, `setup_event`, `setup_repair`) and
is validated against its format on every read. IDs are only ever issued by the lab. Times are UTC ISO 8601. Paths are
relative to the project folder.

### Question: `projects/<p>/questions/Q-NNN.json`

Intent and budget only.

```json
{"schema": 1, "record_type": "question", "id": "Q-001", "project": "hex-tile",
 "question": "What causes the bands on v58's face?", "status": "active", "autonomy_level": 2,
 "budget": {"max_test_minutes": 45, "max_test_g": 25, "max_minutes": 180, "max_g": 100},
 "experiments": ["E-001", "E-002", "E-003", "E-004"],
 "plans": [{"id": "P-005", "after": "E-004", "if": "two-object plate rougher", "next": "one pair per plate vs minimum layer time"}],
 "owner_stop": null, "resumes": []}
```

`owner_stop` is `{reason, at}` when the owner stops the question. `resumes` lists `{at, added: {minutes, g}, reason}`.
**Derived, never stored:** spent minutes and grams, the uninformative streak, automatic stop and its reason, the next
step.

### Experiment: `projects/<p>/experiments/E-NNN.json`

Today's fields (question text, hypothesis, prediction, why this test, test kind, factor, controlled, dependent
adjustments, baseline, findings) plus:

- `question`: the question's ID.
- `judge_on`: what the comparison is about, e.g. `"bands"`.
- `expect`: `{"better": "E-004-B", "than": "E-004-A", "min_strength": "clearly"}`, or `{"same": ["E-004-A", "E-004-B"]}`.
- `derived_from_artifact` and `derived_from_result`: lists of experiment IDs. Only `derived_from_result` carries
  reasoning, and only it is checked against refuted outcomes.
- `controls`: `{"witness_required": bool, "anchor": "E-002-A" | null}`.
- `variants`: `{"id": "E-004-A", "tab": "4A", "factor_value": …}`; the witness is `{"id": "WITNESS-01", "role":
  "control"}` and an anchor `{"id": …, "role": "anchor", "same_as": "E-002-A"}`.
- `builds`: every build attempt, `{"id": "BLD-004-01", "inputs": {model, settings, builder_version, openscad,
  bambu_studio fingerprints}, "job": "job-…", "ok": bool, "artifact": file, "artifact_sha256": …, "estimate":
  {"minutes": …, "g": …}, "plate": {"objects": […], "placements": […]}, "measured": {"layer_time_median_s": …,
  "layer_time_profile": [[z, s], …]}}`. Failed builds stay in the list.
- `approval`: `{"build_id", "artifact_sha256", "approved_reasons": [codes], "by": "owner", "at", "reason"}` or null.
- `print_runs`: `{"id": "PR-004-01", "build_id", "started_at", "setup": {snapshot}, "usage": {"actual_minutes",
  "actual_g", "usage_source", "completion_fraction"}, "failed": {"at_fraction", "note"} | null, "photos":
  [{"path", "sha256", "captured_at", "source"}]}`.
- `owner_verdict`: see below. `superseded_verdicts`: earlier ones, kept.
- `ai_observations`: `[{"type", "variant", "assessment", "confidence", "confirmed": false, "at"}]`. **Never read by
  stop logic, budgets, outcomes or learning.**
- `comparison_validity`: `{"status": "valid" | "confounded" | "unknown", "reasons": [{"code", …}]}`, derived.
- `prediction_outcome`: derived and cached, never authoritative.
- `status`: `planned`, `built`, `build_failed`, `ready`, `needs_approval`, `approved`, `printing`, `answered`,
  `abandoned` (with reason). `ready` and `needs_approval` are display only; `start` re-checks. A failed print run returns
  the experiment to `built`, so the next attempt is checked again.

### Verdicts

```json
{"kind": "ranking", "print_runs": ["PR-004-01"], "order": [["E-004-B"], ["E-004-A"]], "strength": "clearly",
 "about_target": true, "lighting": "diagnostic", "marks": [{"variant": "E-004-A", "mark_z_mm": 6.0, "defect_z_mm": 66.0}],
 "witness": {"id": "WITNESS-01", "condition": "normal" | "abnormal" | "inconclusive", "note": null},
 "witness_override": null, "note": null, "by": "owner", "at": "…"}
{"kind": "inconclusive", "print_runs": […], "reason": "photo too dark", "by": "owner", "at": "…"}
{"kind": "acceptance", "print_runs": […], "good_enough": false, "blocking_defects": ["banding"], "lighting": "installed", "note": null, "by": "owner", "at": "…"}
```

The witness and anchors never appear in `order`; the witness has its own condition, and an anchor is compared with
its earlier self. `defect_z_mm` = strip start height + `mark_z_mm`. `about_target` is `true` for a verdict entered
through `lab exp verdict` (which shows "Judging on: bands" first) unless `--not-about-target`; migrated history has
`null`.

### Prediction outcome (derived)

| Verdict | `expect` B better than A, min strength S | `expect` same |
|---|---|---|
| inconclusive, or witness abnormal / inconclusive without override, or comparison confounded | inconclusive | inconclusive |
| B above A at strength ≥ S, `about_target` true | supported | refuted (unresolved if only "slightly") |
| B above A but weaker than S, or `about_target` false or null | unresolved | unresolved |
| A ≈ B (one group) | refuted | supported (unresolved if `about_target` is false or null) |
| A above B | refuted | refuted (unresolved if only "slightly") |

`supported` and `refuted` are informative; `unresolved` and `inconclusive` are not.

### Setup log: `printer/setup.jsonl`

Append-only, one event per line: `{"schema": 1, "record_type": "setup_event", "id": "SET-00017", "kind":
"filament_dried" | "vibration_calibration" | "nozzle_changed" | "spool_loaded" | "correction" | …, "at", …}`.

- **A valid event with wrong facts** is corrected by appending `{"kind": "correction", "supersedes": "SET-00017",
  "replacement": {…}}`.
- **A malformed line** is repaired by `lab setup repair --line N`, which writes `printer/setup-repairs.jsonl`:
  `{"record_type": "setup_repair", "repair_id", "source_line", "source_sha256", "replacement_event", "reason"}`. The
  reader substitutes a repair only when the damaged line's hash matches. The original bytes are never changed.
- The current setup is derived from the latest event of each kind; `start` snapshots it into the print run, so later
  events never change history.

## Commands

All writes: write a temporary file in the same folder, then replace atomically. **Child and evidence records first,
the parent or index reference last** (e.g. `exp plan` writes `E-005.json`, then adds it to `Q-001.json`; `exp build`
writes the artifact, job, manifest line, then the experiment). Every mutation takes the record's lock
(`fcntl.flock` on `.locks/<id>.lock`, holding `{pid, command, started_at}`), re-reads the record, validates, writes,
releases. A command that can't get the lock in 10 s names the holder from the lock file and changes nothing; the OS
frees the lock if a command dies.

| Command | Writes | Refuses / notes |
|---|---|---|
| `lab question new --project P "text" [--budget 180m,100g]` | `questions/Q-NNN.json` | an open question with the same text |
| `lab question show Q` / `status Q` | nothing | `status`: budget used and after the next test, experiments and their states, evidence counts, stop state, next step |
| `lab question rebuild Q` | cached `prediction_outcome` and `comparison_validity` | validates everything first; **any problem means a full report and no writes**; also reports orphaned artifacts and unattached experiments |
| `lab question stop Q --reason` | `owner_stop` | — |
| `lab question resume Q [--add 60m,30g] --reason` | `resumes`, clears `owner_stop` | the streak counts only from the latest resume |
| `lab exp plan Q --factor … --values … --expect … [--judge-on …]` | `E-NNN.json` (planned), then the question | autonomy level 0; more than one factor; a factor outside the allowlist (`lab/factors.json`: model version, objects on plate, and named slicer settings such as inner and outer wall speed, nozzle temperature, fan speeds, minimum layer time, retraction length, wall loops, filament profile; a new factor is added there by a reviewed change) |
| `lab exp build E [--replace]` | artifact, job, manifest, then a new `builds` entry; status `built` or `build_failed` | **Idempotent:** unchanged inputs say "already built" and write nothing; changed inputs need `--replace`, which adds a new build and keeps the old |
| `lab exp check E` | status `ready` or `needs_approval`, with every reason | read-mostly; safe to rerun; output as in the budget section |
| `lab exp approve E --reason` | `approval` bound to the current build's ID and fingerprint | status isn't `needs_approval`; an owner stop (approval can't override it) |
| `lab exp start E` | a new print run with the setup snapshot; status `printing` | **re-runs the check on live state**; refuses unless it passes or a matching approval exists; already printing says so and writes nothing; missing baseline items warn and are recorded |
| `lab exp usage PR --failed-at 40%` / `--minutes M --grams G` | the print run's `usage` (and `failed`) | — |
| `lab exp verdict E --rank "B>A" --strength clearly [--mark A:6] [--witness normal] [--witness-override "…"] [--not-about-target]` | `owner_verdict`, cached outcome; status `answered` | a verdict exists (unless `--replace`, which moves it to `superseded_verdicts`); witness required but not given |
| `lab exp verdict E --inconclusive "reason"` / `--accept yes|no [--defects …]` | as above | `--accept` only for scaled and full parts |
| `lab exp observe E …` | appends to `ai_observations` | written by Claude only |
| `lab exp abandon E --reason` | status `abandoned` | — |
| `lab setup log KIND [--key value …]` / `lab setup repair --line N …` | appends to `setup.jsonl` / `setup-repairs.jsonl` | — |
| `lab photos add PR IMG…` | converted copies in `projects/<p>/photos/` (git-ignored), then their entries on the print run | the print run doesn't exist; a file that won't convert (nothing half-added) |

## Budget and stopping

**Spent:** the sum over a question's started print runs of `usage`, taken in this order: telemetry (Stage 1B), then
manual minutes and grams, then estimate × completion fraction for a failed run, then the full estimate. Runs never
started cost nothing; analysis and slicing cost nothing.

**Automatic stop** (derived; reasons as codes plus text):

| Code | When |
|---|---|
| `uninformative_streak` | the last two answered experiments since the latest resume are both `unresolved` or `inconclusive` |
| `budget_time_exhausted` / `budget_material_exhausted` | spent ≥ the question's budget |

A failed print isn't a verdict: it uses budget and doesn't touch the streak. **Stops beat remaining budget.**

**`lab exp check`:** every guard is evaluated and every failure listed.

| Guard | Fails when | Result |
|---|---|---|
| `owner_stopped` | the question has an owner stop | **blocked**; only `question resume` lifts it; approval can't |
| `auto_stopped` | an automatic stop applies | needs approval |
| `full_part_required` | test kind is `scaled_part` or `full_part` | needs approval, always |
| `autonomy_level` | the project is at level 1 | needs approval (level 0 can't plan) |
| `refuted_dependency` | a `derived_from_result` experiment came out `refuted` | needs approval |
| `per_test_time` / `per_test_material` | estimate > 45 min or > 25 g | needs approval |
| `question_time` / `question_material` | spent + estimate > budget (equal fits) | needs approval |
| `retry_limit` | two physical print runs of this experiment already failed | needs approval, listing both failures |
| `stale_build` | any input fingerprint (model, settings, builder, OpenSCAD, Bambu Studio) changed since the build | rebuild needed |
| `no_estimate` | the build has no sliced estimate | rebuild needed |
| `plate_mismatch` | see the plate rules | needs approval **and** the comparison stays confounded |

An approval covers the guards it lists, for that exact build only. **Approval to print never makes a confounded
comparison valid.** Blocking geometry findings (Stage 1A checks) can't be approved away.

## Test builders and the plate

**The plate is part of the experiment.** Each build records the plate's objects and placements (inputs) and the
measured layer-time profile from the G-code (a result).

- **Matching:** two plates being compared match only if their layer times over the **judged heights** (the strip's
  judged region, or `defect_z ± 10 mm`) are within 10 % of each other, layer by layer on the median. The whole-print
  median isn't enough. E-004 calibrates the 10 %.
- **When the plate is the factor** (e.g. E-004, objects on the plate), the layer-time difference is the thing being
  tested, not a confound; `plate_mismatch` doesn't apply to that factor.
- **Same plate first:** variants share one plate whenever possible. Repeats mirror positions (A left, B right; then B
  left, A right).
- **Production match:** for a process-sensitive question, the test plate's layer time over the judged heights should
  match the intended production plate's (e.g. one pair per plate or two). A mismatch is flagged.
- **Three levels of control:** same plate (strongest); separate plates sharing an anchor (sound enough); separate
  plates without one (weak, `comparison_validity` = confounded or unknown).

**Builders:**

1. **Height strip** (Stage 1A, extended). `--around Z --target-minutes M` slices candidate heights and picks the
   smallest strip that fits, with at least 6 mm above and below the judged region. **The margin grows** when the
   G-code shows cut-edge effects (unusually short or long layers) reaching into the judged region.
2. **Witness wall `WITNESS-01`.** 40.0 mm long, 2 wall loops, the strip's height, fixed orientation, at least 25 mm
   from the nearest piece, the same settings. Versioned: any change makes `WITNESS-02`. Required by default when a
   comparison spans separate plates; off when all variants share a plate. On every compared plate or on none.
3. **Anchor.** A repeat of an earlier variant (same model, settings, builder), placed where it was before. If the
   anchor's verdict against its earlier self isn't "no meaningful difference", the cross-plate comparison is
   inconclusive.
4. **Stepped settings.** Per-height settings via Bambu Studio's height-range modifiers, gated by the capability test
   `CAP-BAMBU-HEIGHT-RANGE`: build a strip with two bands (inner walls 250 then 80 mm/s), slice with 02.08.02.61, and
   pass only if the G-code's inner-wall speeds change at the boundary within one layer. Each stepped strip prints
   beside a reversed twin on the same plate. Fallback: separate strips on one plate.
5. **Version-ID tab.** 10 × 6 × 1 mm with 0.6 mm raised text (OpenSCAD `text()`), attached by a thin bridge at the
   strip's end at bed level; it touches the first 8 layers only. One-time capability test `CAP-TAB-ISOLATION`: with
   and without tabs, the judged region's layer times are within 2 %, and its speeds and fan are identical.

Builders refuse, with a clear message: a plate too full, colliding tabs, a witness under 25 mm away, a capability
test not yet passed, a plate that doesn't match the plate it's compared with (unless approved, and then confounded).

## Errors

| Situation | Behaviour |
|---|---|
| Invalid JSON or a format error in a record | the command stops, names the file and field, changes nothing; never auto-repaired |
| Wrong `record_type` | refused before parsing fields |
| Valid setup event with wrong facts / malformed setup line | a correction event / `lab setup repair` (above) |
| Damaged or non-Bambu 3MF | clear error (Stage 1A fixes) |
| Tool failure (OpenSCAD, Bambu) | a failed build with its job kept; status `build_failed`; `build --replace` retries without rewriting history |
| Stale build, no estimate | `check` reports it; rebuild needed |
| Verdict twice | refused unless `--replace` |
| Unknown experiment or print-run ID | the error lists the valid IDs for that question |
| Lock held | waits 10 s, then names the holder's command, PID and start time; changes nothing |
| Photo conversion fails | names the file; nothing half-added |

## Moving the existing records

Q-001 "What causes the bands on v58's face?" is created around E-001 to E-004. Known facts are kept; anything not
recorded at the time is `null`; no confidence, lighting, marks or setup are invented.

- **E-001:** owner verdict v58 better than v56 (strength `null`; owner: "looks better … for sure"); prediction "the
  join causes the line" refuted on the AI's reading only, so `unresolved` until the owner confirms.
- **E-002:** the planned change (drying, calibration) wasn't made; recorded as an accidental plate-layout test (one
  object, layer time 18.4 s). Against E-001's v58 strip (two objects, 34.8 s): owner "much better", comparison
  **confounded** (`layer_time_mismatch`).
- **E-003, E-004:** planned; E-004 tests the plate layout directly.

## Testing

TDD throughout: every behaviour starts as a failing test. Fast tests use small fixtures; anything that runs Bambu
Studio is marked slow.

- **Records:** format validation per record type; wrong `record_type` refused; IDs issued in order; atomic write
  (a failure injected before the final replace leaves the original unchanged and the temporary file gone).
- **Outcome table:** every row, for both `expect` forms; witness abnormal / inconclusive forces inconclusive unless
  overridden; `about_target` null never gives supported.
- **Budget and stop:** each guard; the exact boundary (estimate equal to the remaining budget fits; spent equal to
  budget stops); unresolved, unresolved stops; unresolved, refuted, unresolved doesn't; a failed run is charged by
  fraction and doesn't touch the streak; resume resets the streak; approval doesn't survive a rebuild; **an owner stop
  can't be bypassed by approval**; `start` refuses a stale `ready` after budget was used elsewhere; `rebuild` matches
  the step-by-step state and writes nothing when any record is invalid.
- **Plate:** the judged-heights mismatch is caught even with equal whole-print medians; approval leaves a mismatch
  confounded; an anchor that changed makes the comparison inconclusive; mirrored placement on repeats.
- **Builders:** strip margins and the margin growing; witness geometry, spacing and on/off rule; tab size and 8-layer
  limit; `CAP-BAMBU-HEIGHT-RANGE` and `CAP-TAB-ISOLATION` against real slices (slow).
- **Locks:** a lock held by another process makes a mutation wait, time out, name the holder and change nothing.
- **Setup log:** corrections supersede; a repair applies only when the hash matches; history snapshots don't move.
- **End to end (slow, temporary lab folder, real Bambu Studio):** question new → plan (two variants, one plate) →
  build → check ready → start (snapshot, live re-check) → verdict "B>A clearly" → supported, status shows spend and
  the next plan → an over-budget experiment needs approval → approve → rebuild with `--replace` → start refuses →
  owner stop, approve still blocked → resume → allowed → `rebuild` reproduces every total and state.

## Out of scope for 1A.1

Candidate-cause lists, defect matching against G-code, band scores and repeat-variation analysis (1A.2); learning
of any kind (1A.3); Local AI records, telemetry and the phone page (1B); starting prints (level 3).
