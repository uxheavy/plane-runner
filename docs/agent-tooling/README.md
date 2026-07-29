# Plane Agent Tooling Program

This folder is the durable source of truth for taking Plane's agent-facing tooling from architecture through production.

## Status

| Field                 | Value                                         |
| --------------------- | --------------------------------------------- |
| Program status        | Goal-backed delivery                          |
| Current branch        | `codex/agent-tooling-architecture`            |
| Implementation status | Not started                                   |
| Current gate          | Freeze the release and verification manifests |
| Last updated          | 2026-07-29                                    |

## Outcome

Plane-native Hermes agents can safely perform useful Plane work through native semantic tools and TypeScript Code Mode. External agents continue to use Plane's supported MCP interface. Every path shares Plane authorization, result controls, and append-only audit evidence.

## Documents

| Document                                                            | Purpose                                                         |
| ------------------------------------------------------------------- | --------------------------------------------------------------- |
| [Product requirements](./product-requirements.md)                   | Users, outcomes, boundaries, and success measures               |
| [Architecture](./architecture.md)                                   | Components, trust boundaries, contracts, and runtime behavior   |
| [Delivery plan](./delivery-plan.md)                                 | Workstreams, dependencies, gates, rollout, and ownership        |
| [Decision register](./decision-register.md)                         | Accepted, superseded, and open decisions                        |
| [Release manifest](./RELEASE-MANIFEST.md)                           | Frozen scope, versions, rollout cohort, and numeric gates       |
| [Verification manifest](./VERIFICATION-MANIFEST.md)                 | Independent checks, oracles, negative controls, and evidence    |
| [Evaluation scenarios](./EVALUATION-SCENARIOS.md)                   | Seventy-one behavioral contracts and live-trial allocation      |
| [Source inventory](./SOURCE-INVENTORY.md)                           | Observed Plane API, MCP, and Hermes facts                       |
| [Interface design](./INTERFACE-DESIGN.md)                           | Four alternatives and the proposed v1 gateway seam              |
| [MCP compatibility](./MCP-COMPATIBILITY.md)                         | Complete external-tool disposition and conformance plan         |
| [MCP dispositions](./inventories/plane-mcp-v0.2.11-dispositions.md) | Disposition strategy for all 177 pinned external tools          |
| [Runtime design](./RUNTIME-DESIGN.md)                               | TypeScript isolate options and proposed Deno boundary           |
| [Gateway wire](./GATEWAY-WIRE.md)                                   | Accepted JSON HTTP adapter and proposed v1 envelope             |
| [Pilot contracts](./PILOT-CONTRACTS.md)                             | Proposed normalized schemas for the nine pilot operations       |
| [Durable goal](./GOAL.md)                                           | Finish line, constraints, verifiers, and approval gates         |
| [Worklog](./WORKLOG.md)                                             | Attempts, evidence, current state, and next action              |
| [Result](./RESULT.md)                                               | Completion evidence and remaining risks                         |
| [ADR-0001](../decisions/0001-plane-agent-tooling-architecture.md)   | Durable rationale for the overall architecture                  |
| [ADR-0002](../decisions/0002-autonomous-agent-operations.md)        | Supersedes runtime operation approval with autonomous execution |

## Source-of-truth rules

- This folder owns the current product and technical plan.
- ADRs preserve decisions that are expensive to reverse.
- The decision register tracks both accepted decisions and unresolved questions.
- `CONTEXT.md` preserves the broader interview history but does not override accepted decisions here.
- Implementation must not begin for a workstream until its entry gate is satisfied.
- Observable interfaces must have contract tests before production rollout.

## Current next decisions

1. Select the initial eager native tools.
2. Approve the exact operation and external MCP inventory.
3. Complete and approve the release manifest.
4. Complete and approve the verification manifest.
