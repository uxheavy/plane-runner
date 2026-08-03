# Plane Agent ADR Synthesis

## Status

Non-normative design rationale for ADR-0003 through ADR-0010. The ADRs and accepted rows in `decision-register.md` are authoritative.

## Design workspace and source hierarchy

The local Freeform board **Plane-runner**, UUID `8208a432-a415-434c-9f06-5731a6185db4`, is the developer's local **workplace mind**: an exploratory surface for sketches, questions, inventories, and evolving relationships. It is not a repository file, may be unavailable to other contributors, and cannot be the sole source of an implementation decision.

Ideas become durable only when promoted into this repository. Precedence is:

1. Accepted ADRs.
2. Accepted `decision-register.md` rows and integrated `architecture.md` contracts.
3. Proposed ADRs and proposed contract documents.
4. `CONTEXT.md` interview and product-design history.
5. The local Freeform workplace mind and detached research worktrees.

## Cross-repository grounding

Evidence was reconciled with the top-down task before synthesis:

| Repository | Revision inspected                                                               | Role                                                                             |
| ---------- | -------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| Plane      | `416e8b034d99efbfd826f41aa58695ccb0bdefb3` on `codex/agent-tooling-architecture` | Product, durable domain state, authorization, gateway, and ADR authority         |
| Hermes     | `b4f8c491d3452926deb7628edbdb6fe2a85ff576` on clean `main`                       | Execution-kernel donor; no Plane integration exists yet                          |
| Buzz       | `3b8567a05d4c40e667d061666feb7aa7bc38212d` on clean `main`                       | Conversation, ACP, workflow, and UX reference donor; no Plane integration exists |

The Plane branch was 37 commits ahead of and 10 behind local `upstream/preview` during synthesis. Detached Plane worktrees contain useful Hermes-harness, conversation-UX, and MCP/tooling research but are not the decision source of truth. The stale Buzz branch `codex/publish-turn-results` records one useful lesson: internal model completion is insufficient when no useful product event is published.

## Grounded ownership

- Plane owns agent actors, profile versions, assignment contracts, run attempts, runtime-invocation history, conversations, memory and skill definitions, schedules, delegation records, artifacts, outcome submissions, authorization, and audit. It dispatches execution durably to a separate co-located runtime service.
- Hermes supplies model-loop, context-window, retrieval, learning, skill execution, tool-dispatch, transcript/checkpoint, concurrency, and recovery mechanisms behind adapters.
- Buzz supplies design and code evidence but no runtime authority.
- Hermes files are run projections. Plane-governed storage remains authoritative.
- Plane live authorization is the only runtime allow-or-deny decision.
- An evaluator reviews every Agent outcome before a human accepts or returns it; human acceptance remains final.

## Architect arena

Three structurally distinct designs were compared against authority preservation, interface depth, domain modeling, donor provenance, and reader load.

| Candidate | Shape                                                                           | Score |
| --------- | ------------------------------------------------------------------------------- | ----: |
| A         | Plane records plus intent commands and one-function `plane_runtime` contract    | 24/25 |
| B         | Plane-owned run capsule behind public dispatch/observe/cancel runtime interface | 22/25 |
| C         | Outcome-oriented command/event module with one execution-driver seam            | 23/25 |

Candidate A is the base because it most clearly separates existing Plane actor authorization, versioned behavior, assignment/run/outcome lifecycles, product activity, operation audit, and the hidden Hermes kernel.

Grafts:

- From C: name tool configuration as presentation/disclosure rather than capability permission, and sequence implementation as domain transitions, persistence/commands, deterministic runtime adapter, gateway binding, then Hermes adapter.
- From B: separate the persisted frozen run snapshot from each dispatch envelope and support cursor-based bounded event projections. Indeterminate operations remain subject to reconciliation and are never blindly replayed in any run.
- From top-down review: distinguish assignment commission from outcome submission; let a Plane run span kernel sessions; preserve governed Hermes-compatible file projections and agent-scoped learning; require an explicit visible terminal product event.

Rejected:

- Hermes sessions, profiles, chat identity, or filesystem as durable Plane state.
- A broad Plane dependency on `AIAgent` or Hermes process globals.
- An in-process Plane API dependency on the runtime adapter or a run lifecycle tied to one container.
- Buzz as a production runtime dependency.
- A universal mutation tool or profile-owned operation allowlist.
- One outcome aggregate that collapses actor, profile, assignment, run, and submission lifecycles.
- Event sourcing, saved workflow graphs, or open-ended delegation before the single-agent slice proves the domain spine.

## Synthesis decision

ADRs 0003 through 0010 are Accepted. The accepted decisions require governed private memory and skills, dynamic planning and delegation without saved workflows, the versioned runtime seam, and evaluator review before human acceptance or return, with human acceptance final. `APPROVAL-MANIFEST.md` is the single implementation gate; no runtime, application, or verification implementation begins until it is explicitly approved.

The first implementation slice should prove one Plane Agent actor, one profile version, one assignment contract, one immutable run snapshot, one or more invocation envelopes through a deterministic adapter, one visible terminal outcome event, evaluator review, and human acceptance or return. Only then should the Hermes adapter be introduced.

## Verification record

- Read all three arena candidates end to end.
- Cross-judge selected Candidate A and identified bounded grafts and rejections.
- Reconciled current Plane, Hermes, and Buzz heads and active worktrees through the top-down task.
- Screened the synthesis for shallow modules, information leakage, temporal decomposition, and pass-through interfaces.
- Documentation and repository checks are recorded in the final task handoff after execution.
