# Observation records and the "Record what happened" form: spec for milestone 1

**Status:** revision 2, 26 Oct 2026, after the owner's review. The owner approved building it once revised
("Revise the spec to resolve these six issues and the v51 wording, then proceed with the two planned PRs").
The estimate stays provisional until the contracts below are settled in code.

**Implements, from the blueprint** (`~/Documents/Codex/2026-10-24/new-chat/print-lab-blueprint/Print-Lab-Blueprint.md`):
R-02, R-03, R-04, R-09, R-10, R-19, R-20, R-21, R-22, R-25; acceptance scenarios T-02, T-05, T-09, T-11. Figma board 06
("Record what happened") is the only screen in scope. Differences from the blueprint are listed at the end.

## Why

Today a print's result is one `owner_verdict` per experiment. It can't say "21A's face is flawed, the 21A pair came
apart with effort, its back is marked", can't tell the owner's words from an AI's reading of a photo (the v51
mistake), and loses the old value when something is corrected.

## Subjects and the outcomes that belong to them

| Subject `kind` | What it is | Outcomes allowed |
|---|---|---|
| `tile` | one tile of a pair (or a single tile) | face, backing, mounting, acceptance |
| `pair` | the two tiles printed together | separation, acceptance |
| `strip` | a height strip, judged as a whole | face, separation, acceptance |
| `run` | everything one print run made | acceptance |

The write path refuses an outcome on a subject that doesn't allow it. A tile whose side isn't known is
`kind: tile, tile: null, identified: unidentified`, with a note; it is never recorded on the pair instead.

## The record

One file per observation: `projects/<p>/observations/OBS-NNNN.json`. Every revision is a **complete snapshot** of the
subject, viewing conditions and outcomes; nothing is inherited from an earlier revision, so a correction can't erase
an assessment by leaving it out.

```json
{
  "schema": 1, "record_type": "observation", "id": "OBS-0007", "project": "hex-tile",
  "import_key": null,
  "revisions": [{
    "rev": 1,
    "subject": {"kind": "pair", "experiment": "E-023", "run": "PR-023-01", "build": "BLD-023-01",
                "variant": "E-023-A", "label": "23A", "tile": null, "group": "G-0003",
                "identified": "confirmed", "note": null},
    "source": {"kind": "owner_report", "words": "came apart with a twist, a few strings inside",
               "evidence": ["photos/PR-023-01-3.jpg"], "occurred_at": null, "attributed_by": "phone_session"},
    "submitted": {"actor": "owner", "channel": "phone", "request_id": "req-…", "payload_sha256": "…",
                  "recorded_at": "2026-10-27T15:02:11+00:00"},
    "viewing": {"light": "room"},
    "outcomes": {"separation": {"status": "assessed", "value": "effort", "note": null},
                 "acceptance": {"status": "not_assessed", "value": null, "note": null}},
    "correction": null
  }]
}
```

- **Outcomes** (each `{status, value, note}`): `face` clean | flawed | failed; `separation` easily | effort | no;
  `backing` whole | marked | damaged; `mounting` fits | needs_work | unusable; `acceptance` accepted |
  accepted_with_defects | rejected. `status` is `assessed` (value set), `not_assessed`, `unknown` (looked, couldn't
  tell) or `not_applicable` (needs a `note`). Every outcome the subject allows is present in every revision; the
  snapshot is refused if one is missing. Nothing has a default.
- **Linked observations.** One session on the phone makes several observations (the pair, each tile, the run) that
  share a `group` id, so they can be read together without merging their subjects.
- **Acceptance** sits beside the other outcomes and changes none of them. E-020 would be
  `run: acceptance accepted_with_defects`, `pair: separation effort`, `tile: backing damaged`.

### Who said it, and who typed it in

`source.kind` is whose evidence it is: `owner_report`, `ai_reading` (a description of a photo by an AI, attributed to
its model and session), `instrument` (the printer log) or `imported_history`. `submitted.actor` is who put it into
the lab: `owner`, `claude`, or `import`. They are separate because Claude can run CLI commands too.

`source.kind: owner_report` is accepted only with one of:

