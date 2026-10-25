# Print lab slim 1B: the lab page in Local AI (read-only)

Written 24 Oct 2026 for the owner's review. **Status: draft, not started.**

## Goal

See the print lab from the phone: the same page `lab page` draws on the Mac, inside Local AI at
`https://10.0.0.21/#printLab` (Projects › Print lab), current within seconds of any `lab` command.

## Rules (from the owner, 24 Oct)

- **Slim 1B is a projection, not a second source of truth.** The Mac is authoritative. Local AI stores what the Mac
  sends and never changes it.
- `lab sync` pushes validated records, upserting by stable ID. Each push carries the schema version and a source
  fingerprint, so an older push can't overwrite newer data.
- Local AI keeps a normalized index plus each original record.
- Landing page: active question, budget, stops, **Needs you**, recent experiments with requested vs realized values,
  outcome and validity. Each experiment has a phone-friendly detail view: hypothesis, prediction, variants, plate,
  usage, check, verdict and photos.
- **Out of scope:**
  - verdicts, approvals or starting a print from Local AI
  - photo upload from the phone
  - any write from Local AI to the Mac
  - conflict resolution
  - telemetry reconciliation
  - printer actions
- The Pi stays out.

## What already exists

- **On the Mac:** `lab page` builds `page.json` from the records and draws `page.html` from it. Every `lab` command
  that changes a record rebuilds both.
  - `page.json` is `print-lab-index/1`: questions, experiments, the Needs-you list and problems, each with the loop's
    own numbers. It also carries the original records with their sha256.
  - So the work left is moving the page and its JSON to Local AI.

## Design

### The push: `lab sync` (Mac)

1. **Build the index.** `lab sync [--project hex-tile]` builds the index exactly as `lab page` does. An invalid record
   stays on the Mac: it is listed under `problems` and never sent as data.
2. **Find missing photos.** It asks `GET /api/lab/<project>/photos` which photo hashes Local AI already has.
3. **Upload them.** Each missing JPEG goes up once to `PUT /api/lab/<project>/photos/<sha256>.jpg`.
   - Photos are named by content, so a re-upload is a no-op.
4. **Send the index.** `POST /api/lab/<project>/sync` sends the index.
   - It authenticates with the existing Mac key header (`X-LocalAI-Mac-Key`, from `~/.claude/localai-chat/mac.key`)
     and Local AI's CA (`~/.claude/localai-chat/localai-ca.crt`).
   - It goes to `https://10.0.0.21`; `LAB_LOCALAI_URL` overrides that.
   - Each photo in the index carries its sha256 (already in the record), so the page can find it.
5. **Sync after every change.** Every `lab` command that rebuilds the page also starts `lab sync` in the background,
   with a 10 s limit.
   - A failure never fails the command.
   - It is written to `projects/<p>/sync.log`, and the page shows "Local AI: synced 22:05" or "not synced: <reason>".
   - `LAB_SYNC=off` turns it off.

### Local AI: storing it (`app/print-lab.js`, mounted at `/api/lab/`)

- **Who can write.** Only the Mac writes: the handler checks `claudeChat.macAuthorized(req)`, and the write routes
  are added to `GUARDED_WRITES`. Reads follow the normal sign-in (a paired phone today, report-only until sign-in is
  enforced).
- **The sync body.** At most 4 MB; a larger one gets a 413.
  - It must say `schema: "print-lab-index/1"`, or the push gets a 422.
  - The project name must match `[a-z0-9-]{1,40}`.
- **Older pushes lose.** Each push's `generated_at` must be newer than the last one stored for that project;
  otherwise it gets a 409 and nothing changes.
  - Within a push, each record is upserted by ID and skipped when its sha256 is unchanged.
  - A record missing from a newer push is removed, because the projection mirrors the Mac.
- **Storage.** It uses prefixed `settings` rows, so no schema migration is needed:
  - `print-lab/<project>/index`: the derived index, without the originals.
  - `print-lab/<project>/record/<id>`: `{sha256, payload, received_at}`.
  - `print-lab/<project>/meta`: `{generated_at, fingerprint, synced_at, counts}`.
- **Photos.** They live in `DATA_DIR/print-lab/<project>/photos/<sha256>.jpg`.
  - At most 8 MB each.
  - JPEG magic bytes are checked, and the hash must match the body.
  - They are served at `GET /api/lab/<project>/photo/<sha256>.jpg` with `Cache-Control: private, max-age=31536000,
    immutable`.
- **Reads.** `GET /api/lab/projects` lists the projects. `GET /api/lab/<project>` returns the index plus `meta`.
  `GET /api/lab/<project>/record/<id>` returns one original record, for the detail view's "raw record" link.

### Local AI: the page (Projects › Print lab)

- **Wiring.**
  - A registry entry `printLab` with `domain:'projects'`, `section:'Keep'`, `parent:'projects'` and
    `tab:'Print lab'`.
  - A `<section id="printLab">` in `index.html`.
  - `app/public/print-lab.js`, loaded on demand so the shell budget doesn't grow.
  - Its own block at the end of `app.css`, using `--ds-*` tokens and the shared components (`.card`, `.list-group`,
    `.badge--good|bad|attention|accent|neutral`, `.empty-state`, `LocalAIUI.loadInto`).
- **Landing.** In this order:
  1. Needs you: each row has the action, the experiment, why, and the command to run on the Mac, with a copy button.
  2. The open question: time and material bars (spent, then the next test's estimate), the stop state and the
     evidence count.
  3. The notebook of open experiments.
  4. Earlier, folded.
- **Detail view.** `#printLab/E-005` shows:
  - hypothesis, prediction, why this test, judge on
  - variants as requested vs realized
  - plate: estimate, usage and seconds per layer
  - the last check's failing guards
  - the verdict
  - outcome and validity with reasons in plain words
  - photos: the first one large, with the drag-between-photos comparison against the reference
- **Empty and error states, in the page's own words.**
  - "No lab data yet. Run `lab sync` on the Mac."
  - "Last synced 2 h ago. The Mac may be asleep."
  - Errors use `loadInto`'s Retry.
- **Copy.** Avoid the words `copy-lint` bans ("inventory", "artifact", "workspace", "execution", …).

## Testing

- **Mac:**
  - `lab sync` against a fake server: the Mac key is sent; only missing photos go up; a 409 is reported, not
    retried.
  - The background sync never fails or slows a command.
  - `LAB_SYNC=off` turns it off.
- **Local AI unit tests:**
  - A write without the Mac key gets a 401.
  - An older `generated_at` gets a 409.
  - An unchanged record is skipped; a removed record disappears.
  - A photo with a bad hash or that isn't a JPEG is refused.
  - A body over 4 MB gets a 413.
  - The registry and tab-list tests are updated for the new tab.
- **Local AI browser tests:** `print-lab-ui.mjs`, using a fixture pushed through the real sync route.
  - The landing order, Needs-you commands and copy button, and the detail view.
  - axe at 390 px and 1440 px.
  - A visual baseline.
- **Ship:** a PR, then `npm run ci -- <PR>`, then `npm run ship -- <PR>`. Confirm with `/healthz` releaseCommit.

## Delivery: two PRs

1. **print-lab** `lab sync` and background sync, with a fake-server test.
2. **LocalAI** "Print lab in Projects (read-only, synced from the Mac)": the routes, storage, page and tests.

Done when the owner opens Projects › Print lab on the phone and sees E-008's "Judge the print" within 10 s of a
`lab` command on the Mac.

## Open question

Should Home's printer line link to Print lab when something needs you? I recommend yes: one tap from Home to "Judge
the print".
