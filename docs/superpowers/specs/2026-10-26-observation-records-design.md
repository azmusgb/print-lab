# Observation records and the "Record what happened" form: spec for milestone 1 (awaiting owner approval)

**Status:** draft for the owner's review, 26 Oct 2026. Nothing here is built.

**Implements, from the blueprint** (`~/Documents/Codex/2026-10-24/new-chat/print-lab-blueprint/Print-Lab-Blueprint.md`):
R-02 source-preserving observations, R-03 unknown is first-class, R-04 claims separate from observations, R-09 explicit
submission, R-10 independent provenance, R-19 specimen identity, R-20 separate acceptance dimensions, R-21 auditable
corrections, R-22 historical reconciliation, R-25 durable phone drafts. Acceptance scenarios T-02, T-05, T-09, T-11.
Figma board 06 ("Record what happened") is the one screen in scope. This spec narrows the blueprint; where they differ,
the difference is listed under "Differences from the blueprint".

## Why

Today a print's result is one `owner_verdict` per experiment: a ranking, an acceptance, or per-strip grades. It can't
say "21A's face is flawed, the 21A pair came apart with effort, its back is marked", can't tell the owner's words from
an AI's reading of a photo (the v51 mistake), and loses the old value when something is corrected. Boards 01, 03, 04
and 06 all need those distinctions.

## The record

One file per observation: `projects/<p>/observations/OBS-NNNN.json`, created with the existing `create_record` (next
free id under a lock, written in full before it appears). An observation is never edited in place; a correction adds a
revision (below).

```json
{
  "schema": 1, "record_type": "observation", "id": "OBS-0007", "project": "hex-tile",
  "subject": {
    "kind": "pair",                     // tile | pair | strip | run
    "experiment": "E-023", "run": "PR-023-01", "build": "BLD-023-01",
    "variant": "E-023-A",               // the plate position, when there is one
    "label": "23A",                     // what's written or tabbed on the part, as the owner reads it
    "tile": null,                       // for kind "tile": "left" | "right" | the owner's own words
    "identified": "confirmed"           // confirmed | assumed | unidentified
  },
  "revisions": [{
    "rev": 1,
    "source": {
      "kind": "owner_report",           // owner_report | ai_reading | instrument | imported_history
      "by": "owner",                    // "owner", or the AI's model and session for ai_reading
      "words": "came apart with a twist, a few strings inside",   // verbatim; never paraphrased
      "via": "phone",                   // phone | cli | import
      "request_id": "req-…",            // phone only; makes a retry a no-op
      "evidence": ["photos/PR-023-01-3.jpg"],
      "recorded_at": "2026-10-27T15:02:11+00:00",
      "occurred_at": null               // when it was looked at, if known; null means unknown
    },
    "viewing": {"light": "room"},       // diagnostic | room | installed | unknown
    "outcomes": {
      "separation": {"status": "assessed", "value": "effort", "note": null}
    },
    "correction": null                  // on rev 2+: {"reason", "by", "at", "affects": [claim ids]}
  }]
}
```

**Outcomes are separate fields.** One observation can carry any of them, and none of them overwrites another:

| Outcome | Belongs to | Values when assessed |
|---|---|---|
| `face` | tile (or a strip when the strip is the specimen) | clean, flawed, failed |
| `separation` | pair | easily, effort, no |
| `backing` | tile or pair | whole, marked, damaged |
| `mounting` | tile | fits, needs_work, unusable |
| `acceptance` | tile, pair or run | accepted, accepted_with_defects, rejected |

