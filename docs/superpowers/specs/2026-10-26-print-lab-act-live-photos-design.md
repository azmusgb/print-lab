# Print lab page: act from it, see the print live, judge from photos

Written 26 Oct 2026 for the owner's review. **Status: draft, not started.** The owner picked items 1–3 of the GUI
review ("1 2 3", 26 Oct): act from the page, show the print as it happens, and make photos the centre of judging.
Builds on the phone verdicts and photos design (`2026-10-25-print-lab-phone-verdicts-design.md`, live as Local AI
#393) and keeps its rules.

## Rules (unchanged from phone verdicts)

- **The Mac stays the only source of truth.** Local AI never changes a record. The page sends a *request*; the Mac
  applies it with the same functions the CLI uses; the result comes back with the next sync.
- A request is applied once (its id is kept). Only a paired device can send one (`GUARDED_WRITES`).
- Photos stay out of git. Local AI stores them by sha256, as now.
- **Out of scope:** starting the printer from the page (`lab exp send` opens Bambu Connect on the Mac and needs a click
  there; it stays a Mac command), defect marks, editing an experiment's plan, the "How the lab works" panel (#396,
  its own module).

## 1. Act from the page

Each "Needs you" item gets its action as a button. The `uv run lab …` command moves behind a small
"Run it on the Mac instead" disclosure (still copyable).

| Needs you item | Button(s) on the page | Request kind | Mac applies it with |
| --- | --- | --- | --- |
| Judge the print | **Judge it** opens the existing verdict sheet (#393), plus **Add photos** | `verdict`, `photos` (exist) | `record_verdict`, `add_photos` |
| Send it to the printer (approved, not started) | **I've sent it** (after sending from Bambu Connect or Handy) | `start` (new) | the code behind `lab exp start` (`cmd_exp_start`) |
| Approve or drop | **Approve** with an optional reason, **Drop** with a required reason | `approve`, `abandon` (new) | `guards.approve`, `commands.abandon` |
| Fix the plan, Run the next step | No button: these need the Mac. The command stays as now | — | — |

- New kinds take `{experiment, reason?}`; `start` also takes the run id the page saw, so a stale tap can't start the
  wrong run. Unknown or refused requests come back with the CLI's own error text, as `verdict` does today.
- The verdict sheet accepts "–" (not judged) per criterion (already accepted by the Mac as null), e.g. "apart" on a
  strip that failed to print.
- After a tap the item shows "Waiting for the Mac", then "Done" or the refusal, exactly like the verdict sheet.
- **Decision (recommended):** no confirmation on Approve or I've sent it (the Mac refuses anything out of order);
  **Drop** asks for a reason and confirms, because it closes the experiment.

## 2. The print as it happens

Local AI already reads the X2D's state for the Workshop display card: `state` (printing, paused, error, cancelled,
ended, idle), `progress` and `minutesLeft` (`app/workshop.js`). The page uses it for the experiment whose latest run
is printing.

- **Matching:** at most one experiment has a run with a start and no end (`printing` in the index). If two do, nothing
  is matched and the page says "Two runs say they're printing; check the Mac", rather than guess.
- **On that item:** a progress bar, "Layer n of m" when the printer reports it, time left and the finish time ("done
  about 3:30 AM"), and the printer's own state word when it isn't printing (Paused, Stopped with an error 0700_8010).
- **Camera:** a snapshot on the printing item, refreshed every 10 s while the page is visible. Local AI's server
  fetches `http://10.0.0.30:8091/x2d/frame.jpg` (the Pi's camera bridge, which stays open for the Workshop display
  after the lock) and serves it as `GET /api/lab/camera.jpg` (paired device). No picture → "No picture from the
  printer right now" (today: the X2D's LAN Only Liveview is off).
- **When the printer finishes:** the item's main button becomes **Judge it** straight away, before the Mac has synced,
  and Home's Needs you lists "Judge the print · E-0nn". (The Mac's record still changes only through a request.)
- **Pi Hub:** the printer card on Home and Workshop gets a "Print lab: E-020 ↗" link to Local AI's Print lab when a lab
  experiment is printing. The hub reads it from Local AI's existing feed (no new hub storage).

## 3. Photos at the centre of judging

- **Thumbnails** on every notebook item that has photos (up to 6, then "+n"), grouped by tab, not under Details.
- **Viewer:** tap a thumbnail for a full-screen viewer: swipe or arrow keys between photos, the tab and the run under
  each, pinch or double-tap zoom.
- **Compare:** a **Compare** button on an item with photos opens two columns: this run against another run of the same
  question (default: the last run with a "good enough" verdict, else the previous run). Photos are paired by tab, and
  zoom and pan move both sides together. A run picker changes either side.
- **Checklist:** above **Add photos**, the experiment's `judge_on` items and the light rules (raking light from one
  side, same distance, tab in frame) as tick boxes. Ticks are kept on that device only (they are a memory aid, not a
  record).

## Where the code goes

| Piece | Repo / file | Notes |
| --- | --- | --- |
| New request kinds `start`, `approve`, `abandon` | print-lab `lab/pull.py` (+ tests) | Reuses `cmd_exp_start` logic, `guards.approve`, `commands.abandon` |
| Request routes accept the new kinds | LocalAI `app/print-lab.js` | Same size limits and pending cap |
| `/api/lab/camera.jpg` and the live printer block in the project payload | LocalAI `app/print-lab.js` (reads `workshop.js` status) | Read-only |
| Buttons, live block, thumbnails, viewer, compare, checklist | LocalAI `app/public/print-lab.js` and a new `app/public/print-lab-photos.js` (viewer and compare) | Keeps print-lab.js from growing past its budget |
| "Print lab: E-0nn" link | pi-hub `hub/now.py` + home card | Small |

Not touched: `app/public/print-lab-guide.js` (#396), print-lab's `lab watch`, telemetry and `threemf.py` (another
session's work).

## Testing

- print-lab: each new kind applied once, refused out of order with the CLI's text, a stale `start` (wrong run) refused.
- Local AI: route tests for the new kinds and the camera proxy (bridge down → 503 with a reason); `print-lab-ui.mjs`
  for buttons → "Waiting for the Mac", the live block with a stubbed printer state, thumbnails, the viewer and compare
  at phone and desktop sizes, axe clean.
- Pi Hub: the link appears only while a lab experiment is printing.

## Delivery

Three PR-sized steps, each usable alone: (A) act from the page (print-lab + Local AI), (B) live print and camera
(Local AI, then the hub link), (C) photos (Local AI). Local AI work starts after #396 merges, on top of it. The owner
ships Local AI PRs with `npm run ship`.

## Open questions for the owner

1. **Drop from the phone:** OK to allow abandoning an experiment from the page (with a reason and a confirm)? Recommended: yes.
2. **Camera on the page:** a 10 s snapshot is light; a live stream is heavier and needs Liveview on. Recommended: snapshot now.
