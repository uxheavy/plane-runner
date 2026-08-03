# ADR-0009: Separate declared workflows from agent delegation

## Status

Proposed

## Date

2026-08-03

## Context

The Freeform design considers a central delegator, delegation skills embedded in manager profiles, and a new workflow unit. These solve different problems. A workflow expresses declared control flow chosen in advance; delegation is a runtime judgment that creates responsibility, authorization, context, cost, and failure-handling relationships between actors.

Combining them would make deterministic automation depend on model judgment and turn delegation into an implicit workflow engine.

## Decision

Treat Workflow and Delegation as separate Plane concepts.

- A **workflow** has explicit, versioned, auditable control-flow semantics chosen in advance and is invocable by authorized humans or agents. Its agent, external-system, and time-varying steps may still produce nondeterministic results.
- **delegation** is an agent behavior that creates a child assignment contract for another agent or human under explicit scope, budget, lineage, and completion semantics.

Plane owns workflow definitions, schedule/control state, delegated assignment records, lineage, and outcomes. Hermes may execute workflow steps, schedules, or delegated runtime invocations behind Plane adapters; those mechanisms do not own the durable definitions or control state.

Do not require a universal Delegator agent. A specialized delegator may later exist as an agent profile, while manager profiles may receive delegation behavior and tools through skills and tool presentation.

V1 does not add a general workflow-graph DSL and does not require open-ended delegation. The first vertical slice proves one Plane Agent completing one assigned outcome before either surface expands.

## Alternatives considered

### Route every assignment through one Delegator agent

- Benefit: one place for routing behavior.
- Cost: central bottleneck, hidden policy, and single-agent failure domain.
- Rejected as a runtime requirement: delegation can be an optional behavior, tool, and profile.

### Encode all delegation in skills

- Benefit: flexible and close to role behavior.
- Cost: lacks durable product-level lineage and lifecycle by itself.
- Rejected as the complete design: skills may guide decisions but Plane records delegation.

### Represent workflows as agents

- Benefit: one execution abstraction.
- Cost: declared control flow becomes implicit model behavior and harder to reproduce.
- Rejected: workflows and agents have different guarantees.

## Consequences

- Workflow execution can be tested independently from model behavior.
- Delegated assignments preserve parent-child lineage and independent authorization.
- A future Delegator is a profile, not privileged infrastructure.
- Detailed workflow and delegation schemas remain deferred until the single-agent lifecycle is proven.
