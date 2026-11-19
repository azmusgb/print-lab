# print-lab

- **Read the Home Platform design contract before any UI work**: appliance-ui `DESIGN.md`
  (https://github.com/azmusgb/appliance-ui/blob/main/DESIGN.md). Read it at the start of the task, not from memory or
  from this summary. Pi Hub's baseline and its approved amendments win where they differ. If you can't open it (no
  network, no access), say so and stop before changing a screen. This covers anything here with a screen, such as the Fusion parameters panel (`tools/fusion/ParamsPanel/`) and the
  blueprint report (`docs/blueprint/`). Print lab's pages in Pi Hub are Pi Hub's, and follow the same contract there.

## Checks
- `uv sync && uv run pytest` before every PR; paste the counts. It needs nothing running: tests refuse the network and
  writes into the checkout (`tests/conftest.py`), and the tests marked `slow` need OpenSCAD or Bambu Studio.
- If a change makes an existing test wrong, change that test in its own commit and say why. Never loosen or delete an
  assertion to get a pass.
- Branch off `main` and open a PR. Never push to `main`.

## Print and CAD work
- Run Python from the repo root (checkout or worktree) with `uv run python` (needs `lab.design.families`).
- Never queue or start a print job unless asked. Bambuddy queue items use `manual_start: true`; keys are never printed (see `.claude/skills/rift-tile-print/references/bambuddy-queue.md`).
- The same holds for every step that hands a file to the printer's side or records what the owner did. Run one only
  when the owner asks for that step by name: `lab exp send` (opens the checked build in Bambu Connect), `lab exp stage`
  (uploads it to Bambuddy for Pi Hub to start), `lab exp start`, `approve` and `verdict` (the owner's own records), a
  Bambuddy queue request, and `lab pull --install` (a launchd agent). Building, slicing, checking and reading are
  yours: `lab exp build`, `lab exp check`, `lab slice`, `lab gcode`, `lab status --no-printer`.
- Single RIFT tile (faceted_hex seed 3): use the `rift-tile-print` skill. Back-to-back pair: use `hex-tile`.
- Check a model in its real standing orientation before slicing (see the skill's G-code checks).
