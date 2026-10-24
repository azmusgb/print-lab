# Print lab Stage 1A.1 (the experiment loop) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** questions and experiments as validated plain-file records, with commands that plan, build, check, start,
record and judge test prints inside owner-set budgets, and derive outcomes, stops and the next step from the evidence.

**Architecture:** a `lab/records/` layer (atomic JSON, locks, ID allocation, per-type validation) under a
`lab/loop/` layer (outcome, ledger, guards, plate, differences, setup log, builders), driven by new `lab question`,
`lab exp`, `lab setup` and `lab photos` subcommands in `lab/cli_loop.py`. Derived values (spend, streak, stops,
outcomes, validity) are pure functions of the records.

**Tech Stack:** Python 3.12 with uv; trimesh, manifold3d, shapely (existing); Bambu Studio 02.08.02.61 CLI; OpenSCAD
2026.10.11; macOS `sips` for HEIC. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-24-print-lab-stage-1a1-design.md` (approved). Read it with this plan; the
spec's tables are the authority for values and behaviour.

## EXP-004 comes first

**EXP-004 is the first real acceptance test of Stage 1A.1. Do not require every 1A.1 feature before the engine can
migrate, record and judge EXP-004.** Phase 1 (Tasks 1–9) is the vertical path; it ends with EXP-004 migrated and judged
through `lab exp verdict`, and the next experiment (E-005) planned, built, checked and started through the new
commands. **Before E-005 physically starts, both `undeclared_difference` (Task 8) and a preliminary `plate_mismatch`
guard (Task 9) must exist, and a fresh high-capability review of Phase 1 must have run** (see "Review checkpoints").
Phase 2 (Tasks 10–16) adds the remaining guards, builders and safeguards around that working path.

## Review checkpoints

1. After Task 9's tests pass and before E-005 is started on the printer: a fresh review of Tasks 1–9 on the most
   capable model; Critical and Important findings fixed (test first) before the print.
2. After Task 16: the whole-branch review.

EXP-004 finishes printing before this code exists. Until Task 5 lands, record the owner's words in the old E-004 file
(`print_runs[0].result.owner_words`); migration (Task 3) carries them over as an un-entered note, and Task 5's
acceptance step enters the structured verdict with the owner.

## Global Constraints

- Every record: `"schema": 1`, `"record_type"` ∈ `question`, `experiment`, `setup_event`, `setup_repair`; validated on every read; IDs issued only by the lab; UTC ISO 8601 times; paths relative to the project folder.
- Experiment files are evidence; question totals and states are derived and can always be rebuilt.
- Writes: temporary file in the same folder, then atomic replace. Child/evidence records first, parent/index reference last.
- Locks: `fcntl.flock` on `<project>/.locks/<id>.lock` holding `{pid, command, started_at}`; 10 s wait, then name the holder and change nothing. New IDs under `<project>/.locks/id-allocation.lock` with exclusive create.
- Default budgets: per test 45 min and 25 g; per question 180 min and 100 g; at most 2 plans prepared ahead.
- Autonomy levels 0–4; default 2. Level 0 can't plan; level 1 needs approval for every build.
- `ai_observations` are never read by stop logic, budgets, outcomes or learning.
- Only `prospective` experiments can be `supported` or `refuted` or count toward the streak.
- Approval binds to one build ID and artifact fingerprint; never overrides an owner stop; never makes a confounded comparison valid; never overrides blocking geometry findings or `undeclared_difference`.
- `plate_time_tolerance_pct: 10`, `source: provisional`, in `<project>/project.json`.
- Photos stay out of git (`projects/*/photos/` in `.gitignore`).
- Slicing only with Bambu Studio 02.08.02.61 (existing `EXPECTED_VERSION`).
- Plain-language CLI messages: say what happened and what to do; no stack traces for expected errors (exit 1 for input/tool errors, 2 for blocked or needs-approval checks).

## Review Focus

1. A verdict entered for an experiment with no started print run should be refused with "start it first (`lab exp start`)" — Task 5.
2. A ranking naming a variant the experiment doesn't have (`--rank "B>C"`) should be refused, listing the valid variant IDs and tabs — Task 5.
3. `--failed-at` outside 1–99 % (e.g. `140%`, `0`) should be refused; a completed print uses `--minutes/--grams` — Task 5.
4. A budget string without units (`--budget 180,100`) should be refused; `3h`, `180m`, `100g` and `2h30m` parse — Task 1.
5. A ranking that names a variant from an earlier experiment (E-004 against `E-002-A`) works only when that variant is listed in the experiment's `reference_variants` — Task 5.

---

## File structure

| File | Responsibility |
|---|---|
| `lab/records/store.py` | atomic JSON write/read, `RecordError`, record locks, ID allocation, budget-string parsing |
| `lab/records/schema.py` | hand-written validators per `record_type` |
| `lab/records/project.py` | `ProjectPaths` (folders under a project) and `project.json` settings |
| `lab/records/migrate.py` | one-time conversion of E-001..E-004 and creation of Q-001 |
| `lab/loop/outcome.py` | `prediction_outcome`, `comparison_validity` |
| `lab/loop/ledger.py` | spend, streak, automatic stop, question status |
| `lab/loop/setup_log.py` | append, repair, reduce, current setup |
| `lab/loop/plate.py` | layer-time profile from G-code, judged-heights matching |
| `lab/loop/diff.py` | actual-difference check between built variants |
| `lab/loop/guards.py` | `check_experiment` (all guards), used by `check` and `start` |
| `lab/loop/builders.py` | turn an experiment's `build_spec` into a sliced build entry |
| `lab/loop/witness.py`, `lab/loop/tabs.py` | witness wall and version-ID tab geometry |
| `lab/loop/capabilities.py` | `CAP-BAMBU-HEIGHT-RANGE`, `CAP-TAB-ISOLATION`, results in `capabilities/<bambu-version>.json` |
| `lab/factors.json` | factor allowlist and each factor's kind and scope |
| `lab/cli_loop.py` | `question`, `exp`, `setup`, `photos` subcommands, registered from `lab/cli.py` |
| `lab/adapters/threemf.py`, `lab/adapters/bambu.py` | small additions (settings patch, height ranges, estimate) |

The existing `lab/experiments.py` stays for the Stage 1A `lab plan` command; new code doesn't use its `Experiment`
dataclass.

---

## Phase 1: the vertical path

### Task 1: Records store

**Files:**
- Create: `lab/records/__init__.py`, `lab/records/store.py`, `lab/records/project.py`
- Test: `tests/test_records_store.py`

**Interfaces:**
- Produces:
  - `class RecordError(ValueError)` with `.path`, `.field`, `.message`.
  - `atomic_write_json(path: Path, obj: dict) -> None`.
  - `read_json(path: Path) -> dict` (raises `RecordError` naming file and line for invalid JSON).
  - `record_lock(lock_dir: Path, record_id: str, command: str, timeout_s: float = 10.0)` context manager; on timeout raises `RecordError` "E-004 is being changed by `<command>` (PID <pid>, since <time>)".
  - `create_record(lock_dir: Path, folder: Path, prefix: str, make_record: Callable[[str], dict], width: int = 3) -> tuple[str, Path]`: under `id-allocation.lock`, choose the next unused ID, build the complete record with `make_record(new_id)`, validate it (Task 2 plugs in through an optional `validate` argument), write a temp file and atomically link it into place with `os.link` (fails if the name exists), then remove the temp. **A crash before the link leaves no record.** Project-level IDs only: `Q`, `E`, `P`, `SET`.
  - `next_local_id(record: dict, key: str, prefix: str) -> str`: IDs embedded in an experiment (`BLD-004-NN`, `PR-004-NN`), chosen while holding that experiment's record lock. Migrated print runs keep their old IDs (PR-001..PR-006).
  - `parse_budget(text: str) -> dict` → `{"minutes": float | None, "g": float | None}`.
  - `ProjectPaths(root: Path)` with `.questions`, `.experiments`, `.prints`, `.sliced`, `.jobs`, `.photos`, `.sources`, `.locks`, `.setup_log`, `.setup_repairs`, `.project_json`; `project_settings(paths) -> dict` with defaults `{"autonomy_level": 2, "plate_time_tolerance_pct": 10, "plate_time_tolerance_source": "provisional", "budget": {...defaults}}`.

- [ ] **Step 1: Write the failing tests**

```python
def test_atomic_write_leaves_original_when_replace_fails(tmp_path, monkeypatch):
    p = tmp_path / "E-001.json"; atomic_write_json(p, {"a": 1})
    monkeypatch.setattr(os, "replace", lambda *a: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError): atomic_write_json(p, {"a": 2})
    assert json.loads(p.read_text()) == {"a": 1}
    assert [f.name for f in tmp_path.iterdir()] == ["E-001.json"]   # temp file removed

def test_invalid_json_names_file_and_line(tmp_path):
    p = tmp_path / "E-002.json"; p.write_text('{"a": 1,\n "b": }')
    with pytest.raises(RecordError, match=r"E-002.json.*line 2"): read_json(p)

def test_lock_timeout_names_holder(tmp_path):
    # hold the lock from a child process running `sleep 5` inside record_lock(..., command="lab exp verdict E-004")
    with pytest.raises(RecordError, match=r"lab exp verdict E-004.*PID \d+"):
        with record_lock(tmp_path, "E-004", "lab exp observe E-004", timeout_s=0.5): pass

def test_parallel_allocation_never_collides(tmp_path):
    # 8 processes call create_record(..., prefix="E") at once
    assert sorted(names) == [f"E-{i:03d}.json" for i in range(1, 9)]

def test_crash_before_link_leaves_no_record(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "link", lambda *a: (_ for _ in ()).throw(OSError("killed")))
    with pytest.raises(OSError): create_record(tmp_path / ".locks", tmp_path, "E", lambda i: {"id": i})
    assert not list(tmp_path.glob("E-*.json"))

def test_local_ids(): assert next_local_id({"builds": [{"id": "BLD-004-01"}]}, "builds", "BLD-004") == "BLD-004-02"

@pytest.mark.parametrize("text,want", [("180m,100g", {"minutes": 180, "g": 100}), ("3h", {"minutes": 180, "g": None}),
                                       ("2h30m", {"minutes": 150, "g": None}), ("100g", {"minutes": None, "g": 100})])
def test_parse_budget(text, want): assert parse_budget(text) == want

def test_budget_without_units_refused():
    with pytest.raises(ValueError, match="units"): parse_budget("180,100")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_records_store.py -q`
Expected: FAIL (ImportError: `lab.records.store`)

- [ ] **Step 3: Implement `lab/records/store.py` and `lab/records/project.py`**

Temp file via `tempfile.NamedTemporaryFile(dir=path.parent, delete=False)`, `fsync`, `os.replace`; remove the temp
file in `finally` if it still exists. Lock: open `<lock_dir>/<id>.lock`, poll `fcntl.flock(LOCK_EX | LOCK_NB)` every
0.1 s; on success truncate and write `{pid, command, started_at}`; on timeout read the file for the message.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_records_store.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add lab/records tests/test_records_store.py
git commit -m "Records store: atomic JSON, locks, ID allocation, budgets"
```

### Task 2: Record validators

**Files:**
- Create: `lab/records/schema.py`
- Test: `tests/test_records_schema.py`

**Interfaces:**
- Consumes: `RecordError`, `read_json` (Task 1).
- Produces: `validate(record: dict, record_type: str, path: Path) -> dict` (returns the record; raises `RecordError` with field path such as `variants[1].factor_value`); `load(path: Path, record_type: str) -> dict` = `validate(read_json(path), ...)`; constants `STATUSES`, `PROVENANCES = ("prospective", "migrated", "post_hoc")`, `STRENGTHS = ("slightly", "clearly", "a lot")`, `VERDICT_KINDS = ("ranking", "inconclusive", "acceptance")`, `WITNESS_CONDITIONS`, `ANCHOR_CONDITIONS = ("same", "different", "inconclusive")`.

The experiment shape is the spec's "Experiment" section plus two fields this plan adds: `build_spec` (Task 6) and
`reference_variants: list[str]` (variant IDs from earlier experiments that may appear in `order`). Unknown top-level
keys are refused (so typos surface). Optional fields may be absent or `null`.

- [ ] **Step 1: Write the failing tests**

```python
def test_wrong_record_type_refused_before_fields(tmp_path):
    with pytest.raises(RecordError, match="is a question record, not an experiment"):
        validate({"schema": 1, "record_type": "question", "id": "Q-001"}, "experiment", tmp_path / "E-009.json")

def test_bad_field_named_with_path(tmp_path):
    e = minimal_experiment(); e["variants"][1]["tab"] = 4
    with pytest.raises(RecordError, match=r"variants\[1\]\.tab"): validate(e, "experiment", tmp_path / "E-009.json")

def test_unknown_key_refused(tmp_path):
    e = minimal_experiment(); e["verdcit"] = {}
    with pytest.raises(RecordError, match="unknown field 'verdcit'"): validate(e, "experiment", tmp_path / "E-009.json")

def test_bad_provenance_and_strength(tmp_path): ...   # 'guessed' provenance and 'very' strength each refused

def test_question_stops_shape(tmp_path): ...          # an entry with resumed_at but no resume refused
```

`minimal_experiment()` lives in `tests/loop_fixtures.py` (shared by later tasks): a prospective two-variant
height-strip experiment E-009 in Q-009 with `expect = {"better": "E-009-B", "than": "E-009-A", "min_strength": "clearly"}`.

- [ ] **Step 2: Run — Expected: FAIL (ImportError)**  `uv run pytest tests/test_records_schema.py -q`
- [ ] **Step 3: Implement `lab/records/schema.py`** as small per-type field tables (`name -> (type, required, allowed values)`) plus nested checks for `variants`, `builds`, `print_runs`, `owner_verdict`, `anchors`, `stops`, `plans`.
- [ ] **Step 4: Run — Expected: PASS**
- [ ] **Step 5: Commit** `git commit -m "Record validators per record type"`

### Task 3: Migrate EXP-001..EXP-004 and create Q-001

**Files:**
- Create: `lab/records/migrate.py`
- Modify: `lab/cli_loop.py` (create; register `lab migrate --project P`), `lab/cli.py` (call `cli_loop.register(sub)`)
- Test: `tests/test_migrate.py` (copies `projects/hex-tile` into `tmp_path` and migrates the copy)

**Interfaces:**
- Consumes: Tasks 1–2; `lab.analysis.gcode.read_layers`; `lab.adapters.bambu.extract_gcode`.
- Produces: `migrate_project(paths: ProjectPaths) -> list[str]` (report lines; idempotent: a second run reports "already migrated" and writes nothing); `lab.loop.plate.layer_time_profile(gcode: str) -> list[list[float]]` (`[[z, seconds], ...]`, from `read_layers`) and `median_layer_time(profile, z_range=None) -> float` — created here in `lab/loop/plate.py`, extended in Task 10.

What migration writes (spec "Moving the existing records"; no invented facts):
- copies `hexagon_v56_X2D_0.6nozzle.3mf`, `hexagon_v57_X2D_0.4nozzle.3mf`, `hexagon_v58_X2D_0.6nozzle.3mf` from `tests/fixtures/hex/` into `sources/` and records each in `sources/sources.json` as `{"path", "sha256", "source": "migration_fixture"}`; where an existing record already holds a hash of the same file (the history inventory), migration asserts it matches. From then on the project copy is the durable source;
- `questions/Q-001.json` ("What causes the bands on v58's face?", default budget, experiments E-001..E-004, `stops: []`, one plan `P-001` from E-004's record: if two-object plate rougher → "one pair per plate vs minimum layer time");
- each experiment: `provenance` (E-001..E-003 `migrated`, E-004 `prospective`), `builds` reconstructed from the existing print files and sliced files (with `measured.layer_time_profile`), `print_runs` with the recorded start and `setup` = what was recorded (E-004's send-dialog values) else `null`;
- E-001: `owner_verdict` ranking `[["E-001-B"], ["E-001-A"]]` (v58 above v56), strength `null`, `about_target: null`, note = the owner's words;
- E-002: no `owner_verdict` against E-001 as a controlled test; `analysis: [{"claim": "plate layout (1 object, 18.4 s/layer vs 34.8 s) may explain the difference", "provenance": "post_hoc"}]`; the owner's words kept as a note;
- E-004: `reference_variants: ["E-002-A"]`, `expect = {"better": "E-002-A", "than": "E-004-A", "min_strength": "clearly"}` (the record's prediction: two-object strips rougher), `judge_on: "bands"`, factor `objects_on_plate`;
- old ad-hoc keys (`result`, `send_dialog`, …) move under `legacy` so nothing is lost; the old `print_runs` IDs (PR-001..PR-006) are kept.

- [ ] **Step 1: Write the failing tests**

```python
def test_migration_creates_q001_and_validates(migrated):
    q = load(migrated.questions / "Q-001.json", "question")
    assert q["experiments"] == ["E-001", "E-002", "E-003", "E-004"]
    for e in q["experiments"]: load(migrated.experiments / f"{e}.json", "experiment")

def test_provenance(migrated):
    assert [exp(migrated, i)["provenance"] for i in (1, 2, 3, 4)] == ["migrated"] * 3 + ["prospective"]

def test_e001_strength_unknown_and_e002_analysis_post_hoc(migrated):
    assert exp(migrated, 1)["owner_verdict"]["strength"] is None
    assert exp(migrated, 2)["analysis"][0]["provenance"] == "post_hoc"

def test_layer_times_measured(migrated):
    m1 = exp(migrated, 1)["builds"][-1]["measured"]["layer_time_median_s"]
    m2 = exp(migrated, 2)["builds"][-1]["measured"]["layer_time_median_s"]
    assert m1 == pytest.approx(34.8, abs=0.5) and m2 == pytest.approx(18.4, abs=0.5)

def test_migration_is_idempotent(migrated):
    assert migrate_project(migrated) == ["already migrated"]
```

- [ ] **Step 2: Run — Expected: FAIL**  `uv run pytest tests/test_migrate.py -q`
- [ ] **Step 3: Implement** `migrate_project` and `layer_time_profile`; register `lab migrate`.
- [ ] **Step 4: Run — Expected: PASS**
- [ ] **Step 5: Run it on the real project and commit the result**

Run: `uv run lab migrate --project hex-tile && uv run lab migrate --project hex-tile`
Expected: a report of what was written, then "already migrated".

```bash
git add lab tests projects/hex-tile
git commit -m "Migrate E-001..E-004 into Q-001 (migrated/prospective, analysis post_hoc)"
```

### Task 4: Outcome, validity and ledger

**Files:**
- Create: `lab/loop/__init__.py`, `lab/loop/outcome.py`, `lab/loop/ledger.py`
- Test: `tests/test_outcome.py`, `tests/test_ledger.py`

**Interfaces:**
- Consumes: record dicts (Task 2).
- Produces:
  - `prediction_outcome(exp: dict, validity: dict) -> str` — the spec's outcome table exactly, then provenance demotion (`migrated`/`post_hoc` → `supported`/`refuted` become `unresolved`); returns `None` with no owner verdict.
  - `comparison_validity(exp: dict, others: dict[str, dict], tolerance_pct: float) -> dict` — `{"status": "valid"|"confounded"|"unknown", "reasons": [{"code": ...}]}`; Phase 1 codes: `witness_abnormal`, `witness_inconclusive`, `anchor_shifted`, `anchor_inconclusive`, `layer_time_mismatch` (whole judged region median, Task 10 refines to layer-by-layer), skipped when the factor's kind is `plate`.
  - `run_usage(run: dict, build: dict) -> tuple[float, float]` — the spec's order (telemetry, manual, fraction × estimate, estimate); `(0, 0)` for a run not started.
  - `spent(question: dict, exps: dict[str, dict]) -> dict` (`{"minutes", "g"}`).
  - `streak(question: dict, exps: dict[str, dict]) -> int` — answered prospective experiments ordered by verdict time, after the latest `resumed_at`.
  - `auto_stop(question: dict, exps: dict[str, dict]) -> dict | None` — `{"code", "message", "triggered_by"}` for `uninformative_streak`, `budget_time_exhausted`, `budget_material_exhausted`.
  - `owner_stopped(question: dict) -> dict | None` — the open entry in `stops`.

- [ ] **Step 1: Write the failing tests**

```python
# one test per row of the spec's outcome table, for both expect forms, e.g.:
@pytest.mark.parametrize("order,strength,about,want", [
    ([["B"], ["A"]], "clearly", True, "supported"), ([["B"], ["A"]], "slightly", True, "unresolved"),
    ([["A", "B"]], "clearly", True, "refuted"), ([["A"], ["B"]], "clearly", True, "refuted"),
    ([["B"], ["A"]], "clearly", None, "unresolved")])
def test_outcome_better_than(order, strength, about, want): ...

@pytest.mark.parametrize("order,strength,about,want", [
    ([["A", "B"]], None, True, "supported"), ([["A", "B"]], None, None, "unresolved"),
    ([["B"], ["A"]], "slightly", True, "unresolved"), ([["B"], ["A"]], "clearly", True, "refuted")])
def test_outcome_same(order, strength, about, want): ...

def test_abnormal_witness_forces_inconclusive_unless_overridden(): ...
def test_migrated_supported_becomes_unresolved(): ...
def test_anchor_different_confounds_and_inconclusive_unknown(): ...
def test_layer_time_mismatch_not_a_confound_when_plate_is_the_factor(): ...

# ledger
def test_failed_run_charged_by_fraction(): assert run_usage(failed_40, build_50min_20g) == (20.0, 8.0)
def test_two_unresolved_stop(): assert auto_stop(q, exps(["unresolved", "unresolved"]))["code"] == "uninformative_streak"
def test_refuted_between_resets(): assert auto_stop(q, exps(["unresolved", "refuted", "unresolved"])) is None
def test_failed_print_does_not_touch_streak(): ...
def test_migrated_experiments_ignored_by_streak(): ...
def test_resume_resets_streak(): ...
def test_spent_equal_to_budget_stops(): assert auto_stop(q_180, exps_spent(180))["code"] == "budget_time_exhausted"
```

- [ ] **Step 2: Run — Expected: FAIL**  `uv run pytest tests/test_outcome.py tests/test_ledger.py -q`
- [ ] **Step 3: Implement** as pure functions (no file access).
- [ ] **Step 4: Run — Expected: PASS**
- [ ] **Step 5: Commit** `git commit -m "Derived outcome, comparison validity, spend, streak and stops"`

### Task 5: `lab exp verdict`, `lab exp usage`, `lab question status/show` — EXP-004 acceptance

**Files:**
- Modify: `lab/cli_loop.py`
- Create: `lab/loop/commands.py` (command logic, separate from argparse)
- Test: `tests/test_commands_verdict.py`

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces:
  - `record_verdict(paths, exp_id, *, rank: str | None, strength: str | None, inconclusive: str | None, accept: bool | None, defects: list[str], marks: list[str], witness: str | None, witness_override: str | None, anchors: list[str], not_about_target: bool, note: str | None, replace: bool, runs: list[str] | None) -> dict` (the updated experiment).
  - `record_usage(paths, run_id: str, *, failed_at_pct: float | None, minutes: float | None, grams: float | None) -> dict`.
  - `question_status(paths, q_id: str) -> str` (the text block from the spec / review: budget used and after the next ready test, experiments with status and outcome, evidence counts, stop state, next step from `plans`).
  - Rank syntax: `"B>A"`, `"B>A=C"` (`=` groups), letters or tabs (`4A`) or full IDs; marks `A:6` (strip mm) → `defect_z_mm` = strip start + 6.

Rules: refuse with no started print run (Review Focus 1); unknown variant lists valid IDs and tabs (2);
`--failed-at` must be 1–99 % (3); variants from other experiments only via `reference_variants` (5); a second verdict
needs `--replace` (old one into `superseded_verdicts`); witness required but missing refused; `--accept` only for
`scaled_part`/`full_part`; status becomes `answered`; cached `prediction_outcome` and `comparison_validity` written in
the same atomic write; all under the experiment's lock. The command first prints "Judging on: <judge_on>".

- [ ] **Step 1: Write the failing tests** (on a `tmp_path` copy of the migrated project)

```python
def test_verdict_supported_and_status_answered(proj):  # E-009 started, B>A clearly
    e = record_verdict(proj, "E-009", rank="B>A", strength="clearly", ...)
    assert e["status"] == "answered" and e["prediction_outcome"] == "supported"
def test_verdict_before_start_refused(proj): ...       # match="start it first"
def test_unknown_variant_lists_valid(proj): ...        # match="E-009-A \(9A\), E-009-B \(9B\)"
def test_failed_at_out_of_range(proj): ...             # 140 and 0 refused
def test_reference_variant_needs_listing(proj): ...
def test_second_verdict_needs_replace_and_keeps_old(proj): ...
def test_mark_stored_in_model_height(proj): assert marks[0] == {"variant": "E-009-A", "mark_z_mm": 6.0, "defect_z_mm": 66.0}
def test_unknown_experiment_lists_valid_ids(proj): ...   # match="E-009 isn't in hex-tile. Experiments: E-001, …"
def test_status_shows_spend_outcome_and_next_plan(proj): assert "Next" in text and "P-001" in text
```

- [ ] **Step 2: Run — Expected: FAIL**  `uv run pytest tests/test_commands_verdict.py -q`
- [ ] **Step 3: Implement** `record_verdict`, `record_usage`, `question_status`, and wire `lab exp verdict`, `lab exp usage`, `lab question status`, `lab question show`.
- [ ] **Step 4: Run — Expected: PASS**, then the full suite `uv run pytest -q` — Expected: all pass.
- [ ] **Step 5: Commit** `git commit -m "Verdicts, usage and question status"`
- [ ] **Step 6: EXP-004 acceptance (with the owner)**

With the owner's EXP-004 judgment (both two-object strips against the E-002 strip, under the diagnostic light):
`uv run lab exp verdict E-004 --rank "<from the owner>" --strength <from the owner> [--mark …]`, then
`uv run lab question status Q-001`.
Expected: E-004 `answered` with a derived outcome (`supported` if the two-object strips are clearly rougher, `refuted`
if not); status shows spend for Q-001 and the next plan. Commit the record: `git commit -m "E-004 verdict"`.

### Task 6: `lab exp plan` and `lab exp build` (height strips, settings patch, objects on plate)

**Files:**
- Create: `lab/factors.json`, `lab/loop/builders.py`
- Modify: `lab/adapters/threemf.py` (`write_print_3mf(..., settings_patch: dict | None = None)`), `lab/adapters/bambu.py` (`slice_estimate(sliced: Path) -> tuple[float, float]` in minutes and grams, moved out of `cli.cmd_slice`), `lab/loop/commands.py`, `lab/cli_loop.py`
- Test: `tests/test_builders.py` (fast: plan + build with a fake slicer), `tests/test_builders_slow.py` (real Bambu)

**Interfaces:**
- Consumes: Tasks 1–5; `height_strip`, `plate_layout`, `load_object`, `slice_with_job`, `extract_gcode`, `layer_time_profile`.
- Produces:
  - `lab/factors.json`: `{"<name>": {"kind": "setting"|"plate"|"model_version"|"model_parameter"|"filament_profile", "scope": "specific"|"bundle", "settings_key": "...?"}}` with: `inner_wall_speed`, `outer_wall_speed`, `nozzle_temperature`, `fan_min_speed`, `fan_max_speed`, `slow_down_layer_time`, `retraction_length`, `wall_loops` (all `setting`, specific); `objects_on_plate` (`plate`, specific); `model_version`, `filament_profile` (bundle); `model_parameter` (specific, needs a `.scad` source).
  - `plan_experiment(paths, q_id, *, factor, values, expect, judge_on, test_kind, source, object, z, base, hypothesis, prediction, why) -> str` (new E id; writes the experiment, then the question).
  - `build_spec` on the experiment: `{"kind": "height_strip", "source": "sources/<file>", "object": "...", "z": [z0, z1], "base": "sources/<file>", "variants": [{"id", "tab", "settings_patch": {...}, "copies": n}], "witness": false}`.
  - `build_experiment(paths, exp_id, *, replace: bool, slicer=slice_with_job) -> dict` (the new build entry): fingerprints `{model, settings, build_spec_sha256, builder_version, builder_fingerprint, openscad, bambu_studio}`, where `build_spec_sha256` hashes the canonical JSON (`sort_keys`, no spaces) of `build_spec` plus `factor` and `dependent_adjustments`, and `builder_fingerprint` hashes the source of `lab/loop/builders.py`, `witness.py`, `tabs.py`, `lab/adapters/threemf.py` and `lab/geometry/coupons.py` (those that exist); writes artifact (`prints/<project>_<E>_<BLD>.3mf`), job, manifest line, then the experiment; reads `slice_estimate` and `layer_time_profile`; records `plate.objects`/`placements`; failed slice → build `ok: false`, status `build_failed`; unchanged fingerprints → "already built", no writes; changed without `--replace` → refuse.
  - `BUILDER_VERSION = "1a1.1"` in `builders.py` (readable; staleness doesn't depend on remembering to bump it).
  - A comment at the top of `lab/experiments.py`: legacy Stage 1A record for `lab plan`; must not be imported by `lab.loop`.

- [ ] **Step 1: Write the failing tests**

```python
def test_plan_writes_experiment_then_question(proj): ...
def test_plan_refuses_two_factors_and_unknown_factor(proj): ...
def test_plan_refused_at_level_0(proj): ...
def test_build_records_estimate_profile_plate_and_fingerprints(proj, fake_slicer): ...
def test_build_again_unchanged_writes_nothing(proj, fake_slicer): ...
def test_build_spec_change_alone_makes_build_stale(proj, fake_slicer): ...   # same model and settings, a copies change
def test_build_changed_needs_replace_and_keeps_old(proj, fake_slicer): ...
def test_failed_slice_is_build_failed_with_job_kept(proj, failing_slicer): ...
def test_settings_patch_lands_in_3mf(proj, fake_slicer):
    assert read_settings(artifact)["inner_wall_speed"][0] == "80"

@pytest.mark.slow
def test_real_build_of_two_v58_strips_matches_e004(proj):
    b = build_experiment(proj, eid, replace=False)
    assert b["estimate"]["minutes"] == pytest.approx(62, abs=3)
    assert b["measured"]["layer_time_median_s"] == pytest.approx(34.8, abs=1.5)
```

`fake_slicer` copies a stored sliced fixture (`tests/fixtures/hex/studio_saved_v58_strip.gcode.3mf`) to the expected
output and returns a fake `Job`.

- [ ] **Step 2: Run — Expected: FAIL**  `uv run pytest tests/test_builders.py -q`
- [ ] **Step 3: Implement** the factor table, `plan_experiment`, `build_experiment`, the settings patch and `slice_estimate`; wire `lab exp plan` and `lab exp build`.
- [ ] **Step 4: Run — Expected: PASS** (fast), then `uv run pytest tests/test_builders_slow.py -q` — Expected: PASS
- [ ] **Step 5: Commit** `git commit -m "Plan and build experiments (height strips, settings patch, objects on plate)"`

### Task 7: Setup log

**Files:**
- Create: `lab/loop/setup_log.py`
- Modify: `lab/cli_loop.py` (`lab setup log KIND --key value …`, `lab setup repair --line N --event JSON --reason …`, `lab setup show`)
- Test: `tests/test_setup_log.py`

**Interfaces:**
- Produces: `append_event(paths, kind: str, fields: dict) -> dict` (new `SET-NNNNN`: next number after the log's highest, chosen and appended under `id-allocation.lock`); `repair_line(paths, line_no: int, replacement: dict, reason: str) -> dict`; `effective_events(paths) -> list[dict]` (repairs, then corrections, per the spec's reducer); `current_setup(paths, at: str | None = None) -> dict` (`{kind: latest effective event}` up to `at`).

- [ ] **Step 1: Write the failing tests**

```python
def test_correction_supersedes_at_original_time(paths): ...
def test_malformed_line_stops_reading_until_repaired(paths): ...   # RecordError names the line; after repair, readable
def test_repair_applies_only_when_hash_matches(paths): ...
def test_current_setup_at_a_past_time(paths): ...                 # history doesn't move when later events arrive
def test_original_bytes_never_change(paths): ...
```

- [ ] **Step 2: Run — Expected: FAIL**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run — Expected: PASS**
- [ ] **Step 5: Commit** `git commit -m "Setup log: events, corrections, repairs, current setup"`

### Task 8: Actual-difference check

**Files:** Create `lab/loop/diff.py`; modify `lab/loop/guards.py`; test `tests/test_diff.py`.

**Interfaces:** `actual_differences(paths, exp: dict, build: dict) -> list[dict]` — each `{"where": "settings"|"plate"|"geometry", "key", "a", "b"}` between variant pairs (settings from each variant's effective settings: base + patch; plate from objects/placements excluding the mirror swap; geometry from mesh fingerprints and, for `.scad` sources, differing `-D` parameters); `undeclared(diffs, exp, factors) -> list[dict]` (drops the factor's key and declared `dependent_adjustments`); bundle factors write `factor_scope: "bundle"` and `bundle_differences` on the build. Guard `undeclared_difference` → `blocked`; Task 9's `check_experiment` and `start` call it.

- [ ] **Step 1: Failing tests:** `test_undeclared_setting_found`, `test_declared_dependent_adjustment_allowed`, `test_undeclared_plate_change_found`, `test_undeclared_geometry_change_found`, `test_bundle_factor_records_scope_and_list` (Task 9 adds the guard-level tests, including `test_blocked_again_at_start_after_hand_edit`).
- [ ] **Step 2: Run — FAIL.**  **Step 3: Implement.**  **Step 4: Run — PASS; full suite PASS.**
- [ ] **Step 5: Commit** `git commit -m "Actual-difference check (one factor, enforced on the build)"`

### Task 9: `lab exp check`, `lab exp approve`, `lab exp start` — E-005 through the new path

**Files:**
- Create: `lab/loop/guards.py`
- Modify: `lab/loop/commands.py`, `lab/cli_loop.py`
- Test: `tests/test_guards.py`, `tests/test_commands_start.py`

**Interfaces:**
- Consumes: Tasks 1–7.
- Produces:
  - `@dataclass Guard: code: str; ok: bool; result: str  # "blocked" | "needs_approval" | "rebuild"; message: str`.
  - `check_experiment(paths, exp_id) -> CheckResult` with `.status` (`ready` | `needs_approval` | `blocked` | `rebuild`), `.guards: list[Guard]`, `.text` (the spec's check layout: build, question budget used and after, each guard ✓/✗, result, every reason).
  - Phase 1 guards (spec table): `owner_stopped`, `auto_stopped`, `full_part_required`, `autonomy_level`, `refuted_dependency`, `undeclared_difference` (Task 8, blocked), `per_test_time`, `per_test_material`, `question_time`, `question_material` (strict `>`: equal fits), `retry_limit`, `stale_build` (recomputed fingerprints vs the build's), `no_estimate`, the Stage 1A blocking geometry checks on each variant mesh, and a **preliminary `plate_mismatch`**: the judged-region median layer time (Task 4's calculation) against each plate the experiment is compared with, beyond the project tolerance → needs approval, and `comparison_validity` stays confounded. Task 10 replaces the calculation with the layer-by-layer comparison.
  - `approve(paths, exp_id, reason: str) -> dict` (binds `build_id`, `artifact_sha256`, `approved_reasons`); refuses unless `needs_approval`; refuses on an owner stop.
  - `start(paths, exp_id) -> dict` (new `PR-NNN` print run): re-runs `check_experiment`; proceeds if `ready`, or `needs_approval` whose failed guards ⊆ a matching approval's `approved_reasons` (same build ID and fingerprint); snapshots `current_setup`; warns on missing baseline kinds (`filament_dried`, `vibration_calibration`, `nozzle_changed`) and records them; already `printing` → message, no write.
  - Exit codes: `check` 0 ready, 2 otherwise.

- [ ] **Step 1: Write the failing tests**

```python
def test_each_guard(proj): ...                       # parametrized: one failing condition per guard code
def test_undeclared_difference_blocks_check_and_start(proj): ...
def test_blocked_again_at_start_after_hand_edit(proj): ...
def test_preliminary_plate_mismatch_needs_approval_and_stays_confounded(proj): ...
def test_every_failure_listed(proj): ...             # full part + over per-test time → both reasons
def test_exact_budget_boundary_fits(proj): ...       # remaining 25 min, estimate 25 → ready
def test_owner_stop_cannot_be_approved_away(proj): ...
def test_approval_does_not_survive_rebuild(proj, fake_slicer): ...
def test_start_rechecks_live_state(proj): ...        # ready, then budget used elsewhere → start refuses
def test_start_snapshots_setup_and_warns_baseline(proj): ...
def test_start_twice_writes_nothing(proj): ...
def test_failed_run_returns_to_built_and_third_attempt_needs_approval(proj): ...
```

- [ ] **Step 2: Run — Expected: FAIL**  `uv run pytest tests/test_guards.py tests/test_commands_start.py -q`
- [ ] **Step 3: Implement**; wire `lab exp check`, `lab exp approve`, `lab exp start`.
- [ ] **Step 4: Run — Expected: PASS**, then `uv run pytest -q` — Expected: all pass.
- [ ] **Step 5: Commit** `git commit -m "Check, approve and start, with live re-check"`
- [ ] **Step 6: Review checkpoint 1** (fresh review of Tasks 1–9 on the most capable model; fix Critical and Important findings test-first; full suite green).
- [ ] **Step 7: E-005 acceptance**

Plan the next test from Q-001's selected plan (after the E-004 verdict) with `lab exp plan`, then `lab exp build`,
`lab exp check`, hand the sliced file to the owner, `lab exp start` when the owner sends it.
Expected: every step succeeds through the new commands; `lab question status Q-001` shows E-005 printing and the
budget after it. Commit the records.

---

## Phase 2: the remaining guards, builders and safeguards

### Task 10: Plate matching over the judged heights

**Files:** Modify `lab/loop/plate.py`, `lab/loop/outcome.py`, `lab/loop/guards.py`, `lab/loop/builders.py`; test `tests/test_plate.py`.

**Interfaces:** `judged_window(exp: dict) -> tuple[float, float]` (the strip's judged region in strip heights, or `defect_z ± 10` mapped to strip heights); `plates_match(profile_a, profile_b, window, tolerance_pct) -> dict` (`{"match": bool, "worst_pct": float, "at_z": float}`, comparing per-layer times over the window by their medians in 1 mm bins); guard `plate_mismatch` (still needs approval; skipped when the factor's kind is `plate`); `comparison_validity` and the `plate_mismatch` guard use `plates_match` instead of the Phase 1 judged-region median; mirrored placements on repeat builds (`placements` swapped when the experiment already has a build with the same variants); production match flag when `project.json` names `production_plate` (objects per plate) and the judged-window medians differ by more than the tolerance (reported as a warning reason `production_mismatch`).

- [ ] **Step 1: Failing tests:** `test_equal_medians_but_window_mismatch_caught`, `test_approval_leaves_mismatch_confounded`, `test_plate_factor_not_a_confound`, `test_repeat_build_mirrors_placements`, `test_production_mismatch_flagged`.
- [ ] **Steps 2–4:** FAIL → implement → PASS; full suite PASS.
- [ ] **Step 5: Commit** `git commit -m "Plate matching over judged heights"`

### Task 11: Question lifecycle and rebuild

**Files:** Modify `lab/loop/commands.py`, `lab/cli_loop.py`; test `tests/test_question_lifecycle.py`.

**Interfaces:** `new_question(paths, text, budget) -> str` (refuses an open question with the same text); `stop_question(paths, q_id, reason)`; `resume_question(paths, q_id, add: dict | None, reason)` (fills the open entry; an automatic stop is lifted by `--add`, recorded as an entry with `reason: "auto"`); `rebuild_question(paths, q_id) -> list[str]` (validates every record first; any problem → full report, **no writes**; otherwise refreshes cached `prediction_outcome` and `comparison_validity`; reports orphaned artifacts in `prints/` and experiments not listed in the question); `abandon(paths, exp_id, reason)`; `observe(paths, exp_id, observation: dict)` (appends to `ai_observations` with `confirmed: false`).

- [ ] **Step 1: Failing tests:** `test_duplicate_open_question_refused`, `test_stop_then_resume_keeps_history`, `test_auto_stop_lifted_by_add`, `test_rebuild_matches_step_by_step_state`, `test_rebuild_with_invalid_record_writes_nothing`, `test_rebuild_reports_orphans_and_unattached`, `test_observations_never_change_outcome_or_streak`.
- [ ] **Steps 2–4:** FAIL → implement; wire `lab question new|stop|resume|rebuild`, `lab exp abandon|observe` → PASS; full suite PASS.
- [ ] **Step 5: Commit** `git commit -m "Question lifecycle and rebuild"`

### Task 12: Witness wall and anchors

**Files:** Create `lab/loop/witness.py`; modify `lab/loop/builders.py`, `lab/loop/outcome.py`; test `tests/test_witness_anchor.py`.

**Interfaces:** `witness_wall(height_mm: float, line_w: float) -> trimesh.Trimesh` (`WITNESS-01`: 40.0 mm long, 2 × `line_w` thick, fixed orientation along Y); `WITNESS_VERSION = "WITNESS-01"`; builder places it at least 25 mm from the nearest piece (refuses if the plate can't fit it); default `controls.witness_required` = true when `reference_variants` or an anchor spans another plate, false when all variants share the plate; `build_spec.anchor = {"same_as": "E-002-A"}` rebuilds that variant from its original build's inputs at its original placement (refuses if those inputs' fingerprints changed).

- [ ] **Step 1: Failing tests:** `test_witness_geometry_and_version`, `test_witness_spacing_refusal`, `test_witness_default_on_cross_plate_off_same_plate`, `test_anchor_reuses_original_inputs_and_placement`, `test_anchor_with_changed_inputs_refused`.
- [ ] **Steps 2–4:** FAIL → implement → PASS; full suite PASS.
- [ ] **Step 5: Commit** `git commit -m "Witness wall WITNESS-01 and anchors"`

### Task 13: Version-ID tabs and stepped settings, each behind a capability test

**Files:** Create `lab/loop/tabs.py`, `lab/loop/capabilities.py`, `lab/scad/id_tab.scad`; modify `lab/adapters/threemf.py` (height-range modifiers), `lab/loop/builders.py`; test `tests/test_tabs_steps.py`, `tests/test_capabilities_slow.py`.

**Interfaces:**
- `id_tab(text: str, jobs_dir: Path) -> trimesh.Trimesh` (OpenSCAD `text()`; 10 × 6 × 1 mm base, 0.6 mm raised text, thin bridge to the strip end; total height ≤ 1.6 mm = 8 layers at 0.2 mm); builder attaches one per variant only after `CAP-TAB-ISOLATION` passed.
- `write_print_3mf(..., height_ranges: dict[str, list[tuple[float, float, dict]]] | None = None)` writing Bambu Studio's per-object height-range settings (believed to be `Metadata/layer_config_ranges.xml`; the capability test is the proof).
- `run_capability(name: str, paths) -> dict` → `capabilities/<bambu-version>.json` entry `{"name", "passed", "at", "evidence"}`; `capability_passed(name) -> bool`.
- `CAP-BAMBU-HEIGHT-RANGE`: a strip with inner walls 250 mm/s below and 80 mm/s above the middle; passes only if the G-code's inner-wall speeds change at the boundary within one layer.
- `CAP-TAB-ISOLATION`: the same plate with and without tabs; passes if judged-region layer times are within 2 % and speeds and fan identical.
- Stepped builds: with the height-range capability passed, one stepped strip plus its reversed twin on one plate; otherwise separate strips on one plate, and the build says so.

- [ ] **Step 1: Failing tests:** `test_tab_size_and_eight_layer_limit`, `test_tabs_refused_before_capability`, `test_stepped_falls_back_to_separate_strips`, `test_stepped_with_capability_makes_twin_reversed`; slow: `test_cap_height_range_against_real_slice`, `test_cap_tab_isolation_against_real_slice`.
- [ ] **Steps 2–4:** FAIL → implement → PASS (fast and slow); full suite PASS.
- [ ] **Step 5: Run both capabilities for 02.08.02.61 and commit their results** `git commit -m "ID tabs and stepped settings behind capability tests"`

### Task 14: Photos

**Files:** Modify `lab/loop/commands.py`, `lab/cli_loop.py`, `.gitignore` (`projects/*/photos/`); test `tests/test_photos.py`.

**Interfaces:** `add_photos(paths, run_id: str, files: list[Path]) -> list[dict]` — converts each with `sips -s format jpeg -Z 2400` into `photos/<run>-<n>.jpg` (EXIF orientation kept), records `{"path" (project-relative), "sha256", "captured_at" (from `mdls kMDItemContentCreationDate`, else file mtime), "source"}`; converts all before writing any entry (a failure removes the converted copies and changes nothing).

- [ ] **Step 1: Failing tests:** `test_photo_added_with_relative_path_and_hash`, `test_bad_file_adds_nothing`, `test_unknown_run_lists_valid_runs`.
- [ ] **Steps 2–4:** FAIL → implement → PASS.
- [ ] **Step 5: Commit** `git commit -m "Photos on print runs (outside git)"`

### Task 15: Height strip sized to a budget

**Files:** Modify `lab/loop/builders.py`, `lab/cli_loop.py` (`lab exp plan … --around Z --target-minutes M`); test `tests/test_strip_sizing.py`, slow `tests/test_strip_sizing_slow.py`.

**Interfaces:** `size_strip(paths, source, object, around_z: float, target_minutes: float, base, min_margin_mm: float = 6.0, slicer=slice_with_job) -> tuple[float, float]` — slices candidate strips (margins 6, 8, 10, 12 mm), in this order: (1) keep only **representative** candidates, where no cut-edge effect reaches the judged region (the first and last 3 judged layers' times within 25 % of the judged-region median); (2) among those, return the smallest whose estimate fits; (3) if the smallest representative strip doesn't fit, raise `ValueError` "No representative strip fits <M> min; the smallest is <N> min (margin <m> mm). Raise the budget or test a narrower question." — never fall back to a non-representative strip.

- [ ] **Step 1: Failing tests:** `test_smallest_fitting_strip_chosen` (fake slicer with a time table), `test_margin_grows_on_cut_edge_effect`, `test_no_representative_strip_fits_is_an_error`; slow: `test_real_sizing_around_66_fits_45_min`.
- [ ] **Steps 2–4:** FAIL → implement → PASS.
- [ ] **Step 5: Commit** `git commit -m "Height strips sized to the time budget"`

### Task 16: End-to-end test and usage notes

**Files:** Create `tests/test_e2e_loop_slow.py`; modify `README.md` (a short "Running an experiment" section with the command sequence).

- [ ] **Step 1: Write the end-to-end test** exactly as the spec's Testing section lists it (temporary lab folder via `LAB_HOME`, real Bambu Studio, two v58 variants on one plate), plus: an injected failure before the final replace in `exp build` (original unchanged, orphan reported by `rebuild`), and a mutation while another process holds the experiment's lock (waits, times out, names the holder, changes nothing).
- [ ] **Step 2: Run — Expected: PASS**  `uv run pytest tests/test_e2e_loop_slow.py -q`
- [ ] **Step 3: Run the full suite** `uv run pytest -q` — Expected: all pass.
- [ ] **Step 4: Commit** `git commit -m "End-to-end test of the experiment loop; usage notes"`
