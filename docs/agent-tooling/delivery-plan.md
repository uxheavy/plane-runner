# Delivery Plan

## Delivery strategy

Build one narrow vertical slice through the final architecture before expanding catalog coverage. External MCP convergence proceeds after the internal path is proven and must not block the internal pilot.

## Workstreams and gates

### 0. Program definition

Deliverables:

- Approved product scope and named pilot workflows.
- Accepted architecture and decision register.
- Success scorecard with numeric targets.
- Named product, backend, Hermes, security, infrastructure, and quality owners.

Exit gate: no unresolved decision can materially change the first contract or trust boundary.

### 1. Operation contract

Deliverables:

- Existing Python MCP and public API inventory.
- Initial supported operation boundary.
- OpenAPI generation pipeline design.
- Curated overlay schema.
- Typed errors, pagination, idempotency, result, and audit conventions.
- Consumer-independent contract tests.

Exit gate: the same fixtures can validate native, Code Mode callback, and external MCP representations.

### 2. Plane Operation Gateway

Deliverables:

- Gateway boundary inside the Plane API service.
- Dedicated agent identity authentication.
- Live Plane authorization on every operation.
- Approval-policy interception point.
- Idempotency and invocation records.
- Append-only audit events.
- Result shaping and structured errors.

Exit gate: authorization-matrix and audit-completeness tests pass for the pilot operations.

### 3. Native Hermes pilot

Deliverables:

- Thin native tool adapters for the initial eager tools.
- Progressive Tool Search registration for deferred operations.
- Correlated run, turn, tool-call, and invocation IDs.
- Hermes approval and concurrent-execution integration.

Exit gate: named pilot workflows succeed without Code Mode and cannot bypass Plane policy.

### 4. TypeScript Code Mode

Deliverables:

- `docs`, `search`, and `execute` surfaces.
- Generated TypeScript client from the operation contract.
- Restricted child isolate in the run container.
- Credential-free host RPC.
- Resource, call-count, stdout, result, and cumulative limits.
- Nested approval and audit propagation.

Exit gate: sandbox, credential-exfiltration, nested approval, timeout, and oversized-result tests pass.

### 5. Mutation reliability

Deliverables:

- Idempotency support for pilot mutations.
- Explicit `outcome_unknown` behavior.
- Concurrent group preflight where required.
- Per-operation partial-result semantics.
- Reconciliation instructions for ambiguous outcomes.

Exit gate: retry, interruption, network-failure, and container-death tests demonstrate no blind duplicate mutation.

### 6. Evaluation and production hardening

Deliverables:

- Realistic agent task evaluation suite.
- Threat model and security review.
- Load, concurrency, and latency benchmarks.
- Dashboards, alerts, runbooks, kill switches, and credential rotation.
- Data retention and redaction review.
- Version-controlled manifest with at least 50 scenarios.
- At least 50 authenticated live Hermes evaluation runs.
- Ten materially different seeded project shapes.
- Three independent project-planning runs per seeded shape.
- Provider and model assertions for `openai-codex` and `gpt-5.6-luna`.
- Property or fuzz coverage for boundary-sensitive inputs.
- Two consecutive clean-state deterministic-suite passes.
- Three consecutive final passes on the exact release artifact.
- Computer Use screenshots and readbacks for user-visible acceptance.

Exit gate: production scorecard targets are met and rollback is rehearsed.

### 7. Controlled rollout

Stages:

1. Development-only internal agents.
2. One allowlisted workspace.
3. Additional workspaces under feature flag.
4. General availability for the approved catalog.

Each stage requires review of task success, denials, approvals, unknown outcomes, audit gaps, sandbox failures, and operator incidents.

### 8. External MCP convergence

Deliverables:

- Adapter mapping from Python MCP tools to shared operations.
- Compatibility tests for representative MCP clients.
- Shadow comparison between legacy handlers and gateway results.
- Incremental handler migration with rollback.

Exit gate: external behavior remains compatible or follows an approved deprecation plan.

## First vertical slice

Selected contents:

- Seeded allowed and inaccessible control projects.
- Current-cycle, work-item, blocker, dependency, priority, and ownership analysis.
- Native eager tools for common project context.
- Catalog discovery and TypeScript composition for broader analysis.
- One parent release-plan work item.
- Three coordinated child work items.
- One source-linked planning comment.
- Semantic release-plan policy evaluation under the autonomous default.
- A separate administrator-configured real approval control.
- Stable invocation idempotency and duplicate prevention.
- Structured denied-access proof.
- Credential and network-isolation probes.
- Plane state and correlated audit readback.
- A real Hermes process against the authenticated Plane development server.

## Production readiness checklist

- [ ] Product scope and success targets approved.
- [ ] Shared operation contracts versioned and tested.
- [ ] Dedicated agent credential issuance, storage, rotation, and revocation documented.
- [ ] Authorization matrix passes for all pilot operations.
- [ ] Approval cannot bypass Plane authorization.
- [ ] Generated TypeScript cannot access credentials or arbitrary network resources.
- [ ] Every admitted operation produces audit evidence.
- [ ] Mutation retry and unknown-outcome behavior tested.
- [ ] Model-visible and cumulative results remain bounded.
- [ ] Temporary artifact retention and cleanup verified.
- [ ] Metrics, alerts, kill switches, and runbooks operational.
- [ ] Rollback rehearsed before each rollout expansion.
- [ ] External MCP compatibility verified before handler migration.
- [ ] Mandatory live Hermes project-planning acceptance passes without a mocked gateway.
- [ ] Every counted live run resolves `openai-codex` and `gpt-5.6-luna` without fallback.
- [ ] Extensive evaluation coverage and repetition requirements pass.
- [ ] Approved release and verification manifests are fully satisfied or carry explicit approved exceptions.
- [ ] Independent verifier passes qualified negative controls and final clean-checkout execution.

## Ownership model

| Role                   | Accountability                                                      |
| ---------------------- | ------------------------------------------------------------------- |
| Product/technical lead | Scope, sequencing, decision closure, production gates               |
| Plane backend owner    | Operation contract, gateway, authorization, audit, idempotency      |
| Hermes owner           | Native tools, Tool Search, Code Mode runtime, approval integration  |
| Security owner         | Threat model, credential boundary, sandbox and authorization review |
| Infrastructure owner   | Containers, limits, observability, retention, incident controls     |
| Quality owner          | Contract tests, permission matrix, failure tests, agent evaluations |
