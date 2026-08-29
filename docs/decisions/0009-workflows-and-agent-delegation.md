# ADR-0009: Use dynamic planning and delegation, not saved workflows

## Status

Accepted

## Date

2026-08-03

## Context

The product needs a dedicated delegator that can plan each case and route unclaimed work, but it does not need a saved workflow-definition product. A dynamic plan creates responsibility, authorization, context, cost, and failure-handling relationships at assignment time. Encoding that plan as a reusable definition would create a second product lane and make the target larger than the required Plane Agent model.

Approved schedules are still useful triggers, but they create normal assignments and runs through the ordinary Plane lifecycle. They do not store or execute versioned workflow definitions.

## Decision

Do not create a saved or versioned workflow-definition system in this scope. Do not add a workflow-graph DSL or a workflow-definition delivery lane.

- A **dynamic plan** is a case-specific decision made at assignment time; it is not a saved definition and is recorded as rationale and normal assignment lineage.
- **delegation** is a capability of the dedicated `delegator` role. It creates normal child assignment contracts for another agent or human under explicit scope, budget, lineage, authorization, and completion semantics.

Plane owns schedule/control state, delegated assignment records, dynamic-plan rationale, lineage, and outcomes. The execution kernel may execute schedules or delegated runtime invocations behind Plane adapters; it does not own durable definitions or control state.

The dedicated delegator dynamically plans work, automatically assigns unclaimed work to humans or agents, and records why each assignment was made. Worker and ordinary specialist roles do not freely delegate merely because they have skills or discoverable operations. Delegator actions remain subject to live Plane permissions and the same assignment/run/audit lifecycle as human-created work.

The first vertical slice proves one Plane Agent completing one assigned outcome. Dynamic planning, schedule-triggered normal assignments, and delegated assignment breadth complete the non-UI program only after the single-agent lifecycle and full Plane operation/action coverage are verified.

## Alternatives considered

### Add a saved workflow-definition product

- Benefit: reusable declared control flow.
- Cost: adds a second product model and a versioned execution lane that is not required for case-specific planning.
- Rejected: the delegator plans each case dynamically and creates ordinary assignments.

### Let every agent delegate freely

- Benefit: simple local behavior.
- Cost: uncontrolled assignment fan-out and unclear accountability.
- Rejected: only the dedicated delegator role owns dynamic routing; specialist agents execute their assignments.

### Encode all delegation only in skills

- Benefit: flexible and close to role behavior.
- Cost: lacks durable product-level rationale and assignment lineage by itself.
- Rejected as the complete design: skills may guide decisions, but Plane records delegation as normal assignments.

## Consequences

- Dynamic planning is tested as assignment creation and rationale, not as workflow replay.
- Delegated assignments preserve parent-child lineage and independent authorization.
- The dedicated delegator is a role in the one Agent model, not privileged infrastructure.
- Approved schedules create ordinary assignments and runs, so schedule recovery uses the existing lifecycle.
