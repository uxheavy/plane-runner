# Worklog

This file records durable progress for the Plane Agent Tooling goal. Append entries chronologically. Preserve failed attempts and exact evidence.

## Current state

| Field                      | Value                                                                                                   |
| -------------------------- | ------------------------------------------------------------------------------------------------------- |
| Phase                      | Program definition                                                                                      |
| Active gate                | Freeze and approve release and verification manifests                                                   |
| Plane branch               | `codex/agent-tooling-architecture`                                                                      |
| Hermes branch              | Not created from baseline `5e88745f125c0d332c1d16ea0363860d447657f5`                                    |
| Last verified Plane commit | `a1954f991d`                                                                                            |
| Next action                | Resolve manifest-blocking eager tools, operation IDs, MCP inventory, verifier ownership, and thresholds |

## 2026-07-29 — Goal grounding

### Evidence

- Plane architecture baseline exists under `docs/agent-tooling/`.
- ADR-0001 is accepted.
- Plane worktree was clean before goal artifacts were added.
- No prior `GOAL.md`, `WORKLOG.md`, or `RESULT.md` existed in the inspected Plane tree.
- Implementation status remains not started.

### Decisions carried forward

- Internal Plane agents use native Hermes tools plus TypeScript Code Mode.
- External agents retain the Python MCP compatibility interface.
- Every path converges on the Plane Operation Gateway.
- Dedicated agents use one revocable Plane credential held host-side.
- Plane authorization and approval run on every operation.
- Existing Hermes concurrency and approval behavior is reused.
- Pending approval does not survive runtime restart.

### Next action

Resolve the eager native tools and supported operation boundary required by the broader project-planning pilot.

## 2026-07-29 — Live acceptance scope

### Decision

- The user selected a broader project-planning workflow rather than simple CRUD or the narrower triage proposal.
- Goal completion requires a real Hermes process against the authenticated Plane development server.
- The final live proof cannot use a mocked Plane Operation Gateway.

### Required proof

- Analyze a seeded allowed project's release readiness.
- Create one parent plan and three coordinated child work items after approval.
- Add one source-linked planning comment.
- Prove retry idempotency.
- Verify created state and correlated audit evidence.
- Prove structured denial against an inaccessible control project.
- Probe generated-TypeScript credential and network isolation.

## 2026-07-29 — Model and evaluation requirements

### Observed evidence

- Local ChatGPT subscription authentication exists at `~/.codex/auth.json`.
- Hermes source supports subscription-backed provider `openai-codex`.
- The local Codex model registry advertises canonical model ID `gpt-5.6-luna`.
- No credential contents were read or copied into program artifacts.

### Requirements

- All counted live acceptance and evaluation runs use `openai-codex` and `gpt-5.6-luna`.
- Silent provider or model fallback fails verification.
- Evaluation includes at least 50 version-controlled scenarios.
- Evaluation includes at least 50 authenticated live Hermes runs.
- The complete deterministic suite passes twice from clean state.
- Computer Use provides user-visible Plane and Hermes readback evidence.

## 2026-07-29 — Independent goal red-team

### Corrections adopted

- Added immutable release and verification manifests with explicit change control.
- Added verifier negative controls and independent clean-checkout execution.
- Strengthened live proof with frozen prompts, separate approver and verifier principals, pre-write readback, unique tags, canary secrets, controlled egress probes, and cleanup.
- Increased evaluation to 50 retained live Luna runs across ten project variants and adversarial scenarios.
- Required at least 90% workflow success and zero security, duplicate-mutation, or audit violations.
- Added cross-repository provenance, operator lifecycle, audit-failure, confused-deputy, full MCP inventory, GA, and rollout-promotion gates.
