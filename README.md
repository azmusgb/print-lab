# Print lab

An experiment engine for 3D printing: it measures a model, checks it against rules learned from real prints,
cuts small test coupons, slices with Bambu Studio and reads the G-code, so a defect is narrowed to its cause in a
few controlled prints. Design: `docs/superpowers/specs/2026-10-24-print-lab-design.md`.

    brew install uv && brew install --cask openscad@snapshot
    uv sync && uv run pytest
    uv run lab --help
