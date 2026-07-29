# Chat Semantic Context Picker

## Current status

| Item               | Value                                                          |
| ------------------ | -------------------------------------------------------------- |
| Phase              | M5 server hydration                                            |
| Branch             | `chat-semantic-context-picker-core`                            |
| Owner              | Codex: product and technical lead                              |
| UI ownership       | Separate user-managed branch                                   |
| Product validation | Complete through prior use of Cursor and Codex inspector modes |
| Release audience   | Single user; no staged rollout required                        |
| Next milestone     | Resolve references canonically with server permissions         |

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
| [M3 evidence](./m3-plane-entity-adapter.md)           | Plane store mapping, field allowlist, freshness, and privacy proof      |
| [M4 evidence](./m4-live-editor-adapter.md)            | Live Tiptap/Yjs blocks, ranges, embeds, and privacy proof               |
| [Delivery plan](./delivery-plan.md)                   | Milestones, ownership, status, and completion evidence                  |
| [ADR 0001](./decisions/0001-selection-foundation.md)  | Selection foundation and dependency decision                            |
| [ADR 0002](./decisions/0002-picker-core-interface.md) | Minimal domain-typed picker interface decision                          |
| [ADR 0003](./decisions/0003-live-editor-identity.md)  | Editor block and range identity decision                                |

## Working rules

- This folder is the source of truth for product scope, decisions, status, and integration requirements.
- Milestone status changes belong in `delivery-plan.md`.
- Durable technical decisions receive an ADR under `decisions/`.
- UI work remains outside this branch unless needed to prove a core interface.
- Final completion requires integration with the Plane AI composer when its implementation is available.

## Immediate next actions

1. Map current Django entity retrieval and permission paths.
2. Define the versioned hydration request and result contract.
3. Reauthorize every reference and return canonical current values.
4. Verify workspace roles, private projects and pages, deletion, and mismatch cases.
