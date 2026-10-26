# Verdicts and photos from the phone: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record photos and a per-strip verdict for a lab print from the phone in Local AI › Projects › Print lab; the
Mac applies them with the lab's own code.

**Architecture:** Two repos.
- **print-lab:** gains per-experiment `criteria`, a `criteria` verdict kind, and `lab pull`, which fetches the phone's
  requests from Local AI, applies them with `record_verdict` / `add_photos`, and reports the result.
- **LocalAI:** stores requests and incoming photos from a paired device, serves pending ones to the Mac key, and
  adds an Add photos button and a Record verdict sheet to the existing Print lab page.

**Tech Stack:** print-lab: Python 3.12, uv, pytest, launchd. LocalAI: Node (no framework), `node:test`, the
browser suite (`tests/run-browser.mjs`), plain JS in `app/public/print-lab.js`.

**Spec:** `docs/superpowers/specs/2026-10-25-print-lab-phone-verdicts-design.md` (approved 25 Oct with the
recommended answers: 60 s pickup; E-012 words clean / flawed / failed and yes / hard / no).

## Global Constraints

- The Mac is the only writer of lab records; Local AI never edits one.
- A request is applied at most once, by its id.
- Request kinds are exactly `verdict` and `photos`. The Mac maps payload fields to named `record_verdict` /
  `add_photos` arguments; nothing else in a payload is passed through.
- Request routes: phone writes need a paired device (`deviceFor(req)`); `GET …/requests?status=pending` and
  `POST …/requests/<id>/result` need the Mac key.
