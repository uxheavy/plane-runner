# ADR-0003: Plane Agent is a native Plane product

## Status

Accepted

## Date

2026-08-03

## Context

Plane needs agents that behave like teammates inside normal Plane workflows. Treating Hermes as a visible adjacent product would expose a second identity model, vocabulary, configuration surface, and interaction model. Users would have to understand both Plane and Hermes even though their intent is to assign an outcome in Plane and review the result there.

The product boundary must remain stable even if the execution kernel changes later.

## Decision

Plane Agent is the product abstraction. It is a first-class Plane actor whose durable identity, memberships, roles, object permissions, credential, behavioral profiles, assignment contracts, run attempts, conversations, outcome submissions, artifacts, and history are owned by Plane.

Users create, configure, assign, observe, and review agents entirely through Plane. Model-facing concepts use Plane vocabulary and natural Plane workflows. Hermes is not exposed as the agent's identity, user experience, or configuration contract.

Buzz may inform conversation, ACP, and inspectability design, but it is a reference and code donor rather than a Plane runtime dependency or source of durable product state.

## Alternatives considered

### Embed the Hermes product inside Plane

- Benefit: preserves more upstream behavior and UI assumptions.
- Cost: creates two overlapping product models and leaks implementation details.
- Rejected: it does not produce a native Plane teammate.

### Keep Plane and Hermes as loosely integrated products

- Benefit: stronger implementation independence.
- Cost: assignments, permissions, conversations, and run state would cross a visible product seam.
- Rejected: the seam would be borne by users instead of the implementation.

## Consequences

- Plane owns all durable user-facing agent concepts and contracts.
- Hermes may be replaced without migrating the Plane Agent product model.
- Buzz may be replaced or ignored without migrating the Plane Agent product model.
- Hermes-specific names and configuration do not appear in Plane-facing APIs or UI.
- Native Plane workflows, not upstream Hermes defaults, determine the system prompt and tool surface.