1. `channel: phone`: sent from the owner's signed-in phone through Local AI (the existing paired-device check);
2. `channel: cli` and an interactive confirmation: `lab observe` asks on the terminal "Are these your own words and
   your own assessment? (type yes)" and reads the answer from the TTY; with no TTY it refuses. Claude's sessions run
   without a TTY, so they can't pass it. This is a guard against mistakes, not a security boundary: anyone at the
   keyboard can type yes;
3. `channel: import` with `source.attributed_by` naming the record it came from (e.g. `verdict E-012 at
   2026-10-26T02:43:41Z, by: owner`).

Anything Claude submits otherwise is `ai_reading` or goes in an interpretation.

**Interpretations** are separate records (`projects/<p>/interpretations/INT-NNNN.json`): `{claim, by, cites:
[{observation, rev}], status: hypothesis, needs_review}`. An explanation of a cause is always an interpretation.

### Corrections

A correction is a new complete revision with `correction: {reason, by, at}` and the `expected_rev` the corrector
read. It's applied under the observations lock; if the current revision isn't `expected_rev`, it's refused as a
conflict and nothing is written. Subject changes (a wrong label, a wrong tile) are corrections like any other,
because the subject is part of every revision. Earlier revisions stay. Interpretations and case reviews that cite an
earlier revision get `needs_review: true`.

### Retries can't create duplicates

