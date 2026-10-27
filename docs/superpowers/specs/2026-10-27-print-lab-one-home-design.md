# Print lab UI, part 1: one home

Written 27 Oct 2026 for the owner's review. **Status: design approved in conversation (27 Oct); spec awaiting review.**

## Where this sits

The owner asked for the print lab's UI and UX to evolve on four fronts (27 Oct, "1, 2, 3, 4"): day-to-day friction,
seeing the big picture, one home instead of two, and the look and feel. They are split into four sub-projects, each
with its own spec, plan and build, in this order:

1. **One home** (this spec): the Local AI print lab page is the only interface.
2. **The daily loop**: print finished → what happened → verdict → what next, without the Mac for routine steps.
3. **The big picture**: design history (v51 … v72): what was tried, what worked, what the lab has learned.
4. **Visual and interaction pass** across the finished layout.

## Goal

The Local AI print lab page is where the owner looks, on the phone and in a desktop browser beside the terminal on the
Mac. The static `page.html` stops being a second interface.

The owner uses `page.html` today at the Mac while running `lab` commands (27 Oct, option 2). Local AI's page already
has everything `page.html` has (Needs you with commands to copy, questions, notebook, Earlier, records the Mac can't
read) plus buttons, live print, camera and photos. Two things are missing:

- **It doesn't update itself.** Every `lab` command already pushes to Local AI in the background, but the open page
  only changes after a reload.
- **No spool colours.** `page.html` draws each experiment's spool swatch from Bambuddy's colours; `lab sync` doesn't
  send them.

**Done means:** after a `lab` command, an open Local AI page shows the result within about 5 seconds without a reload;
the desktop layout serves at the Mac as `page.html` did (commands to copy, problems, spool colours); `lab page` no
longer writes a page anyone opens.

**Accepted (owner, 27 Oct):** when Local AI is down, the Mac has the terminal only; there is no fallback page.

**Out of scope:** the daily loop, design history and visual pass (parts 2–4); server push (see Approaches).

## Approaches considered

- **The page checks for changes (chosen).** Poll the existing projects route for the sync fingerprint every 3 s while
  visible. No new server route, works the same on phone and desktop, idle when hidden.
- **Server-sent events from Local AI.** About 1 s faster, but needs long-lived connections through Caddy and the
  paired-device check, plus reconnect handling, to save 2–3 seconds.
- **The Mac reloads the browser tab (AppleScript).** Mac-only, depends on the browser, does nothing for the phone.

## 1. The page notices and applies changes (Local AI)

- **What it checks:** `GET /api/lab/projects`, which already returns each project's `fingerprint` and `synced_at`.
  No new route.
- **When:** every 3 s while the print lab section is active and `document.visibilityState` is `visible`. It pauses
  when hidden, when the section isn't showing, or when offline, and checks at once on becoming visible again.
- **On a new fingerprint:** fetch the project and its requests, then render **quietly**: no loading state, keeping the
  scroll position, which `<details>` (experiment details, "Run it on the Mac instead", Earlier) are open, and focus
  when the focused element still exists (matched by id).
- **Never during input:** while any lab sheet is open (Judge it, Add photos, Approve, Drop, Record what happened) or
  focus is in a field inside the print lab, the refresh is held and applied when the sheet closes or focus leaves.
  Drafts are never lost.
- **Visible cue:** the "Synced from the Mac …" line updates; experiment cards whose record changed get a brief
  highlight (respecting `prefers-reduced-motion`). No live-region announcement, so screen readers aren't interrupted
  every few seconds.
- **Errors:** a failed check is silent and retried on the next tick. After 3 failures in a row the sync line reads
  "Can't reach Local AI" until a check succeeds.
- The existing live-print and camera polling are unchanged.

## 2. Retiring page.html

### print-lab (Mac)

- `lab page` and the after-command refresh (`page.refresh`, called from `cli.py`, `sync.py`, `pull.py`) write
  **`page.json`** only: the index plus the saved spool colours. They stop writing `page.html`.
  `page.refresh` currently does nothing unless `page.html` exists; it now keys off `page.json`.
- `lab page` keeps refreshing spool colours from Bambuddy; other commands reuse the saved ones and never wait on the
  network (as now). It prints the Local AI page's address.
- `lab sync` sends `colours` (from `page.json`, or `{}` when there is none) with the index.
- The HTML builder in `lab/page.py` is deleted (`build` and its HTML/CSS helpers, about 300 of 403 lines).
  `bambuddy_colours`, `spool_colour`, `write` (now page.json only), `refresh`, `cmd_page` and `register` stay.
- `projects/hex-tile/page.html` is removed from git and `page.html` is added to `.gitignore`.
- Docstrings that say "page.json is what sync pushes" are corrected: sync pushes `build_index` plus colours.

### Local AI

- `sync()` stores `colours` with the project; the project GET returns it.
- Experiment cards draw the spool swatch with the same rule as print-lab's `spool_colour`: the longest colour name
  found in the filament text wins, only `#rrggbb` values are used, neutral `#8698b1` when nothing matches.
- Commands to copy stay visible at desktop width as now (Copy button; "Run it on the Mac instead" where a button
  exists).

## Testing

- **print-lab:** `lab page` writes `page.json` and no `page.html`; refresh works with only `page.json` present; sync's
  body carries `colours`; existing index tests unchanged; tests that rendered HTML are rewritten against the index or
  removed with the builder.
- **Local AI:** refresh logic: unchanged fingerprint does nothing, changed one re-renders; held while a sheet is open
  and applied on close; scroll, open `<details>` and focus kept; paused while hidden; three failures show "Can't reach
  Local AI". Swatch matching (longest name, invalid hex ignored, neutral fallback). UI test at 390px and 1440px: a sync
  while the page is open updates it without a reload; axe clean.

## Delivery

Two PRs, each usable alone:

- **A (print-lab):** colours in sync, `page.html` retired. Safe first: Local AI ignores the extra field until B.
- **B (Local AI):** quiet auto-refresh and spool swatches. Built on Local AI `main` at the time (after the open
  print-lab PRs such as Record what happened land, to avoid conflicts in `app/public/print-lab.js`). The owner ships
  it with `npm run ship`.
