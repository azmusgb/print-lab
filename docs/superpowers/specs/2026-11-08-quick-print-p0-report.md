# A19 Quick Print, P0: read-only runtime probe — Report

Date: 2026-11-08 (run 02:36–02:50) · Plan: pi-hub `docs/superpowers/plans/2026-11-08-a19-quick-print.md`, P0 · Status:
**findings, no behaviour change.** Read-only on every host: Bambuddy and the Pi were only read (GET, and a read-only
SQLite open of Bambuddy's key table, names and flags only, never key values). Nothing was uploaded, queued or started.
The only writes are local slice outputs in a scratch directory and the fixtures in this PR.

Environment: Mac (Darwin 27.2), print-lab `origin/main` ca0e79d, pi-hub `origin/main` a53b5ed (A19 and its plan merged),
Pi Hub live e693e6e.

## What this changes in the plan

| Plan decision | Finding | Effect |
|---|---|---|
| 5 (start check) | A naive `^M620 ` check counts **0 on the good file too**. The real check is a whole-start-block comparison. | Decision 5's wording stands; the validator below is the proposed form. |
| 4 (settings) | All seven candidates work, with three traps (below). Studio **silently accepts** some bad values. | P1 must allow-list and range-check itself; one candidate needs a second key. |
| 9 (credentials) | Bambuddy scopes are **boolean flags per key plus a printer list; no folder scope exists.** A separate staging key is possible. | Separate keys, folder enforced in Pi Hub's adapter. The control key needs **no** Library right (it has none). |
| 8 (storage) | Pi `/`: 29 GB, 10 GB free. The 3 GiB reserve and 4 GiB cap fit (10 − 4 = 6 GiB spare). The Pi is busy (load 5.3). | Figures kept. Slicing stays off the Pi. |

## Bambu Studio

- Executable `/Applications/BambuStudio.app/Contents/MacOS/BambuStudio`; `Info.plist` and `--help` both read
  **02.09.01.70**, equal to `EXPECTED_VERSION` (`lab/adapters/bambu.py:9`). OrcaSlicer is also installed (not used).
- Headless CLI works: `--slice`, `--outputdir`, `--export-3mf`, exit 0 and `plate_1.gcode`, `slice_info.config`
  in the output. The lab adapter slices a probe project in about 1 s for a small model. Real-model timing is P1's job.
- Output format: `.gcode.3mf` with `Metadata/plate_1.gcode`; estimate fields `prediction` and `weight` in
  `slice_info.config` (`lab/adapters/bambu.py:158`).
- **Base project:** the lab's known-good build `hex-tile_E-022_BLD-022-01.3mf` carries a complete project
  (`project_settings.config` with a 14,848-character `machine_start_gcode`, X2D 0.4, `0.20mm Standard @BBL X2D`, PLA).
  Not yet a Studio-saved preset for P1: the plan needs the owner to save one in Studio ("Standard 0.20 mm PLA, X2D 0.4").
  The Studio-saved fixture in the repo is `tests/fixtures/hex/studio_saved_v58_strip.gcode.3mf`.

## G-code regression (the 27 Oct air-print)

Compared the start region (from `; EXECUTABLE_BLOCK_START` to `; MACHINE_START_GCODE_END`) of a known-good slice and a
loose slice. The loose slice is the memory's recipe, re-made today on the installed Studio:

```
BambuStudio --load-settings "<BBL>/machine/Bambu Lab X2D 0.4 nozzle.json;<BBL>/process/0.20mm Standard @BBL X2D.json" \
  --load-filaments "<BBL>/filament/Bambu PLA Basic @BBL X2D 0.4 nozzle.json" --slice 0 cube20.stl
```

| | Known good (E-022) | Loose (STL + presets) |
|---|---|---|
| Start block | 404 lines | **12 lines** |
| `machine_start_gcode` setting | 15,321 chars | **48 chars** |
| `filament_ids` | `GFL99;GFL99;GFL99;GFL99` | **`""` (empty)** |
| Commands only in the good one | 64 distinct, including `M620`, `M620.10/.11/.17/.22/.6`, `M621`, `M622`, `M623`, `G29`, `G29.1/.2/.99`, `G150.x`, `G383.x`, `M1002` (29), `M109`, `M141`, `M960`, `M972`, `M975`, `T0` | none |

- `M620` appears **indented** (`  M620 S0A H-1 B`) and as `M620.10` and similar, so `^M620 ` at line start counts 0 in the good
  file. The old "grep for M620" rule would have rejected a good file.
- The stored `HEX_TILE_v73_textured.gcode.3mf` in the lab's checkout has the *good* start block. It was re-sliced; the
  original air-printing v73 file isn't kept. The loose slice above is the reproduction.
- **Proposed validator** (in `settings_probe.py`, `verdict`): the start block exists, contains every command the
  known-good start contains (whitespace-insensitive, any count ≥ 1), and `filament_ids` is non-empty. Result: **loose
  rejected** (12 lines; every `G29`, `M62x`, `M1002`, `M109` … missing; ids empty); **good accepted**. Fixtures:
  `tests/fixtures/quick/good_start_block.gcode`, `loose_start_block.gcode`. Caveat: the "good" reference is derived from
  the known-good file, so accepting it proves nothing; the rejection is the evidence. P1 should also compare the project's
  `machine_start_gcode` hash with the base project's.

## Verified setting overrides (real Studio slices, `write_print_3mf` + `patch_settings`)

Base: E-022 project, probe model of two stacked boxes (20×20×6 and 40×20×4 overhanging). Full table:
`docs/superpowers/specs/quick-print-p0/settings_probe.json`. Every successful slice also passed the start check.

| UI setting | Slicer key | Effect shown | Range / notes |
|---|---|---|---|
| Layer height | `layer_height` | 0.12 → 83 layers; 0.20 → 50; 0.28 → 36 | Profile's `min/max_layer_height` are 0.08 / 0.28. Studio **accepted 0.01 (981 layers) and 0.04**, and refused 0.6 ("cannot exceed nozzle diameter"). P1 must clamp to 0.08–0.28. |
| Walls | `wall_loops` | 2 → fewer inner walls; 4 → more; 0 and 20 accepted | Offer 1–6 or similar, chosen in P1. |
| Top layers | `top_shell_layers` | 7 → more solid layers; **3 changed nothing** | The profile's `top_shell_thickness` = 1 mm forces ≥ 5 layers. With `top_shell_thickness` = 0, 3 works (−10 KB). Needs both keys. |
| Bottom layers | `bottom_shell_layers` | 2 and 6 both change output | `bottom_shell_thickness` is 0 in the base, so no override. |
| Infill % | `sparse_infill_density` | 10% / 40% / 0% change output | 150% **refused** (range 0–100); 100% **refused with grid** ("grid doesn't work at 100%"). |
| Infill pattern | `sparse_infill_pattern` | `gyroid` +116 KB vs `grid` | A bogus value (`nonsense`) was **silently accepted** and sliced (−114 bytes): P1 must allow-list the pattern names. |
| Supports | `enable_support` | on → 26 `Support` + 3 `Support interface` features, +285 KB; off = baseline | Works. |
| Brim | `brim_type`, `brim_width` | `no_brim` removes the `Brim` feature (−31 KB); width 5 → −19 KB; width 100 accepted (+733 KB) | Clamp the width in P1. |

None of these is "approved" by P0 alone: each still needs its P1 test with the allowed range written down. P0 shows
the keys are real and have an effect on the installed Studio.

## Bambuddy

- **Version 1.3.0** (`GET /api/v1/updates/version`), matching `SUPPORTED_VERSION` (`hub/lab_start.py:22`). The OpenAPI
  document is at `/openapi.json` (not `/api/v1/openapi.json`): 660 paths.
- Relevant routes (read from the document, not exercised): `POST /api/v1/library/files/` (upload),
  `GET /library/files/{id}/download` (read-back), `DELETE /library/files/{id}`, `GET,POST /library/folders`,
  `POST /queue/`, `POST /queue/{id}/start`, `POST /queue/{id}/cancel`, `DELETE /queue/{id}`, `GET /queue/{id}`,
  `GET,POST,PATCH,DELETE /api-keys/`. It also has `POST /library/files/{id}/slice` (its own slicing; out of scope, A19).
- **Key scopes** (names and flags, read-only from `bambuddy.db`):

  | id | Name | Scopes | Printers |
  |---|---|---|---|
  | 1 | Pi Hub (read) | `can_read_status` | all |
  | 2 | Local AI Materials (read) | `can_read_status` | all |
  | 3 | Local AI Clear plate (control) | `can_control_printer`, `can_read_status` | 1 |
  | 4 | Pi Hub control | `can_queue`, `can_control_printer` | 1 |
  | 6 | print-lab | `can_read_status`, `can_manage_library` | all |

- **No folder-level scope.** The key table has one `can_manage_library` flag and a printer list; nothing names a
  folder. A key that can upload can delete any library file. So the limit to `quick-print` lives in Pi Hub's adapter:
  fixed folder id, an allow-list of calls, and delete only for ids Pi Hub recorded uploading.
- **Separation is possible:** a new "Pi Hub staging" key with `can_read_status` + `can_manage_library` (exactly the shape
  of key 6) keeps Library rights off both the read key and the control key. The control key (4) keeps `can_queue` and
  `can_control_printer` and gains nothing. Creating the key is an owner step (admin sign-in, as
  `deploy/bambuddy-control-key.py` does for key 4).
- Library folders today: `print-lab` (id 1, 5 files). No `quick-print` folder yet.
- Printer 1 status (`GET /printers/1/status`): connected, state FINISH, `developer_mode: true`, **`sdcard: true`**,
  `store_to_sdcard: false`. The `sdcard` flag says storage is present; it doesn't say that it is the USB stick, but it
  agrees with the owner's report. The 553 failure itself was not retried (needs an upload).

## Existing Pi Hub (pi-hub `origin/main` a53b5ed, by code)

- Gateway: `printer_control.BUSY` (`hub/printer_control.py:19`), `hold()` at :24; experiment start `hub/lab_start.py:96`,
  routes `hub/app.py:445, 460, 507, 515`; bed hold `hub/lab_hold.py` (`place` :32, `step` :73); owner role from
  `hub/auth.py`. Mac channel `hub/lab.py:700` with `hub/lab_guard.py`; Mac silent after 180 s (`hub/mac_lab.py:9`).
- Pi measurements (read-only SSH): `/` 29 GB, 18 GB used, **10 GB free**; `/mnt/usb1` 133 GB free (Movies drive);
  `/var/lib/pi-hub` 34 MB; Bambuddy's data 53 MB; 3.7 GB RAM with 1.8 GB available; **load average 5.29, 4.01, 3.39**
  on four cores. The Pi is already busy, which supports keeping slicing and mesh work off it.
- Design contracts in force: A7, A10, A12, A12b, A14, A16 (experiment preview), A19.

## Not verified here

- Bambuddy's upload, read-back, queue, start and error/timeout behaviour were **not exercised**: each needs a write.
  The known 553 behaviour without storage is from A12's facts, not re-run. P6 proves these against a fake first, and the
  real thing only in P10 with the owner present.
- Whether `sdcard: true` is the USB stick; the live queue's contents; the Studio-saved base preset (the owner must save
  one in Studio); timings for real models and large slices.
- `settings_probe.py` ran against one model and one base; it shows keys and effects, not every combination.

## Reproduce

```
uv run python docs/superpowers/specs/quick-print-p0/settings_probe.py \
  projects/hex-tile/prints/hex-tile_E-022_BLD-022-01.3mf \
  projects/hex-tile/prints/sliced/hex-tile_E-022_BLD-022-01.gcode.3mf <scratch dir>
```

(Both inputs are in the lab's main checkout; `projects/hex-tile/prints/` is partly untracked there.) Bambuddy: `curl
http://10.0.0.30:8000/openapi.json`, and the key table read with `sqlite3` in `mode=ro` on the Pi.
