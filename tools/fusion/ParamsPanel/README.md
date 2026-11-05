# Parameters Panel (Fusion add-in)

A panel docked on the right of Fusion that lists the active design's user parameters.

- Edit an expression and press **Enter** (or move focus away) to apply it. **Esc** reverts the field.
- Each change runs as one "Change parameter" command, so **Edit › Undo** takes it back.
- Invalid expressions are rejected before Fusion sees them; the field turns red with the reason.
- While another command is open (a sketch tool, Extrude...), editing is disabled until it finishes.
- Starred parameters (☆ in Modify › Change Parameters) sort to the top. The filter box matches names and comments.
- The **Model** footer shows the visible solid bodies' overall size, volume and an estimated PLA weight
  (density 1.24 g/cm³, solid; a sliced print with infill weighs less).

## Install (macOS)

Link this folder into Fusion's add-ins folder from the main print-lab checkout:

```
ln -s ~/dev/print-lab/tools/fusion/ParamsPanel \
  "$HOME/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/ParamsPanel"
```

Then in Fusion: **UTILITIES › ADD-INS › Scripts and Add-Ins** (Shift+S) › **Add-Ins** tab › **ParamsPanel** › **Run**,
and tick **Run on Startup**. Reopen a closed panel with **UTILITIES › ADD-INS › Parameters Panel**.

To remove it: Stop it in the same dialog and delete the link.
