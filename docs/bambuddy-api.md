# Bambuddy API endpoints

Bambuddy **1.2.5.7** at `http://10.0.0.30:8000` (the Pi). Generated 27 Oct 2026 from the live `/openapi.json`: **625 paths, 786 operations** in 61 groups. Interactive docs: `http://10.0.0.30:8000/docs`.

## Using it

- **Auth:** send an API key as `X-API-Key: bb_…` (or a signed-in user's `Authorization: Bearer <token>`). Sign-in is on, so almost everything refuses an anonymous call with 401.
- **print-lab's key** is in `~/.config/bambuddy/print-lab-key` (mode 600). `lab page` uses it to read spool colours (`GET /api/v1/inventory/spools`).
- **Key permissions** are set per key in Settings › API Keys (Read Status, Manage Queue, Control Printer, Manage Library, Manage Inventory, Manage Maintenance, Manage Archives, Manage Projects, cloud, electricity price, notifications). No key can change settings except the electricity price; that needs a signed-in user.
- `*` after a query parameter = required; `{name}` = path parameter; **Body** = request schema name (see `/docs` for its fields).

### What the print-lab key can read

Every GET without a path parameter was called once with the print-lab key on 27 Oct 2026 (read-only; status code only; nothing written). Skipped on purpose: `GET /api/v1/settings/backup` (creates a backup), the OIDC callback and authorize pages, the three exports, update/firmware checks (they call out to the internet) and `/cloud/*` (acts on the Bambu Cloud account).

| Result | Count | Meaning |
|---|---|---|
| ✅ 200 | 110 | readable with this key |
| 🚫 403 | 32 | the key lacks that permission |
| 🔒 401 | 6 | needs a signed-in user, not an API key |
| ⚠️ 400 / 422 | 20 | reachable, but needs query parameters |
| 404 | 1 | nothing there right now |

## Groups

| Group | Operations |
|---|---|
| [2fa](#2fa) | 24 |
| [ams-history](#ams-history) | 2 |
| [announcements](#announcements) | 2 |
| [api-keys](#api-keys) | 5 |
| [archives-purge](#archives-purge) | 4 |
| [archives](#archives) | 70 |
| [authentication](#authentication) | 26 |
| [bug-report](#bug-report) | 3 |
| [camera](#camera) | 17 |
| [camwall](#camwall) | 1 |
| [cloud](#cloud) | 18 |
| [connected-apps](#connected-apps) | 8 |
| [discovery](#discovery) | 8 |
| [external-links](#external-links) | 9 |
| [filament-catalog](#filament-catalog) | 8 |
| [finance](#finance) | 20 |
| [firmware](#firmware) | 6 |
| [github-backup](#github-backup) | 14 |
| [groups](#groups) | 10 |
| [ha-sensors](#ha-sensors) | 7 |
| [inventory](#inventory) | 65 |
| [kprofiles](#kprofiles) | 7 |
| [labels](#labels) | 4 |
| [library-tags](#library-tags) | 7 |
| [library-trash](#library-trash) | 8 |
| [library-variants](#library-variants) | 8 |
| [library](#library) | 40 |
| [Local Presets](#local-presets) | 9 |
| [local-backup](#local-backup) | 7 |
| [location-ha-sensors](#location-ha-sensors) | 7 |
| [maintenance](#maintenance) | 14 |
| [makerworld](#makerworld) | 5 |
| [metrics](#metrics) | 1 |
| [notification-templates](#notification-templates) | 7 |
| [notifications](#notifications) | 14 |
| [obico](#obico) | 4 |
| [orca-cloud](#orca-cloud) | 6 |
| [Other](#other) | 6 |
| [pending-uploads](#pending-uploads) | 7 |
| [print-log](#print-log) | 5 |
| [printer-sensor-history](#printer-sensor-history) | 2 |
| [printers](#printers) | 75 |
| [projects](#projects) | 29 |
| [queue](#queue) | 18 |
| [scheduled-dryings](#scheduled-dryings) | 3 |
| [settings](#settings) | 20 |
| [slice-jobs](#slice-jobs) | 1 |
| [Slicer Pipelines](#slicer-pipelines) | 13 |
| [Slicer Presets](#slicer-presets) | 4 |
| [smart-plugs](#smart-plugs) | 18 |
| [sponsor-prompt](#sponsor-prompt) | 2 |
| [spoolbuddy](#spoolbuddy) | 27 |
| [spoolman-inventory](#spoolman-inventory) | 29 |
| [spoolman](#spoolman) | 12 |
| [support](#support) | 5 |
| [system](#system) | 5 |
| [updates](#updates) | 4 |
| [user-notifications](#user-notifications) | 2 |
| [users](#users) | 10 |
| [virtual-printers](#virtual-printers) | 8 |
| [webhook](#webhook) | 6 |

## 2fa

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| DELETE | `/api/v1/auth/2fa/admin/{user_id}` | Admin Disable 2Fa | `{user_id}` | AdminDisable2FARequest |  |
| POST | `/api/v1/auth/2fa/email/disable` | Disable Email Otp |  | EmailOTPDisableRequest |  |
| POST | `/api/v1/auth/2fa/email/enable` | Enable Email Otp |  |  |  |
| POST | `/api/v1/auth/2fa/email/enable/confirm` | Confirm Enable Email Otp |  | EmailOTPEnableConfirmRequest |  |
| POST | `/api/v1/auth/2fa/email/send` | Send Email Otp |  | EmailOTPSendRequest |  |
| GET | `/api/v1/auth/2fa/status` | Get 2Fa Status |  |  | 🔒 401 user sign-in only |
| POST | `/api/v1/auth/2fa/totp/disable` | Disable Totp |  | TOTPDisableRequest |  |
| POST | `/api/v1/auth/2fa/totp/enable` | Enable Totp |  | TOTPEnableRequest |  |
| POST | `/api/v1/auth/2fa/totp/regenerate-backup-codes` | Regenerate Backup Codes |  | TOTPDisableRequest |  |
| POST | `/api/v1/auth/2fa/totp/setup` | Setup Totp |  | TOTPSetupRequest or null |  |
| POST | `/api/v1/auth/2fa/verify` | Verify 2Fa |  | TwoFAVerifyRequest |  |
| GET | `/api/v1/auth/oidc/authorize/{provider_id}` | Oidc Authorize | `{provider_id}` |  |  |
| GET | `/api/v1/auth/oidc/callback` | Oidc Callback | code, state, error |  | not probed |
| POST | `/api/v1/auth/oidc/exchange` | Oidc Exchange |  | OIDCExchangeRequest |  |
| GET | `/api/v1/auth/oidc/links` | List Oidc Links |  |  | 🔒 401 user sign-in only |
| DELETE | `/api/v1/auth/oidc/links/{provider_id}` | Remove Oidc Link | `{provider_id}` |  |  |
| GET | `/api/v1/auth/oidc/providers` | List Oidc Providers |  |  | ✅ 200 |
| POST | `/api/v1/auth/oidc/providers` | Create Oidc Provider |  | OIDCProviderCreate |  |
| GET | `/api/v1/auth/oidc/providers/all` | List All Oidc Providers |  |  | ✅ 200 |
| DELETE | `/api/v1/auth/oidc/providers/{provider_id}` | Delete Oidc Provider | `{provider_id}` |  |  |
| PUT | `/api/v1/auth/oidc/providers/{provider_id}` | Update Oidc Provider | `{provider_id}` | OIDCProviderUpdate |  |
| DELETE | `/api/v1/auth/oidc/providers/{provider_id}/icon` | Delete Oidc Provider Icon | `{provider_id}` |  |  |
| GET | `/api/v1/auth/oidc/providers/{provider_id}/icon` | Get Oidc Provider Icon | `{provider_id}` |  |  |
| POST | `/api/v1/auth/oidc/providers/{provider_id}/icon/refresh` | Refresh Oidc Provider Icon | `{provider_id}` |  |  |

## ams-history

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| DELETE | `/api/v1/ams-history/{printer_id}` | Delete Old History | `{printer_id}`, days |  |  |
| GET | `/api/v1/ams-history/{printer_id}/{ams_id}` | Get Ams History | `{printer_id}`, `{ams_id}`, hours |  |  |

## announcements

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/announcements` | List Announcements |  |  | ✅ 200 |
| POST | `/api/v1/announcements/{public_id}/read` | Mark Announcement Read | `{public_id}` |  |  |

## api-keys

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/api-keys/` | List Api Keys |  |  | 🚫 403 no permission |
| POST | `/api/v1/api-keys/` | Create Api Key |  | APIKeyCreate |  |
| DELETE | `/api/v1/api-keys/{key_id}` | Delete Api Key | `{key_id}` |  |  |
| GET | `/api/v1/api-keys/{key_id}` | Get Api Key | `{key_id}` |  |  |
| PATCH | `/api/v1/api-keys/{key_id}` | Update Api Key | `{key_id}` | APIKeyUpdate |  |

## archives

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/archives/` | List Archives | printer_id, project_id, date_from, date_to, limit, offset |  | ✅ 200 |
| GET | `/api/v1/archives/analysis/failures` | Analyze Failures | days, date_from, date_to, printer_id, project_id, created_by_id |  | ✅ 200 |
| POST | `/api/v1/archives/backfill-hashes` | Backfill Content Hashes |  |  |  |
| GET | `/api/v1/archives/compare` | Compare Archives | archive_ids* |  | ⚠️ 422 needs query params |
| GET | `/api/v1/archives/confirm/{token}/{verdict}` | Confirm Outcome Page | `{token}`, `{verdict}` |  |  |
| POST | `/api/v1/archives/confirm/{token}/{verdict}` | Confirm Outcome By Token | `{token}`, `{verdict}` |  |  |
| GET | `/api/v1/archives/export` | Export Archives | format, fields, printer_id, project_id, status, date_from, date_to, search |  | not probed |
| GET | `/api/v1/archives/no-3mf-warning` | No 3Mf Warning |  |  | ✅ 200 |
| POST | `/api/v1/archives/recalculate-costs` | Recalculate All Costs |  |  |  |
| POST | `/api/v1/archives/rescan-all` | Rescan All Archives |  |  |  |
| GET | `/api/v1/archives/search` | Search Archives | q*, printer_id, project_id, status, limit, offset |  | ⚠️ 422 needs query params |
| POST | `/api/v1/archives/search/rebuild-index` | Rebuild Search Index |  |  |  |
| GET | `/api/v1/archives/slim` | List Archives Slim | date_from, date_to, created_by_id, limit, offset |  | ✅ 200 |
| GET | `/api/v1/archives/stats` | Get Archive Stats | date_from, date_to, created_by_id |  | ✅ 200 |
| GET | `/api/v1/archives/stats/export` | Export Stats | format, days, printer_id, project_id, created_by_id |  | not probed |
| GET | `/api/v1/archives/tags` | Get All Tags |  |  | ✅ 200 |
| DELETE | `/api/v1/archives/tags/{tag_name}` | Delete Tag | `{tag_name}` |  |  |
| PUT | `/api/v1/archives/tags/{tag_name}` | Rename Tag | `{tag_name}` |  |  |
| POST | `/api/v1/archives/upload` | Upload Archive | printer_id, prefer_filename_for_name | Body_upload_archive_api_v1_archives_upload_post |  |
| POST | `/api/v1/archives/upload-bulk` | Upload Archives Bulk | printer_id, prefer_filename_for_name | Body_upload_archives_bulk_api_v1_archives_upload_bulk_post |  |
| POST | `/api/v1/archives/upload-source` | Upload Source 3Mf By Name | print_name | Body_upload_source_3mf_by_name_api_v1_archives_upload_source_post |  |
| DELETE | `/api/v1/archives/{archive_id}` | Delete Archive | `{archive_id}`, purge_stats |  |  |
| GET | `/api/v1/archives/{archive_id}` | Get Archive | `{archive_id}` |  |  |
| PATCH | `/api/v1/archives/{archive_id}` | Update Archive | `{archive_id}` | ArchiveUpdate |  |
| GET | `/api/v1/archives/{archive_id}/capabilities` | Get Archive Capabilities | `{archive_id}` |  |  |
| GET | `/api/v1/archives/{archive_id}/delete-impact` | Get Archive Delete Impact | `{archive_id}` |  |  |
| GET | `/api/v1/archives/{archive_id}/dl/{token}/{filename}` | Download Archive For Slicer | `{archive_id}`, `{token}`, `{filename}` |  |  |
| GET | `/api/v1/archives/{archive_id}/download` | Download Archive | `{archive_id}`, inline |  |  |
| GET | `/api/v1/archives/{archive_id}/duplicates` | Get Archive Duplicates | `{archive_id}` |  |  |
| DELETE | `/api/v1/archives/{archive_id}/f3d` | Delete F3D | `{archive_id}` |  |  |
| GET | `/api/v1/archives/{archive_id}/f3d` | Download F3D | `{archive_id}` |  |  |
| POST | `/api/v1/archives/{archive_id}/f3d` | Upload F3D | `{archive_id}` | Body_upload_f3d_api_v1_archives__archive_id__f3d_post |  |
| POST | `/api/v1/archives/{archive_id}/favorite` | Toggle Favorite | `{archive_id}` |  |  |
| GET | `/api/v1/archives/{archive_id}/filament-requirements` | Get Filament Requirements | `{archive_id}`, plate_id, request_id, full_slots |  |  |
| GET | `/api/v1/archives/{archive_id}/file/{filename}` | Download Archive With Filename | `{archive_id}`, `{filename}` |  |  |
| GET | `/api/v1/archives/{archive_id}/gcode` | Get Gcode | `{archive_id}`, plate |  |  |
| POST | `/api/v1/archives/{archive_id}/media-download-token` | Create Archive Media Download Token | `{archive_id}` |  |  |
| GET | `/api/v1/archives/{archive_id}/media/dl/{token}/{filename}` | Download Archive Media With Token | `{archive_id}`, `{token}`, `{filename}` |  |  |
| POST | `/api/v1/archives/{archive_id}/photos` | Upload Photo | `{archive_id}` | Body_upload_photo_api_v1_archives__archive_id__photos_post |  |
| DELETE | `/api/v1/archives/{archive_id}/photos/{filename}` | Delete Photo | `{archive_id}`, `{filename}` |  |  |
| GET | `/api/v1/archives/{archive_id}/photos/{filename}` | Get Photo | `{archive_id}`, `{filename}`, token |  |  |
| GET | `/api/v1/archives/{archive_id}/plate-preview` | Get Plate Preview | `{archive_id}`, token |  |  |
| GET | `/api/v1/archives/{archive_id}/plate-thumbnail/{plate_index}` | Get Plate Thumbnail | `{archive_id}`, `{plate_index}`, token |  |  |
| GET | `/api/v1/archives/{archive_id}/plates` | Get Archive Plates | `{archive_id}` |  |  |
| GET | `/api/v1/archives/{archive_id}/printer-media` | Get Archive Printer Media | `{archive_id}` |  |  |
| GET | `/api/v1/archives/{archive_id}/project-image/{image_path}` | Get Project Image | `{archive_id}`, `{image_path}`, token |  |  |
| GET | `/api/v1/archives/{archive_id}/project-page` | Get Project Page | `{archive_id}` |  |  |
| PATCH | `/api/v1/archives/{archive_id}/project-page` | Update Project Page | `{archive_id}` | object |  |
| GET | `/api/v1/archives/{archive_id}/qrcode` | Get Qrcode | `{archive_id}`, size, token |  |  |
| POST | `/api/v1/archives/{archive_id}/reprint` | Reprint Archive | `{archive_id}`, printer_id* |  |  |
| POST | `/api/v1/archives/{archive_id}/rescan` | Rescan Archive | `{archive_id}` |  |  |
| GET | `/api/v1/archives/{archive_id}/runs` | List Archive Runs | `{archive_id}` |  |  |
| GET | `/api/v1/archives/{archive_id}/similar` | Find Similar Archives | `{archive_id}`, limit |  |  |
| POST | `/api/v1/archives/{archive_id}/slice` | Slice Archive | `{archive_id}` | SliceRequest |  |
| POST | `/api/v1/archives/{archive_id}/slicer-token` | Create Archive Slicer Token | `{archive_id}` |  |  |
| DELETE | `/api/v1/archives/{archive_id}/source` | Delete Source 3Mf | `{archive_id}` |  |  |
| GET | `/api/v1/archives/{archive_id}/source` | Download Source 3Mf | `{archive_id}` |  |  |
| POST | `/api/v1/archives/{archive_id}/source` | Upload Source 3Mf | `{archive_id}` | Body_upload_source_3mf_api_v1_archives__archive_id__source_post |  |
| GET | `/api/v1/archives/{archive_id}/source-dl/{token}/{filename}` | Download Source 3Mf For Slicer With Token | `{archive_id}`, `{token}`, `{filename}` |  |  |
| POST | `/api/v1/archives/{archive_id}/source-slicer-token` | Create Source Slicer Token | `{archive_id}` |  |  |
| GET | `/api/v1/archives/{archive_id}/source/{filename}` | Download Source 3Mf For Slicer | `{archive_id}`, `{filename}` |  |  |
| GET | `/api/v1/archives/{archive_id}/thumbnail` | Get Thumbnail | `{archive_id}`, token |  |  |
| DELETE | `/api/v1/archives/{archive_id}/timelapse` | Delete Timelapse | `{archive_id}` |  |  |
| GET | `/api/v1/archives/{archive_id}/timelapse` | Get Timelapse | `{archive_id}`, token |  |  |
| GET | `/api/v1/archives/{archive_id}/timelapse/info` | Get Timelapse Info | `{archive_id}` |  |  |
| POST | `/api/v1/archives/{archive_id}/timelapse/process` | Process Timelapse | `{archive_id}` | Body_process_timelapse_api_v1_archives__archive_id__timelapse_process_post |  |
| POST | `/api/v1/archives/{archive_id}/timelapse/scan` | Scan Timelapse | `{archive_id}` |  |  |
| POST | `/api/v1/archives/{archive_id}/timelapse/select` | Select Timelapse | `{archive_id}`, filename* |  |  |
| GET | `/api/v1/archives/{archive_id}/timelapse/thumbnails` | Get Timelapse Thumbnails | `{archive_id}`, count, width |  |  |
| POST | `/api/v1/archives/{archive_id}/timelapse/upload` | Upload Timelapse | `{archive_id}` | Body_upload_timelapse_api_v1_archives__archive_id__timelapse_upload_post |  |

## archives-purge

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| POST | `/api/v1/archives/purge` | Execute Archive Purge |  | ArchivePurgeRequest |  |
| GET | `/api/v1/archives/purge/preview` | Preview Archive Purge | older_than_days*, purge_stats |  | 🚫 403 no permission |
| GET | `/api/v1/archives/purge/settings` | Get Archive Purge Settings |  |  | 🚫 403 no permission |
| PUT | `/api/v1/archives/purge/settings` | Update Archive Purge Settings |  | ArchivePurgeSettings |  |

## authentication

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| POST | `/api/v1/auth/advanced-auth/disable` | Disable Advanced Auth |  |  |  |
| POST | `/api/v1/auth/advanced-auth/enable` | Enable Advanced Auth |  |  |  |
| GET | `/api/v1/auth/advanced-auth/status` | Get Advanced Auth Status |  |  | ✅ 200 |
| POST | `/api/v1/auth/disable` | Disable Auth |  |  |  |
| GET | `/api/v1/auth/encryption-status` | Get Encryption Status |  |  | 🚫 403 no permission |
| POST | `/api/v1/auth/forgot-password` | Forgot Password |  | ForgotPasswordRequest |  |
| POST | `/api/v1/auth/forgot-password/confirm` | Forgot Password Confirm |  | ForgotPasswordConfirmRequest |  |
| POST | `/api/v1/auth/ldap/provision` | Provision Ldap User |  | LDAPProvisionRequest |  |
| GET | `/api/v1/auth/ldap/search` | Search Ldap Directory | q* |  | 🚫 403 no permission |
| GET | `/api/v1/auth/ldap/status` | Get Ldap Status |  |  | ✅ 200 |
| POST | `/api/v1/auth/ldap/test` | Test Ldap |  |  |  |
| POST | `/api/v1/auth/login` | Login |  | LoginRequest |  |
| POST | `/api/v1/auth/logout` | Logout |  |  |  |
| GET | `/api/v1/auth/me` | Get Current User Info |  |  | ✅ 200 |
| POST | `/api/v1/auth/media-token` | Mint Media Token |  |  |  |
| POST | `/api/v1/auth/reset-password` | Reset User Password |  | ResetPasswordRequest |  |
| POST | `/api/v1/auth/setup` | Setup Auth |  | SetupRequest |  |
| GET | `/api/v1/auth/smtp` | Get Smtp Config |  |  | ✅ 200 |
| POST | `/api/v1/auth/smtp` | Save Smtp Config |  | SMTPSettings |  |
| POST | `/api/v1/auth/smtp/test` | Test Smtp Connection |  | TestSMTPRequest |  |
| GET | `/api/v1/auth/status` | Get Auth Status |  |  | ✅ 200 |
| GET | `/api/v1/auth/tokens` | List Long Lived Tokens | user_id |  | 🚫 403 no permission |
| POST | `/api/v1/auth/tokens` | Create Long Lived Camera Token |  | object |  |
| GET | `/api/v1/auth/tokens/all` | List All Long Lived Tokens |  |  | 🚫 403 no permission |
| DELETE | `/api/v1/auth/tokens/{token_id}` | Revoke Long Lived Token | `{token_id}` |  |  |
| POST | `/api/v1/auth/ws-token` | Mint Websocket Token |  |  |  |

## bug-report

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| POST | `/api/v1/bug-report/start-logging` | Start Logging |  |  |  |
| POST | `/api/v1/bug-report/stop-logging` | Stop Logging | was_debug |  |  |
| POST | `/api/v1/bug-report/submit` | Submit Bug Report |  | BugReportRequest |  |

## camera

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| POST | `/api/v1/printers/camera/stream-token` | Create Stream Token |  |  |  |
| GET | `/api/v1/printers/{printer_id}/camera/check-plate` | Check Plate Empty | `{printer_id}`, plate_type, use_external, include_debug_image |  |  |
| POST | `/api/v1/printers/{printer_id}/camera/diagnose` | Diagnose Camera Route | `{printer_id}` |  |  |
| POST | `/api/v1/printers/{printer_id}/camera/external/test` | Test External Camera | `{printer_id}`, url*, camera_type* |  |  |
| DELETE | `/api/v1/printers/{printer_id}/camera/plate-detection/calibrate` | Delete Plate Calibration | `{printer_id}`, plate_type |  |  |
| POST | `/api/v1/printers/{printer_id}/camera/plate-detection/calibrate` | Calibrate Plate Detection | `{printer_id}`, label, use_external |  |  |
| GET | `/api/v1/printers/{printer_id}/camera/plate-detection/references` | Get Plate References | `{printer_id}` |  |  |
| DELETE | `/api/v1/printers/{printer_id}/camera/plate-detection/references/{index}` | Delete Reference | `{printer_id}`, `{index}` |  |  |
| PUT | `/api/v1/printers/{printer_id}/camera/plate-detection/references/{index}` | Update Reference Label | `{printer_id}`, `{index}`, label* |  |  |
| GET | `/api/v1/printers/{printer_id}/camera/plate-detection/references/{index}/thumbnail` | Get Reference Thumbnail | `{printer_id}`, `{index}`, token |  |  |
| GET | `/api/v1/printers/{printer_id}/camera/plate-detection/status` | Get Plate Detection Status | `{printer_id}`, plate_type |  |  |
| GET | `/api/v1/printers/{printer_id}/camera/snapshot` | Camera Snapshot | `{printer_id}`, token |  |  |
| GET | `/api/v1/printers/{printer_id}/camera/status` | Camera Status | `{printer_id}` |  |  |
| GET | `/api/v1/printers/{printer_id}/camera/stop` | Stop Camera Stream | `{printer_id}` |  |  |
| POST | `/api/v1/printers/{printer_id}/camera/stop` | Stop Camera Stream | `{printer_id}` |  |  |
| GET | `/api/v1/printers/{printer_id}/camera/stream` | Camera Stream | `{printer_id}`, fps, token |  |  |
| GET | `/api/v1/printers/{printer_id}/camera/test` | Test Camera | `{printer_id}` |  |  |

## camwall

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/camwall/printers` | List Camwall Printers | token |  | 🔒 401 user sign-in only |

## cloud

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/cloud/builtin-filaments` | Get Builtin Filaments |  |  | not probed |
| GET | `/api/v1/cloud/devices` | Get Devices |  |  | not probed |
| GET | `/api/v1/cloud/fields` | Get All Preset Fields |  |  | not probed |
| GET | `/api/v1/cloud/fields/{preset_type}` | Get Preset Fields | `{preset_type}` |  |  |
| GET | `/api/v1/cloud/filament-id-map` | Get Filament Id Map |  |  | not probed |
| POST | `/api/v1/cloud/filament-info` | Get Filament Info |  | string[] |  |
| GET | `/api/v1/cloud/filaments` | Get Filament Presets | version |  | not probed |
| GET | `/api/v1/cloud/firmware-updates` | Get Firmware Updates |  |  | not probed |
| POST | `/api/v1/cloud/login` | Login |  | CloudLoginRequest |  |
| POST | `/api/v1/cloud/logout` | Logout |  |  |  |
| GET | `/api/v1/cloud/settings` | Get Slicer Settings | version |  | not probed |
| POST | `/api/v1/cloud/settings` | Create Setting |  | SlicerSettingCreate |  |
| DELETE | `/api/v1/cloud/settings/{setting_id}` | Delete Setting | `{setting_id}` |  |  |
| GET | `/api/v1/cloud/settings/{setting_id}` | Get Setting Detail | `{setting_id}` |  |  |
| PUT | `/api/v1/cloud/settings/{setting_id}` | Update Setting | `{setting_id}` | SlicerSettingUpdate |  |
| GET | `/api/v1/cloud/status` | Get Auth Status |  |  | not probed |
| POST | `/api/v1/cloud/token` | Set Token |  | CloudTokenRequest |  |
| POST | `/api/v1/cloud/verify` | Verify Code |  | CloudVerifyRequest |  |

## connected-apps

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/connect/apps` | List Connected Apps |  |  | 🚫 403 no permission |
| POST | `/api/v1/connect/apps` | Create Connected App |  | ConnectedAppCreate |  |
| DELETE | `/api/v1/connect/apps/{app_id}` | Delete Connected App | `{app_id}` |  |  |
| PATCH | `/api/v1/connect/apps/{app_id}` | Update Connected App | `{app_id}` | ConnectedAppUpdate |  |
| POST | `/api/v1/connect/apps/{app_id}/rotate-secret` | Rotate Connected App Secret | `{app_id}` |  |  |
| POST | `/api/v1/connect/authorize` | Authorize |  | ConnectAuthorizeRequest |  |
| GET | `/api/v1/connect/authorize/info` | Authorize Info | client_id*, redirect_uri* |  | not probed |
| POST | `/api/v1/connect/token` | Exchange Code |  | ConnectTokenRequest |  |

## discovery

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/discovery/info` | Get Discovery Info |  |  | 🚫 403 no permission |
| GET | `/api/v1/discovery/printers` | Get Discovered Printers |  |  | 🚫 403 no permission |
| POST | `/api/v1/discovery/scan` | Start Subnet Scan |  | SubnetScanRequest |  |
| GET | `/api/v1/discovery/scan/status` | Get Scan Status |  |  | 🚫 403 no permission |
| POST | `/api/v1/discovery/scan/stop` | Stop Subnet Scan |  |  |  |
| POST | `/api/v1/discovery/start` | Start Discovery | duration |  |  |
| GET | `/api/v1/discovery/status` | Get Discovery Status |  |  | 🚫 403 no permission |
| POST | `/api/v1/discovery/stop` | Stop Discovery |  |  |  |

## external-links

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/external-links/` | List External Links |  |  | ✅ 200 |
| POST | `/api/v1/external-links/` | Create External Link |  | ExternalLinkCreate |  |
| PUT | `/api/v1/external-links/reorder` | Reorder External Links |  | ExternalLinkReorder |  |
| DELETE | `/api/v1/external-links/{link_id}` | Delete External Link | `{link_id}` |  |  |
| GET | `/api/v1/external-links/{link_id}` | Get External Link | `{link_id}` |  |  |
| PATCH | `/api/v1/external-links/{link_id}` | Update External Link | `{link_id}` | ExternalLinkUpdate |  |
| DELETE | `/api/v1/external-links/{link_id}/icon` | Delete Icon | `{link_id}` |  |  |
| GET | `/api/v1/external-links/{link_id}/icon` | Get Icon | `{link_id}`, token |  |  |
| POST | `/api/v1/external-links/{link_id}/icon` | Upload Icon | `{link_id}` | Body_upload_icon_api_v1_external_links__link_id__icon_post |  |

## filament-catalog

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/filament-catalog/` | List Filaments |  |  | ✅ 200 |
| POST | `/api/v1/filament-catalog/` | Create Filament |  | FilamentCreate |  |
| GET | `/api/v1/filament-catalog/by-type/{filament_type}` | Get Filaments By Type | `{filament_type}` |  |  |
| POST | `/api/v1/filament-catalog/calculate-cost` | Calculate Cost | filament_id*, weight_grams* |  |  |
| POST | `/api/v1/filament-catalog/seed-defaults` | Seed Default Filaments |  |  |  |
| DELETE | `/api/v1/filament-catalog/{filament_id}` | Delete Filament | `{filament_id}` |  |  |
| GET | `/api/v1/filament-catalog/{filament_id}` | Get Filament | `{filament_id}` |  |  |
| PATCH | `/api/v1/filament-catalog/{filament_id}` | Update Filament | `{filament_id}` | FilamentUpdate |  |

## finance

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/finance/cost-centers` | List Cost Centers | include_inactive |  | 🔒 401 user sign-in only |
| POST | `/api/v1/finance/cost-centers` | Create Cost Center |  | CostCenterCreateRequest |  |
| GET | `/api/v1/finance/cost-centers/mine` | Get My Cost Centers |  |  | 🔒 401 user sign-in only |
| DELETE | `/api/v1/finance/cost-centers/{cost_center_id}` | Delete Cost Center | `{cost_center_id}` |  |  |
| GET | `/api/v1/finance/cost-centers/{cost_center_id}` | Get Cost Center | `{cost_center_id}` |  |  |
| PATCH | `/api/v1/finance/cost-centers/{cost_center_id}` | Update Cost Center | `{cost_center_id}` | CostCenterUpdateRequest |  |
| PATCH | `/api/v1/finance/cost-centers/{cost_center_id}/budgets` | Update Cost Center Budgets | `{cost_center_id}` | CostCenterBudgetUpdateRequest |  |
| POST | `/api/v1/finance/cost-centers/{cost_center_id}/members` | Upsert Cost Center Member | `{cost_center_id}` | CostCenterMemberRequest |  |
| DELETE | `/api/v1/finance/cost-centers/{cost_center_id}/members/{user_id}` | Remove Cost Center Member | `{cost_center_id}`, `{user_id}` |  |  |
| GET | `/api/v1/finance/me/balance` | Get My Balance |  |  | 🚫 403 no permission |
| GET | `/api/v1/finance/me/transactions` | Get My Transactions | limit, offset |  | 🚫 403 no permission |
| POST | `/api/v1/finance/rebuild-balance-ledger` | Rebuild Balance Ledger |  |  |  |
| GET | `/api/v1/finance/transactions` | Get All Transactions | limit, offset, user_id |  | 🚫 403 no permission |
| POST | `/api/v1/finance/transactions/manual` | Create Manual Print |  | ManualPrintRequest |  |
| DELETE | `/api/v1/finance/transactions/{transaction_id}` | Delete Transaction | `{transaction_id}` |  |  |
| PATCH | `/api/v1/finance/transactions/{transaction_id}` | Edit Transaction | `{transaction_id}` | TransactionEditRequest |  |
| GET | `/api/v1/finance/users/{user_id}/balance` | Get User Balance | `{user_id}` |  |  |
| POST | `/api/v1/finance/users/{user_id}/deposit` | Deposit User Balance | `{user_id}` | WalletAdjustmentRequest |  |
| GET | `/api/v1/finance/users/{user_id}/transactions` | Get User Transactions | `{user_id}`, limit, offset |  |  |
| POST | `/api/v1/finance/users/{user_id}/withdraw` | Withdraw User Balance | `{user_id}` | WalletAdjustmentRequest |  |

## firmware

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/firmware/latest` | Get All Latest Firmware |  |  | not probed |
| GET | `/api/v1/firmware/updates` | Check Firmware Updates |  |  | not probed |
| GET | `/api/v1/firmware/updates/{printer_id}` | Check Printer Firmware | `{printer_id}` |  |  |
| GET | `/api/v1/firmware/updates/{printer_id}/prepare` | Prepare Firmware Upload | `{printer_id}`, version |  |  |
| POST | `/api/v1/firmware/updates/{printer_id}/upload` | Start Firmware Upload | `{printer_id}`, version |  |  |
| GET | `/api/v1/firmware/updates/{printer_id}/upload/status` | Get Firmware Upload Status | `{printer_id}` |  |  |

## github-backup

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/github-backup/cloud-accounts` | Get Cloud Accounts |  |  | 🚫 403 no permission |
| GET | `/api/v1/github-backup/commits` | List Commits | limit |  | 🚫 403 no permission |
| DELETE | `/api/v1/github-backup/config` | Delete Config |  |  |  |
| GET | `/api/v1/github-backup/config` | Get Config |  |  | 🚫 403 no permission |
| PATCH | `/api/v1/github-backup/config` | Update Config |  | GitHubBackupConfigUpdate |  |
| POST | `/api/v1/github-backup/config` | Save Config |  | GitHubBackupConfigCreate |  |
| DELETE | `/api/v1/github-backup/logs` | Clear Logs | keep_last |  |  |
| GET | `/api/v1/github-backup/logs` | Get Logs | limit, offset |  | 🚫 403 no permission |
| POST | `/api/v1/github-backup/restore` | Restore Backup |  | GitHubRestoreRequest |  |
| GET | `/api/v1/github-backup/restore/preview` | Preview Restore | ref |  | 🚫 403 no permission |
| POST | `/api/v1/github-backup/run` | Trigger Backup |  |  |  |
| GET | `/api/v1/github-backup/status` | Get Status |  |  | 🚫 403 no permission |
| POST | `/api/v1/github-backup/test` | Test Connection | repo_url*, token*, provider |  |  |
| POST | `/api/v1/github-backup/test-stored` | Test Stored Connection |  |  |  |

## groups

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/groups` | List Groups |  |  | 🚫 403 no permission |
| POST | `/api/v1/groups` | Create Group |  | GroupCreate |  |
| GET | `/api/v1/groups/` | List Groups |  |  | 🚫 403 no permission |
| POST | `/api/v1/groups/` | Create Group |  | GroupCreate |  |
| GET | `/api/v1/groups/permissions` | List Permissions |  |  | 🚫 403 no permission |
| DELETE | `/api/v1/groups/{group_id}` | Delete Group | `{group_id}` |  |  |
| GET | `/api/v1/groups/{group_id}` | Get Group | `{group_id}` |  |  |
| PATCH | `/api/v1/groups/{group_id}` | Update Group | `{group_id}` | GroupUpdate |  |
| DELETE | `/api/v1/groups/{group_id}/users/{user_id}` | Remove User From Group | `{group_id}`, `{user_id}` |  |  |
| POST | `/api/v1/groups/{group_id}/users/{user_id}` | Add User To Group | `{group_id}`, `{user_id}` |  |  |

## ha-sensors

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/ha-sensors/` | List Ha Sensors | printer_id |  | ✅ 200 |
| POST | `/api/v1/ha-sensors/` | Create Ha Sensor |  | PrinterHASensorCreate |  |
| GET | `/api/v1/ha-sensors/by-printer/{printer_id}/readings` | Get Printer Sensor Readings | `{printer_id}` |  |  |
| GET | `/api/v1/ha-sensors/entities` | List Bindable Entities | search |  | ⚠️ 400 needs input |
| DELETE | `/api/v1/ha-sensors/{sensor_id}` | Delete Ha Sensor | `{sensor_id}` |  |  |
| GET | `/api/v1/ha-sensors/{sensor_id}` | Get Ha Sensor | `{sensor_id}` |  |  |
| PATCH | `/api/v1/ha-sensors/{sensor_id}` | Update Ha Sensor | `{sensor_id}` | PrinterHASensorUpdate |  |

## inventory

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/inventory/assignments` | List Assignments | printer_id |  | ✅ 200 |
| POST | `/api/v1/inventory/assignments` | Assign Spool |  | SpoolAssignmentCreate |  |
| DELETE | `/api/v1/inventory/assignments/{printer_id}/{ams_id}/{tray_id}` | Unassign Spool | `{printer_id}`, `{ams_id}`, `{tray_id}` |  |  |
| GET | `/api/v1/inventory/catalog` | Get Spool Catalog |  |  | ✅ 200 |
| POST | `/api/v1/inventory/catalog` | Add Catalog Entry |  | CatalogEntryCreate |  |
| POST | `/api/v1/inventory/catalog/bulk-delete` | Bulk Delete Catalog Entries |  | BulkDeleteIdsRequest |  |
| POST | `/api/v1/inventory/catalog/reset` | Reset Spool Catalog |  |  |  |
| DELETE | `/api/v1/inventory/catalog/{entry_id}` | Delete Catalog Entry | `{entry_id}` |  |  |
| PUT | `/api/v1/inventory/catalog/{entry_id}` | Update Catalog Entry | `{entry_id}` | CatalogEntryUpdate |  |
| GET | `/api/v1/inventory/colors` | Get Color Catalog |  |  | ✅ 200 |
| POST | `/api/v1/inventory/colors` | Add Color Entry |  | ColorEntryCreate |  |
| POST | `/api/v1/inventory/colors/bulk-delete` | Bulk Delete Color Entries |  | BulkDeleteIdsRequest |  |
| GET | `/api/v1/inventory/colors/by-material` | Get Color By Material | hex*, material |  | ⚠️ 422 needs query params |
| GET | `/api/v1/inventory/colors/lookup` | Lookup Color | manufacturer*, color_name*, material |  | ⚠️ 422 needs query params |
| GET | `/api/v1/inventory/colors/map` | Get Color Name Map |  |  | ✅ 200 |
| POST | `/api/v1/inventory/colors/reset` | Reset Color Catalog |  |  |  |
| GET | `/api/v1/inventory/colors/search` | Search Colors | manufacturer, material |  | ✅ 200 |
| POST | `/api/v1/inventory/colors/sync` | Sync From Filamentcolors |  |  |  |
| DELETE | `/api/v1/inventory/colors/{entry_id}` | Delete Color Entry | `{entry_id}` |  |  |
| PUT | `/api/v1/inventory/colors/{entry_id}` | Update Color Entry | `{entry_id}` | ColorEntryUpdate |  |
| GET | `/api/v1/inventory/locations` | List Locations |  |  | ✅ 200 |
| POST | `/api/v1/inventory/locations` | Create Location |  | LocationCreate |  |
| DELETE | `/api/v1/inventory/locations/{location_id}` | Delete Location | `{location_id}` |  |  |
| PATCH | `/api/v1/inventory/locations/{location_id}` | Update Location | `{location_id}` | LocationUpdate |  |
| DELETE | `/api/v1/inventory/shopping-list` | Clear Shopping List |  |  |  |
| GET | `/api/v1/inventory/shopping-list` | Get Shopping List |  |  | ✅ 200 |
| POST | `/api/v1/inventory/shopping-list` | Add To Shopping List |  | ShoppingListItemCreate |  |
| DELETE | `/api/v1/inventory/shopping-list/{item_id}` | Remove From Shopping List | `{item_id}` |  |  |
| PATCH | `/api/v1/inventory/shopping-list/{item_id}/status` | Update Shopping List Status | `{item_id}` | ShoppingListItemStatusUpdate |  |
| GET | `/api/v1/inventory/sku-settings` | List Sku Settings |  |  | ✅ 200 |
| POST | `/api/v1/inventory/sku-settings` | Upsert Sku Settings |  | FilamentSkuSettingsUpsert |  |
| GET | `/api/v1/inventory/spools` | List Spools | include_archived |  | ✅ 200 |
| POST | `/api/v1/inventory/spools` | Create Spool |  | SpoolCreate |  |
| POST | `/api/v1/inventory/spools/bulk` | Bulk Create Spools |  | SpoolBulkCreate |  |
| POST | `/api/v1/inventory/spools/bulk-archive` | Bulk Archive Spools |  | BulkIdsRequest |  |
| POST | `/api/v1/inventory/spools/bulk-delete` | Bulk Delete Spools |  | BulkIdsRequest |  |
| POST | `/api/v1/inventory/spools/bulk-restore` | Bulk Restore Spools |  | BulkIdsRequest |  |
| POST | `/api/v1/inventory/spools/bulk-update` | Bulk Update Spools |  | BulkUpdateRequest |  |
| GET | `/api/v1/inventory/spools/by-tag` | Get Spool By Tag | tray_uuid, tag_uid, include_archived |  | ⚠️ 400 needs input |
| GET | `/api/v1/inventory/spools/export` | Export Spools Csv |  |  | not probed |
| POST | `/api/v1/inventory/spools/from-slot` | Create Spool From Slot |  | CreateSpoolFromSlotRequest |  |
| POST | `/api/v1/inventory/spools/import` | Import Spools Csv | dry_run | Body_import_spools_csv_api_v1_inventory_spools_import_post |  |
| POST | `/api/v1/inventory/spools/reset-consumed-counter-bulk` | Bulk Reset Spool Consumed Counter |  | object |  |
| DELETE | `/api/v1/inventory/spools/{spool_id}` | Delete Spool | `{spool_id}` |  |  |
| GET | `/api/v1/inventory/spools/{spool_id}` | Get Spool | `{spool_id}` |  |  |
| PATCH | `/api/v1/inventory/spools/{spool_id}` | Update Spool | `{spool_id}` | SpoolUpdate |  |
| POST | `/api/v1/inventory/spools/{spool_id}/archive` | Archive Spool | `{spool_id}` |  |  |
| GET | `/api/v1/inventory/spools/{spool_id}/filament-presets` | List Filament Presets | `{spool_id}` |  |  |
| PUT | `/api/v1/inventory/spools/{spool_id}/filament-presets` | Replace Filament Presets | `{spool_id}` | SpoolFilamentPresetBase[] |  |
| GET | `/api/v1/inventory/spools/{spool_id}/k-profiles` | List K Profiles | `{spool_id}` |  |  |
| PUT | `/api/v1/inventory/spools/{spool_id}/k-profiles` | Replace K Profiles | `{spool_id}` | SpoolKProfileBase[] |  |
| PATCH | `/api/v1/inventory/spools/{spool_id}/link-tag` | Link Tag To Spool | `{spool_id}` | LinkTagRequest |  |
| POST | `/api/v1/inventory/spools/{spool_id}/reset-consumed-counter` | Reset Spool Consumed Counter | `{spool_id}` |  |  |
| POST | `/api/v1/inventory/spools/{spool_id}/restore` | Restore Spool | `{spool_id}` |  |  |
| PUT | `/api/v1/inventory/spools/{spool_id}/suppliers` | Replace Spool Suppliers | `{spool_id}` | SpoolSupplierLinkInput[] |  |
| DELETE | `/api/v1/inventory/spools/{spool_id}/usage` | Clear Spool Usage History | `{spool_id}` |  |  |
| GET | `/api/v1/inventory/spools/{spool_id}/usage` | Get Spool Usage History | `{spool_id}`, limit |  |  |
| GET | `/api/v1/inventory/stats/material-numbers` | Get Material Number Stats | date_from, date_to |  | ✅ 200 |
| GET | `/api/v1/inventory/stats/suppliers` | Get Supplier Stats | date_from, date_to |  | ✅ 200 |
| GET | `/api/v1/inventory/suppliers` | List Suppliers |  |  | ✅ 200 |
| POST | `/api/v1/inventory/suppliers` | Create Supplier |  | SupplierCreate |  |
| DELETE | `/api/v1/inventory/suppliers/{supplier_id}` | Delete Supplier | `{supplier_id}` |  |  |
| PATCH | `/api/v1/inventory/suppliers/{supplier_id}` | Update Supplier | `{supplier_id}` | SupplierUpdate |  |
| POST | `/api/v1/inventory/sync-ams-weights` | Sync Weights From Ams |  |  |  |
| GET | `/api/v1/inventory/usage` | Get All Usage History | limit, printer_id |  | ✅ 200 |

## kprofiles

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| DELETE | `/api/v1/printers/{printer_id}/kprofiles/` | Delete Kprofile | `{printer_id}` | KProfileDelete |  |
| GET | `/api/v1/printers/{printer_id}/kprofiles/` | Get Kprofiles | `{printer_id}`, nozzle_diameter |  |  |
| POST | `/api/v1/printers/{printer_id}/kprofiles/` | Set Kprofile | `{printer_id}` | KProfileCreate |  |
| POST | `/api/v1/printers/{printer_id}/kprofiles/batch` | Set Kprofiles Batch | `{printer_id}` | KProfileCreate[] |  |
| GET | `/api/v1/printers/{printer_id}/kprofiles/notes` | Get Kprofile Notes | `{printer_id}` |  |  |
| PUT | `/api/v1/printers/{printer_id}/kprofiles/notes` | Set Kprofile Note | `{printer_id}` | KProfileNote |  |
| DELETE | `/api/v1/printers/{printer_id}/kprofiles/notes/{setting_id}` | Delete Kprofile Note | `{printer_id}`, `{setting_id}` |  |  |

## labels

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| POST | `/api/v1/inventory/labels` | Render Local Inventory Labels |  | LabelRequest |  |
| POST | `/api/v1/inventory/labels/preview` | Preview Local Inventory Label |  | LabelPreviewRequest |  |
| POST | `/api/v1/spoolman/labels` | Render Spoolman Labels |  | LabelRequest |  |
| POST | `/api/v1/spoolman/labels/preview` | Preview Spoolman Label |  | LabelPreviewRequest |  |

## library

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| POST | `/api/v1/library/bulk-delete` | Bulk Delete |  | BulkDeleteRequest |  |
| GET | `/api/v1/library/files` | List Files | folder_id, project_id, include_root, internal_only, external_only, recursive, tag_ids |  | ✅ 200 |
| POST | `/api/v1/library/files` | Upload File | folder_id, generate_stl_thumbnails | Body_upload_file_api_v1_library_files_post |  |
| GET | `/api/v1/library/files/` | List Files | folder_id, project_id, include_root, internal_only, external_only, recursive, tag_ids |  | ✅ 200 |
| POST | `/api/v1/library/files/` | Upload File | folder_id, generate_stl_thumbnails | Body_upload_file_api_v1_library_files__post |  |
| POST | `/api/v1/library/files/add-to-queue` | Add Files To Queue |  | AddToQueueRequest |  |
| POST | `/api/v1/library/files/combine` | Combine Files |  | CombineFilesRequest |  |
| POST | `/api/v1/library/files/extract-zip` | Extract Zip File | folder_id, preserve_structure, create_folder_from_zip, generate_stl_thumbnails | Body_extract_zip_file_api_v1_library_files_extract_zip_post |  |
| POST | `/api/v1/library/files/move` | Move Files |  | FileMoveRequest |  |
| DELETE | `/api/v1/library/files/{file_id}` | Delete File | `{file_id}` |  |  |
| GET | `/api/v1/library/files/{file_id}` | Get File | `{file_id}` |  |  |
| PUT | `/api/v1/library/files/{file_id}` | Update File | `{file_id}` | FileUpdate |  |
| GET | `/api/v1/library/files/{file_id}/dl/{token}/{filename}` | Download Library File For Slicer | `{file_id}`, `{token}`, `{filename}` |  |  |
| GET | `/api/v1/library/files/{file_id}/download` | Download File | `{file_id}` |  |  |
| GET | `/api/v1/library/files/{file_id}/filament-requirements` | Get Library File Filament Requirements | `{file_id}`, plate_id, request_id, full_slots |  |  |
| GET | `/api/v1/library/files/{file_id}/gcode` | Get Gcode | `{file_id}`, plate |  |  |
| POST | `/api/v1/library/files/{file_id}/photos` | Upload File Photo | `{file_id}` | Body_upload_file_photo_api_v1_library_files__file_id__photos_post |  |
| DELETE | `/api/v1/library/files/{file_id}/photos/{filename}` | Delete File Photo | `{file_id}`, `{filename}` |  |  |
| GET | `/api/v1/library/files/{file_id}/photos/{filename}` | Get File Photo | `{file_id}`, `{filename}`, token |  |  |
| GET | `/api/v1/library/files/{file_id}/plate-thumbnail/{plate_index}` | Get Library File Plate Thumbnail | `{file_id}`, `{plate_index}`, token |  |  |
| GET | `/api/v1/library/files/{file_id}/plates` | Get Library File Plates | `{file_id}` |  |  |
| POST | `/api/v1/library/files/{file_id}/preview-thumbnail` | Upload Preview Thumbnail | `{file_id}` | Body_upload_preview_thumbnail_api_v1_library_files__file_id__preview_thumbnail_post |  |
| POST | `/api/v1/library/files/{file_id}/print` | Print Library File | `{file_id}`, printer_id* |  |  |
| POST | `/api/v1/library/files/{file_id}/slice` | Slice Library File | `{file_id}` | SliceRequest |  |
| POST | `/api/v1/library/files/{file_id}/slicer-token` | Create Library Slicer Token | `{file_id}` |  |  |
| GET | `/api/v1/library/files/{file_id}/thumbnail` | Get Thumbnail | `{file_id}`, token |  |  |
| GET | `/api/v1/library/folders` | List Folders |  |  | ✅ 200 |
| POST | `/api/v1/library/folders` | Create Folder |  | FolderCreate |  |
| GET | `/api/v1/library/folders/` | List Folders |  |  | ✅ 200 |
| POST | `/api/v1/library/folders/` | Create Folder |  | FolderCreate |  |
| GET | `/api/v1/library/folders/by-archive/{archive_id}` | Get Folders By Archive | `{archive_id}` |  |  |
| GET | `/api/v1/library/folders/by-project/{project_id}` | Get Folders By Project | `{project_id}` |  |  |
| POST | `/api/v1/library/folders/external` | Create External Folder |  | ExternalFolderCreate |  |
| DELETE | `/api/v1/library/folders/{folder_id}` | Delete Folder | `{folder_id}` |  |  |
| GET | `/api/v1/library/folders/{folder_id}` | Get Folder | `{folder_id}` |  |  |
| PUT | `/api/v1/library/folders/{folder_id}` | Update Folder | `{folder_id}` | FolderUpdate |  |
| GET | `/api/v1/library/folders/{folder_id}/readme` | Get Folder Readme | `{folder_id}` |  |  |
| POST | `/api/v1/library/folders/{folder_id}/scan` | Scan External Folder | `{folder_id}` |  |  |
| POST | `/api/v1/library/generate-stl-thumbnails` | Batch Generate Stl Thumbnails |  | BatchThumbnailRequest |  |
| GET | `/api/v1/library/stats` | Get Library Stats |  |  | ✅ 200 |

## library-tags

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/library/tags` | List Tags |  |  | ✅ 200 |
| POST | `/api/v1/library/tags` | Create Tag |  | TagCreate |  |
| GET | `/api/v1/library/tags/` | List Tags |  |  | ✅ 200 |
| POST | `/api/v1/library/tags/` | Create Tag |  | TagCreate |  |
| POST | `/api/v1/library/tags/bulk-assign` | Bulk Assign |  | TagBulkAssignRequest |  |
| DELETE | `/api/v1/library/tags/{tag_id}` | Delete Tag | `{tag_id}` |  |  |
| PATCH | `/api/v1/library/tags/{tag_id}` | Update Tag | `{tag_id}` | TagUpdate |  |

## library-trash

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| POST | `/api/v1/library/purge` | Execute Purge |  | PurgeRequest |  |
| GET | `/api/v1/library/purge/preview` | Preview Purge | older_than_days*, include_never_printed |  | 🚫 403 no permission |
| DELETE | `/api/v1/library/trash` | Empty Trash |  |  |  |
| GET | `/api/v1/library/trash` | List Trash | limit, offset |  | ✅ 200 |
| GET | `/api/v1/library/trash/settings` | Get Trash Settings |  |  | 🚫 403 no permission |
| PUT | `/api/v1/library/trash/settings` | Update Trash Settings |  | TrashSettings |  |
| DELETE | `/api/v1/library/trash/{file_id}` | Hard Delete From Trash | `{file_id}` |  |  |
| POST | `/api/v1/library/trash/{file_id}/restore` | Restore From Trash | `{file_id}` |  |  |

## library-variants

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| POST | `/api/v1/library/variant-groups` | Create Variant Group |  | VariantGroupCreate |  |
| POST | `/api/v1/library/variant-groups/` | Create Variant Group |  | VariantGroupCreate |  |
| GET | `/api/v1/library/variant-groups/by-file/{file_id}` | Get Group For File | `{file_id}` |  |  |
| DELETE | `/api/v1/library/variant-groups/{group_id}` | Delete Variant Group | `{group_id}` |  |  |
| GET | `/api/v1/library/variant-groups/{group_id}` | Get Variant Group | `{group_id}` |  |  |
| PATCH | `/api/v1/library/variant-groups/{group_id}` | Update Variant Group | `{group_id}` | VariantGroupUpdate |  |
| POST | `/api/v1/library/variant-groups/{group_id}/members` | Add Variant Group Member | `{group_id}` | VariantGroupMemberRequest |  |
| DELETE | `/api/v1/library/variant-groups/{group_id}/members/{file_id}` | Remove Variant Group Member | `{group_id}`, `{file_id}` |  |  |

## Local Presets

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/local-presets/` | List Local Presets |  |  | ✅ 200 |
| POST | `/api/v1/local-presets/` | Create Local Preset |  | LocalPresetCreate |  |
| POST | `/api/v1/local-presets/base-cache/refresh` | Refresh Cache |  |  |  |
| GET | `/api/v1/local-presets/base-cache/status` | Base Cache Status |  |  | ✅ 200 |
| POST | `/api/v1/local-presets/import` | Import Presets |  | Body_import_presets_api_v1_local_presets_import_post |  |
| POST | `/api/v1/local-presets/reclassify` | Reclassify |  |  |  |
| DELETE | `/api/v1/local-presets/{preset_id}` | Delete Local Preset | `{preset_id}` |  |  |
| GET | `/api/v1/local-presets/{preset_id}` | Get Local Preset | `{preset_id}` |  |  |
| PUT | `/api/v1/local-presets/{preset_id}` | Update Local Preset | `{preset_id}` | LocalPresetUpdate |  |

## local-backup

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/local-backup/backups` | List Backups |  |  | 🚫 403 no permission |
| DELETE | `/api/v1/local-backup/backups/{filename}` | Delete Backup | `{filename}` |  |  |
| GET | `/api/v1/local-backup/backups/{filename}/download` | Download Backup | `{filename}` |  |  |
| POST | `/api/v1/local-backup/backups/{filename}/restore` | Restore Backup | `{filename}` |  |  |
| GET | `/api/v1/local-backup/path-check` | Check Path |  |  | 🚫 403 no permission |
| POST | `/api/v1/local-backup/run` | Trigger Backup |  |  |  |
| GET | `/api/v1/local-backup/status` | Get Status |  |  | 🚫 403 no permission |

## location-ha-sensors

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/location-ha-sensors/` | List Location Ha Sensors | location_id |  | ✅ 200 |
| POST | `/api/v1/location-ha-sensors/` | Create Location Ha Sensor |  | LocationHASensorCreate |  |
| GET | `/api/v1/location-ha-sensors/by-location/{location_id}/readings` | Get Location Sensor Readings | `{location_id}`, show_on_card |  |  |
| GET | `/api/v1/location-ha-sensors/entities` | List Bindable Entities | search |  | ⚠️ 400 needs input |
| DELETE | `/api/v1/location-ha-sensors/{sensor_id}` | Delete Location Ha Sensor | `{sensor_id}` |  |  |
| GET | `/api/v1/location-ha-sensors/{sensor_id}` | Get Location Ha Sensor | `{sensor_id}` |  |  |
| PATCH | `/api/v1/location-ha-sensors/{sensor_id}` | Update Location Ha Sensor | `{sensor_id}` | LocationHASensorUpdate |  |

## maintenance

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| DELETE | `/api/v1/maintenance/items/{item_id}` | Remove Maintenance Item | `{item_id}` |  |  |
| PATCH | `/api/v1/maintenance/items/{item_id}` | Update Printer Maintenance | `{item_id}` | PrinterMaintenanceUpdate |  |
| GET | `/api/v1/maintenance/items/{item_id}/history` | Get Maintenance History | `{item_id}` |  |  |
| POST | `/api/v1/maintenance/items/{item_id}/perform` | Perform Maintenance | `{item_id}` | PerformMaintenanceRequest |  |
| GET | `/api/v1/maintenance/overview` | Get All Maintenance Overview |  |  | ✅ 200 |
| GET | `/api/v1/maintenance/printers/{printer_id}` | Get Printer Maintenance | `{printer_id}` |  |  |
| POST | `/api/v1/maintenance/printers/{printer_id}/assign/{type_id}` | Assign Maintenance Type | `{printer_id}`, `{type_id}` |  |  |
| PATCH | `/api/v1/maintenance/printers/{printer_id}/hours` | Set Printer Hours | `{printer_id}`, total_hours* |  |  |
| GET | `/api/v1/maintenance/summary` | Get Maintenance Summary |  |  | ✅ 200 |
| GET | `/api/v1/maintenance/types` | Get Maintenance Types |  |  | ✅ 200 |
| POST | `/api/v1/maintenance/types` | Create Maintenance Type |  | MaintenanceTypeCreate |  |
| POST | `/api/v1/maintenance/types/restore-defaults` | Restore Default Maintenance Types |  |  |  |
| DELETE | `/api/v1/maintenance/types/{type_id}` | Delete Maintenance Type | `{type_id}` |  |  |
| PATCH | `/api/v1/maintenance/types/{type_id}` | Update Maintenance Type | `{type_id}` | MaintenanceTypeUpdate |  |

## makerworld

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| POST | `/api/v1/makerworld/import` | Import Instance |  | MakerWorldImportRequest |  |
| GET | `/api/v1/makerworld/recent-imports` | Recent Imports | limit |  | ✅ 200 |
| POST | `/api/v1/makerworld/resolve` | Resolve Url |  | MakerWorldResolveRequest |  |
| GET | `/api/v1/makerworld/status` | Get Status |  |  | ✅ 200 |
| GET | `/api/v1/makerworld/thumbnail` | Proxy Thumbnail | url* |  | ⚠️ 422 needs query params |

## metrics

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/metrics` | Get Metrics |  |  | 404 |

## notification-templates

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/notification-templates` | Get Templates |  |  | ✅ 200 |
| GET | `/api/v1/notification-templates/` | Get Templates |  |  | ✅ 200 |
| POST | `/api/v1/notification-templates/preview` | Preview Template |  | TemplatePreviewRequest |  |
| GET | `/api/v1/notification-templates/variables` | Get Variables |  |  | ✅ 200 |
| GET | `/api/v1/notification-templates/{template_id}` | Get Template | `{template_id}` |  |  |
| PUT | `/api/v1/notification-templates/{template_id}` | Update Template | `{template_id}` | NotificationTemplateUpdate |  |
| POST | `/api/v1/notification-templates/{template_id}/reset` | Reset Template | `{template_id}` |  |  |

## notifications

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/notifications/` | List Notification Providers |  |  | ✅ 200 |
| POST | `/api/v1/notifications/` | Create Notification Provider |  | NotificationProviderCreate |  |
| POST | `/api/v1/notifications/app-message` | Send App Message |  | AppMessage |  |
| GET | `/api/v1/notifications/app-message/channels` | App Message Channels |  |  | ✅ 200 |
| DELETE | `/api/v1/notifications/logs` | Clear Notification Logs | older_than_days |  |  |
| GET | `/api/v1/notifications/logs` | Get Notification Logs | limit, offset, provider_id, event_type, success, days |  | ✅ 200 |
| GET | `/api/v1/notifications/logs/stats` | Get Notification Log Stats | days |  | ✅ 200 |
| GET | `/api/v1/notifications/photos/{filename}` | Get Notification Photo | `{filename}` |  |  |
| POST | `/api/v1/notifications/test-all` | Test All Notification Providers |  |  |  |
| POST | `/api/v1/notifications/test-config` | Test Notification Config |  | NotificationTestRequest |  |
| DELETE | `/api/v1/notifications/{provider_id}` | Delete Notification Provider | `{provider_id}` |  |  |
| GET | `/api/v1/notifications/{provider_id}` | Get Notification Provider | `{provider_id}` |  |  |
| PATCH | `/api/v1/notifications/{provider_id}` | Update Notification Provider | `{provider_id}` | NotificationProviderUpdate |  |
| POST | `/api/v1/notifications/{provider_id}/test` | Test Notification Provider | `{provider_id}` |  |  |

## obico

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/obico/cached-frame/{nonce}` | Cached Frame | `{nonce}` |  |  |
| GET | `/api/v1/obico/printer-status` | Get Printer Status |  |  | ✅ 200 |
| GET | `/api/v1/obico/status` | Get Status |  |  | ✅ 200 |
| POST | `/api/v1/obico/test-connection` | Test Connection |  | TestConnectionRequest |  |

## orca-cloud

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| POST | `/api/v1/orca-cloud/device/poll` | Device Poll |  |  |  |
| POST | `/api/v1/orca-cloud/device/start` | Device Start |  |  |  |
| POST | `/api/v1/orca-cloud/logout` | Logout |  |  |  |
| GET | `/api/v1/orca-cloud/profiles` | List Profiles |  |  | 🔒 401 user sign-in only |
| GET | `/api/v1/orca-cloud/profiles/{profile_id}` | Get Profile | `{profile_id}` |  |  |
| GET | `/api/v1/orca-cloud/status` | Get Status |  |  | ✅ 200 |

## Other

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/` | Serve Frontend |  |  | ✅ 200 |
| GET | `/health` | Health Check |  |  | ✅ 200 |
| GET | `/manifest.json` | Serve Manifest |  |  | ✅ 200 |
| GET | `/sw-register.js` | Serve Sw Register |  |  | ✅ 200 |
| GET | `/sw.js` | Serve Service Worker |  |  | ✅ 200 |
| GET | `/{full_path}` | Serve Spa | `{full_path}` |  |  |

## pending-uploads

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/pending-uploads/` | List Pending Uploads |  |  | ✅ 200 |
| POST | `/api/v1/pending-uploads/archive-all` | Archive All Pending |  |  |  |
| GET | `/api/v1/pending-uploads/count` | Get Pending Count |  |  | ✅ 200 |
| DELETE | `/api/v1/pending-uploads/discard-all` | Discard All Pending |  |  |  |
| DELETE | `/api/v1/pending-uploads/{upload_id}` | Discard Pending Upload | `{upload_id}` |  |  |
| GET | `/api/v1/pending-uploads/{upload_id}` | Get Pending Upload | `{upload_id}` |  |  |
| POST | `/api/v1/pending-uploads/{upload_id}/archive` | Archive Pending Upload | `{upload_id}` | ArchiveRequest |  |

## print-log

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| DELETE | `/api/v1/print-log/` | Clear Print Log |  |  |  |
| GET | `/api/v1/print-log/` | Get Print Log | search, printer_id, created_by_username, status, date_from, date_to, limit, offset, sort_by, sort_dir |  | ✅ 200 |
| DELETE | `/api/v1/print-log/{entry_id}` | Delete Print Log Entry | `{entry_id}` |  |  |
| PATCH | `/api/v1/print-log/{entry_id}` | Update Print Log Entry | `{entry_id}` | PrintLogEntryUpdate |  |
| GET | `/api/v1/print-log/{entry_id}/thumbnail` | Get Print Log Thumbnail | `{entry_id}`, token |  |  |

## printer-sensor-history

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| DELETE | `/api/v1/printer-sensor-history/{printer_id}` | Delete Old History | `{printer_id}`, days |  |  |
| GET | `/api/v1/printer-sensor-history/{printer_id}` | Get Printer Sensor History | `{printer_id}`, hours, kinds |  |  |

## printers

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/printers/` | List Printers |  |  | ✅ 200 |
| POST | `/api/v1/printers/` | Create Printer |  | PrinterCreate |  |
| GET | `/api/v1/printers/available-filaments` | Get Available Filaments | model*, location |  | ⚠️ 422 needs query params |
| GET | `/api/v1/printers/developer-mode-warnings` | Get Developer Mode Warnings |  |  | ✅ 200 |
| POST | `/api/v1/printers/diagnostic` | Diagnose Connection |  | DiagnosticRequest |  |
| POST | `/api/v1/printers/test` | Test Printer Connection | ip_address*, serial_number*, access_code* |  |  |
| GET | `/api/v1/printers/usb-cameras` | List Usb Cameras |  |  | ✅ 200 |
| DELETE | `/api/v1/printers/{printer_id}` | Delete Printer | `{printer_id}`, delete_archives |  |  |
| GET | `/api/v1/printers/{printer_id}` | Get Printer | `{printer_id}` |  |  |
| PATCH | `/api/v1/printers/{printer_id}` | Update Printer | `{printer_id}` | PrinterUpdate |  |
| POST | `/api/v1/printers/{printer_id}/airduct-mode` | Set Airduct Mode | `{printer_id}`, mode* |  |  |
| POST | `/api/v1/printers/{printer_id}/ams-backup` | Set Ams Backup | `{printer_id}`, enabled* |  |  |
| GET | `/api/v1/printers/{printer_id}/ams-labels` | Get Ams Labels | `{printer_id}` |  |  |
| DELETE | `/api/v1/printers/{printer_id}/ams-labels/{ams_id}` | Delete Ams Label | `{printer_id}`, `{ams_id}`, ams_serial |  |  |
| PUT | `/api/v1/printers/{printer_id}/ams-labels/{ams_id}` | Save Ams Label | `{printer_id}`, `{ams_id}` | AmsLabelBody |  |
| POST | `/api/v1/printers/{printer_id}/ams/load` | Ams Load | `{printer_id}`, tray_id*, extruder_id |  |  |
| POST | `/api/v1/printers/{printer_id}/ams/unload` | Ams Unload | `{printer_id}`, tray_id |  |  |
| POST | `/api/v1/printers/{printer_id}/ams/{ams_id}/slot/{slot_id}/refresh` | Refresh Ams Slot | `{printer_id}`, `{ams_id}`, `{slot_id}` |  |  |
| POST | `/api/v1/printers/{printer_id}/ams/{ams_id}/tray/{tray_id}/reset` | Reset Ams Slot | `{printer_id}`, `{ams_id}`, `{tray_id}` |  |  |
| POST | `/api/v1/printers/{printer_id}/bed-jog` | Bed Jog | `{printer_id}`, distance* |  |  |
| POST | `/api/v1/printers/{printer_id}/calibration` | Start Calibration | `{printer_id}`, bed_leveling, vibration, motor_noise, nozzle_offset, high_temp_heatbed |  |  |
| POST | `/api/v1/printers/{printer_id}/chamber-light` | Set Chamber Light | `{printer_id}`, on* |  |  |
| POST | `/api/v1/printers/{printer_id}/clear-plate` | Clear Plate | `{printer_id}` |  |  |
| POST | `/api/v1/printers/{printer_id}/connect` | Connect Printer | `{printer_id}` |  |  |
| GET | `/api/v1/printers/{printer_id}/cover` | Get Printer Cover | `{printer_id}`, view, token |  |  |
| GET | `/api/v1/printers/{printer_id}/current-print-user` | Get Current Print User | `{printer_id}` |  |  |
| POST | `/api/v1/printers/{printer_id}/debug/simulate-print-complete` | Debug Simulate Print Complete | `{printer_id}` |  |  |
| GET | `/api/v1/printers/{printer_id}/diagnostic` | Diagnose Printer | `{printer_id}` |  |  |
| POST | `/api/v1/printers/{printer_id}/disconnect` | Disconnect Printer | `{printer_id}` |  |  |
| POST | `/api/v1/printers/{printer_id}/drying/start` | Start Drying | `{printer_id}`, ams_id*, temp, duration, filament, rotate_tray |  |  |
| POST | `/api/v1/printers/{printer_id}/drying/stop` | Stop Drying | `{printer_id}`, ams_id* |  |  |
| POST | `/api/v1/printers/{printer_id}/extruder-jog` | Extruder Jog | `{printer_id}`, distance* |  |  |
| POST | `/api/v1/printers/{printer_id}/fan-speed` | Set Fan Speed | `{printer_id}`, fan*, speed* |  |  |
| DELETE | `/api/v1/printers/{printer_id}/files` | Delete Printer File | `{printer_id}`, path* |  |  |
| GET | `/api/v1/printers/{printer_id}/files` | List Printer Files | `{printer_id}`, path |  |  |
| GET | `/api/v1/printers/{printer_id}/files/dl/{token}/{filename}` | Download Prepared Printer Files | `{printer_id}`, `{token}`, `{filename}` |  |  |
| GET | `/api/v1/printers/{printer_id}/files/download` | Download Printer File | `{printer_id}`, path* |  |  |
| POST | `/api/v1/printers/{printer_id}/files/download-job` | Create Printer Files Download Job | `{printer_id}` | PrinterFilesJobRequest |  |
| DELETE | `/api/v1/printers/{printer_id}/files/download-jobs/{job_id}` | Cancel Printer Files Download Job | `{printer_id}`, `{job_id}` |  |  |
| GET | `/api/v1/printers/{printer_id}/files/download-jobs/{job_id}` | Get Printer Files Download Job | `{printer_id}`, `{job_id}` |  |  |
| POST | `/api/v1/printers/{printer_id}/files/download-zip` | Download Printer Files As Zip | `{printer_id}` | PrinterFilesDownloadRequest |  |
| GET | `/api/v1/printers/{printer_id}/files/gcode` | Get Printer File Gcode | `{printer_id}`, path* |  |  |
| GET | `/api/v1/printers/{printer_id}/files/plate-thumbnail/{plate_index}` | Get Printer File Plate Thumbnail | `{printer_id}`, `{plate_index}`, path*, token |  |  |
| GET | `/api/v1/printers/{printer_id}/files/plates` | Get Printer File Plates | `{printer_id}`, path* |  |  |
| POST | `/api/v1/printers/{printer_id}/hms/clear` | Clear Hms Errors | `{printer_id}` |  |  |
| POST | `/api/v1/printers/{printer_id}/hms/execute-action` | Execute Hms Action | `{printer_id}` | HmsActionBody |  |
| POST | `/api/v1/printers/{printer_id}/home-axes` | Home Axes | `{printer_id}`, axes |  |  |
| GET | `/api/v1/printers/{printer_id}/inventory-remain` | Get Inventory Remain | `{printer_id}` |  |  |
| DELETE | `/api/v1/printers/{printer_id}/logging` | Clear Mqtt Logs | `{printer_id}` |  |  |
| GET | `/api/v1/printers/{printer_id}/logging` | Get Mqtt Logs | `{printer_id}` |  |  |
| POST | `/api/v1/printers/{printer_id}/logging/disable` | Disable Mqtt Logging | `{printer_id}` |  |  |
| POST | `/api/v1/printers/{printer_id}/logging/enable` | Enable Mqtt Logging | `{printer_id}` |  |  |
| GET | `/api/v1/printers/{printer_id}/overlay-status` | Get Overlay Status | `{printer_id}`, token |  |  |
| POST | `/api/v1/printers/{printer_id}/print-options` | Set Print Option | `{printer_id}`, module_name*, enabled*, print_halt, sensitivity |  |  |
| POST | `/api/v1/printers/{printer_id}/print-speed` | Set Print Speed | `{printer_id}`, mode* |  |  |
| GET | `/api/v1/printers/{printer_id}/print/objects` | Get Printable Objects | `{printer_id}`, reload |  |  |
| POST | `/api/v1/printers/{printer_id}/print/pause` | Pause Print | `{printer_id}` |  |  |
| POST | `/api/v1/printers/{printer_id}/print/resume` | Resume Print | `{printer_id}` |  |  |
| POST | `/api/v1/printers/{printer_id}/print/skip-objects` | Skip Objects | `{printer_id}` | integer[] |  |
| POST | `/api/v1/printers/{printer_id}/print/stop` | Stop Print | `{printer_id}` |  |  |
| POST | `/api/v1/printers/{printer_id}/refresh-status` | Refresh Printer Status | `{printer_id}` |  |  |
| GET | `/api/v1/printers/{printer_id}/runtime-debug` | Get Runtime Debug | `{printer_id}` |  |  |
| POST | `/api/v1/printers/{printer_id}/select-extruder` | Select Extruder | `{printer_id}`, extruder* |  |  |
| GET | `/api/v1/printers/{printer_id}/slot-presets` | Get Slot Presets | `{printer_id}` |  |  |
| DELETE | `/api/v1/printers/{printer_id}/slot-presets/{ams_id}/{tray_id}` | Delete Slot Preset | `{printer_id}`, `{ams_id}`, `{tray_id}` |  |  |
| GET | `/api/v1/printers/{printer_id}/slot-presets/{ams_id}/{tray_id}` | Get Slot Preset | `{printer_id}`, `{ams_id}`, `{tray_id}` |  |  |
| PUT | `/api/v1/printers/{printer_id}/slot-presets/{ams_id}/{tray_id}` | Save Slot Preset | `{printer_id}`, `{ams_id}`, `{tray_id}`, preset_id*, preset_name*, preset_source, tray_info_idx |  |  |
| POST | `/api/v1/printers/{printer_id}/slots/{ams_id}/{tray_id}/configure` | Configure Ams Slot | `{printer_id}`, `{ams_id}`, `{tray_id}`, tray_info_idx*, tray_type*, tray_sub_brands*, tray_color*, nozzle_temp_min*, nozzle_temp_max*, cali_idx, nozzle_diameter, setting_id, kprofile_filament_id, kprofile_setting_id, k_value, orca_profile_id |  |  |
| GET | `/api/v1/printers/{printer_id}/slots/{ams_id}/{tray_id}/spool-defaults` | Get Slot Spool Defaults | `{printer_id}`, `{ams_id}`, `{tray_id}` |  |  |
| GET | `/api/v1/printers/{printer_id}/status` | Get Printer Status | `{printer_id}` |  |  |
| GET | `/api/v1/printers/{printer_id}/storage` | Get Printer Storage | `{printer_id}` |  |  |
| POST | `/api/v1/printers/{printer_id}/temperature/bed` | Set Bed Temperature | `{printer_id}`, target* |  |  |
| POST | `/api/v1/printers/{printer_id}/temperature/chamber` | Set Chamber Temperature | `{printer_id}`, target* |  |  |
| POST | `/api/v1/printers/{printer_id}/temperature/nozzle` | Set Nozzle Temperature | `{printer_id}`, target*, nozzle |  |  |
| POST | `/api/v1/printers/{printer_id}/xy-jog` | Xy Jog | `{printer_id}`, x, y |  |  |

## projects

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/projects` | List Projects | status |  | ✅ 200 |
| GET | `/api/v1/projects/` | List Projects | status |  | ✅ 200 |
| POST | `/api/v1/projects/` | Create Project |  | ProjectCreate |  |
| POST | `/api/v1/projects/from-template/{template_id}` | Create Project From Template | `{template_id}`, name |  |  |
| POST | `/api/v1/projects/import` | Import Project |  | ProjectImport |  |
| POST | `/api/v1/projects/import/file` | Import Project File |  | Body_import_project_file_api_v1_projects_import_file_post |  |
| GET | `/api/v1/projects/templates` | List Templates |  |  | ✅ 200 |
| DELETE | `/api/v1/projects/{project_id}` | Delete Project | `{project_id}` |  |  |
| GET | `/api/v1/projects/{project_id}` | Get Project | `{project_id}` |  |  |
| PATCH | `/api/v1/projects/{project_id}` | Update Project | `{project_id}` | ProjectUpdate |  |
| POST | `/api/v1/projects/{project_id}/add-archives` | Add Archives To Project | `{project_id}` | BatchAddArchives |  |
| POST | `/api/v1/projects/{project_id}/add-queue` | Add Queue Items To Project | `{project_id}` | BatchAddQueueItems |  |
| GET | `/api/v1/projects/{project_id}/archives` | List Project Archives | `{project_id}`, limit, offset |  |  |
| POST | `/api/v1/projects/{project_id}/attachments` | Upload Attachment | `{project_id}` | Body_upload_attachment_api_v1_projects__project_id__attachments_post |  |
| DELETE | `/api/v1/projects/{project_id}/attachments/{filename}` | Delete Attachment | `{project_id}`, `{filename}` |  |  |
| GET | `/api/v1/projects/{project_id}/attachments/{filename}` | Download Attachment | `{project_id}`, `{filename}` |  |  |
| GET | `/api/v1/projects/{project_id}/bom` | List Bom Items | `{project_id}` |  |  |
| POST | `/api/v1/projects/{project_id}/bom` | Create Bom Item | `{project_id}` | BOMItemCreate |  |
| DELETE | `/api/v1/projects/{project_id}/bom/{item_id}` | Delete Bom Item | `{project_id}`, `{item_id}` |  |  |
| PATCH | `/api/v1/projects/{project_id}/bom/{item_id}` | Update Bom Item | `{project_id}`, `{item_id}` | BOMItemUpdate |  |
| DELETE | `/api/v1/projects/{project_id}/cover-image` | Delete Project Cover Image | `{project_id}` |  |  |
| GET | `/api/v1/projects/{project_id}/cover-image` | Get Project Cover Image | `{project_id}`, token |  |  |
| POST | `/api/v1/projects/{project_id}/cover-image` | Upload Project Cover Image | `{project_id}` | Body_upload_project_cover_image_api_v1_projects__project_id__cover_image_post |  |
| POST | `/api/v1/projects/{project_id}/create-template` | Create Template From Project | `{project_id}` |  |  |
| GET | `/api/v1/projects/{project_id}/export` | Export Project | `{project_id}`, format |  |  |
| GET | `/api/v1/projects/{project_id}/file-progress` | Get Project File Progress | `{project_id}` |  |  |
| GET | `/api/v1/projects/{project_id}/queue` | List Project Queue | `{project_id}` |  |  |
| POST | `/api/v1/projects/{project_id}/remove-archives` | Remove Archives From Project | `{project_id}` | BatchAddArchives |  |
| GET | `/api/v1/projects/{project_id}/timeline` | Get Project Timeline | `{project_id}`, limit |  |  |

## queue

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/queue/` | List Queue | printer_id, status, target_model |  | ✅ 200 |
| POST | `/api/v1/queue/` | Add To Queue |  | PrintQueueItemCreate |  |
| GET | `/api/v1/queue/batches` | List Batches | status, external_source, external_ref |  | ✅ 200 |
| POST | `/api/v1/queue/batches` | Create Batch |  | PrintBatchCreate |  |
| DELETE | `/api/v1/queue/batches/{batch_id}` | Cancel Batch | `{batch_id}` |  |  |
| GET | `/api/v1/queue/batches/{batch_id}` | Get Batch | `{batch_id}` |  |  |
| PATCH | `/api/v1/queue/batches/{batch_id}` | Update Batch | `{batch_id}` | PrintBatchUpdate |  |
| POST | `/api/v1/queue/batches/{batch_id}/dispatch` | Dispatch Batch | `{batch_id}` | PrintBatchDispatchRequest |  |
| POST | `/api/v1/queue/batches/{batch_id}/ungroup` | Ungroup Batch | `{batch_id}` |  |  |
| PATCH | `/api/v1/queue/bulk` | Bulk Update Queue Items |  | PrintQueueBulkUpdate |  |
| POST | `/api/v1/queue/printer/{printer_id}/resume` | Resume Queue After Failure | `{printer_id}` |  |  |
| POST | `/api/v1/queue/reorder` | Reorder Queue |  | PrintQueueReorder |  |
| DELETE | `/api/v1/queue/{item_id}` | Delete Queue Item | `{item_id}` |  |  |
| GET | `/api/v1/queue/{item_id}` | Get Queue Item | `{item_id}` |  |  |
| PATCH | `/api/v1/queue/{item_id}` | Update Queue Item | `{item_id}` | PrintQueueItemUpdate |  |
| POST | `/api/v1/queue/{item_id}/cancel` | Cancel Queue Item | `{item_id}` |  |  |
| POST | `/api/v1/queue/{item_id}/start` | Start Queue Item | `{item_id}`, skip_filament_check |  |  |
| POST | `/api/v1/queue/{item_id}/stop` | Stop Queue Item | `{item_id}` |  |  |

## scheduled-dryings

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/scheduled-dryings` | List Scheduled Dryings | printer_id |  | ✅ 200 |
| POST | `/api/v1/scheduled-dryings` | Create Scheduled Drying |  | ScheduledDryingCreate |  |
| DELETE | `/api/v1/scheduled-dryings/{scheduled_drying_id}` | Cancel Scheduled Drying | `{scheduled_drying_id}` |  |  |

## settings

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/settings` | Get Settings |  |  | ✅ 200 |
| PATCH | `/api/v1/settings` | Patch Settings |  | AppSettingsUpdate |  |
| GET | `/api/v1/settings/` | Get Settings |  |  | ✅ 200 |
| PATCH | `/api/v1/settings/` | Patch Settings |  | AppSettingsUpdate |  |
| PUT | `/api/v1/settings/` | Update Settings |  | AppSettingsUpdate |  |
| GET | `/api/v1/settings/backup` | Create Backup |  |  | not probed |
| GET | `/api/v1/settings/check-ffmpeg` | Check Ffmpeg |  |  | ✅ 200 |
| GET | `/api/v1/settings/default-sidebar-order` | Get Default Sidebar Order |  |  | ✅ 200 |
| POST | `/api/v1/settings/electricity-price` | Update Electricity Price |  | ElectricityPriceUpdate |  |
| GET | `/api/v1/settings/mqtt/status` | Get Mqtt Status |  |  | ✅ 200 |
| GET | `/api/v1/settings/network-interfaces` | Get Network Interfaces |  |  | ✅ 200 |
| POST | `/api/v1/settings/reset` | Reset Settings |  |  |  |
| POST | `/api/v1/settings/restore` | Restore Backup |  | Body_restore_backup_api_v1_settings_restore_post |  |
| GET | `/api/v1/settings/spoolman` | Get Spoolman Settings |  |  | ✅ 200 |
| PUT | `/api/v1/settings/spoolman` | Update Spoolman Settings |  | object |  |
| GET | `/api/v1/settings/ui-flags` | Get Ui Flags |  |  | ✅ 200 |
| GET | `/api/v1/settings/ui-preferences` | Get Ui Preferences |  |  | ✅ 200 |
| GET | `/api/v1/settings/virtual-printer` | Get Virtual Printer Settings |  |  | ✅ 200 |
| PUT | `/api/v1/settings/virtual-printer` | Update Virtual Printer Settings | enabled, access_code, mode, model, target_printer_id, remote_interface_ip, tailscale_disabled, archive_name_source |  |  |
| GET | `/api/v1/settings/virtual-printer/models` | Get Virtual Printer Models |  |  | ✅ 200 |

## slice-jobs

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/slice-jobs/{job_id}` | Get Slice Job | `{job_id}` |  |  |

## Slicer Pipelines

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/pipeline-runs` | List All Runs | limit, offset, pipeline_id, status, target_printer_id, target_model_class |  | ✅ 200 |
| POST | `/api/v1/pipeline-runs/clear` | Clear Terminal Runs |  |  |  |
| GET | `/api/v1/pipeline-runs/{run_id}` | Get Run | `{run_id}` |  |  |
| POST | `/api/v1/pipeline-runs/{run_id}/cancel` | Cancel Run | `{run_id}` |  |  |
| POST | `/api/v1/pipeline-runs/{run_id}/retry-failed` | Retry Failed | `{run_id}` |  |  |
| GET | `/api/v1/slicer-pipelines/` | List Pipelines |  |  | ✅ 200 |
| POST | `/api/v1/slicer-pipelines/` | Create Pipeline |  | SlicerPipelineCreate |  |
| DELETE | `/api/v1/slicer-pipelines/{pipeline_id}` | Delete Pipeline | `{pipeline_id}` |  |  |
| GET | `/api/v1/slicer-pipelines/{pipeline_id}` | Get Pipeline | `{pipeline_id}` |  |  |
| PUT | `/api/v1/slicer-pipelines/{pipeline_id}` | Update Pipeline | `{pipeline_id}` | SlicerPipelineUpdate |  |
| POST | `/api/v1/slicer-pipelines/{pipeline_id}/check-eligibility` | Check Eligibility | `{pipeline_id}` | CheckEligibilityRequest |  |
| POST | `/api/v1/slicer-pipelines/{pipeline_id}/run` | Run Pipeline | `{pipeline_id}` | PipelineRunCreateRequest |  |
| GET | `/api/v1/slicer-pipelines/{pipeline_id}/runs` | List Runs For Pipeline | `{pipeline_id}`, limit |  |  |

## Slicer Presets

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/slicer/preset-values` | Get Preset Values | source*, id*, slot |  | ⚠️ 422 needs query params |
| GET | `/api/v1/slicer/presets` | List Unified Presets | refresh |  | ✅ 200 |
| GET | `/api/v1/slicer/preview-progress/{request_id}` | Get Preview Slice Progress | `{request_id}` |  |  |
| GET | `/api/v1/slicer/printer-models` | List Printer Models |  |  | ✅ 200 |

## smart-plugs

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/smart-plugs/` | List Smart Plugs |  |  | ✅ 200 |
| POST | `/api/v1/smart-plugs/` | Create Smart Plug |  | SmartPlugCreate |  |
| GET | `/api/v1/smart-plugs/by-printer/{printer_id}` | Get Smart Plug By Printer | `{printer_id}` |  |  |
| GET | `/api/v1/smart-plugs/by-printer/{printer_id}/scripts` | Get Script Plugs By Printer | `{printer_id}` |  |  |
| GET | `/api/v1/smart-plugs/discover/devices` | Get Discovered Tasmota Devices |  |  | ✅ 200 |
| POST | `/api/v1/smart-plugs/discover/scan` | Start Tasmota Scan |  | TasmotaScanRequest or null |  |
| GET | `/api/v1/smart-plugs/discover/status` | Get Tasmota Scan Status |  |  | ✅ 200 |
| POST | `/api/v1/smart-plugs/discover/stop` | Stop Tasmota Scan |  |  |  |
| GET | `/api/v1/smart-plugs/ha/entities` | List Ha Entities | search |  | ⚠️ 400 needs input |
| GET | `/api/v1/smart-plugs/ha/sensors` | List Ha Sensor Entities |  |  | ⚠️ 400 needs input |
| POST | `/api/v1/smart-plugs/ha/test-connection` | Test Ha Connection |  | HATestConnectionRequest |  |
| POST | `/api/v1/smart-plugs/rest/test-connection` | Test Rest Connection |  | RESTTestConnectionRequest |  |
| POST | `/api/v1/smart-plugs/test-connection` | Test Connection |  | SmartPlugTestConnection |  |
| DELETE | `/api/v1/smart-plugs/{plug_id}` | Delete Smart Plug | `{plug_id}` |  |  |
| GET | `/api/v1/smart-plugs/{plug_id}` | Get Smart Plug | `{plug_id}` |  |  |
| PATCH | `/api/v1/smart-plugs/{plug_id}` | Update Smart Plug | `{plug_id}` | SmartPlugUpdate |  |
| POST | `/api/v1/smart-plugs/{plug_id}/control` | Control Smart Plug | `{plug_id}` | SmartPlugControl |  |
| GET | `/api/v1/smart-plugs/{plug_id}/status` | Get Plug Status | `{plug_id}` |  |  |

## sponsor-prompt

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/sponsor-prompt/check` | Check Sponsor Prompt |  |  | ✅ 200 |
| POST | `/api/v1/sponsor-prompt/dismiss` | Dismiss Sponsor Prompt |  | SponsorPromptDismissRequest |  |

## spoolbuddy

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/spoolbuddy/devices` | List Devices |  |  | ✅ 200 |
| POST | `/api/v1/spoolbuddy/devices/register` | Register Device |  | DeviceRegisterRequest |  |
| DELETE | `/api/v1/spoolbuddy/devices/{device_id}` | Unregister Device | `{device_id}` |  |  |
| GET | `/api/v1/spoolbuddy/devices/{device_id}/calibration` | Get Calibration | `{device_id}` |  |  |
| POST | `/api/v1/spoolbuddy/devices/{device_id}/calibration/set-factor` | Set Calibration Factor | `{device_id}` | SetCalibrationFactorRequest |  |
| POST | `/api/v1/spoolbuddy/devices/{device_id}/calibration/set-tare` | Set Tare Offset | `{device_id}` | SetTareRequest |  |
| POST | `/api/v1/spoolbuddy/devices/{device_id}/calibration/tare` | Tare Scale | `{device_id}` |  |  |
| POST | `/api/v1/spoolbuddy/devices/{device_id}/cancel-write` | Cancel Write | `{device_id}` |  |  |
| GET | `/api/v1/spoolbuddy/devices/{device_id}/display` | Get Display Settings | `{device_id}` |  |  |
| PUT | `/api/v1/spoolbuddy/devices/{device_id}/display` | Update Display Settings | `{device_id}` | DisplaySettingsRequest |  |
| POST | `/api/v1/spoolbuddy/devices/{device_id}/heartbeat` | Device Heartbeat | `{device_id}` | HeartbeatRequest |  |
| POST | `/api/v1/spoolbuddy/devices/{device_id}/system/command` | Queue System Command | `{device_id}` | SystemCommandRequest |  |
| POST | `/api/v1/spoolbuddy/devices/{device_id}/system/command-result` | System Command Result | `{device_id}` | SystemCommandResultRequest |  |
| POST | `/api/v1/spoolbuddy/devices/{device_id}/system/config` | Queue System Config Update | `{device_id}` | SystemConfigRequest |  |
| POST | `/api/v1/spoolbuddy/devices/{device_id}/update` | Trigger Daemon Update | `{device_id}` | object or null |  |
| GET | `/api/v1/spoolbuddy/devices/{device_id}/update-check` | Check Daemon Update | `{device_id}` |  |  |
| POST | `/api/v1/spoolbuddy/devices/{device_id}/update-status` | Report Update Status | `{device_id}` | UpdateStatusRequest |  |
| GET | `/api/v1/spoolbuddy/diagnostics/{device_id}/result` | Get Diagnostic Result | `{device_id}`, diagnostic* |  |  |
| POST | `/api/v1/spoolbuddy/diagnostics/{device_id}/result` | Report Diagnostic Result | `{device_id}` | DiagnosticResultRequest |  |
| POST | `/api/v1/spoolbuddy/diagnostics/{device_id}/run` | Queue Diagnostic | `{device_id}`, diagnostic* |  |  |
| POST | `/api/v1/spoolbuddy/nfc/tag-removed` | Nfc Tag Removed |  | TagRemovedRequest |  |
| POST | `/api/v1/spoolbuddy/nfc/tag-scanned` | Nfc Tag Scanned |  | TagScannedRequest |  |
| POST | `/api/v1/spoolbuddy/nfc/write-result` | Nfc Write Result |  | WriteTagResultRequest |  |
| POST | `/api/v1/spoolbuddy/nfc/write-tag` | Nfc Write Tag |  | WriteTagRequest |  |
| POST | `/api/v1/spoolbuddy/scale/reading` | Scale Reading |  | ScaleReadingRequest |  |
| POST | `/api/v1/spoolbuddy/scale/update-spool-weight` | Update Spool Weight |  | UpdateSpoolWeightRequest |  |
| GET | `/api/v1/spoolbuddy/ssh/public-key` | Get Ssh Public Key |  |  | ✅ 200 |

## spoolman

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| POST | `/api/v1/spoolman/connect` | Connect Spoolman |  |  |  |
| POST | `/api/v1/spoolman/disconnect` | Disconnect Spoolman |  |  |  |
| GET | `/api/v1/spoolman/filaments` | Get Filaments |  |  | ⚠️ 400 needs input |
| GET | `/api/v1/spoolman/spools` | Get Spools |  |  | ⚠️ 400 needs input |
| POST | `/api/v1/spoolman/spools/from-slot` | Create Spool From Slot |  | CreateSpoolFromSlotRequest |  |
| GET | `/api/v1/spoolman/spools/linked` | Get Linked Spools |  |  | ⚠️ 400 needs input |
| GET | `/api/v1/spoolman/spools/unlinked` | Get Unlinked Spools |  |  | ⚠️ 400 needs input |
| POST | `/api/v1/spoolman/spools/{spool_id}/link` | Link Spool | `{spool_id}` | LinkSpoolRequest |  |
| POST | `/api/v1/spoolman/spools/{spool_id}/unlink` | Unlink Spool | `{spool_id}` |  |  |
| GET | `/api/v1/spoolman/status` | Get Spoolman Status |  |  | ✅ 200 |
| POST | `/api/v1/spoolman/sync-all` | Sync All Printers |  |  |  |
| POST | `/api/v1/spoolman/sync/{printer_id}` | Sync Printer Ams | `{printer_id}` |  |  |

## spoolman-inventory

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/spoolman/inventory/filaments` | List Spoolman Filaments |  |  | ⚠️ 400 needs input |
| PATCH | `/api/v1/spoolman/inventory/filaments/{filament_id}` | Patch Spoolman Filament | `{filament_id}` | SpoolmanFilamentPatch |  |
| GET | `/api/v1/spoolman/inventory/slot-assignments` | Get Spoolman Slot Assignment | printer_id*, ams_id*, tray_id* |  | ⚠️ 422 needs query params |
| POST | `/api/v1/spoolman/inventory/slot-assignments` | Assign Spoolman Slot |  | SpoolSlotAssignmentRequest |  |
| GET | `/api/v1/spoolman/inventory/slot-assignments/all` | Get All Spoolman Slot Assignments | printer_id |  | ✅ 200 |
| DELETE | `/api/v1/spoolman/inventory/slot-assignments/{spoolman_spool_id}` | Unassign Spoolman Slot | `{spoolman_spool_id}` |  |  |
| GET | `/api/v1/spoolman/inventory/spools` | List Spools | include_archived |  | ⚠️ 400 needs input |
| POST | `/api/v1/spoolman/inventory/spools` | Create Spool |  | SpoolmanInventoryCreate |  |
| POST | `/api/v1/spoolman/inventory/spools/bulk` | Bulk Create Spools |  | SpoolmanInventoryBulkCreate |  |
| POST | `/api/v1/spoolman/inventory/spools/bulk-archive` | Bulk Archive Spools |  | SpoolmanBulkIdsRequest |  |
| POST | `/api/v1/spoolman/inventory/spools/bulk-delete` | Bulk Delete Spools |  | SpoolmanBulkIdsRequest |  |
| POST | `/api/v1/spoolman/inventory/spools/bulk-restore` | Bulk Restore Spools |  | SpoolmanBulkIdsRequest |  |
| POST | `/api/v1/spoolman/inventory/spools/bulk-update` | Bulk Update Spools |  | SpoolmanBulkUpdateRequest |  |
| POST | `/api/v1/spoolman/inventory/spools/reset-consumed-counter-bulk` | Bulk Reset Spool Consumed Counter |  | object |  |
| DELETE | `/api/v1/spoolman/inventory/spools/{spool_id}` | Delete Spool | `{spool_id}` |  |  |
| GET | `/api/v1/spoolman/inventory/spools/{spool_id}` | Get Spool | `{spool_id}` |  |  |
| PATCH | `/api/v1/spoolman/inventory/spools/{spool_id}` | Update Spool | `{spool_id}` | SpoolmanInventoryUpdate |  |
| POST | `/api/v1/spoolman/inventory/spools/{spool_id}/archive` | Archive Spool | `{spool_id}` |  |  |
| GET | `/api/v1/spoolman/inventory/spools/{spool_id}/filament-presets` | Get Spoolman Filament Presets | `{spool_id}` |  |  |
| PUT | `/api/v1/spoolman/inventory/spools/{spool_id}/filament-presets` | Save Spoolman Filament Presets | `{spool_id}` | SpoolFilamentPresetBase[] |  |
| GET | `/api/v1/spoolman/inventory/spools/{spool_id}/k-profiles` | Get Spoolman K Profiles | `{spool_id}` |  |  |
| PUT | `/api/v1/spoolman/inventory/spools/{spool_id}/k-profiles` | Save Spoolman K Profiles | `{spool_id}` | SpoolKProfileBase[] |  |
| POST | `/api/v1/spoolman/inventory/spools/{spool_id}/reset-consumed-counter` | Reset Spool Consumed Counter | `{spool_id}` |  |  |
| POST | `/api/v1/spoolman/inventory/spools/{spool_id}/restore` | Restore Spool | `{spool_id}` |  |  |
| GET | `/api/v1/spoolman/inventory/spools/{spool_id}/suppliers` | Get Spoolman Spool Suppliers | `{spool_id}` |  |  |
| PUT | `/api/v1/spoolman/inventory/spools/{spool_id}/suppliers` | Save Spoolman Spool Suppliers | `{spool_id}` | SpoolSupplierLinkInput[] |  |
| PATCH | `/api/v1/spoolman/inventory/spools/{spool_id}/tag` | Link Tag To Spoolman Spool | `{spool_id}` | SpoolTagLinkRequest |  |
| PATCH | `/api/v1/spoolman/inventory/spools/{spool_id}/weight` | Sync Spool Weight | `{spool_id}` | SpoolWeightUpdate |  |
| POST | `/api/v1/spoolman/inventory/sync-ams-weights` | Sync Spoolman Ams Weights |  |  |  |

## support

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/support/bundle` | Generate Support Bundle |  |  | ⚠️ 400 needs input |
| GET | `/api/v1/support/debug-logging` | Get Debug Logging State |  |  | ✅ 200 |
| POST | `/api/v1/support/debug-logging` | Toggle Debug Logging |  | DebugLoggingToggle |  |
| DELETE | `/api/v1/support/logs` | Clear Logs |  |  |  |
| GET | `/api/v1/support/logs` | Get Logs | limit, level, search |  | ✅ 200 |

## system

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/system/appliance` | Get Appliance Defaults |  |  | ✅ 200 |
| GET | `/api/v1/system/db-pool` | Get Db Pool |  |  | ✅ 200 |
| GET | `/api/v1/system/health` | Get System Health |  |  | ✅ 200 |
| GET | `/api/v1/system/info` | Get System Info |  |  | ✅ 200 |
| GET | `/api/v1/system/storage-usage` | Get Storage Usage | refresh, max_age_seconds |  | ✅ 200 |

## updates

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| POST | `/api/v1/updates/apply` | Apply Update |  |  |  |
| GET | `/api/v1/updates/check` | Check For Updates |  |  | not probed |
| GET | `/api/v1/updates/status` | Get Update Status |  |  | ✅ 200 |
| GET | `/api/v1/updates/version` | Get Version |  |  | ✅ 200 |

## user-notifications

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/user-notifications/preferences` | Get User Email Preferences |  |  | 🚫 403 no permission |
| PUT | `/api/v1/user-notifications/preferences` | Update User Email Preferences |  | UserEmailPreferenceUpdate |  |

## users

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/users` | List Users |  |  | 🚫 403 no permission |
| POST | `/api/v1/users` | Create User |  | UserCreate |  |
| GET | `/api/v1/users/` | List Users |  |  | 🚫 403 no permission |
| POST | `/api/v1/users/` | Create User |  | UserCreate |  |
| POST | `/api/v1/users/me/change-password` | Change Own Password |  | ChangePasswordRequest |  |
| GET | `/api/v1/users/slim` | List Users Slim |  |  | ✅ 200 |
| DELETE | `/api/v1/users/{user_id}` | Delete User | `{user_id}`, delete_items |  |  |
| GET | `/api/v1/users/{user_id}` | Get User | `{user_id}` |  |  |
| PATCH | `/api/v1/users/{user_id}` | Update User | `{user_id}` | UserUpdate |  |
| GET | `/api/v1/users/{user_id}/items-count` | Get User Items Count | `{user_id}` |  |  |

## virtual-printers

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| GET | `/api/v1/virtual-printers` | List Virtual Printers |  |  | ✅ 200 |
| POST | `/api/v1/virtual-printers` | Create Virtual Printer |  | VirtualPrinterCreate |  |
| GET | `/api/v1/virtual-printers/ca-certificate` | Get Ca Certificate |  |  | ✅ 200 |
| GET | `/api/v1/virtual-printers/tailscale-status` | Get Tailscale Status |  |  | ✅ 200 |
| DELETE | `/api/v1/virtual-printers/{vp_id}` | Delete Virtual Printer | `{vp_id}` |  |  |
| GET | `/api/v1/virtual-printers/{vp_id}` | Get Virtual Printer | `{vp_id}` |  |  |
| PUT | `/api/v1/virtual-printers/{vp_id}` | Update Virtual Printer | `{vp_id}` | VirtualPrinterUpdate |  |
| GET | `/api/v1/virtual-printers/{vp_id}/diagnostic` | Diagnose Virtual Printer | `{vp_id}` |  |  |

## webhook

| Method | Path | Summary | Parameters | Body | print-lab key |
|---|---|---|---|---|---|
| POST | `/api/v1/webhook/printer/{printer_id}/cancel` | Webhook Cancel Print | `{printer_id}` |  |  |
| POST | `/api/v1/webhook/printer/{printer_id}/start` | Webhook Start Print | `{printer_id}` |  |  |
| GET | `/api/v1/webhook/printer/{printer_id}/status` | Webhook Get Printer Status | `{printer_id}` |  |  |
| POST | `/api/v1/webhook/printer/{printer_id}/stop` | Webhook Stop Print | `{printer_id}` |  |  |
| GET | `/api/v1/webhook/queue` | Webhook Get Queue Status | printer_id |  | ✅ 200 |
| POST | `/api/v1/webhook/queue/add` | Webhook Add To Queue |  | QueueAddRequest |  |
