# Bambuddy upload and queue

Bambuddy runs on the Pi at port 8000. Everything below is from the 15 Nov 2026 session.

## Keys

| Key | Where | Can do |
|---|---|---|
| print-lab key | used by `lab.bambuddy.upload` | upload files |
| control key | `ssh pi` then `sudo -n cat /etc/pi-hub/secrets/bambuddy_control_key` | create and delete queue items; cannot list the queue |
| read key | `~/.config/bambuddy/api-key` | inventory and printer status |

Never print a key into the chat or a file.

## Upload

From the print-lab repo root: `lab.bambuddy.upload(path, staging_folder())`. The result is the library file id (the 10 in tile was library #14).

## Queue

`POST /api/v1/queue/` with the control key (send it from the Pi over `ssh pi`) and body:

```json
{"printer_id": 1, "library_file_id": 14, "ams_mapping": [1], "manual_start": true}
```

- `ams_mapping` index is slot minus 1: `[1]` is AMS slot 2.
- `manual_start: true` keeps the print waiting until the owner presses Start.
- Remove an item with `DELETE /api/v1/queue/<id>` (the 10 in tile was item #11).

## Before queueing

- `printer_status` (MCP `home`) and the read key show the AMS trays. At last check: slot 1 AF7933, slot 2 F95D73, slot 3 F98C36, slot 4 D4B1DD, external 161616. The Shadow Storm Marble (inventory spool #6) was not loaded.
- Match material, not colour label: the Kexcelled K5 PLA Matte Light Matte Terracotta reads F95D73 on the printer, D3C5A3 in the slice header and C97B5A in inventory. All three are metadata.
- If the printer says "Done: clear the plate", the plate is not ready; tell the owner.
- Queueing is not starting. Never press Start or send a start command.
