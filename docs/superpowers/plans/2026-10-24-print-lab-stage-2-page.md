# Print lab Stage 2: the page in Local AI (plan)

Written 24 Oct 2026, after `lab page` (a static, read-only preview built from the local records). Design:
`docs/superpowers/specs/2026-10-24-print-lab-design.md` › "Print lab page". This plan turns the preview into the
interactive page, in small PRs. **Not started; needs the owner's go-ahead.**

## What `lab page` already settles

Use the preview to try the layout before building it. It already has the parts the interactive page keeps:

- **Order:** Needs you (approvals, verdicts due), then each open question as a sentence with its open experiment and
  "Why this test?", then the notebook, newest first.
- **Notebook rows:** each spine in the spool's real colour (from Bambuddy); status and prediction-outcome pills; the
  owner's verdict; the print-run photos.
- **The evidence wipe:** the experiment's first photo over its reference's, with a handle to drag between them.
- **Phone first:** a two-column desktop layout (sidebar 360 px), dark and light.

## Prerequisite: Stage 1B (records in Local AI)

The page reads and writes through Local AI, so Stage 1B comes first:

1. `/api/lab/*` in Local AI: questions, experiments, print runs and photos (the local JSON records are imported once).
   Writes take the same checks as the engine: one factor, test kind and overrides.
2. **Sign-in:** every write is guarded (paired device or Mac key; see Local AI `app/signin.js` `GUARDED`), because a
   verdict or an approval sends a print.
3. **Photos:** uploaded from the phone into the appliance's data folder; the 3MF and G-code stay on the Mac.
4. The engine (`lab`) syncs its records to Local AI after each command, and reads approvals back before printing.

## Stage 2 PRs (each usable on its own)

| # | PR | Done when |
|---|---|---|
| 1 | Registry view `printLab` and a Projects tab "Print lab": the read-only page from `/api/lab`, matching `lab page` | It shows the same content as the preview on a phone; axe passes; visual baseline |
| 2 | **Verdict buttons** (Fixed, Better, Same, Worse), only when a verdict is due; saving records `owner_verdict` | A verdict from the phone appears in the engine's record |
| 3 | **Photos from the phone**, with the profile's checklist on screen (raking light, fixed distance, reference card) | Photos land on the print run and in the wipe |
| 4 | **Mark a defect:** tap a photo, pick the type from the profile's list; marks pinned on both sides of the wipe | Marks survive a reload and show in the engine |
| 5 | **Override sheet** ("Print the full 6\" pair?"): the 7 requirements, each met or not with evidence; **Approve full print** stays disabled until all but the owner's approval are met | E-006 can be approved from the phone; the engine refuses a print without it |
| 6 | **Size ladder** (Coupon, 3", 6", 10") and the notebook's spool colour from the experiment's spool id (not text matching) | The ladder shows where each experiment sat |
| 7 | **Errors and empty states** in the design's words ("No open question. Ask the lab what to test next.") | Every failure says its cause and its fix |

## Tests

- **Browser:** `print-lab-ui.mjs` (plan, verdict, defect marking, override sheet; axe; visual baselines at 390 px and
  1440 px, light and dark).
- **Unit:** the verdict and approval routes refuse unsigned callers, and the one-factor rule is checked server-side.
- **Ship:** each PR goes out with Local AI's `npm run ship`.

## Open questions for the owner

- Should verdicts be allowed from the Workshop display too (Better / Same / Worse as one tap), or only from the phone?
- Should spool colours keep coming from Bambuddy, or should the experiment record carry the colour when it's planned?
