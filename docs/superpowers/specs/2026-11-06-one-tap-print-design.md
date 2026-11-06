# One tap to print: the lab stages a checked build, the owner starts it from the phone

Date: 2026-11-06 · Status: **proposed** (approved when the owner merges this PR) · Amends: the print lab design
(`2026-10-24-print-lab-design.md`, "the owner starts every print"), the lab designs spec (`2026-11-05-lab-designs-design.md`,
"Out of scope: sending prints") and one-print (`pi-hub/…/2026-10-27-one-print-design.md`, "Bambuddy is third-party:
… never change it or write to it"). Needs a platform amendment (A12, below) before any Pi Hub code: the baseline keeps
Bambuddy read-only and names one printer-control path.

## Problem

From an approved experiment to a running print takes five hand steps on the Mac: `lab exp send`, Bambu Connect opens,
pick the printer, press Print, then `lab exp start` (and correct `started_at` if it was late). The owner is often not at
the Mac when the plate is free. Since 6 Nov the X2D is in LAN-only and Developer Mode, so Bambuddy can upload and start
prints; nothing in the lab uses that.

What must not change: the printer gets **exactly** the file the lab checked (E-020's first run printed re-sliced G-code
that wasn't), only the owner starts a print, and nothing starts on a plate that isn't clear.

## Facts this rests on (checked 6 Nov 2026 against Bambuddy 1.2.5.7)

- Bambuddy can take a file and start it: `POST /api/v1/library/files/` (multipart upload), `POST /api/v1/queue/`
  (`library_file_id`, `printer_id`, `manual_start`, `confirm_outcome`, `require_previous_success`, `ams_mapping`, …),
  `POST /api/v1/queue/{item_id}/start`, and stop, pause, resume.
- It has camera plate detection, but it **does not gate a start**: it runs in `on_print_start` and, if it sees objects,
  *pauses* the print that already began (probe, below). On the X2D it is off and uncalibrated.
- `/api/v1/printers/developer-mode-warnings` is empty: the X2D is reachable for control.
- Both keys can upload, queue and start (probe, below). The print-lab key can't make admin changes (settings, keys).
  Pi Hub's key is the one the baseline lets act.
- Lab prints are recognised by name (`one-print` P2: `<project>_<E-nnn>_<BLD-nnn-nn>`), and `lab pull` already creates a
  run from a print-log entry the lab wasn't told about. A print started this way is recorded without `lab exp start`.
- Bambuddy hashes the file the printer receives, so its `content_hash` never matched a lab artifact before (one-print).
  The staged file's identity has to be checked another way (decision S3).

## Probe (6 Nov 2026, Bambuddy 1.2.5.7; PR 2)

Re-run on 1.3.0 the same day, after the owner updated Bambuddy: the same scopes for both keys, the same start path
(`manual_start`, then start), plate detection still in `on_print_start`, and a byte-identical round trip of
`hex-tile_E-026_BLD-026-01.gcode.3mf` (deleted after). Staging is pinned to 1.3.0.

Nothing was queued or started; the printer was running the owner's print throughout.

- **Scopes.** Each route checks its scope in a dependency before the handler runs, so a request with a nonexistent id
  that returns 404 (not 403) proves the key holds the scope. Both the print-lab key (Mac) and Pi Hub's key (on the Pi)
  got past: `POST /queue/` (`can_queue`), `POST /queue/{id}/start` (`can_queue`, Bambuddy's `QUEUE_UPDATE_*`), and
  library download and delete (`can_manage_library`, which also covers upload). **So the Mac's key can start a print
  today**; S1's "the Mac never starts" holds only by the lab's code until the owner removes *Queue* from the print-lab
  key (Bambuddy › Settings › API keys; an admin change only the owner can make).
- **The start path.** `POST /library/files/{id}/print` is gone (410: "Create a print queue item with POST /queue/").
  Pi Hub adds a queue item with `manual_start: true`, then `POST /queue/{id}/start` clears the flag and the scheduler
  sends it. An item added **without** `manual_start` is dispatched by the scheduler on its own, so Pi Hub always sets
  it. Start returns 409 with the deficit when the assigned spool lacks the grams, unless `skip_filament_check`.
- **The file round trip.** The lab created the library folder `print-lab` (id 1), uploaded
  `hex-tile_E003_PR005.gcode.3mf` (187,972 bytes), and downloaded it back: same size, same sha256 (`52a4700d…`), so S3's
  check works as written. Bambuddy reads the file's metadata on upload (objects, 2041 s, 9.35 g, filament slots). The
  probe file was deleted after; delete moves a file to Bambuddy's trash.
- **Plate detection.** `plate_detection_enabled` is false and the X2D has no reference images ("Not calibrated - please
  calibrate with empty plate"). When enabled it checks the plate after the print starts and pauses if it sees objects.
  S4's tick stays the gate; calibrating detection (owner, with an empty plate) adds a backstop that pauses a wrong
  start within its first seconds.

## Decisions

| # | Decision |
|---|---|
| S1 | **Two halves.** The Mac *stages* (uploads the checked file, never starts it); Pi Hub *starts* (the one printer-control path, owner-only, logs the device). No other app starts a print. The print-lab key keeps only *Read status* and *Manage library*, so Bambuddy enforces this, not just the lab's code (probe). |
| S2 | **Only a build that passes `lab exp check` and is approved can be staged.** Staging re-runs the check, as `lab exp send` does today. |
| S3 | **The file is proven, not trusted.** After the upload the lab downloads the library file back and compares its sha256 with the build's `sliced_sha256`; a mismatch deletes it and stages nothing. At start, Pi Hub confirms the queue item names that library file. |
| S4 | **The start is one tap, never zero.** The owner opens "Ready to print" on the phone, sees what will print, ticks *Plate is clear and dry* and *Filament matches* (pre-filled from the AMS reading; a mismatch blocks), and presses **Start E-0nn**. Nothing starts from a notification button or on a schedule. |
| S5 | **Fresh at the moment of start.** Pi Hub starts only if, within the last 2 minutes: the printer is idle with no error, the bed is below 35 °C, the staged build is still READY in the lab's mirror (no newer build, same sha256), and the question's budget still covers it. Any miss shows the reason and leaves the Start button disabled. |
| S6 | **The lab records the start itself.** `lab pull` links the print-log entry (P2), sets `started_at` from Bambuddy, and marks the run `started_by: "pi-hub one-tap"` with the device Pi Hub logged. `lab exp start` stays for prints sent the old way. |
| S7 | **Stopping stays where it is.** Pause, stop and failure detection are unchanged; a failure pauses or stops through Bambuddy as today and is recorded by `lab pull`. |
| S8 | **Bambu Connect stays.** `lab exp send` keeps working; one-tap is an addition, so a Pi Hub or Bambuddy outage never blocks printing. |

## The flow

```
Mac (print-lab)                          Pi Hub                                  Bambuddy / X2D
lab exp approve E-0nn (owner)
lab exp stage E-0nn ──check (S2)──► upload ─────────────────────────────────────► library file
                    ◄── download back, sha256 = build (S3) ─────────────────────── 
                    ── mirror: "staged, file #id" ─►  Needs you: "E-0nn ready to print"
                                                      owner taps → sheet (S4), checks (S5)
                                                      Start ─► queue add + start ─────► printing
lab pull ◄──────────────────────────────── print-log entry (P2 name) ───────────────────
  run: started_at, started_by (S6)
```

`lab exp stage` may run by hand, or `lab pull` may stage an approved build when the printer has been idle for 10
minutes, so the phone sheet is ready when the owner is. Staging never starts anything.

## What the owner sees (Pi Hub, Workshop › Print lab)

A Needs-you item "E-0nn ready to print" while a staged build exists and the printer is idle. Its sheet follows the Home
Platform design contract (one faceplate, one primary action):

- the design's render (from the gallery when it came from `lab design make`), print time and grams from the slice,
  and the risk bands with heights;
- the two checks of S4, then **Start E-0nn**, disabled with the reason while any S5 condition fails;
- after pressing: *Sent*, *Accepted* (queue item created), *Printing* (the printer reports it), each shown as it happens.

## Platform amendment A12 (pi-hub, before any Pi Hub code)

1. Bambuddy stays the system of record for prints and read-only for everything else, **except** that Pi Hub's
   printer-control path may upload, queue and start a print staged by the lab, and the lab's Mac agent may upload a
   library file into the `print-lab` folder (S1, S3).
2. The baseline's printer actions gain "Start a staged lab print": owner-only, confirms through its sheet, logs the
   device, never a palette one-key action.

## Out of scope

Starting anything that isn't a staged lab build (Bambuddy's own UI does that); queues of several lab prints; starting
on a schedule or unattended; automatic plate clearing; changing what the experiment check guards.

## PRs

1. This spec, and amendment A12 in pi-hub.
2. Probe and record (no behaviour): whether each key can upload, queue and start, and whether plate detection gates a
   start on the X2D. Results go into this spec's facts; a "no" changes S1–S5 before anything is built.
3. print-lab: `lab exp stage` (S2, S3) and the staged state in the mirror. Tests with a fake Bambuddy.
4. Pi Hub: the Needs-you item, the sheet, S5 checks, start through the printer-control path, and the start record
   (device, queue item) that `lab pull` reads for S6; then print-lab's S6. Tests with a fake Bambuddy. (S6 moved here
   from PR 3: only Pi Hub knows a print was its start, so the lab has nothing to read until Pi Hub records it.)
5. One real lab print started this way, with its run showing S6's fields: the acceptance.

Each PR: tests green, and anything touching the printer proven on the real one only in PR 5, with the owner present.

## Risks

- **A stale start.** A build rebuilt after staging, or a plate cleared in the sheet but not in fact. S3 and S5 catch the
  first; the second is the owner's tick, as pressing Print in Bambu Connect is today.
- **A queue item that starts itself.** One added without `manual_start` is dispatched at once (probe). Pi Hub's adapter
  always sets it, and a test with the fake Bambuddy fails if it doesn't.
- **Bambuddy changes its API.** Every call is behind one adapter on each side, with its version checked
  (1.3.0 today); a different version disables Start until the probe of PR 2 passes again.
- **Developer Mode exposure.** Anything on the home network with the access code can command the printer; that is
  true already. One-tap adds no new listener: Pi Hub is behind Tailscale and owner sign-in.
