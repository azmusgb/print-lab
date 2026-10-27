# Print Lab GUI — Figma Architecture & Visual Design Critique

**Date:** 2026-10-27  
**Reference Document:** `docs/blueprint/Print-Lab-Blueprint.md`  
**Figma Canvas:** `https://www.figma.com/design/ZDNyoPD0ZQRLEWw6NtmFPi` (Boards 01–10)  
**Implementation Surface:** `LocalAI` frontend (`Projects › Print lab`) / `print-lab` CLI & daemon

---

## 1. Executive Summary

A comprehensive visual, architectural, and interaction audit was conducted across the 10 Figma proposal boards against the deployed implementation in `LocalAI` (`app/public/print-lab.js`, `app/public/print-lab-observe.js`, `app/public/print-lab-photos.js`, and `app/public/app.css`).

The blueprint proposal establishes strong scientific rigor:
- Explicit separation of **requested** vs **sliced** vs **physically observed** parameters.
- Disambiguation of physical observations from machine reservation estimates.
- Complete snapshot payloads containing every subject outcome (no implicit defaults).
- Strict authority boundaries: the Mac daemon is the single source of truth; phone clients queue durable idempotent requests.

Key visual and interaction frictions identified during the critique:
1. **Vertical Observation Bloat (Mobile 390w)**: The initial layout stacked 6 full-width radio buttons per question, inflating the phone form to ~2,400px of scrolling for an inspection session.
2. **Modal Sheet Affordance**: Bottom sheets lacked native iOS grab indicators, making dismissability ambiguous on touchscreen devices.
3. **Telemetry Bar Glanceability**: The live print progress bar at 8px height lacked presence and suffered typography jitter from non-tabular fonts during countdowns.
4. **Filament Spool Spine Contrast**: Direct application of raw hex colors to card borders produced extreme glare on neon/white filaments and visual drop-out on dark filaments against the dark background.

All immediate high-leverage quick wins were implemented in PR #413 and verified across automated test suites.

---

## 2. Token Architecture & Design System Alignment

### 2.1 Palette and Surface Elevation
The proposal specifies a calibrated dark palette intended to align with Local AI's dark mode (`#0b121e` / `#121b2b`):
- **Base Canvas (`--ds-surface`)**: `#121b2b` (Local AI container background).
- **Secondary Surfaces (`--ds-surface-2`)**: `#162133` (Card and row container level).
- **Line Tokens (`--ds-line`, `--ds-line-2`)**: `#243049` and `#334155`.
- **Semantic Accents**:
  - Primary Action / Info: Blue (`--ds-accent` `#38bdf8`, soft `#1e3a5f`).
  - Attention / Pending: Amber (`--ds-attention` `#f59e0b`, soft `#78350f`).
  - Success / Validated: Green (`--ds-good` `#22c55e`, soft `#14532d`).
  - Blocking / Error: Red (`--ds-bad` `#ef4444`, soft `#7f1d1d`).

### 2.2 Typography & Radius Token Budget
Local AI enforces strict token rules in `tests/budgets.test.cjs`:
- All font sizes outside the legacy Missions view must map to the 5-step scale (`--ds-fs-1: 13px`, `--ds-fs-2: 14px`, `--ds-fs-3: 16px`, `--ds-fs-4: 20px`, `--ds-fs-5: 28px`).
- All radii must use `--ds-r-sm` (4px), `--ds-r-md` (8px), or `--ds-r-lg` (12px).
- `app.css` is strictly constrained within its gzipped budget (46 KB).

---

## 3. Screen-by-Screen Critique (Figma Boards 01–10)

### Board 01: Overview / Desktop (1440w)
- **Strengths**: Clear information hierarchy. One active question (`Q-002`), active test telemetry, and prominent *Needs You* cards sorted by urgency.
- **Critique**: Budget summary boxes (`Spent: 99.4 min / 29.1 g`, `Remaining: 380 min / 270 g`) were visually detached from the question progress.
- **Recommendation**: Unify question budget and cumulative run consumption into a cohesive telemetry card with split-bar progress.

