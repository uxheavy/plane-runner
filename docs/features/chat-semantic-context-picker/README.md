# Chat Semantic Context Picker

## Current status

| Item               | Value                                                          |
| ------------------ | -------------------------------------------------------------- |
| Phase              | M3 Plane entity adapters                                       |
| Branch             | `chat-semantic-context-picker-core`                            |
| Owner              | Codex: product and technical lead                              |
| UI ownership       | Separate user-managed branch                                   |
| Product validation | Complete through prior use of Cursor and Codex inspector modes |
| Release audience   | Single user; no staged rollout required                        |
| Next milestone     | Resolve supported Plane entities and allowlisted fields        |

## Product outcome

A user can point at visible Plane content and attach useful context to an agent message without manually identifying or copying it.

Structured Plane references and current values are preferred. Visual context is a fallback for regions that Plane cannot describe semantically.

## Documents

| Document                                              | Purpose                                                                 |
| ----------------------------------------------------- | ----------------------------------------------------------------------- |
| [Product specification](./product-spec.md)            | Scope, behavior, boundaries, and acceptance criteria                    |
| [Active goal](./GOAL.md)                              | Non-UI finish line, verifier, constraints, and approval gates           |
| [Worklog](./WORKLOG.md)                               | Attempts, evidence, current state, and next action                      |
| [Final result](./RESULT.md)                           | Completion proof and UI-branch handoff                                  |
| [Technical design](./technical-design.md)             | Core modules, contracts, freshness, and permissions                     |
| [Interface design](./interface-design.md)             | Alternatives, comparison, and chosen public seam                        |
| [M1 evidence](./m1-selection-foundation.md)           | Pinned dependency, browser proof, bundle proof, and boundary correction |
| [M2 evidence](./m2-core-contracts.md)                 | Versioned contract, registry, lifecycle, browser, and build proof       |
| [Delivery plan](./delivery-plan.md)                   | Milestones, ownership, status, and completion evidence                  |
| [ADR 0001](./decisions/0001-selection-foundation.md)  | Selection foundation and dependency decision                            |
| [ADR 0002](./decisions/0002-picker-core-interface.md) | Minimal domain-typed picker interface decision                          |

## Working rules

- This folder is the source of truth for product scope, decisions, status, and integration requirements.
- Milestone status changes belong in `delivery-plan.md`.
- Durable technical decisions receive an ADR under `decisions/`.
- UI work remains outside this branch unless needed to prove a core interface.
- Final completion requires integration with the Plane AI composer when its implementation is available.

## Immediate next actions

1. Map each supported entity and field to its existing Plane store owner.
2. Define the M3 resolver evidence contract before implementation.
3. Implement current-value and label sources without exposing whole records.
4. Add adapter tests for missing, unloaded, stale, and detached state.
