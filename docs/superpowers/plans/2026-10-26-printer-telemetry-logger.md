# Printer telemetry logger: plan (approved by the owner, 26 Oct 2026)

**Goal.** While an experiment prints, record what the printer reports, once per layer and at every change: chamber
temperature, every fan, nozzle and bed temperatures, layer number, print state and HMS codes. Then a ridge at a
given height can be checked against what the printer was doing at that layer, instead of guessed from the G-code.

**Why now.** E-021/E-022 ridged at uneven heights; the leading suspect is the X2D's chamber auto-cooling (`M142`),
which switches the exhaust and auxiliary fans by chamber temperature at moments the G-code can't predict. Nothing
records those fans today: Bambuddy keeps only job start/end/state, and `lab exp telemetry` reads Local AI's summary
(state, progress, minutes left).

## What it does

1. `lab exp log <EID>` starts after `lab exp start`. It connects to the printer's own MQTT service
   (10.0.0.136:8883, TLS, user `bblp`), subscribes to `device/<serial>/report`, and sends one `pushall` request so the
   printer reports its full state. It sends nothing else: no commands, no settings.
2. It writes `projects/<p>/telemetry/<RUN>.jsonl` (kept out of git): one line per layer change, plus one line whenever
   a fan, the chamber temperature (±1 °C) or the state changes. Each line: time, layer, height, the fields above.
3. It stops when the printer reports FINISH, FAILED or idle, then writes a summary into the run record:
   - fan and chamber events with their layer and height ("aux fan 0 → 60% at layer 87, 17.4 mm")
   - the printer's own start, end and state (fixes the telemetry bug below)
4. `lab exp verdict` accepts ridge heights (`--marks "ridge@14mm,ridge@21mm"`), and the page lines them up against the
   logged events. Matching heights are a lead, not a cause, until a single-factor test confirms it.

## Credentials

The logger reads the printer's serial and access code from `~/.config/print-lab/printer.env` (mode 600), which the
owner creates. Claude never reads or writes that file. The code never goes into the repo, logs or records.
The printer's certificate is self-signed, so the file also pins its SHA-256 (`BAMBU_CERT_SHA256`); the logger checks it
before sending the code and refuses on a mismatch or when nothing is pinned (the first run prints the value to pin).

### Enrolling the printer's certificate

A fingerprint read over the network proves nothing by itself, so pinning is a check by the owner, not automatic:

1. Create `printer.env` without `BAMBU_CERT_SHA256` and run `lab exp log` once. It connects, sends nothing, and
   prints the certificate's subject, issuer, expiry and SHA-256.
2. Check the subject's CN is the serial shown on the printer's own screen (Settings → Device), and that the issuer
   is Bambu Lab's device CA. Do this on your own network, with the printer at its known address.
3. Only then add the `BAMBU_CERT_SHA256=…` line. Every later handshake, reconnects included, must present exactly
   that certificate; anything else is refused before the access code is sent.

An expired certificate is refused and never bypassed. If the printer is reset or replaced, repeat the enrolment.
Not yet done: checking the chain against Bambu's published device CA, which needs one real handshake to confirm
which CA the X2D uses.

## Also fixed in the same change

`lab exp telemetry` computes "elapsed" as now minus start, even after the print ended; that is how E-021 got 118.2 min
while the printer ran 87. Usage will come from the printer's own start and end times when the log has them.

## Tests (written first)

- Parsing recorded MQTT reports (fixtures copied from a real print, with the serial replaced) into per-layer lines.
- A change-only filter: no line when nothing changed within a layer.
- The client never publishes anything except the single `pushall` request (asserted on a fake broker).
- The summary finds the fan/chamber events and their heights.
- `elapsed` after a finished print uses the printer's end time.

## Cost and limits

- One new dependency: `paho-mqtt`.
- About half a day of work, built in a worktree, with a review before merge.
- The X2D's exact report field names (especially chamber temperature and the exhaust fan) need confirming from a real
  report before the parser is final; the first step records one raw report during E-023.
- Not in scope: controlling the printer, the camera, or replacing Bambuddy.
