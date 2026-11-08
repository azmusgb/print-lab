# Camera-fit page

Finish the `camera_carrier` Fusion model from an iPhone on the home network: Fusion's own pictures of the model (Iso,
Front, Top, Right, Back) and sliders for the parameters whose comments still say placeholder, provisional or verify.

```
iPhone  --http, token-->  server.py (Mac, :8765)  --127.0.0.1:8766-->  PhoneBridge add-in (inside Fusion)
```

- Only plain `N mm` parameters that are still provisional can change, within half to double their first-seen value.
  Derived ones (`carrier_x = board_x + ...`) and README figures (`stand_x`, `stand_y`, `coupon_x`) are read-only.
- Each change is one Fusion command, so **Edit › Undo** in Fusion takes it back. **Back to start** returns a parameter to
  the value it had when the server first saw it. Failed timeline steps show in a red banner on the page.
- It never saves the Fusion document. Changes are logged to `data/changes.log`. Picking a view turns Fusion's camera.

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

## Not yet checked

The PhoneBridge add-in has not been run inside Fusion yet; the server and page are tested against a fake of it.
