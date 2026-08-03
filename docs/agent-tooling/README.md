# Plane Agent Tooling Program

This folder is the durable source of truth for taking Plane's agent-facing tooling from architecture through production.

## Status

| Field                  | Value                                                         |
| ---------------------- | ------------------------------------------------------------- |
| Program status         | Architecture and contract definition                          |
| Current branch         | `codex/agent-tooling-architecture`                            |
| Agent runtime status   | Not implemented                                               |
| Related delivered base | Semantic context picker core merged separately into `preview` |
| Current gate           | Reconcile native domain/runtime ADRs and contract fixtures    |
| Last updated           | 2026-08-03                                                    |

## Outcome

Plane-native agents backed by the forked Hermes kernel can safely perform useful Plane work through native semantic tools and TypeScript Code Mode. External agents continue to use Plane's supported MCP interface. Every path shares Plane authorization, result controls, and append-only audit evidence.

## Documents

| Document                                                                | Purpose                                                              |
| ----------------------------------------------------------------------- | -------------------------------------------------------------------- |
| [Product requirements](./product-requirements.md)                       | Users, outcomes, boundaries, and success measures                    |
| [Architecture](./architecture.md)                                       | Components, trust boundaries, contracts, and runtime behavior        |
| [Delivery plan](./delivery-plan.md)                                     | Workstreams, dependencies, gates, rollout, and ownership             |
| [Non-UI implementation overview](./NON-UI-IMPLEMENTATION-OVERVIEW.md)   | Generated parallel-lane execution map through production rollout     |
| [Decision register](./decision-register.md)                             | Accepted, superseded, and open decisions                             |
| [Release manifest](./RELEASE-MANIFEST.md)                               | Frozen scope, versions, rollout cohort, and numeric gates            |
| [Verification manifest](./VERIFICATION-MANIFEST.md)                     | Independent checks, oracles, negative controls, and evidence         |
| [Requirement coverage](./REQUIREMENT-COVERAGE.md)                       | Criterion and release-row checks, oracles, and evidence              |
| [Evaluation scenarios](./EVALUATION-SCENARIOS.md)                       | Seventy-one behavioral contracts and live-trial allocation           |
| [Planning fixture contract](./EVALUATION-FIXTURE-CONTRACT.md)           | Digest-bound EV-001 through EV-010 inputs and predicates             |
| [Safety evaluation design](./SAFETY-EVALUATION-DESIGN.md)               | Exact EV-011 through EV-030 trial, evidence, fault, and oracle seams |
| [Source inventory](./SOURCE-INVENTORY.md)                               | Observed Plane API, MCP, and Hermes facts                            |
| [Interface design](./INTERFACE-DESIGN.md)                               | Four alternatives and the proposed v1 gateway seam                   |
| [MCP compatibility](./MCP-COMPATIBILITY.md)                             | Complete external-tool disposition and conformance plan              |
| [MCP exact mapping](./MCP-MAPPING-CONTRACT.md)                          | Per-tool branch, SDK edge, route join, and sensitivity contract      |
| [MCP dispositions](./inventories/plane-mcp-v0.2.11-dispositions.md)     | Disposition strategy for all 177 pinned external tools               |
| [Runtime design](./RUNTIME-DESIGN.md)                                   | TypeScript isolate options and proposed Deno boundary                |
| [Gateway wire](./GATEWAY-WIRE.md)                                       | Accepted JSON HTTP adapter and proposed v1 envelope                  |
| [Pilot contracts](./PILOT-CONTRACTS.md)                                 | Proposed normalized schemas for the nine pilot operations            |
| [Durable goal](./GOAL.md)                                               | Finish line, constraints, verifiers, and approval gates              |
| [Worklog](./WORKLOG.md)                                                 | Attempts, evidence, current state, and next action                   |
| [Result](./RESULT.md)                                                   | Completion evidence and remaining risks                              |
| [ADR synthesis](./ADR-SYNTHESIS.md)                                     | Non-normative grounding, arena comparison, and design provenance     |
| [ADR-0001](../decisions/0001-plane-agent-tooling-architecture.md)       | Durable rationale for the overall architecture                       |
| [ADR-0002](../decisions/0002-autonomous-agent-operations.md)            | Supersedes runtime operation approval with autonomous execution      |
| [ADR-0003](../decisions/0003-plane-agent-native-product-boundary.md)    | Plane Agent is the native product abstraction                        |
| [ADR-0004](../decisions/0004-fork-hermes-as-hidden-execution-kernel.md) | Hermes fork is the hidden execution kernel                           |
| [ADR-0005](../decisions/0005-plane-owned-agent-profiles.md)             | Actor identity and versioned behavioral profiles                     |
| [ADR-0006](../decisions/0006-assignment-and-run-lifecycle.md)           | Assignment, run, invocation, outcome, and publication lifecycle      |
| [ADR-0007](../decisions/0007-adaptive-plane-tool-exposure.md)           | Adaptive tool availability and disclosure                            |
| [ADR-0008](../decisions/0008-scoped-memory-and-context.md)              | Proposed scoped memory, context, and file projections                |
| [ADR-0009](../decisions/0009-workflows-and-agent-delegation.md)         | Proposed workflow and delegation separation                          |
| [ADR-0010](../decisions/0010-plane-runtime-contract.md)                 | Proposed Plane-to-Hermes runtime contract                            |

## Source-of-truth rules

- This folder owns the current product and technical plan.
- ADRs preserve decisions that are expensive to reverse.
- The decision register tracks both accepted decisions and unresolved questions.
- `CONTEXT.md` preserves the broader interview history but does not override accepted decisions here.
- The local Freeform board `Plane-runner` (`8208a432-a415-434c-9f06-5731a6185db4`) is the developer's non-normative workplace mind. Ideas become durable only when promoted into this repository.
- Implementation must not begin for a workstream until its entry gate is satisfied.
- Observable interfaces must have contract tests before production rollout.

## Current next decisions

1. Freeze the Plane runtime contract and fixtures across Plane and the Hermes fork.
2. Resolve the proposed memory/context and workflow/delegation governance decisions.
3. Approve the exact operation and external MCP inventory.
4. Complete and approve the release and verification manifests.
