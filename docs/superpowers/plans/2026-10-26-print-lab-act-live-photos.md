# Print lab page: act, live print, photos — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The owner acts on "Needs you" from the Print lab page, sees the running print live, and judges from photos.

**Architecture:** The page sends requests; the Mac's `lab pull` applies them with the CLI's own functions (new kinds
`start`, `approve`, `abandon`). Local AI adds a live printer block and a camera proxy to the print-lab routes, and
the page grows buttons, a live block and a photo viewer/compare module. Pi Hub links a printing lab experiment.

**Tech Stack:** Python 3.13 + pytest (print-lab, `uv run`); Node 22 vanilla JS + node:test + Playwright (Local AI);
FastAPI/vanilla JS (Pi Hub).

**Spec:** `docs/superpowers/specs/2026-10-26-print-lab-act-live-photos-design.md`

## Global Constraints

- The Mac stays the only source of truth; Local AI never changes a record. A request is applied once.
- Approve calls `lab.loop.guards.approve()` unchanged. Start records the phone's tap time.
- Drop is allowed from the phone with a reason and a confirm (owner, 26 Oct). Camera = a 10 s snapshot (owner, 26 Oct).
- Don't touch: `app/public/print-lab-guide.js` (#396), print-lab `threemf.py`, `lab watch`, telemetry; records
  E-019, E-020, Q-003. Local AI work starts after #396 merges, on top of it. Photos stay out of git.

## Review Focus

1. A `start` request arriving after the run was already started from the Mac → "already started", nothing written
   (Task 1, `test_start_twice_is_not_two_runs`).
2. A `start` whose run id the page saw is stale (the experiment moved on) → refused (Task 1, `test_stale_start_refused`).
3. A phone clock far off → the tap time is used only if within 6 h before pickup and not in the future, else now
   (Task 1, `test_tap_time_bounds`).
4. The camera bridge down or slow → the page item still renders; the proxy answers 503 within 3 s (Task 2).
5. Two experiments claiming to be printing → no live match, a plain message (Task 2).

---

### Task 1: New request kinds on the Mac (`start`, `approve`, `abandon`)

**Files:** Modify `lab/pull.py`, `lab/loop/guards.py` (`start(..., started_at=None)`); Test `tests/test_pull.py`.

**Interfaces:** Produces request kinds — `start {experiment, run_seen?: str|null, payload: {tapped_at: ISO}}`,
`approve {experiment, payload: {reason: str}}`, `abandon {experiment, payload: {reason: str}}`.
`guards.start(paths, exp_id, started_at: str | None = None)`.

- [ ] Tests: `test_start_request_opens_a_run_at_the_tap_time`, `test_start_twice_is_not_two_runs`,
  `test_stale_start_refused` (`run_seen` given and the experiment's latest run differs → refused),
  `test_tap_time_bounds`, `test_approve_request_uses_the_guard` (status `approved`, `approval.reason` = the payload's),
  `test_approve_refused_when_nothing_to_approve` (the guard's own message), `test_abandon_needs_a_reason`,
  `test_abandon_request` (status `abandoned`).
- [ ] Run → FAIL ("unknown request kind").
- [ ] Implement in `pull.py` with the same applied/refused/duplicate bookkeeping as `verdict`.
- [ ] Run `uv run pytest -q` → all pass. Commit.

### Task 2: Local AI routes — new kinds, live printer block, camera proxy (after #396 merges)

**Files:** `app/print-lab.js`, `tests/print-lab*.test.cjs`.
- [ ] Request route accepts `start | approve | abandon` (same 4 KB / 20-pending limits); `reason` required for
  `abandon`, ≤ 500 chars.
- [ ] The project payload gains `live: {experiment, run, state, progress, minutesLeft, finishAt}` from the Workshop
  status (`workshop.js`), matched to the one experiment whose latest run is printing; two → `live: {conflict: true}`.
- [ ] `GET /api/lab/camera.jpg` (paired device): fetch `http://10.0.0.30:8091/x2d/frame.jpg` with a 3 s timeout;
  on failure 503 `{reason}` using the Pi hub's `/api/camera` reason when it answers. `LOCALAI_LAB_CAMERA_URL`
  overrides the address (tests).

### Task 3: Page — buttons and sheets (after Task 2)

**Files:** `app/public/print-lab.js`, `app/public/app.css`, `tests/print-lab-ui.mjs`.
- [ ] Judge it / Add photos (existing sheet, "–" allowed), It's printing now (hint "only once it's actually
  printing"), Approve sheet (guard list + reason), Drop (reason + confirm). "Run it on the Mac instead" disclosure.
- [ ] Waiting → Done / refusal states.

### Task 4: Page — live block and camera (after Task 2)

**Files:** `app/public/print-lab.js`, `tests/print-lab-ui.mjs`.
- [ ] Progress, time left, finish time, state word; snapshot every 10 s while visible; no-picture reason; Judge it as
  the main button once the printer reports finished.

### Task 5: Photos — thumbnails, viewer, compare, checklist

**Files:** Create `app/public/print-lab-photos.js`; modify `app/public/print-lab.js` (mount points only), `app/public/sw.js`,
`tests/frontend-scripts.test.cjs`, `tests/print-lab-ui.mjs`.
- [ ] Thumbnails (6 + "+n"); viewer (swipe/arrows/zoom); compare (pair by tab, linked zoom, run picker; default the
  last good-enough run); checklist ticks in localStorage.

### Task 6: Pi Hub link

**Files:** `hub/now.py` / home card, tests.
- [ ] "Print lab: E-0nn ↗" on the printer card while a lab experiment is printing (from Local AI's feed).