### Board 02: Plan & Build Detail / Desktop (1440w)
- **Strengths**: Excellent disclosure of requested vs realized settings. For instance, inner wall speed requested at 250 mm/s correctly flagged as realized at 147 mm/s due to volumetric flow clamping.
- **Critique**: Pre-print checklist was easy to miss when placed beneath the large camera snapshot frame.
- **Recommendation**: Dock pre-print verification checklists directly adjacent to the primary action trigger (*"Send to printer"* / *"Judge it"*).

### Board 03: Evidence Comparison Studio / Desktop (1440w)
- **Strengths**: Side-by-side macro photography with explicit specimen identification tabs (`40 mm/s · Clean` vs `80 mm/s · Faint`).
- **Critique**: Static side-by-side views require eye-scanning back and forth across 600px width; subtle layer banding differences are hard to pinpoint without an interactive overlay.
- **Recommendation**: Upgrade `.lab-wipe` to an interactive curtain slider and provide synchronized pan-and-zoom controls across both viewports.

### Board 04: History & Reconciliation / Desktop (1440w)
- **Strengths**: Does not hide contradictory findings (e.g. v51 contradiction between machine rating and operator rating).
- **Critique**: Long lists of past experiments (`Earlier`) require rapid filtering.
- **Recommendation**: Introduce multi-attribute filter chips (by filament spool, by outcome grade, by defect type).

### Board 05: Current Print & Telemetry / Phone (390w)
- **Strengths**: Touch-friendly 44px tap targets, prominent ETA countdown (`done about 7:45 PM`), and instant access to camera frame.
- **Critique**: Thin 8px progress track lacked presence on high-DPI displays.
- **Resolution**: Heightened progress bar to 14px with rounded end-caps and tabular typography (`font-variant-numeric: tabular-nums`).

### Board 06: Record Observations / Phone (390w)
- **Strengths**: Implements strict data completeness: every question requires explicit operator answers, providing "Not looked at", "Couldn't tell", and "Doesn't apply" alongside physical grades.
- **Critique**: Vertical stacking of 6 radio options per outcome created excessive scrolling (>2,400px), causing operator fatigue.
- **Resolution**: Refactored `.lab-obs__opts` into a responsive 3x2 matrix of segmented touch chips, reducing scroll height by ~65% while keeping WCAG 2.2 AA target size.

### Board 07: Approve Exact Build / Phone (390w)
- **Strengths**: Forces explicit human accountability. Requires inputting a reason before waiving guards (e.g. `248.7 / 45 min per test`).
- **Critique**: Destructive "Drop" action was placed immediately adjacent to "Approve".
- **Recommendation**: Isolate "Drop" behind a secondary tap confirmation or separate button container.

### Board 08: States & Recovery
- **Strengths**: Clear specifications for offline daemon, expired leases, camera pass-through timeouts, and conflict resolutions.
- **Critique**: Optimistic request states need clear feedback when background sync takes >30 seconds.
- **Recommendation**: Show polite live-region announcements with retry affordances when the Mac daemon is unreachable.

### Boards 09 & 10: Architecture, Delivery & Components
- **Strengths**: Complete inventory of reusable components (`ActionButton`, `StateNotice`, `QuantitySummary`, `EvidencePair`, `ObservationField`).
- **Recommendation**: Enforce CSS token reuse to keep the app bundle within download budgets without introducing redundant classes.

---

## 4. Summary of Applied Quick Wins

| Item | Component | File | Result |
|---|---|---|---|
| **iOS Drag Handle** | `.lab-sheet::before` | `app/public/app.css` | Native bottom-sheet drag affordance on mobile viewports (`max-width: 640px`). |
| **3x2 Touch Matrix** | `.lab-obs__opts` | `app/public/app.css` | Compact 3-column chip matrix; 65% height reduction; 44px tap target preserved. |
| **Telemetry Glance** | `.lab-live__bar` | `app/public/app.css` | Heightened to 14px with pill radius; tabular font embedding (`font-variant-numeric: tabular-nums`). |
| **Spool Spine Contrast** | `.lab-exp[style*="--spine"]` | `app/public/app.css` | Clamped with `color-mix()` and inset shadow border to ensure accessibility across all 37 filament colors. |