Every outcome has a `status`: `assessed` (then `value` is set), `not_assessed` (nobody looked), `unknown` (looked, couldn't
tell), or `not_applicable` (it can't apply, for example separation on a pair that failed to print). `not_applicable`
needs a `note` saying why. An outcome left out of a revision means `not_assessed`. Nothing has a default value.

`acceptance` is the owner's overall call for a purpose, and it sits beside the others: E-020 would be
`acceptance: accepted_with_defects` with `separation: effort`-or-worse and `backing: damaged` kept as they are.

**Interpretations are separate records.** `projects/<p>/interpretations/INT-NNNN.json` hold explanations and AI photo
readings that go beyond what was seen: `{"claim": "…", "by": "<model/session>", "cites": [{"observation": "OBS-0007",
"rev": 1}], "status": "hypothesis"}`. An AI photo reading that is only a description ("two separate backs are in the
photos") is an observation with `source.kind: ai_reading`; anything that explains a cause is an interpretation. Neither
can be saved with `source.kind: owner_report` by the AI: the write path checks `via` (`phone` and `cli` verdict commands
only) for owner reports.

**Corrections.** A correction appends `rev: n+1` with the changed fields and `correction: {reason, by, at, affects}`.
Earlier revisions stay. `affects` lists interpretations and case reviews that cite the observation; each gets
`needs_review: true` until someone looks again (case reviews already go stale the same way).

**Identity.** `subject.identified` is `confirmed` only when the owner says which part it is (label or tab read off the
part). `assumed` is the lab's guess from position or order. Historical evidence that can't be tied to a run is
`unidentified` with `run` and `build` null and a `note`. Nothing fills in a run or build that isn't known.

**What the printer log can and can't say.** A logged finish belongs to a run only when the job is confirmed (the
logger's `job_confirmed`). Until milestone 2 adds job matching for every send, the form shows "Printer finished a job;
not yet matched to this run" rather than "This print finished".

## Worked example: v51

From the reconciled history (local file `history/hex-tile/chat/reconciled-2026-10-26.md`):

- `OBS-0001`, subject `{kind: "pair", experiment: null, run: null, label: "v51 6in", identified: "unidentified",
  note: "no run records before 23 Oct"}`, source `{kind: "owner_report", words: "defects - 6\"", via: "import",
  occurred_at: "2026-10-20T13:52Z"}`, outcomes: none assessed (the words don't say what was judged).
- `OBS-0002`, same subject, source `{kind: "ai_reading", by: "claude (cloud chat cse_012L…)", words: "big face areas
  are clean … and the pair came apart", evidence: ["IMG_0633"… "IMG_0641"]}`, outcomes `face: assessed/flawed`
  (note "ripple near a top corner, strings, a line 3 mm from the edges") and `separation: unknown` (note "the photos
  show the tiles apart; how hard it was isn't recorded").
- What this resolves: the "the pair came apart" quote was an AI reading, not the owner's. What stays open: how hard
  v51 was to separate. E-023 can answer it with a new owner observation.

## The phone form (board 06)

One form per subject, opened from a printed experiment. Steps, in order: **identify** (pick the plate position, confirm
the label you can read, or mark it unidentified) → **face** → **separation** → **backing** → **mounting** →
**overall** → **light** → review → send. Each outcome offers its values plus "Not assessed", "Couldn't tell" and "Not
applicable" (which asks why). Nothing is preselected. Photos are optional and shown as attached or not.

States:

| State | What the owner sees |
|---|---|
| Draft | Saved on the phone as it's filled in; survives reload, closing the tab and losing signal |
| Incomplete | Send stays off; the missing step is named and linked |
| Sending / queued | "Waiting for the Mac": the request is in Local AI, not yet applied |
| Applied | "Recorded as OBS-0007", with the revision |
| Refused | The Mac's reason, with the draft kept for fixing |
| Conflict | Someone changed this subject's observation since the draft started: show both, keep the draft, offer "send as a correction" |
| Photo upload failed | The draft stays; only the missing photo is retried |

Every request carries a `request_id` made when the draft is first sent. The Mac applies a given `request_id` once
(it's recorded inside the observation, and `lab pull` checks for it before creating anything), so a retry after a
timeout can't make a second observation.

The terminal gets the same through `lab observe <EXP> --subject pair:23A --separation effort --light room --words "…"`
with the same rules (no defaults; `--not-applicable separation="pair failed to print"`).

## Existing verdicts (migration)

Nothing is rewritten. `owner_verdict` stays on experiments and keeps driving prediction outcomes and findings, so the
current page and phone verdicts keep working (dual reading).

`lab observe import-verdicts` creates observations from existing verdicts at their **original scope**:
criteria grades become one observation per strip (`kind: strip`, `identified: assumed`), acceptance verdicts one per
run (`kind: run`), with `source.kind: owner_report`, `via: import`, the verdict's note as `words`, and the verdict's
light. A strip-level grade is never split into tile grades. Rankings aren't imported (they compare, not observe).
The import is a dry run unless `--apply` is given, and it reports what it would create.

## Acceptance tests (written first)

1. A separation observation on a pair and face observations on its two tiles coexist; acceptance on the run changes
   none of them. (R-20, T-05)
2. Each missing-answer status is stored as given; `not_applicable` without a note is refused; nothing defaults. (R-03, R-09)
3. The AI can save an `ai_reading` observation and an interpretation, and can't save an `owner_report` outside the
   owner's verdict and observe commands. (R-04)
4. A correction keeps revision 1, records reason/author/time, and marks citing interpretations and case reviews
   `needs_review`. (R-21, T-09)
5. The same `request_id` applied twice creates one observation and returns the same receipt. (R-25, T-11)
6. A draft survives reload and a failed photo upload; a conflict keeps the draft and offers a correction. (T-11,
   browser test)
7. Importing E-012's criteria verdict makes three strip observations and no tile observations. (migration)
8. An unidentified historical observation saves with null run/build and its note; an assumed one is shown as assumed.
   (R-19, R-22)
9. The form has no preselected answers, 44 px targets, labelled radio groups, and passes axe. (blueprint §15)

## Not in this milestone

- Photo comparison, annotation and measuring (board 03).
- History reconciliation screens and the reference register (board 04); the records can hold them, the screens wait.
- Frozen approved files, printer-job matching for every send, crash-safe request receipts beyond the `request_id`
  check (milestone 2, boards 05, 07, 08).
- Any change to how prediction outcomes or case levels are computed from verdicts.
- Importing the v29–v56 cloud-chat history beyond the v51 example, which is done by hand as the first real record.

## Differences from the blueprint

- Observations live beside experiments as their own records instead of a full "v2 schema" rewrite of experiments.
  Verdicts stay; reading both is simpler to ship and easy to undo.
- Only board 06 is built. The blueprint's milestone 3 screens follow once these records exist.

## Cost

About 3 days: records, CLI, `lab pull` handling and import with tests (1.5), the phone form in Local AI with browser
tests (1.5). Two PRs: print-lab, then Local AI.
