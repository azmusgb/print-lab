# Parameters Panel (Fusion add-in)

A panel docked on the right of Fusion that lists the active design's user parameters.

- Edit an expression and press **Enter** (or move focus away) to apply it. **Esc** reverts the field.
  **−/+** (and ↑/↓ in the field) step a plain number by 1; Shift ×10, Alt ×0.1. **↺** returns a parameter to the
  value it had when the panel first saw the design this session.
- A value that breaks one of the project's design rules (`projects/<project>/design-rules.json`, e.g. edge_depth at
  least skin_axial + land_thickness + 1.6 mm) gets an amber note under it naming the limit and why. Rules warn and
  never block; the project is the one picked under Print-lab check.
- Each row says what the parameter **drives** (the features and sketches using it), or that nothing uses it.
- If a change breaks the timeline, a red banner names the failed steps; export is disabled until it's fixed.
- The status line reports each change with the volume before and after.
- Each change runs as one "Change parameter" command, so **Edit › Undo** takes it back.
- Invalid expressions are rejected before Fusion sees them; the field turns red with the reason.
- While another command is open (a sketch tool, Extrude...), editing is disabled until it finishes.
- Starred parameters (☆ in Modify › Change Parameters) sort to the top. The filter box matches names and comments.
- The **Model** footer shows the visible solid bodies' overall size, volume and an estimated PLA weight
  (density 1.24 g/cm³, solid; a sliced print with infill weighs less).
- **Print-lab check** exports the visible solid bodies as one STL to `projects/<project>/fusion/` (not tracked by git),
  runs `lab inspect --json` on it and lists the findings. **Upright** turns it the way the hex tiles print (model +Y up,
  face toward -Y, as in the SCAD `upright()` module; `upright.py`); **Flat** keeps the model's own axes.
  It runs `uv` in the print-lab checkout this folder lives in, so Fusion waits a few seconds while it works.
- **Send to lab** turns the design into a new registered source: it exports the visible bodies, and
  `lab variant add` writes `sources/<name>.3mf` with the chosen **base** project's full print settings (so it slices
  with the X2D's own start G-code), registers it in `sources/sources.json` (sha256, `derived_from`, a change line from
  the parameter differences) and keeps the parameters beside it as `sources/<name>.params.json`. It never overwrites a
  source. The report ends with the `lab exp plan … --source … --object … --base …` line to plan an experiment with it.

## Install (macOS)

Link this folder into Fusion's add-ins folder from the main print-lab checkout:

```
ln -s ~/dev/print-lab/tools/fusion/ParamsPanel \
  "$HOME/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/ParamsPanel"
```

Then in Fusion: **UTILITIES › ADD-INS › Scripts and Add-Ins** (Shift+S) › **Add-Ins** tab › **ParamsPanel** › **Run**,
and tick **Run on Startup**. **UTILITIES › ADD-INS › Parameters Panel** shows or hides the panel (its × also hides it);
give it a keyboard shortcut from the ⋮ next to it in that menu.

To remove it: Stop it in the same dialog and delete the link.
