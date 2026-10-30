---
name: local-ai-project-status
description: Establish fresh status, repository ownership, and the next action for Bill's Local AI, Pi Hub, Print Lab, or Workshop OS work. Use for project reviews, architecture-boundary questions, and continuing an established engineering task; not for unrelated requests or automatic deployment.
---

# Local AI project status and next action

Resolve what is true now and which repository owns the requested change. Preserve the user's scope: review-only requests produce findings; continuation requests resume already authorized work.

## Establish the evidence
- Resolve the repository from the user's path or URL, then inspect applicable AGENTS.md, the working tree, branch, HEAD, remotes, and relevant source. Preserve unrelated edits.
- Use current source/runtime evidence before project documents and chat history. A README can contain stale release tables or migration plans.
- For GitHub status, inspect the relevant current branch/PR and checks against its exact SHA. A local HEAD, a remote branch, and a deployed build are separate observations.
- Read only the source necessary to answer the question. Do not fetch credentials or print environment values merely to discover an integration.
- For cross-project questions, read [repository-boundaries.md](references/repository-boundaries.md). Treat its snapshot as discovery hints; verify routes, callers, schemas and ownership before acting.

## Choose the next action
- Identify the requested outcome, its data owner, serving UI, execution host, and downstream consumers. Distinguish data ownership from cached copies and request queues.
- Prioritize reproduced correctness defects and incomplete validation before feature expansion when they block the requested outcome.
- If a feature spans repositories, name the producer and consumers and the compatibility/deployment order. Do not copy a fix into another repository without checking its implementation.
- Continue reversible work already authorized. The skill itself grants no authority to merge, deploy, flash hardware, send messages, or change credentials.
- If a plugin or runtime is unavailable, complete independent source analysis and state exactly what remains unverified. Never use an older successful run as current evidence.

## Report and hand off
Lead with findings or the current outcome. Include repository/branch/SHA, relevant dirty-tree caveats, validation results, remaining blocker, and next concrete action when material.
Keep implemented, locally validated, CI green, merged, deployed, runtime verified, and physically accepted distinct; mark inapplicable stages as such.
For reviews, supply reproducible trigger, expected versus actual result, source location, impact, and a specific fix/test.
For implementation, deliver a complete patch and appropriate tests; use existing platform/design/deployment skills when relevant rather than duplicating their procedures.
Do not create a durable report unless requested or useful to the ongoing work.
