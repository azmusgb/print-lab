# Print lab UI part 1: one home — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Local AI print lab page shows everything `page.html` shows and updates itself after each `lab` command; then `lab page` stops writing `page.html`.

**Architecture:** print-lab sends spool colours with each sync. Local AI stores them, renders the page-only items through a new on-demand module (`print-lab-evidence.js`), and a second new module (`print-lab-refresh.js`) polls `/api/lab/projects` for a new fingerprint and re-renders quietly, keeping scroll, open sections and focus, and never while a sheet or field is in use. Last, print-lab deletes its HTML builder.

**Tech Stack:** print-lab: Python 3, pytest (`uv run pytest`). Local AI: Node, plain browser scripts (`(function(root){…})(window)` modules), `node --test tests/*.test.cjs`, Playwright suite `tests/print-lab-ui.mjs`.

**Spec:** `docs/superpowers/specs/2026-10-27-print-lab-one-home-design.md` (print-lab repo)

## Global Constraints

- The Mac stays the only source of truth; Local AI never changes a record.
- Poll every **3 s**, only while the print lab section is active and `document.visibilityState === 'visible'`; check at once on becoming visible.
- After **3** failed checks in a row the sync line reads exactly **"Can't reach Local AI"** until one succeeds.
- Never re-render while a lab sheet (`dialog.lab-sheet[open]`) is open or focus is in an `input`, `textarea` or `select` inside `#printLab`; apply when that ends.
- No live-region announcement for auto-refresh. Changed-card highlight respects `prefers-reduced-motion`.
- Spool colour rule: longest colour name contained in the lower-cased filament text wins; only `#rrggbb` values; else neutral **`#8698b1`**.
- Copy, exactly as `lab/page.py` today: "Plans" / "After {after}, if {if}: {next}"; " · {grade}"; "Finding: {finding}"; "AI reading ({round(confidence×100)}% sure[, unconfirmed]): {assessment}"; wipe input `aria-label` "Drag between {ref} and {id}", range 0–100, default 50.
- Every value from the Mac is escaped (`esc`) or set as text.
- Local AI: new front-end files go in ui.js's print-lab loader, `sw.js` `SHELL` (bump `CACHE` with a `-labhome1` suffix) and `frontend-scripts.test.cjs` `ON_DEMAND`. Any budget raised in `tests/budgets.test.cjs` gets a dated comment saying why, as the file does.
- Delivery order: Task 1 (print-lab PR A) → Tasks 2–5 (Local AI PR B, after #411 merges; base on `main` then) → Task 6 (print-lab PR C, only after B is live).

## Review Focus

1. **Refresh arrives while a sheet is open with a half-written verdict** — the draft and the sheet stay; the update applies on close. (Task 4 test `held while a sheet is open`.)
2. **Refresh while the owner has scrolled into Earlier with a card's details open** — same scroll position, same `<details>` open. (Task 4 test `quiet render keeps scroll and open details`.)
3. **Mac sleeps / Local AI unreachable for a while, then returns** — no error spam; one "Can't reach Local AI" line; it clears on the first good check. (Task 4 test `three failures then recovery`.)
4. **Filament text from the Mac with markup, or a colour value that isn't hex** (`"red; background:url(x)"`) — escaped text, colour ignored → neutral. (Task 3 test `colour values that aren't #rrggbb are ignored`.)
5. **A reference experiment with no photos, or a reference id that isn't in the index** — no wipe, no error. (Task 3 test `no wipe without both photos`.)

---

### Task 1: `lab sync` sends spool colours (print-lab, PR A)

**Files:**
- Modify: `lab/sync.py` (`sync()`, module docstring line 1)
- Test: `tests/test_sync.py`

**Interfaces:**
- Produces: the sync POST body is `build_index(pdir)` plus `"colours": dict[str, str]` (from `page.json`'s `colours`, `{}` when the file is missing or unreadable).

- [ ] **Step 1: Write the failing tests** in `tests/test_sync.py`, using the existing `Fake` server and `lab` fixture:
  - `test_sync_sends_the_saved_spool_colours`: write `page.json` = `{"colours": {"terracotta": "#c0623a"}}`; after `sync.sync(lab.root, base=f.url)`, the POST `sync` body's `colours == {"terracotta": "#c0623a"}`.
  - `test_sync_sends_no_colours_without_page_json`: delete `page.json` if present; body `colours == {}`.
- [ ] **Step 2: Run** `uv run pytest -q tests/test_sync.py` → the two new tests FAIL (`KeyError: 'colours'`).
- [ ] **Step 3: Implement** in `sync()`: after `ix = build_index(pdir)`, set `ix["colours"]` from `pdir / "page.json"` (`(OSError, ValueError)` → `{}`). Correct the module docstring: sync pushes `build_index` plus colours, not page.json.
- [ ] **Step 4: Run** `uv run pytest -q` → all pass.
- [ ] **Step 5: Commit** `feat: lab sync sends the saved spool colours` on a branch `feat/sync-colours`; push and open PR A.

### Task 2: Local AI keeps the colours (PR B starts here)

**Files:**
- Modify: `app/print-lab.js` (`sync()`: the line `const { records: _drop, colours: _c, ...index } = ix;`)
- Test: `tests/print-lab.test.cjs`

**Interfaces:**
- Produces: `GET /api/lab/<project>` → `index.colours` is the pushed `colours` object when it is a plain object of string → string, else `{}`.

- [ ] **Step 1: Write the failing test** `test('a push keeps its spool colours', …)`: push with `colours: { terracotta: '#c0623a' }` through `lab.sync`, then the stored index (via the GET route the file's other tests use) has `colours` deep-equal to it; a second push with `colours: 'x'` stores `{}`.
- [ ] **Step 2: Run** `node --test tests/print-lab.test.cjs` → FAIL.
- [ ] **Step 3: Implement**: keep `colours` in the stored index, kept only when every key and value is a string (else `{}`). Keep dropping `records`.
- [ ] **Step 4: Run** `npm test` → all pass.
- [ ] **Step 5: Commit** `Print lab: keep the Mac's spool colours`.

### Task 3: What only page.html showed — `print-lab-evidence.js`

**Files:**
- Create: `app/public/print-lab-evidence.js`
- Modify: `app/public/print-lab.js` (`questionHtml`, `experimentHtml`, variant rows), `app/public/app.css` (`.lab-swatch`, `--spine` edge, `.lab-wipe` — port the `.wipe` rules from print-lab `lab/page.py`), `app/public/ui.js` (loader list), `app/public/sw.js` (`SHELL`, `CACHE`), `tests/frontend-scripts.test.cjs` (`ON_DEMAND`)
- Test: `tests/print-lab-evidence.test.cjs` (new; load the file with `vm.runInNewContext(src, { window: ctx })` and read `ctx.LocalAIPrintLabEvidence`)

**Interfaces:**
- Produces `window.LocalAIPrintLabEvidence`:
  - `spoolColour(filament: string, colours: object) -> string` (hex)
  - `plansHtml(q) -> string` ('' when none)
  - `gradeText(v) -> string` (`' · faint'` or '')
  - `findingHtml(x) -> string`
  - `aiHtml(x) -> string`
  - `wipeHtml(x, byId, photoSrc: (photo) => string) -> string` (`photoSrc` is the URL function the thumbnails already use)
- Loader: ui.js loads `/print-lab-evidence.js` and `/print-lab-refresh.js` **before** `/print-lab.js`, each with `e.async = false` so they run in list order; print-lab.js still guards with `?.` and renders without them.

- [ ] **Step 1: Write the failing tests** in `tests/print-lab-evidence.test.cjs`:
  - `longest colour name wins`: `spoolColour('Light Matte Terracotta PLA', {terracotta:'#c0623a','light matte terracotta':'#d08a6a'}) === '#d08a6a'`.
  - `colour values that aren't #rrggbb are ignored`: `spoolColour('Red PLA', {red:'red; background:url(x)'}) === '#8698b1'`; no match → `'#8698b1'`.
  - `plans read as on the Mac`: `plansHtml({plans:[{after:'E-024',if:'clean',next:'v70 on terracotta'}]})` contains `After E-024, if clean: v70 on terracotta` and `Plans`; `plansHtml({})===''`.
  - `grade and finding`: `gradeText({grade:'faint'})===' · faint'`; `findingHtml({finding:'clean up to 60'})` contains `Finding: clean up to 60`; both '' when absent.
  - `AI readings`: `{ai_observations:[{confidence:0.834,confirmed:false,assessment:'<b>ok'}]}` → contains `AI reading (83% sure, unconfirmed): &lt;b&gt;ok`.
  - `wipe`: with `reference_variants:['E-020-A']`, both experiments having photos → contains `type="range"`, `value="50"`, `aria-label="Drag between E-020 and E-021"`.
  - `no wipe without both photos`: reference with no photos, or reference id not in `byId` → `''`.
- [ ] **Step 2: Run** `node --test tests/print-lab-evidence.test.cjs` → FAIL (file missing).
- [ ] **Step 3: Implement** the module (same `esc` as print-lab-photos.js). The wipe's range input moves the cut with an `input` listener delegated from print-lab.js's container (no inline `oninput`), setting `--cut` on the figure.
- [ ] **Step 4: Wire it in** print-lab.js: swatch + `style="--spine:…"` on each experiment card from `data.index.colours`; plans under the question; grade after each variant row; finding and AI readings in the card; wipe at the top of the card's photos. Add the file to the loader, `SHELL`, `ON_DEMAND`; bump `CACHE`.
- [ ] **Step 5: Extend** `tests/print-lab-ui.mjs`: the fixture gains `colours`, a plan, a graded variant, a finding, one AI reading and a reference with photos; assert each is visible on iPhone and desktop, the wipe's range changes `--cut`, and axe stays clean.
- [ ] **Step 6: Run** `npm test` and `npm run test:browser -- print-lab` → all pass. If `budgets.test.cjs` fails on app.css or ui.js, raise that budget by the measured amount with a dated comment.
- [ ] **Step 7: Commit** `Print lab: spool colour, plans, grades, finding, AI readings and the reference wipe`.

### Task 4: Quiet auto-refresh — `print-lab-refresh.js`

**Files:**
- Create: `app/public/print-lab-refresh.js`
- Modify: `app/public/print-lab.js` (`refresh()` gains a quiet path; `init()` starts the watcher; the sync line shows the failure text), loader / `SHELL` / `ON_DEMAND` (as Task 3), `app/public/app.css` (`.lab-changed` highlight, none under `prefers-reduced-motion`)
- Test: `tests/print-lab-refresh.test.cjs` (new, via `vm`, with fake timers passed in)

**Interfaces:**
- Produces `window.LocalAIPrintLabRefresh`:
  - `watch({ check: () => Promise<string|null>, apply: () => Promise<void>, isActive: () => boolean, isBusy: () => boolean, onFailures: (n: number) => void, every = 3000, timers = { setTimeout, clearTimeout } }) -> { stop(), poke() }`
    - `check` returns the current fingerprint; the first value is the baseline; a different value later calls `apply` (or holds it while `isBusy()`, re-checking busy every tick and applying once free).
    - `onFailures(n)` is called with the consecutive failure count after each failure and with `0` after a success that follows failures.
    - `poke()` checks now (used on `visibilitychange` to visible and when the section becomes active).
  - `snapshot(container) -> { scrollY, open: string[], focusId: string|null }` (`open` = ids of open `<details>` inside `container`; give each lab `<details>` a stable id in print-lab.js)
  - `restore(container, snap) -> void`
- Consumes: print-lab.js's existing `refresh()` fetch code; quiet render = same fetch, then `snapshot` → `innerHTML` render → `restore`, without `UI.loadInto`'s loading state; cards whose experiment object differs from the previous render (`JSON.stringify` per id) get `.lab-changed` for 2 s.

- [ ] **Step 1: Write the failing tests** in `tests/print-lab-refresh.test.cjs`:
  - `unchanged fingerprint does nothing`: check returns `'a'` three ticks → `apply` not called.
  - `a new fingerprint applies once`: `'a'`, `'b'`, `'b'` → `apply` called once.
  - `held while a sheet is open`: `isBusy` true when `'b'` arrives → no apply; next tick busy false → apply once.
  - `paused while hidden or inactive`: `isActive` false → `check` not called; `poke()` after it turns true → checked at once.
  - `three failures then recovery`: check rejects 3× → `onFailures` called with 1, 2, 3; then resolves → `onFailures(0)`.
  - `quiet render keeps scroll and open details`: with a minimal fake DOM object (`querySelectorAll('details[open]')` → ids, `scrollY`), `restore(c, snapshot(c))` reopens the same ids and calls `scrollTo` with the same Y.
- [ ] **Step 2: Run** `node --test tests/print-lab-refresh.test.cjs` → FAIL.
- [ ] **Step 3: Implement** the module (one `setTimeout` chain, not `setInterval`, so a slow check never overlaps the next).
- [ ] **Step 4: Wire it in** print-lab.js `init()`: `check` = `fetchJson('/api/lab/projects')` → the current project's `fingerprint`; `apply` = quiet render; `isActive` = section active and page visible; `isBusy` = `#printLab dialog.lab-sheet[open]` or focus in a field inside `#printLab`, re-checked on sheet close (`close` event → `poke()`); `onFailures(n)` → `n >= 3` puts "Can't reach Local AI" in the sync line, `0` restores "Synced from the Mac …". Add `visibilitychange` → `poke()`.
- [ ] **Step 5: Extend** `tests/print-lab-ui.mjs` (390 px and 1440 px): with the page open and scrolled to Earlier with one card's details open, push a second index through the real sync route with a changed experiment → within 5 s the change is on screen, `page.evaluate(() => scrollY)` is unchanged, the details are still open, no reload (a `window.__marker` set before survives). With the Judge it sheet open and text typed, push again → sheet and text remain; close → update appears. Axe clean.
- [ ] **Step 6: Run** `npm test` and `npm run test:browser -- print-lab` → all pass (budgets as Task 3).
- [ ] **Step 7: Commit** `Print lab: the page updates itself after each lab command`.

### Task 5: Ship PR B

- [ ] **Step 1:** `npm run ci` → passes. Open PR B ("Print lab: one home — spool colours, what only the Mac page showed, quiet auto-refresh"), linking the spec. The owner ships it with `npm run ship`.
- [ ] **Step 2:** After it's live, on the Mac run `uv run lab sync --project hex-tile` and open `https://10.0.0.21/#/printLab` at desktop width: colours, grades, finding and the wipe show; run any refreshing `lab` command and see the page change within ~5 s without a reload.

### Task 6: Retire page.html (print-lab, PR C — only after Task 5 step 2)

**Files:**
- Modify: `lab/page.py` (delete `build`, `_e`, `_n`, `_when`, `_value`, `_num`, `_badge`, `_bar`, `_question`, `_variants`, `_wipe`, `_experiment`, the CSS and `STATUS`/`OUTCOME`/`DONE` if nothing else uses them; keep `NEUTRAL`, `bambuddy_colours`, `spool_colour`, `write`, `refresh`, `cmd_page`, `register`; update the module docstring)
- Modify: `tests/test_page.py`, `tests/test_sync.py` (`_html` fixture and `test_the_page_says_when_it_last_synced`), `tests/test_speed_sweep.py:109-110`
- Modify: `lab/page_index.py` docstring line 1 (what `lab page` draws → what Local AI shows)

**Interfaces:**
- Produces: `write(pdir, colours=None) -> Path` writes `page.json` only (index + colours), deletes a stale `page.html` beside it, returns the `page.json` path. `refresh(pdir)` rebuilds when `page.json` exists (was: `page.html`). `lab page` prints `Wrote …/page.json` and `Open the print lab: {LAB_LOCALAI_URL or BASE}/#/printLab`; `--open` opens that URL; `--out` is removed.

- [ ] **Step 1: Rewrite the tests first:**
  - `test_page.py`: delete the HTML-text tests (their data is covered by `test_page_index.py`); rename and change `test_lab_page_writes_html_and_json_and_commands_keep_it_current` → `test_lab_page_writes_json_only_and_commands_keep_it_current`: after `main(["page"])`, `page.json` exists and `page.html` does not; a pre-existing `page.html` is removed; after `question new`, `page.json` contains `"Is the top edge clean?"`; output contains `#/printLab`. Keep `test_bambuddy_off_and_unreachable_give_no_colours`.
  - `test_sync.py`: the `lab` fixture builds the project with `test_page_index._project` (no `page.build`); delete `test_the_page_says_when_it_last_synced` (Local AI shows the sync time).
  - `test_speed_sweep.py`: drop the two `page.build` lines; the index assertions above them stay.
- [ ] **Step 2: Run** `uv run pytest -q tests/test_page.py` → the json-only test FAILS (`page.html` still written).
- [ ] **Step 3: Implement** the `lab/page.py` changes above.
- [ ] **Step 4: Run** `uv run pytest -q` → all pass; `grep -rn "page.build\|page.html" lab tests` → only the stale-file deletion and its test.
- [ ] **Step 5: Commit** `lab page: page.json only; the print lab page lives in Local AI` on `feat/retire-page-html`; push and open PR C.
