# Repository boundaries: where to look

This file holds pointers only. Ownership is decided by the platform baseline, and it is verified against code and
records on each task. Don't use a remembered table.

## Authorities, in order

1. **The platform baseline:** pi-hub `docs/superpowers/specs/2026-11-01-platform-product-architecture-design.md` on
   `origin/main`. The sections that matter here are §3 Domains, §7 Page ownership, §10 Failure boundaries,
   §11 Migration sequence, §12 Decisions, and `## Amendments`. It is frozen. An amendment is part of it once merged
   under `## Amendments`; a proposed amendment (open PR) is not.
2. **What is live:** Pi Hub's `release:<target>` records (`/api/records`, or the home MCP `releases` tool). These are
   the deployment truth for pi-hub, localai, firmware, netmon, mac-watch, x2d-bridge-mac and print-lab. Probes only
   verify them, and a record's `verified` block is a probe's observation, not the release.
3. **Plans and status:** pi-hub `docs/superpowers/plans/` (one per baseline item) and `docs/status.md`.
4. **Each repo's own code** at `origin/main`. A local checkout can be behind, and production checkouts can be dirty.

## Ownership in one line each (baseline D1, D5; verify before relying on it)

- **Pi Hub:** operational truth, meaning what is live where (System › Versions), Needs you, and the one phone
  channel. It also holds Print Lab's projection and queued requests.
- **print-lab:** the Mac experiment and build engine, and canonical experiment, run, qualification and package
  records. Authoring stays CLI-only (D8).
- **LocalAI:** engineering and change work (Improve, the Claude board, ship, Atlas).
- **Bambuddy:** spools, AMS and the print archive or queue.
- **Workshop OS (bambuhelper-smart-display):** the nearby physical interface and OTA. It keeps the `home.arpa` names and
  the local CA by design until a firmware release can move (D4).

## Things that still trip people up

- A cached display, an AI answer, a queued request or a printer "finished" event is not an accepted verdict. Only
  print-lab's owner verdict is.
- Two printer-control paths exist until baseline step 8 removes the display's direct Bambuddy call. Trace both before
  claiming one command path.
- `lab/sync.py` writes only to Pi Hub (D5 premise). Older docs that name LocalAI as the UI destination are historical.
