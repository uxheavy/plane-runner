# Plane Agent Tooling Program

This folder is the durable source of truth for taking Plane's agent-facing tooling from architecture through production.

## Status

| Field                 | Value                                                |
| --------------------- | ---------------------------------------------------- |
| Program status        | Architecture definition                              |
| Current branch        | `codex/agent-tooling-architecture`                   |
| Implementation status | Not started                                          |
| Current gate          | Approve the first pilot scope and operation contract |
| Last updated          | 2026-07-29                                           |

## Outcome

Plane-native Hermes agents can safely perform useful Plane work through native semantic tools and TypeScript Code Mode. External agents continue to use Plane's supported MCP interface. Every path shares Plane authorization, approval policy, result controls, and append-only audit evidence.

## Documents

| Document                                                          | Purpose                                                       |
| ----------------------------------------------------------------- | ------------------------------------------------------------- |
| [Product requirements](./product-requirements.md)                 | Users, outcomes, boundaries, and success measures             |
| [Architecture](./architecture.md)                                 | Components, trust boundaries, contracts, and runtime behavior |
| [Delivery plan](./delivery-plan.md)                               | Workstreams, dependencies, gates, rollout, and ownership      |
| [Decision register](./decision-register.md)                       | Accepted, superseded, and open decisions                      |
| [ADR-0001](../decisions/0001-plane-agent-tooling-architecture.md) | Durable rationale for the overall architecture                |

## Source-of-truth rules

- This folder owns the current product and technical plan.
- ADRs preserve decisions that are expensive to reverse.
- The decision register tracks both accepted decisions and unresolved questions.
- `CONTEXT.md` preserves the broader interview history but does not override accepted decisions here.
- Implementation must not begin for a workstream until its entry gate is satisfied.
- Observable interfaces must have contract tests before production rollout.

## Current next decisions

1. Select the first pilot scope.
2. Select the initial eager native tools.
3. Approve the first supported operation boundary.
4. Define measurable production targets.
