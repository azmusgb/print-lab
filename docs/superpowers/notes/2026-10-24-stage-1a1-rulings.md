# Stage 1A.1: rulings and deferred minors

Decisions the implementer made on the owner's behalf while building Stage 1A.1 (from the execution ledger), each with what it costs if wrong, and the review findings left for later.

## Rulings

- - T2→T3: migration writes records validated by T2; plan adds build_spec, reference_variants, analysis, legacy fields beyond spec list. Ruling: schema allows them (plan is explicit) — cost if wrong: field rename.
- - T6 build_experiment uses fingerprints; T9 stale_build recomputes them via a shared function. Ruling: builders.py exposes input_fingerprints(paths, exp) used by both — cost: none.
- Task 1: Ruling: setup log lives at <LAB_HOME>/printer/ (one printer shared by projects, as the spec's printer/setup.jsonl) — cost if wrong: move one path property
- Task 2: Ruling: the experiment's question text is 'question_text'; 'question' holds the Q id (spec reuses 'question' for both) — cost if wrong: a field rename
- Task 3: Ruling: E-002 keeps an owner_verdict (E-002-A above E-001-B, "a lot") with reference_variants, as the spec's migration section records it; the plan said no verdict — spec wins — cost if wrong: one field
- Task 3: Ruling: E-003 is prospective, not migrated: its plan was written before printing and it hasn't printed (the spec's stated reason for 'migrated' is that the print happened before 1A.1) — cost if wrong: E-003's outcome could count when it shouldn't; revert one value
- Task 3: Ruling: migration tests run against frozen pre-1A.1 copies of E-001..E-004 (tests/fixtures/migration) so they stay repeatable after the real project is migrated — cost: none
- Task 4: Ruling: about_target false or null gives 'unresolved' in every ranking row (the spec's table says so for 'B above A' and for 'same' A≈B; applying it to A≈B and A above B in the 'better' form too, since a verdict not about the target can't refute it) — cost if wrong: a few refuted results shown as unresolved
- Task 4: Ruling: an acceptance verdict has no prediction outcome (None): it answers 'good enough', which has its own field — cost if wrong: acceptance never feeds the streak
- Task 4: Ruling: comparison_validity reasons carry status internally; witness abnormal → confounded, witness inconclusive → unknown (spec: 'abnormal or inconclusive makes the plate inconclusive' — both yield outcome inconclusive either way) — cost: none
- Task 5: Ruling: strip start height comes from build_spec.z, else from 'Z60-' in the plate's object names (migrated builds have no build_spec) — cost if wrong: a mark's model height is null
- Task 5: Ruling: a ranking with one group (A=B) takes no strength; a difference requires one — cost: none
- Task 6: Ruling: a setting shared by every object on the plate goes into the project settings; differing settings go on each object (per-object overrides in model_settings.config, proven in the G-code by test_real_per_object_speeds_reach_the_gcode) — cost if wrong: none found
- Task 6: Ruling: --values are strings; a setting value is written as the string Bambu stores — cost: none
- Task 8: Ruling: the difference check also compares each variant against its reference variants' latest build on the earlier plate (a single-variant experiment like E-003 otherwise has nothing to compare); the spec names variants and anchors only — cost if wrong: an extra refusal when a reference's settings legitimately differ (declare them as dependent adjustments)
- Task 8: Ruling: positions on the plate aren't a difference (each object has its own spot); object counts are — cost: none
- Task 9: Ruling: geometry_blocking runs the Stage 1A checks on each built object (nozzle-mismatch excluded: the strip mesh has no file name/settings context) and blocks; it is listed as its own guard code — cost if wrong: a slow check (~1 s per object)
- Task 9: Ruling: check status 'approved' when a matching approval covers every needs-approval reason; 'blocked' and 'rebuild' leave the stored status unchanged — cost: none
- Task 9: Ruling: stale_build is skipped for migrated builds with no build_spec (nothing to recompute) — cost if wrong: a migrated build can't be detected as stale; they can't be rebuilt anyway
- Checkpoint 1: Ruling: plate-factor experiments (objects_on_plate) cross plates by design; reason cross_plate_by_design, status valid (an anchor would change the factor itself) — cost if wrong: E-004 counts as informative though plate-to-plate drift is uncontrolled
- Checkpoint 1: Ruling: only inner and outer wall speed (proven) and geometry factors are per-object; every other setting is plate-wide until a capability test proves otherwise — cost: experiments on those settings need two plates
- Checkpoint 1: Ruling: objects_on_plate with two values on one plate is refused too (both copies would share one layer time) — cost: none
- Ruling: minimum layer time and retraction are 'unknown', not 'per_plate_only' as the owner's message listed: only temperature and fan were actually sliced and seen plate-wide; unknown is treated as plate-wide anyway — cost if wrong: none (same behaviour), the record is just honest
- Task 10: Ruling: production match uses the number of objects on the plate against project.json production_plate.objects (a reason 'production_mismatch' with status valid: a warning, not a confound) — the spec asks for layer-time matching to production, which needs a production plate measurement that doesn't exist yet — cost if wrong: a coarser flag
- Task 10: Ruling: mirroring happens when an earlier build of the same experiment was printed (odd count of printed builds → reversed order) — cost: none
- Task 12: Ruling: a builder-code change alone isn't stale when today's builder writes a file with identical contents (zip timestamps and the build ID in print_lab.json ignored; both mirror orientations tried) — the plan's builder_fingerprint would otherwise void every approval at each code change (E-005's approval survived this way) — cost if wrong: a content-identical rebuild skipped; none in practice
- Task 12: Ruling: an anchor is captured at plan time (source, cut, settings, original placement, input fingerprints) and must match its original exactly in the difference check (any difference blocks) — cost: none
- Task 12: Ruling: load_object prefers an exact name match before substring (E-002-A vs E-002-ANCHOR) — cost: none
- Task 12: Ruling: the witness is required whenever there's a reference or an anchor (any cross-plate comparison) — cost: 3 min per such plate
- Task 13: Ruling: capability tests use the lab's reference specimen (tests/fixtures/hex v58 strip on v57 0.4 settings) — cost if wrong: a capability proven on one geometry may differ on another
- Task 13: Ruling: tabs default on when CAP-TAB-ISOLATION has passed (--no-tabs to leave them off); the difference check ignores the first 1.7 mm so tab text doesn't count as a geometry difference — cost if wrong: a real geometry difference confined to the first 1.7 mm is missed (strip bases are cut, not judged)
- Task 13: Ruling: stepped strips are objects STEP-1 (bands in order) and STEP-2 (reversed); variants still name the values; the realized-factor check is skipped for stepped builds (the capability proves the mechanism; per-band reading is 1A.2) — cost: a clamped band isn't caught in 1A.1
- Task 13: Ruling: tests run with an isolated capability folder (conftest autouse fixture) — cost: none
- Task 15: Ruling: sizing judges a band of around_z ± 2 mm; margins 6/8/10/12 mm beyond it; the size measure is injectable (real slicing by default) — cost: none
- Task 15: Ruling: a band uniformly affected by a cut edge can't be detected by the edge-vs-median rule; accepted as a 1A.1 limit (1A.2 band analysis) — cost if wrong: a non-representative strip passes when the whole band is disturbed
- Task 16: Ruling: the e2e rebuild with --replace changes the settings file first (a zip comment), since --replace with unchanged inputs returns the existing build and keeps the approval by design — cost: none
- Task 16: fixed the owner-found tab false positive — test_tab_text_is_not_a_geometry_finding RED→GREEN: on a tabbed strip, feature-below-line-width findings no higher than the tab (1.6 mm) don't block. Ruling: a whole finding spanning above the tab still blocks — cost if wrong: thin real geometry within the first 1.6 mm of a tabbed strip is missed (strip bases are cut, not judged)
- Final: Ruling: a ranking judged under any light but the diagnostic one is at most 'unresolved' — the spec judges evidence under the diagnostic light — cost if wrong: a real room-light result doesn't count; E-004 keeps its recorded 'diagnostic' until the owner says otherwise

## Deferred minors

- verdict input errors give raw messages (--mark A, --failed-at abc; duplicate or partial rankings refused only deep in _place)
- concurrent `start` can open two print runs (check and status test outside the lock)
- an experiment missing from the question's list isn't charged to it
- geometry_blocking always uses nozzle 0.4
- an approval of auto_stopped covers a later stop of a different kind
- parse_budget silently keeps the last of duplicate units (3h,4h)
- realized-factor check reports 'as asked' for migrated records with no build_spec (requested unknown), e.g. E-003
- witness and anchor accepted in --rank (resolve_variant should filter to variants and references)
- --reference not validated at plan time
- realized check takes the first object on a multi-object reference plate when names don't match
- G2/G3 arc moves ignored in object_feature_speeds
- duplicate-question check and setup repair IDs not under a lock
- verdict accepted on an abandoned experiment (overwrites status)
- schema doesn't validate the inside of expect and budget
