# Chat Semantic Context Picker

## Current status

| Item | Value |
| --- | --- |
| Phase | Foundation and dependency validation |
| Branch | `chat-semantic-context-picker-core` |
| Owner | Codex: product and technical lead |
| UI ownership | Separate user-managed branch |
| Product validation | Complete through prior use of Cursor and Codex inspector modes |
| Release audience | Single user; no staged rollout required |
| Next milestone | Validate and isolate React Grab primitives |

## Product outcome

A user can point at visible Plane content and attach useful context to an agent message without manually identifying or copying it.

Structured Plane references and current values are preferred. Visual context is a fallback for regions that Plane cannot describe semantically.

## Documents

| Document | Purpose |
| --- | --- |
| [Product specification](./product-spec.md) | Scope, behavior, boundaries, and acceptance criteria |
| [Technical design](./technical-design.md) | Core modules, contracts, freshness, and permissions |
| [Interface design](./interface-design.md) | Alternatives, comparison, and chosen public seam |
| [Delivery plan](./delivery-plan.md) | Milestones, ownership, status, and completion evidence |
| [ADR 0001](./decisions/0001-selection-foundation.md) | Selection foundation and dependency decision |
| [ADR 0002](./decisions/0002-picker-core-interface.md) | Minimal domain-typed picker interface decision |

## Working rules

- This folder is the source of truth for product scope, decisions, status, and integration requirements.
- Milestone status changes belong in `delivery-plan.md`.
- Durable technical decisions receive an ADR under `decisions/`.
- UI work remains outside this branch unless needed to prove a core interface.
- Final completion requires integration with the Plane AI composer when its implementation is available.

## Immediate next actions

1. Inspect the pinned React Grab primitives and their transitive dependencies.
2. Prove point hit-testing, ignored subtrees, cleanup, and portal behavior in Plane.
3. Validate the accepted core contract against the spike evidence.
4. Implement the registry and resolver interfaces with tests.
