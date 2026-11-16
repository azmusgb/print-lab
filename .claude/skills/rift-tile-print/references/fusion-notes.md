# Fusion MCP notes for the RIFT tiles

Server `fusion` at 127.0.0.1:27182, tools `fusion_mcp_read` and `fusion_mcp_execute`.

- **Scripts fail while a command dialog is open.** Ask the owner to close it.
- **An exception rolls back the whole script.** Fix and rerun; check state first, since nothing from the failed run survives.
- **Occurrence names follow component names.** After renaming a component, look the occurrence up by its new name.
- **Deleting timeline features resets an occurrence's `transform2`.** Re-apply the transform and add a snapshot.
- **Import STEP for a smooth solid.** `RIFT_10IN_seed3_tear_matched6in_tileframe.step` gives 247 planar faces, a valid solid and about 106.51 cm3. A mesh convert gives triangle faces (844) and the owner rejected it ("Need a smooth solid").
- **Draft analysis** needs a B-rep body: `createInput([body], directionEntity)` takes a Python list. Meshes must be converted first.
- **Units:** the document works in cm; 3MF export from Fusion is in inches. Convert before slicing, or use the generator's STEP/STL instead.
- **Layout used:** the printed-scale 6 in component sits at Y +175.32 mm beside the 10 in at the origin, with a 0.001 mm gap (edge to edge). Add about 0.5 mm wall clearance if the owner asks for a real mounting gap.
- **Do not delete the owner's analyses or bodies** (a deleted CurvatureMap1 was lost once and had to be reported). Ask before removing anything, even an old copy.
- The document title was "faceted_hex seed 3 (c9f530ce03f2) - not saved"; do not save it for the owner.
