# Worklog

This file records durable progress for the Plane Agent Tooling goal. Append entries chronologically. Preserve failed attempts and exact evidence.

## Current state

| Field                      | Value                                                                          |
| -------------------------- | ------------------------------------------------------------------------------ |
| Phase                      | Program definition                                                             |
| Active gate                | Freeze and approve release and verification manifests                          |
| Plane branch               | `codex/agent-tooling-architecture`                                             |
| Hermes branch              | Not created from baseline `5e88745f125c0d332c1d16ea0363860d447657f5`           |
| Last verified Plane commit | `f70ec0466a`                                                                   |
| Next action                | Approve the proposed v1 gateway interface, eager tools, and operation boundary |

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

## 2026-07-29 — Source and interface inventory

### Evidence

- Pinned the official Python MCP compatibility surface at commit `96cf4d51d65cfa5e47d10ff7a4a4caba3b7a98d1`, package `0.2.11`.
- Captured 177 unique MCP tools in a machine-readable, checksummed inventory.
- Traced the public Plane operations and current authorization behavior required by the project-planning workflow.
- Traced Hermes eager registration, deferred dispatch, middleware, approval, and current Python Code Mode seams.
- Compared four independent gateway interfaces: one deep operation seam, a named semantic facade, a durable state machine, and a catalog/batch/plan facade.

### Proposed decision

- Use request-bound `execute` as the core gateway interface.
- Keep catalog `search` and `describe` as a separate read-only interface.
- Keep approval, idempotency, reconciliation, and audit lifecycle as an internal state machine.
- Expose five eager domain tools plus `plane_docs`, `plane_search`, and `plane_execute` in Hermes.
- Do not expose a general graph-planning DSL in v1.

### Next action

Obtain user approval of the proposed interface boundary before freezing the corresponding manifest rows.

## 2026-07-29 — Compatibility and verifier design

### Proposed external MCP disposition

- Route 171 ordinary pinned MCP tools through gateway-backed compatibility adapters.
- Retain `get_pql_reference` as versioned local read-only behavior.
- Route five attachment tools through a hardened attachment adapter with explicit SSRF, transfer, redaction, and cleanup policy.
- Deprecate or omit none of the 177 pinned v0.2.11 tools.

### Verifier strengthening

- Added verifier ownership and independence requirements.
- Mapped every goal area to required verification checks.
- Defined the immutable 50-trial evaluation ledger.
- Defined expected-failure semantics for all four negative controls.
- Defined the clean-checkout verifier execution contract and proposed final command.

### Next action

Independently review the proposed compatibility and verification documents, then resolve the remaining numeric and runtime manifest rows.