- Limits: request JSON ≤ 4 KB; ≤ 20 pending requests per project (429 with "The Mac hasn't picked up the last 20
  requests. Check that the Mac is awake."); incoming photo ≤ 8 MB, JPEG magic bytes, sha256 must match.
- Pickup every 60 s from launchd (`com.printlab.pull`), and at the start of every `lab sync`; `LAB_SYNC=off` turns
  both off.
- Copy is fixed by the spec: "Waiting for the Mac", "Recorded", "The Mac hasn't picked this up. It runs when the Mac
  is awake." (after 2 minutes), "This phone isn't paired with Local AI. Pair it in Settings › Devices."
- UI uses existing `--ds-*` tokens and components only; the on-demand script stays within its size budget.

## Rulings made while planning

- **Sweep grades stay as they are.** The spec reads old sweep grades as a `bands` criterion; leaving the sweep
  code untouched gives the same "no migration" result with less change. Criteria apply only to experiments that
  declare them. Cost if wrong: a later refactor to merge the two.
- **Grades are stored by variant id** (`E-012-B`), as sweep grades are; tabs (`12B`) are accepted as input. Cost if
  wrong: none for the page, which maps ids to tabs.
- **Photos are converted to JPEG on the phone** (canvas, quality 0.9, longest side 2400 px, as `add_photos` does),
  because iPhone pictures are often HEIC. The Mac still runs `sips` through `add_photos`. Cost if wrong: double
  conversion, slight quality loss.

## Review Focus

1. The phone resends after a timeout with the same request id → stored once, applied once.
2. A verdict request for an experiment that already has one, or isn't printed → refused with the CLI's own message,
   shown on the phone; nothing else changes.
3. launchd pickup and a background `lab sync` pickup run at the same moment → one applies, the other skips.
4. Requests arrive while the Mac sleeps (photos, then a verdict) → applied in the order they were sent.
5. A payload with extra fields (e.g. `approve`, `replace_build`) → those fields are ignored, never passed on.

---

## Part A: print-lab (branch `feat/phone-verdicts`)

### Task 1: Per-experiment criteria

**Files:**
- Modify: `lab/records/schema.py` (EXPERIMENT gets `criteria`; `VERDICT_KINDS` gains `"criteria"`)
- Modify: `lab/loop/commands.py` (new `set_criteria`)
- Modify: `lab/cli_loop.py` (`lab exp criteria`)
- Test: `tests/test_criteria.py`

**Interfaces:**
- Produces: `set_criteria(paths, eid: str, specs: list[str]) -> dict` (returns the saved experiment). A spec string is
  `"key=Label?:choice1,choice2,choice3"`. Stored as `e["criteria"] = [{"key", "label", "choices": [...]}]`.
- Produces: CLI `lab exp criteria E-012 --add "print=Printed cleanly?:clean,flawed,failed" --add "apart=Twists apart by hand?:yes,hard,no"`.

- [x] **Step 1: Write the failing tests**

```python
def test_criteria_are_saved_in_order(project):          # loop_fixtures.make_project with a printing experiment
    e = set_criteria(paths, "E-009", ["print=Printed cleanly?:clean,flawed,failed", "apart=Twists apart by hand?:yes,hard,no"])
    assert e["criteria"] == [{"key": "print", "label": "Printed cleanly?", "choices": ["clean", "flawed", "failed"]},
                             {"key": "apart", "label": "Twists apart by hand?", "choices": ["yes", "hard", "no"]}]

def test_criteria_refused_after_a_verdict(...):        # ValueError mentioning "already has a verdict"
def test_criteria_spec_needs_two_choices_and_a_key(...):  # "print=Label?:clean" and "=x:a,b" raise ValueError naming the format
def test_criteria_keys_are_unique(...):                # two "print=" specs raise ValueError
def test_schema_accepts_criteria_and_rejects_bad_shape(...)  # criteria item without "choices" fails load()
```

- [x] **Step 2: Run** `uv run pytest tests/test_criteria.py -q`. Expected: FAIL (no `set_criteria`).
- [x] **Step 3: Implement** `set_criteria` under `record_lock`, the schema field (`F(L, each=F(D, fields=CRITERION))`
  with `CRITERION = {"key": F(S, True), "label": F(S, True), "choices": F(L, True)}`), key pattern `[a-z]{1,12}`,
  2–4 choices of `[a-z]{1,12}`, and the CLI subcommand. Add `"criteria"` to `VERDICT_KINDS`.
- [x] **Step 4: Run** the same command. Expected: PASS. Then `uv run pytest -q -m "not slow"`. Expected: all pass.
- [x] **Step 5: Commit** `feat: per-experiment criteria (lab exp criteria)`.

### Task 2: The criteria verdict, finding and page index

**Files:**
- Modify: `lab/loop/commands.py` (`_criteria_grades`, branch in `record_verdict`)
- Modify: `lab/loop/outcome.py` (`prediction_outcome` returns None for `criteria`; new `criteria_finding`)
- Modify: `lab/cli_loop.py` (`--grade` help; print `criteria_finding`)
- Modify: `lab/page_index.py` (experiment entry gets `criteria` and `run`; Needs-you command for criteria)
- Test: `tests/test_criteria.py`, `tests/test_page_index.py`

**Interfaces:**
- Consumes: `e["criteria"]` from Task 1.
- Produces: `record_verdict(..., grades="12A=print:clean,apart:no;12B=…")` on an experiment with criteria stores
  `{"kind": "criteria", "grades": {"E-012-A": {"print": "clean", "apart": "no"}, …}, "lighting": …}`.
  `grades` may also be a dict in that stored shape (Task 3 passes the dict).
- Produces: `criteria_finding(exp) -> str | None`.
- Produces: index experiment fields `criteria: list | None` and `run: str | None` (the latest print run id).

- [x] **Step 1: Write the failing tests**

```python
def test_criteria_verdict_by_tab(e012_like):           # three variants with tabs 12A..12C, criteria from Task 1
    e = record_verdict(..., grades="12A=print:clean,apart:no;12B=print:clean,apart:yes;12C=print:flawed,apart:yes")
    assert e["owner_verdict"]["kind"] == "criteria"
    assert e["owner_verdict"]["grades"]["E-012-B"] == {"print": "clean", "apart": "yes"}
    assert e["prediction_outcome"] is None

def test_criteria_verdict_accepts_the_stored_dict(...)  # same result from grades={"E-012-A": {...}, ...}
def test_criteria_verdict_needs_every_strip_and_criterion(...)  # missing 12C, or 12B without apart -> ValueError naming them
def test_criteria_verdict_refuses_unknown_choice(...)   # apart:maybe -> ValueError listing yes, hard, no
def test_criteria_verdict_does_not_move_the_streak(...) # ledger.streak unchanged after the verdict
def test_criteria_finding_sentence(...):
    assert criteria_finding(e) == ("12A: printed clean, didn't come apart. 12B: printed clean, came apart. "
                                   "12C: printed flawed, came apart.")
def test_index_carries_criteria_and_run(...)            # entry["criteria"] == e["criteria"]; entry["run"] == "PR-009-01"
def test_needs_you_command_for_criteria(...)            # command starts 'uv run lab exp verdict E-009 --grade "12A=print:'
```

Finding words per choice: `print`: clean → "printed clean", flawed → "printed flawed", failed → "failed to print";
`apart`: yes → "came apart", hard → "came apart with force", no → "didn't come apart". Any other criterion falls
back to "<label> <choice>".

- [x] **Step 2: Run** `uv run pytest tests/test_criteria.py tests/test_page_index.py -q`. Expected: the new tests FAIL.
- [x] **Step 3: Implement.** Branch order in `record_verdict`: inconclusive, then `e.get("criteria")`, then
  speed_sweep, as today. `lighting` defaults to `"diagnostic"` as for rankings.
- [x] **Step 4: Run** the same command, then `uv run pytest -q -m "not slow"`. Expected: all pass.
- [x] **Step 5: Commit** `feat: criteria verdicts, finding sentence and page index fields`.

### Task 3: `lab pull`

**Files:**
- Create: `lab/pull.py`
- Modify: `lab/sync.py` (call `pull.apply_pending` before building the index; refresh the page if anything applied)
- Modify: `lab/cli.py` (register `pull`)
- Test: `tests/test_pull.py` (a fake Local AI, as `tests/test_sync.py` does)

**Interfaces:**
- Consumes: `record_verdict`, `add_photos`, `sync._call`, `sync._key`, `page.refresh`.
- Produces: `apply_pending(pdir: Path, base: str, key: str, timeout: float = 10) -> list[dict]`, one
  `{"id", "status": "applied" | "refused" | "duplicate", "message"}` per request handled.
- Produces: `projects/<p>/requests.jsonl` (one line per handled id) and a lock at `projects/<p>/.pull.lock`.
- Request wire shape (from Task 5): `{"id": "rq-<16 hex>", "kind": "verdict" | "photos", "experiment": "E-012",
  "run": "PR-012-01", "payload": {...}, "at": iso}`.
  - `verdict` payload fields used: `grades`, `rank`, `strength`, `inconclusive`, `lighting`, `note`, `replace`.
  - `photos` payload: `{"photos": [{"sha256", "tab"}]}`; each is fetched from `GET /api/lab/<p>/incoming/<sha>.jpg`.

- [x] **Step 1: Write the failing tests**

```python
def test_pull_applies_a_verdict_and_reports_it(fake, project):   # fake serves one pending verdict
    out = apply_pending(pdir, fake.base, "k")
    assert out == [{"id": "rq-0000000000000001", "status": "applied", "message": "E-009 answered"}]
    assert load_experiment(paths, "E-009")["owner_verdict"]["kind"] == "criteria"
    assert fake.results["rq-0000000000000001"]["status"] == "applied"

def test_pull_refuses_with_the_cli_message(...)    # experiment already answered -> status refused, message contains "already has a verdict"
def test_pull_never_applies_an_id_twice(...)       # same id served twice -> second is "duplicate"; one verdict
def test_pull_adds_photos_with_their_tabs(...)     # two incoming JPEGs -> run photos +2, each entry has "tab"
def test_pull_applies_in_sent_order(...)           # photos then verdict, served out of order -> applied by "at"
def test_pull_ignores_unknown_payload_fields(...)  # payload {"approve": True, ...} -> record_verdict called without it; no approval
def test_pull_skips_when_locked(...)               # lock held -> returns [] and makes no request
def test_sync_pulls_first_and_refreshes(...)       # sync() with a pending verdict -> pushed index shows the verdict
def test_pull_is_off_with_lab_sync_off(...)        # LAB_SYNC=off -> apply_pending not called by sync
```

Add `"tab"` to photo entries: `add_photos(paths, run_id, files, tabs: list[str | None] | None = None)`.

- [x] **Step 2: Run** `uv run pytest tests/test_pull.py -q`. Expected: FAIL (no `lab.pull`).
- [x] **Step 3: Implement.** The lock is `fcntl.flock(LOCK_EX | LOCK_NB)`; on `BlockingIOError` return `[]`. Handle
  requests sorted by `at`. Downloaded photos go to a temporary directory, which is removed afterwards. Any
  `ValueError` from the lab becomes `refused` with `str(e)`. Write the `requests.jsonl` line before posting the
  result, so a lost result post never causes a reapply.
- [x] **Step 4: Run** the same command, then `uv run pytest -q -m "not slow"`. Expected: all pass.
- [x] **Step 5: Commit** `feat: lab pull applies the phone's requests`.

### Task 4: Pickup every 60 s (launchd)

**Files:**
- Modify: `lab/pull.py` (`cmd_pull` with `--install` / `--uninstall`)
- Test: `tests/test_pull.py`

**Interfaces:**
- Produces: `plist_text(repo: Path, uv: str) -> str`, a LaunchAgent with label `com.printlab.pull`,
  `StartInterval` 60, `ProgramArguments` `[uv, "run", "--project", repo, "lab", "pull"]`, `RunAtLoad` true,
  stdout and stderr to `~/Library/Logs/print-lab-pull.log`.
- Produces: `lab pull` (one pass: apply, then refresh the page and sync if anything was applied),
  `lab pull --install` (writes `~/Library/LaunchAgents/com.printlab.pull.plist`, then
  `launchctl bootstrap gui/<uid> <plist>`), and `lab pull --uninstall` (`launchctl bootout`, then delete the file).

- [x] **Step 1: Write the failing tests:** `test_plist_has_label_interval_and_command` (parse with `plistlib`) and
  `test_install_writes_plist_to_the_given_dir` (directory and `launchctl` runner injected; asserts the bootstrap
  arguments).
- [x] **Step 2: Run.** Expected: FAIL.
- [x] **Step 3: Implement.** `uv` comes from `shutil.which("uv")`; if it's missing, install refuses with "uv isn't on
  PATH."
- [x] **Step 4: Run** `uv run pytest -q -m "not slow"`. Expected: all pass.
- [x] **Step 5: Commit** `feat: lab pull --install runs pickup every minute`.

## Part B: LocalAI (worktree `~/dev/ai-harness/LocalAI-phone-verdicts`, branch `feat/lab-phone-requests` off `origin/main`)

### Task 5: Request and incoming-photo routes

**Files:**
- Modify: `app/print-lab.js` (new routes; `createPrintLab` takes `deviceFor`)
- Modify: `app/server.js:135` (pass `deviceFor: req => claudeChat.deviceFor(req)`)
- Test: `tests/print-lab-requests.test.cjs` (call `createPrintLab` directly with a `Storage` in a temp directory, a stub
  `deviceFor` and a stub `macAuthorized`, as `tests/claude-chat-pairing.test.cjs` does)

**Interfaces:**
- Produces, under `/api/lab/<project>/`:
  - `POST requests` (device) `{id, kind, experiment, run, payload}` → `200 {ok, id, status: "pending"}`; a repeat
    id → `200` with the stored status, unchanged.
  - `GET requests` (device or Mac) → `{items: [{id, kind, experiment, status, message, at}]}`, newest first, at most 50.
  - `GET requests?status=pending` (Mac only) → full items, oldest first.
  - `POST requests/<id>/result` (Mac only) `{status: "applied" | "refused" | "duplicate", message}`.
  - `PUT incoming/<sha>.jpg` (device) and `GET incoming/<sha>.jpg` (Mac only).
- Storage: `printLab:<project>:request:<id>` = `{id, kind, experiment, run, payload, status, message, at, by}`,
  where `by` is the device id. Incoming photos go in `DATA_DIR/print-lab/<project>/incoming/`; each is deleted when
  its request is applied.

- [x] **Step 1: Write the failing tests**

```js
test('a paired phone sends a request; the Mac sees it pending and posts the result', ...)
test('the same id sent twice is stored once', ...)                       // Review Focus 1
test('no device: 401 with the pairing message', ...)                     // body.error === "This phone isn't paired with Local AI. Pair it in Settings › Devices."
test('pending list and result need the Mac key', ...)                    // device cookie -> 401
test('kind other than verdict/photos, bad ids, over 4 KB are refused', ...)  // 422, 422, 413
test('the 21st pending request gets 429 with the Mac-awake message', ...)
test('incoming photo: JPEG only, sha must match, 8 MB cap; applied request removes it', ...)
test('the existing sync and photo routes still need the Mac key', ...)   // device cookie on POST sync -> 401
```

- [x] **Step 2: Run** `node --test tests/print-lab-requests.test.cjs`. Expected: FAIL.
- [x] **Step 3: Implement.** Extend the route regex with `requests` and `incoming`. Authorization moves from the
  blanket write check to per route: `sync`, `photos` PUT and `result` need the Mac key; `requests` POST and
  `incoming` PUT need `deviceFor(req)`. `/api/lab/` stays in `GUARDED_WRITES` (`app/signin.js`), with no change
  there. Request ids match `/^rq-[0-9a-f]{16}$/`; experiment and run match `/^[A-Z]{1,4}-\d{1,6}(-\d{2})?$/`.
- [x] **Step 4: Run** `npm test`. Expected: all pass.
- [x] **Step 5: Commit** `feat(print-lab): requests and incoming photos from a paired phone`.

### Task 6: Add photos and Record verdict on the page

**Files:**
- Modify: `app/public/print-lab.js`
- Modify: `app/public/app.css` (the lab block only)
- Test: `tests/print-lab-ui.mjs` (plus visual baselines at 390 px and 1440 px, light and dark)

**Interfaces:**
- Consumes: index fields `criteria`, `run`, `variants[].tab` (Task 2) and the routes from Task 5.
- Produces: on an experiment card whose status is `printing` with no verdict yet: **Add photos** and **Record
  verdict**, plus a request list under them showing each request's status. A card without `criteria` shows only Add
  photos in this release.

- [x] **Step 1: Write the failing browser tests**
  - Selecting two images shows two thumbnails, each with tab chips 12A/12B/12C. **Send photos** PUTs two JPEGs and
    then POSTs one `photos` request with their tabs.
  - The verdict sheet has one row per tab and one chip group per criterion. **Send to the Mac** stays disabled until
    every row is complete, and the incomplete row is outlined. The sheet also has "Print failed or can't tell" (with
    a reason), the light used, and a note.
  - After sending, the sheet shows "Waiting for the Mac". When the request list (polled every 10 s while the sheet is
    open) shows `applied` it says "Recorded"; for `refused` it shows the message as sent. After 2 minutes still
    pending, it shows the asleep message.
  - A 401 shows the pairing message.
  - A refusal containing "already has a verdict" offers **Replace verdict**, which resends the same grades with
    `replace: true` under a new request id.
  - An unsent draft survives a reload (localStorage key `printLab:draft:<experiment>`, in try/catch).
  - The page passes axe.
- [x] **Step 2: Run** `npm run test:browser -- print-lab-ui`. Expected: FAIL.
- [x] **Step 3: Implement.** Convert photos to JPEG with `createImageBitmap` → canvas (longest side 2400 px) →
  `toBlob('image/jpeg', 0.9)`, and get each sha256 with `crypto.subtle.digest`. Request ids are `rq-` plus 16 hex
  characters from `crypto.getRandomValues`, made once per send and reused on retry. The light choices are
  diagnostic, room and installed, as the CLI has them.
- [x] **Step 4: Run** `npm run ci -- --no-pr` (or the repo's local CI). Expected: green, with size budgets met;
  update baselines only for the lab views.
- [x] **Step 5: Commit** `feat(print-lab): photos and verdicts from the phone`.

## Part C: Rollout (owner and Claude)

### Task 7: First real use on E-012

- [x] Open the PR for Part B. CI must be green. **The owner runs `npm run ship -- <PR>`** (it's blocked for Claude).
- [x] Merge Part A to print-lab main and push.
- [x] On the Mac, run `uv run lab exp criteria E-012 --add "print=Printed cleanly?:clean,flawed,failed" --add "apart=Twists apart by hand?:yes,hard,no"`, then `uv run lab pull --install`.
- [x] Check: the page shows E-012 with **Add photos** and **Record verdict**; `launchctl print gui/$(id -u)/com.printlab.pull` reports it loaded.
- [x] After E-012 prints, the owner sends photos and the verdict from the phone. Done when `E-012.json` holds the
  `criteria` verdict and the photos carry tabs.
