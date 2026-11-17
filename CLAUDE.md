# print-lab

- **Read the Home Platform design contract before any UI work**: appliance-ui `DESIGN.md`
  (https://github.com/azmusgb/appliance-ui/blob/main/DESIGN.md). Read it at the start of the task, not from memory or
  from this summary. Pi Hub's baseline and its approved amendments win where they differ. If you can't open it (no
  network, no access), say so and stop before changing a screen. This covers anything here with a screen, such as the Fusion parameters panel (`tools/fusion/ParamsPanel/`) and the
  blueprint report (`docs/blueprint/`). Print lab's pages in Pi Hub are Pi Hub's, and follow the same contract there.

## Print and CAD work
- Run Python from the repo root (checkout or worktree) with `uv run python` (needs `lab.design.families`).
- Never queue or start a print job unless asked. Bambuddy queue items use `manual_start: true`; keys are never printed (see `.claude/skills/rift-tile-print/references/bambuddy-queue.md`).
- Single RIFT tile (faceted_hex seed 3): use the `rift-tile-print` skill. Back-to-back pair: use `hex-tile`.
- Check a model in its real standing orientation before slicing (see the skill's G-code checks).
