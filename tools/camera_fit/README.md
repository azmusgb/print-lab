# Camera-fit page

Finish the `camera_carrier` Fusion model from an iPhone on the home network: Fusion's own pictures of the model (Iso,
Front, Top, Right, Back) and sliders for the parameters whose comments still say placeholder, provisional or verify.

```
iPhone  --http, token-->  server.py (Mac, :8765)  --127.0.0.1:38117-->  PhoneBridge add-in (inside Fusion)
```

- Only plain `N mm` parameters that are still provisional can change, within half to double their first-seen value.
  Derived ones (`carrier_x = board_x + ...`) and README figures (`stand_x`, `stand_y`, `coupon_x`) are read-only.
- Each change is one Fusion command, so **Edit › Undo** in Fusion takes it back. **Back to start** returns a parameter to
  the value it had when the server first saw it. Failed timeline steps show in a red banner on the page.
- It never saves the Fusion document. Changes are logged to `data/changes.log`. Picking a view turns Fusion's camera.

The add-in is not open to the rest of the Mac: it refuses a request without the shared secret in `data/bridge-token`
(made by the server on first start), one with an `Origin` header (any browser page) or a wrong `Host` (DNS rebinding), a
body that isn't JSON, and an expression that isn't a plain `N mm`.

## Run

1. Install the add-in once (from the main checkout) and run it in Fusion (**Shift+S › Add-Ins › PhoneBridge › Run**):
   ```
   ln -s ~/dev/print-lab/tools/camera_fit/PhoneBridge \
     "$HOME/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/PhoneBridge"
   ```
2. Open `camera_carrier` in Fusion, then on the Mac: `python3 tools/camera_fit/server.py`
3. Open the printed `http://<mac ip>:8765/?t=<token>` link on the iPhone (same Wi-Fi or Tailscale; the Mac is 100.109.178.34
   on the tailnet). The token is in `data/token`; delete that file to rotate it.

The server listens on every interface so the phone can reach it, and anything with the link can change the placeholder sizes
while it runs. Stop it (Ctrl+C) when you're done. Standard library only; tests: `tests/test_camera_fit.py` (a fake bridge,
no Fusion).

## Checked

Run inside Fusion on 8 and 9 Nov: the add-in starts, the page reads the model, a slider edits a parameter, Back to start
returns it, and a change that breaks the timeline (`ring_hole_d` at its maximum) comes back with the failed step named and
recovers on reset. The view picker did nothing on 9 Nov (every view was the same picture, because Fusion ignores
`Viewport.viewOrientation` here); the add-in now sets the camera directly, and needs to be stopped and run again to pick that up.

## Walkthrough

The page opens on a step-through of the model's components: Whole model, then each top-level component in Fusion's browser
(carrier, head sled, rear gate, stand, tilt knob, lens ring, fit coupon, the reference board). A step shows that part on its own
(the others are hidden for the picture and put back before the add-in answers; untick "on its own" to see it in place), its
size and volume as Fusion measures them, the sizes tied to it by name with their sliders, and the fixed ones. Next/Previous,
the step chips and the left/right arrow keys move between steps. "All placeholder sizes" keeps the full list.

Which sizes belong to which part is a name-prefix table in `server.py` (`COMPONENT_PARAMS`): a part with no match says so. After
updating, stop and run the PhoneBridge add-in again so Fusion loads the new version.

## Build guide

The **Build guide** tab is a checklist for making the camera housing, read from `guide.json` on every load: confirm the board,
post and housing sizes (each size has a "measured and entered" tick), check the model builds clean (read live from Fusion), print
the fit coupon, print the carrier alone, print the rest, assemble. Each step shows the model's current values, buttons that jump to
that part in the walkthrough, a Done tick and a note. Progress and notes are saved in `data/progress.json` (not tracked).

The steps are a draft written from the model's own parameter comments: the build and assembly order isn't recorded anywhere else in
the repo. Edit `guide.json` to match how you actually work. With Fusion closed the guide still opens; current values show as "not read".
