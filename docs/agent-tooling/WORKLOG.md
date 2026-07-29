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

## 2026-07-29 — Independent pre-freeze review

### Verdict

Reject manifest freeze at Plane commit `805f12ddbf`.

### Confirmed evidence

- The 177-tool inventory count and digest are correct.
- The 171 + 1 + 5 compatibility partition is syntactically complete.
- The proposed hybrid gateway is a reasonable conceptual seam.

### Freeze blockers to close

- Replace category-only MCP disposition with a 177-row behavioral and gateway mapping.
- Capture runtime `tools/list` schemas and behavioral fixtures rather than treating AST signatures as the compatibility oracle.
- Freeze 50 distinct scenario specifications and correct scenario/trial arithmetic.
- Expand verifier coverage from goal areas to every normative requirement and release row.
- Define the gateway wire transport, authenticated binding, version negotiation, approval transition, and retry protocol.
- Define pilot schemas, errors, authorization, approval, idempotency, result, and semantic-composition contracts.
- Define approval classes, approver authorization, group preflight, freshness, dependency substitution, partial failure, and external MCP behavior.
- Add negative controls for approval, isolate, callback identity, duplicate mutation, result limits, MCP omission, provenance, and rollback.
- Define evidence storage, signing, trust, retention, and replacement rules.
- Resolve immutable-model limitations, evaluator authentication, exact client versions, rollout cohorts, and durable authorities.
- Resolve the full 177-tool release commitment versus narrow vertical-slice sequencing.

### Progress after reviewed commit

- Proposed explicit Deno supervisor/Worker isolate architecture at commit `1bdb3b4a14`.
- Proposed exact execution, result, retention, performance, recovery, and observation thresholds for later approval.

### Next action

Obtain the immediate gateway-interface decision, then close the remaining technical pre-freeze blockers before requesting whole-manifest approval.

## 2026-07-29 — Core gateway interface accepted

### Decision

- The user accepted the deep-hybrid core gateway boundary.
- The gateway exposes one request-bound operation-execution seam.
- Read-only catalog discovery remains a separate interface.
- Approval, idempotency, reconciliation, result control, and audit lifecycle remain internal.
- Friendly native Hermes tools remain thin adapters rather than a second enforcement implementation.

### North Star

Use the least custom code that satisfies the approved production and security gates. Prefer reuse and generation over additional interfaces or protocols.

### Still open

- Exact eager tools and supported operation boundary.
- Explicit preflight groups and omission or inclusion of a graph DSL.
- Wire transport and external approval behavior.
- All remaining independent-review blockers before manifest freeze.

## 2026-07-29 — MCP reuse and release-plan write accepted

### Official MCP boundary

- Reuse Plane's official Python MCP server as the external adapter host.
- Preserve its deployed transports and 177-tool compatibility surface.
- Migrate existing handlers incrementally to the gateway rather than recreating the server.
- Keep internal Hermes on native tools and TypeScript Code Mode without an MCP hop.

### Release-plan write boundary

- Represent the parent, three children, and source comment as one curated `plane.release_plans.create@1` semantic operation.
- Validate, authorize, approve, claim idempotency, execute, reconcile, and audit the complete business action in the gateway.
- Do not add a general workflow-graph DSL in v1.

### Rationale

These choices reuse existing code and avoid both a duplicate MCP implementation and a generic workflow engine.

### Next action

Freeze the exact semantic operation contract and the gateway wire adapter.

## 2026-07-29 — Official MCP gateway seam and forks

### Decision

- Add one optional gateway transport at the official Plane Python SDK `BaseResource` seam.
- Keep existing official MCP handlers and their tool-level contracts in place.
- Select gateway mode in the MCP client factory.
- Preserve explicit local PQL and specialized attachment exceptions.

### External repositories

- Forked `makeplane/plane-mcp-server` to `uxheavy/plane-mcp-server`.
- Created `uxheavy/plane-mcp-server` branch `codex/agent-tooling-v1` at `96cf4d51d65cfa5e47d10ff7a4a4caba3b7a98d1`.
- Forked `makeplane/plane-python-sdk` to `uxheavy/plane-python-sdk`.
- Created `uxheavy/plane-python-sdk` branch `codex/agent-tooling-v1` at `78702e9224bd9c5e8fffdabfbfdd582ac1fa9426`.
- Added both forks as pinned submodules under `external/` at Plane commit `f4d2dd3119`.

### Evidence

- The pinned official MCP server centralizes `PlaneClient` creation in `get_plane_client_context()`.
- Plane Python SDK v0.2.20 routes every ordinary resource request through `BaseResource`.
- `BaseResource` owns the shared HTTP session, URL, authentication, retry, and response-normalization seam.

### Consequence

The release integration lock and clean-checkout verifier cover four repositories: Plane, Hermes, the official MCP server, and the Plane Python SDK.

### Next action

Specify the versioned gateway wire contract used by native Hermes, Code Mode callbacks, and the SDK transport.

## 2026-07-29 — Gateway wire transport accepted

### Decision

- Use one versioned JSON HTTP adapter inside Plane's existing `/api/v1` service.
- Reuse current Plane API-key and OAuth authentication.
- Keep identity, authorization, approval, idempotency, result control, and audit inside the deep gateway module.
- Do not add an internal MCP hop, gRPC service, broker, or separate gateway deployment.

### Proposed wire contract

- Bounded authenticated catalog search and description endpoints.
- One workspace-bound operation-execution endpoint.
- Operation major version and catalog digest on every call.
- Host-derived mutation `Idempotency-Key`.
- Structured `succeeded`, `approval_required`, `rejected`, `failed`, and `outcome_unknown` states.
- Optional shared Python SDK transport over the same endpoint.

### Still open

The wire reserves `approval_required`, but the approver authority, decision transport, expiry, and exact resume protocol require a separate decision before manifest freeze.

### Next action

Specify the pilot semantic operation schemas and approval protocol.

## 2026-07-29 — Pilot operation contracts proposed

### Contract boundary

- Defined nine callable pilot operations plus host-bound workspace context.
- Replaced raw serializer passthrough with narrow canonical project, cycle, work-item, comment, and page projections.
- Reserved credentials, actor identity, workspace identity, idempotency, approval, and audit fields for trusted host context.
- Required non-leaking reference resolution and independent authorization of related objects.
- Added cycle removal to the observed public-operation mapping for work-item placement updates.

### Source-driven differences

- Project-name resolution is excluded because project names are not unique.
- Current-cycle results remain plural because Plane can return zero or multiple current cycles.
- Agent comment writes use the same member-or-admin role as work-item writes, closing the weaker public comment-permission mismatch.
- Gateway idempotency replaces public external-ID check-then-create behavior as the concurrency guarantee.
- The release-plan operation requires one transaction and commit-safe activity delivery to guarantee exact counts and replay.

### Verification

- A fresh independent source review confirmed the serializer constraints, permission mappings, cycle-placement behavior, comment sanitization gap, and release-plan atomicity requirements.
- The repository formatter initially rejected both changed documents; they were formatted before commit verification.

### Still open

The contracts remain proposed until approval authority, effect labels, generated schema digest, executable fixtures, and manifest approval are resolved.

### Next action

Resolve the approval decision authority and resume protocol, one product decision at a time.
