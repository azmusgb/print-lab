# Print lab: verdicts and photos from the phone

Written 25 Oct 2026 for the owner's review. **Status: draft, not started.** Roadmap steps 1 and 2 (steps 3–6, the
Bambuddy link, approvals, the evidence wipe and the ladder, come later and each get their own spec).

## Goal

After a print, take the photos and record the verdict on the phone, in Local AI › Projects › Print lab, instead of
AirDropping photos and pasting `lab exp verdict …` on the Mac. The first print to use it is E-012.

## Rules

- **The Mac stays the only source of truth.** Local AI never changes a record. The phone sends a *request*; the Mac
  applies it with the same functions the CLI uses (`record_verdict`, `add_photos`), so every check stays in one place.
  The result comes back to the page with the next sync.
- **A request is applied once.** Each one has an id; the Mac keeps the ids it has applied.
- **Only a paired device can send a request.** The routes go in `GUARDED_WRITES` (`app/signin.js`), which refuses
  callers without a device even while sign-in is report-only. (Correction to the roadmap note: `/api/lab/` writes are
  already guarded this way; the new part is allowing a paired phone, not only the Mac key, on the request routes.)
- **Out of scope:** approvals, starting a print, Bambuddy, the evidence wipe, defect marks, editing an experiment.

## What already exists

- `lab sync` pushes the index and photos (by sha256) to `/api/lab/<project>/…` with the Mac key, after every
  mutating `lab` command (`lab/sync.py`). Local AI stores them as `settings` rows and files (`app/print-lab.js`).
- `add_photos(paths, run_id, files)` converts photos to JPEG and lists them on the run, all or nothing.
- `record_verdict(...)` takes ranks, `inconclusive`, `lighting`, sweep `grades`, `note` and `replace`.
- Grades are fixed to `clean / faint / banded` (`GRADES` in `lab/records/schema.py`), which suits a speed sweep and
  nothing else. E-012 needs "printed cleanly?" and "came apart?" per strip.

## Design

### 1. Per-experiment criteria (Mac)

- An experiment may carry `criteria`: a list of `{key, label, choices}`, judged per strip (by tab).
  - The speed sweep keeps its current meaning as the default criterion `bands: clean | faint | banded`.
  - E-012 gets two: `print: clean | flawed | failed` ("Printed cleanly?") and
    `apart: yes | hard | no` ("Twists apart by hand?").
- `lab exp criteria E-012 --add "print=Printed cleanly?:clean,flawed,failed" --add "apart=…"` sets them. Allowed
  until the first verdict; refused after, because it would change what a verdict meant.
- The verdict stores `grades` as `{tab: {criterion: choice}}`. The old sweep shape (`{tab: grade}`) is read as
  `{tab: {bands: grade}}`, so existing records need no migration.
- **Outcome:** with no prediction, the verdict produces a finding sentence, e.g. "12B (0.15 mm): printed clean, came
  apart. 12A: printed clean, didn't come apart." It doesn't count towards the uninformative streak. A prediction on
  criteria is out of scope for now.
- CLI: `lab exp verdict E-012 --grade "12A=print:clean,apart:no;12B=…"`.

### 2. Requests (Local AI)

- `POST /api/lab/<project>/requests` (paired device): `{id, kind, experiment, run, payload}`.
  - `kind: "verdict"`: payload is what `record_verdict` takes (grades, rank, inconclusive reason, lighting, note,
    replace).
  - `kind: "photos"`: payload is `{run, photos: [{sha256, tab}]}` for photos already uploaded with
    `PUT /api/lab/<project>/incoming/<sha256>.jpg` (paired device; JPEG checked, at most 8 MB, hash must match).
  - At most 4 KB of JSON; at most 20 pending requests per project, otherwise 429 with "The Mac hasn't picked up the
    last 20 requests. Check that the Mac is awake."
- Stored as `print-lab/<project>/request/<id>`: `{status: pending | applied | refused, message, at, by}`.
- `GET /api/lab/<project>/requests?status=pending` and `POST …/requests/<id>/result` are Mac-key only.

### 3. Pickup (Mac)

- `lab pull [--project]` fetches pending requests, downloads any incoming photos, applies each request, and posts the
  result: `applied`, or `refused` with the error text the CLI would print.
  - Applied ids go in `projects/<p>/requests.jsonl` (outside git, like `sync.json`). A repeat id is reported as
    already applied, not applied twice.
  - After applying, it runs the normal page rebuild and sync, so the page shows the new verdict.
- It runs at the start of every `lab sync`, and from a launchd agent every 60 s while the Mac is awake
  (`~/Library/LaunchAgents/com.printlab.pull.plist`, installed with `lab pull --install`). `LAB_SYNC=off` turns both
  off.

### 4. The page (phone)

- On an experiment whose run is printing or awaiting a verdict:
  - **Add photos:** a file picker (camera or library), several at once. Each photo gets a tab chip from the plate's
    tabs (12A, 12B, 12C). The light checklist is shown above the button: raking light from one side, same distance,
    tab in frame.
  - **Record verdict:** a sheet with one row per strip and one chip group per criterion; for a two-variant experiment,
    tap the better one (or "No real difference"). Then "Print failed or can't tell" with a reason, the light used, a
    note, and **Send to the Mac**.
- After sending, the sheet shows "Waiting for the Mac", then "Recorded" or the refusal message as the Mac wrote it.
  If nothing happens within 2 minutes: "The Mac hasn't picked this up. It runs when the Mac is awake."
- The sheet keeps an unsent draft in the browser, so a lost connection doesn't lose the grades.
- Uses the existing `--ds-*` tokens, Figtree, dark and light; nothing new in the design system.

## Errors

| Case | What the owner sees |
|---|---|
| Phone not paired | "This phone isn't paired with Local AI. Pair it in Settings › Devices." |
| Verdict already recorded | The Mac's refusal: "E-012 already has a verdict…", with a **Replace verdict** option |
| A criterion left out | Send stays disabled, and the missing row is outlined |
| Photo won't convert | The Mac's refusal; no photos from that request are added |
| Mac asleep | The 2-minute message above; the request stays pending and applies when it wakes |

## Testing

- **Mac (pytest):** criteria set and refused after a verdict; old sweep grades still read; the E-012 finding sentence;
  `lab pull` applies a verdict and photos, refuses with the CLI's message, and never applies an id twice; a fake
  Local AI for the routes.
- **Local AI (unit):** request routes refuse callers without a device and refuse the Mac-only routes without the key;
  size and pending limits; incoming photo checks.
- **Browser (`print-lab-ui.mjs`):** add photos with tabs, the verdict sheet for E-012's criteria, the waiting and
  refused states; axe; baselines at 390 px and 1440 px, light and dark.
- **Real run:** E-012's verdict recorded from the phone and visible in `E-012.json`.

## Open questions for the owner

1. Is the 60-second pickup on the Mac fine, or should it only happen when you run a `lab` command?
2. For E-012's criteria, are clean / flawed / failed and yes / hard / no the words you'd use?