Creating an observation, applying a correction and recording a phone request happen under one lock
(`observations` in the project's lock folder):

1. Look for an observation (any revision) with this `request_id`.
2. Found, same `payload_sha256`: return its receipt (`{id, rev}`); write nothing.
3. Found, different payload: refuse ("this request id was already used for different content").
4. Not found: write the observation (temp file, then link into place), then release the lock.

The receipt is the observation itself, so a crash right after the write leaves a record the next retry finds in
step 1. Tests cover two concurrent deliveries of one request, a retry after a simulated crash, and a reused id with
a changed payload.

## Worked example: v51

From the reconciled history (local file `history/hex-tile/chat/reconciled-2026-10-26.md`). All three share
`group G-0001`.

- `OBS-0001`, subject `{kind: pair, label: "v51 6in", run: null, build: null, identified: unidentified, note: "printed
  20 Oct; no run records before 23 Oct"}`, source `{kind: owner_report, words: "defects - 6\"", attributed_by:
  "owner-notes.md (transcript of cloud chat cse_012L…), 2026-10-20 13:52Z"}`, submitted `{actor: import}`, outcomes:
  separation `not_assessed`, acceptance `not_assessed` (the words don't say what was judged).
- `OBS-0002`, subject `{kind: pair, …same}`, source `{kind: ai_reading, by: "claude, cloud chat cse_012L…",
  words: "… and the pair came apart", evidence: photos IMG_0633–0641}`, outcomes: separation `unknown` (note "the
  photos show the tiles apart; how hard it was isn't recorded"), acceptance `not_assessed`.
- `OBS-0003`, subject `{kind: tile, tile: null, identified: unidentified, note: "face as photographed; which tile
  isn't recorded"}`, source as OBS-0002, outcomes: face `assessed/flawed` (note "big areas clean; ripple near a top
  corner, strings, a line 3 mm from the edges"), backing, mounting, acceptance `not_assessed`.

What the source resolves: the quote "the pair came apart" was an AI reading, not the owner's. What stays open: how
hard the original v51 pair was to separate. E-023 can show how a new reproduction behaves; it can't establish how
the original specimen behaved.

## The phone form (board 06)

One guided session per printed pair (or strip, or run), opened from a printed experiment:

1. **Identify**: pick the plate position, confirm the label you can read off the part, or mark it unidentified.
2. **The pair**: separation.
3. **Each tile** (left, right, or "can't tell which"): face, backing, mounting.
4. **Overall**: acceptance for the pair or run.
5. **Light**, review, send.

Only the outcomes valid for each subject are asked. Each offers its values plus "Not assessed", "Couldn't tell"
and "Not applicable" (which asks why). Nothing is preselected. Sending creates the linked observations in one
request (one `request_id`, applied all-or-nothing under the lock).

| State | What the owner sees |
|---|---|
| Draft | Saved on the phone as it's filled in; survives reload, closing the tab and losing signal |
| Incomplete | Send stays off; the missing step is named and linked |
| Queued | "Waiting for the Mac": the request is in Local AI, not yet applied |
| Applied | "Recorded" with the observation ids |
| Refused | The Mac's reason, with the draft kept |
| Conflict | A correction's `expected_rev` is out of date: both versions shown, the draft kept |
| Photo upload failed | The draft stays; only the missing photo is retried |

The terminal gets the same through `lab observe` (same rules, the TTY confirmation for owner reports).

## Existing verdicts

**Import.** `lab observe import-verdicts` (dry run unless `--apply`) turns existing verdicts into observations at
their **original scope**: criteria grades become one `strip` (or `pair`) observation per variant with
`identified: assumed`; acceptance verdicts one `run` observation. Each gets:

- `source.kind: imported_history`, `attributed_by` naming the verdict and its `by` field. It isn't promoted to an
  owner report, because some verdicts were recorded from pasted text (E-012).
- `viewing.light`: the recorded light only for verdicts recorded after 26 Oct 2026 (when the default was removed).
  Earlier ones that say `diagnostic` become `unknown` with the note "recorded as diagnostic while that was the
  default".
- run and build as the verdict names them, else null.
- `import_key: "verdict:<experiment>:<verdict at>:<variant or run>"`. Re-running finds the key and creates nothing.

A strip grade is never split into tile grades. Rankings aren't imported (they compare variants, they don't observe a
subject).

**Which record wins.**

- Prediction outcomes (rankings, sweeps) keep coming from `owner_verdict`; observations don't change them.
- For face, separation, backing, mounting and acceptance, observations win: once an experiment has observations,
  the page's findings for those outcomes come from the observations' latest revisions, not from the verdict.
- An experiment whose findings still come only from a legacy verdict shows them marked "from the old verdict, not
  re-checked".
- If an imported observation is corrected, the finding follows the correction, and the verdict-derived finding is
  no longer shown.

## Acceptance tests (written first)

1. Subject-valid fields: separation on a tile, face on a pair or acceptance missing from a snapshot are refused.
2. Face on two tiles, separation on their pair and acceptance on the run coexist in one group; none changes another.
3. Missing-answer statuses are stored as given; `not_applicable` without a note is refused; no defaults anywhere.
4. Owner attribution: `owner_report` is refused from the CLI without a TTY confirmation and from an import without
   `attributed_by`; Claude's submissions are stored as `ai_reading`.
5. Complete snapshots: a correction that omits an outcome is refused; a valid correction keeps revision 1, records
   reason/author/time, and marks citing interpretations and case reviews `needs_review`.
6. `expected_rev`: a correction against an out-of-date revision is refused as a conflict and writes nothing.
7. Retries: the same `request_id` delivered twice concurrently creates one set of observations; a retry after a
   save-then-crash returns the existing receipt; the same id with a changed payload is refused.
8. Import: running it twice creates nothing the second time; E-012 becomes strip observations with no tile grades;
   pre-26-Oct "diagnostic" becomes `unknown`; unknown run identity stays null.
9. Precedence: after an imported observation is corrected, the page's finding follows the observation; a legacy-only
   finding is marked as such; prediction outcomes are unchanged.
10. Phone form: no preselected answers, only subject-valid questions, 44 px targets, labelled radio groups; a draft
    survives reload and a failed photo upload; a conflict keeps the draft; axe finds nothing.

## Not in this milestone

- Photo comparison, annotation and measuring (board 03); history screens (board 04).
- Frozen approved files and printer-job matching (milestone 2). Until then the form says "Printer finished a job; not
  yet matched to this run" when the logger saw a finish without a confirmed job.
- Changes to how prediction outcomes or case levels are computed.
- Importing the cloud-chat history beyond the v51 example.

## Differences from the blueprint

- Observations are records beside experiments, not a rewrite of the experiment schema; verdicts stay and keep
  driving predictions.
- Only board 06 is built in this milestone.

## Cost (provisional)

About 3–4 days, two PRs: print-lab (records, rules, lock and receipts, CLI, import, `lab pull` handling, page index),
then Local AI (the board 06 form and its request route).
