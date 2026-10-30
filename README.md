# Print lab

An experiment engine for 3D printing: it measures a model, checks it against rules learned from real prints,
cuts small test coupons, slices with Bambu Studio and reads the G-code, so a defect is narrowed to its cause in a
few controlled prints. Design: `docs/superpowers/specs/2026-10-24-print-lab-design.md`.

    brew install uv && brew install --cask openscad@snapshot
    uv sync && uv run pytest
    uv run lab --help

## Running an experiment

Each experiment answers one question, changes one factor and is judged by you. Records are plain JSON under
`projects/<name>/` (questions, experiments, prints); add `--project <name>` to any command (default `hex-tile`).

    uv run lab question new "Do slower inner walls help?" --budget 3h,100g
    uv run lab exp plan Q-001 "Slow vs fast inner walls" --factor inner_wall_speed --values 250,80 \
        --expect "B>A:clearly" --source sources/<model>.3mf --object <name> --around 66 \
        --base sources/<settings>.3mf --hypothesis "..." --prediction "..."
    uv run lab exp build E-005              # cut, lay out and slice the plate (prints/sliced/...)
    uv run lab exp check E-005              # READY, NEEDS APPROVAL or BLOCKED, with the reasons
    uv run lab exp approve E-005 --reason "..."   # only for budget or full-part reasons; never a block
    uv run lab exp send E-005               # open the checked .gcode.3mf in Bambu Connect; print it there unchanged
    uv run lab exp start E-005              # when you send the print: re-checks and snapshots the setup
    uv run lab photos add PR-005-01 ~/Pictures/IMG_*.HEIC
    uv run lab exp verdict E-005 --rank "B>A" --strength clearly
    uv run lab question status Q-001        # spend, outcomes, stop state, what's next

`lab question stop|resume` pauses a question; `lab question rebuild` re-derives every total from the records and
writes nothing if any record is invalid. `lab setup log <kind>` records drying, calibration and nozzle changes so
each print knows the setup it ran on.

## File integrity and test isolation

New builds freeze both the source print archive and sliced archive with SHA-256 digests. Check, send and start
refuse missing or changed frozen files. Existing builds without a sliced digest must be rebuilt with
`lab exp build E-NNN --replace`; the lab never treats their current bytes as an approved baseline.
`lab exp verify` compares sliced candidates to the stored build-time digest. A content-equivalent source archive
can only be verified against a source archive that still matches its frozen digest.

Photo imports stage conversions before publishing uniquely named files under the experiment lock. Concurrent
starts use that same lock for eligibility checks and run creation, so a second start returns the existing run.

Tests disable default Bambuddy access and refuse non-loopback socket connections and DNS lookups. Loopback fake
servers and mocked clients remain available. `uv run pytest --live-network` explicitly enables live networking;
record isolation still applies. Run live checks only in an environment configured for the intended services.
The full suite also needs Bambu Studio 02.08.02.61, OpenSCAD 2025+ and macOS photo utilities.
