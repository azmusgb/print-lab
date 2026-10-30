---
name: print-lab-run-integrity
description: Review or implement Print Lab run, artifact, evidence, qualification, reconciliation, and production-package behavior. Use when changes affect which physical print was accepted or which exact files a release contains; not for unrelated UI styling.
---

# Print Lab run integrity

Protect the link between a physical attempt, its exact inputs, the owner's evidence, and the production package. Apply this workflow to the current schema rather than assuming historical field names still exist.

## Trace the current path
Read applicable repository instructions and the current run/build schema, start path, reconciliation, qualification, packaging, and relevant tests. Typical discovery points are lab/runs.py, lab/loop/guards.py, lab/qualification.py, lab/production.py, lab/index_v2.py, lab/pull.py and lab/sync.py.
Trace consumers in Pi Hub or LocalAI only when the changed contract reaches them. Keep UI projections and queued requests separate from the Mac's canonical records.

## Invariants to check
- Artifact identity: preserve the hash bound to the physical run. A later sync must not rehash a changed file and silently replace that binding. Legacy evidence without a trustworthy original identity remains explicitly unverified.
- Run-specific acceptance: resolve the selected canonical run and any explicit legacy source-run mapping. The accepting verdict must cover that attempt, not simply its experiment. Printer completion and telemetry are not owner acceptance.
- Package identity: verify all required sources and the copied destination bytes; reject missing/changed inputs. Preserve every evidence item with a unique destination even when basenames match. Manifest entries and checksum contents must agree.
- Paths: resolve paths within the intended project/package root, including symlinks; reject escapes and unsafe destination names. Do not loosen path rules to make a package pass.
- Publication: an existing sealed package must not be silently overwritten. Advance the current reference only after successful sealing. Test recovery when publication succeeds but metadata persistence fails.
- Reconciliation and retries: repeated or concurrent reconciliation must not create duplicate canonical records, erase bound evidence, or change accepted identity. Repeated request IDs should have explicit idempotent outcomes.
- State: missing, stale, failed, completed, accepted, and packaged mean different things. A successful sync or a files-exist projection cannot prove hash integrity.

## Validate in isolation
Use disposable fixture projects and fake service adapters. Before running tests, inspect their side effects and disable or replace production sync, printer dispatch, background polling, and live deployment paths as appropriate.
Choose regression tests for the changed invariant, especially:
1. Modify a slice after binding it, reconcile, and require the original binding plus a mismatch.
2. Accept attempt A, select attempt B, and require fresh acceptance for B (including legacy/canonical mappings).
3. Seal two different evidence files with the same basename and verify both bytes through their manifest entries.
4. Inject a copy/write failure or retry and confirm no false promotion or silent overwrite.
Do not claim these tests already exist or pass. Verify current behavior before fixing it. Distinguish environment-blocked tests from product failures; do not weaken assertions or controls.

## Deliver
For review: report severity, exact source location, reproduction, expected/actual behavior, and proposed fix.
For implementation: provide the complete patch and meaningful regression coverage, with commands and results. State any consumer compatibility changes and outstanding runtime checks.
This skill does not authorize actual printer control, production qualification, firmware promotion, merging, or deployment. Use synthetic records for verification unless live mutation is already explicitly authorized.
