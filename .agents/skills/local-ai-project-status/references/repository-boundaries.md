# Repository boundaries: discovery snapshot

Source-inspected 2026-10-29 (America/New_York). This is not live deployment verification. Recheck these links and relevant implementations on each task; branch names and source paths can change.

| Repository/service | Observed responsibility | Useful source |
| --- | --- | --- |
| azmusgb/pi-hub | Household browser UI on the Pi; Print Lab projection and queued requests; printer pause/resume/clear via Bambuddy | https://github.com/azmusgb/pi-hub/blob/main/hub/lab.py ; https://github.com/azmusgb/pi-hub/blob/main/hub/printer_control.py |
| azmusgb/print-lab | Mac experiment/build engine; canonical project files, physical-run records, qualification and production packages | https://github.com/azmusgb/print-lab/blob/main/lab/runs.py ; https://github.com/azmusgb/print-lab/blob/main/lab/qualification.py |
| azmusgb/LocalAI | Windows-hosted AI appliance, model/service orchestration, engineering workspace; display-feed integration | https://github.com/azmusgb/LocalAI/blob/main/docs/ARCHITECTURE.md |
| azmusgb/bambuhelper-smart-display | Workshop OS firmware, WS350 touchscreen, guarded printer/device controls, OTA/recovery and physical acceptance | https://github.com/azmusgb/bambuhelper-smart-display/blob/main/docs/REPOSITORY_BOUNDARIES.md |
| Bambuddy (separate service on Pi) | Spools, quantities, AMS placement, workshop projects, print archive/queue; printer integration | Verify consuming adapters in pi-hub/hub/bambuddy.py and print-lab/lab/bambuddy.py |

## Important discrepancies to recheck
- Print Lab's lab/sync.py targets() selected Pi Hub only at the snapshot, while its module docstring and older one-home spec described LocalAI as the UI destination. Trust the actual selected targets, not the historical narrative.
- Workshop OS boundary documentation names Bambuddy as inventory authority and says the old Filament Inventory app was retired, but retains historical inventory contracts and old candidate sequencing. Do not revive retired endpoints based on those sections.
- Print Lab still contains LocalAI telemetry helpers; a Pi Hub-only UI sync does not prove the Windows dependency has been eliminated.
- Pi Hub and Workshop OS expose different printer control paths. Do not claim a shared command service exists without tracing both.

## Recommended ownership, not a completed migration
Pi Hub should be the everyday household/workshop entry point; Print Lab should own experimental truth; Bambuddy should own stock and print operations; LocalAI should provide optional AI assistance; Workshop OS should provide the nearby physical interface.
Use explicit run/build/artifact identifiers and source timestamps across services. A cached display, AI answer, queued request or printer-completed event is not an accepted experiment verdict.
Prefer one owner per fact and a documented command policy. Preserve proven device-local operation and guards during any control-path consolidation.
