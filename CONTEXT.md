# Agent-Native Plane: Decision Context

## Intended Outcome

Build an additive, agent-native version of Plane that combines:

| Source       | Contribution to Plane                                                                                   |
| ------------ | ------------------------------------------------------------------------------------------------------- |
| Plane        | Product shell, work graph, permissions, APIs, Postgres data, and system of record                       |
| Buzz         | Reference and code donor for human-agent conversations, threads, teams, transcripts, and inspectability |
| Hermes Agent | Execution harness, tools, delegation, memory, skills, learning loop, scheduling, and model portability  |

The target experience is: discuss real work inside Plane, approve a proposed agent team, let that team coordinate and execute, inspect its work in Plane, and accept the resulting outcome.

## Importance Scoring

Replace each `__/10` placeholder with a score:

| Score | Meaning                                            |
| ----- | -------------------------------------------------- |
| 1–3   | Useful, but negotiable                             |
| 4–6   | Material preference                                |
| 7–8   | Strong product or architecture constraint          |
| 9–10  | Defining principle; changing it alters the product |

## Product Boundaries

| ID  | Confirmed decision                                                                                                                                                                                                                                                                                                     | Importance |
| --- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| P1  | Plane remains the product, control plane, work graph, and source of truth.                                                                                                                                                                                                                                             | 7/10       |
| P2  | Buzz is a reference implementation and code donor. Do not deploy its Nostr relay as Plane's canonical backend.                                                                                                                                                                                                         | 8/10       |
| P3  | Hermes capabilities must feel native inside Plane; users should not experience a separate Hermes product.                                                                                                                                                                                                              | 8/10       |
| P4  | Existing Plane installations receive an additive, compatible upgrade through forward migrations and feature flags.                                                                                                                                                                                                     | 7/10       |
| P5  | The initial audience is all knowledge teams, not only software teams.                                                                                                                                                                                                                                                  | 10/10      |
| P6  | The shared job is to drive an assigned outcome to done, not merely chat, answer questions, or maintain project hygiene.                                                                                                                                                                                                | 10/10      |
| P7  | Reuse Plane’s existing external-link foundation. Every external artifact must remain directly accessible from Plane. Where a provider integration exists, Plane should upgrade the link into a typed, synchronized external reference with status, selected evidence, backlink, permissions, and agent-run provenance. | 10/10      |
| P8  | The first end-to-end proof is conversation to completed project slice, demonstrated with a product-launch operations project.                                                                                                                                                                                          | 8/10       |

## Conversation and Artifact Model

| ID  | Confirmed decision                                                                                                                                                                                                                                                                                           | Importance |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------- |
| C1  | Conversation is contextual: every Plane entity can expose its persistent conversation in a sidebar.                                                                                                                                                                                                          | 7/10       |
| C2  | Each entity has one canonical main conversation with branchable message threads.                                                                                                                                                                                                                             | 6/10       |
| C3  | General conversations may exist without an initial Plane entity and later create or link projects, pages, goals, modules, cycles, and work items.                                                                                                                                                            | 10/10      |
| C4  | Existing work-item comments converge into the unified conversation while preserving authorship, timestamps, reactions, permissions, and links.                                                                                                                                                               | 8/10       |
| C5  | Conversation is the primary collaboration surface. Each agent's role or persona determines how it communicates; Plane imposes no universal human-like voice. Technical run detail remains available through a secondary inspectable view.                                                                    | \_\_/10    |
| C6  | Agent-produced plans, research, decisions, approvals, and deliverables become Plane-native work artifacts.                                                                                                                                                                                                   | \_\_/10    |
| C7  | Current-object context is always available. Additional permitted project context is retrieved on demand with citations rather than loading all parent history.                                                                                                                                               | \_\_/10    |
| C8  | Opening a Plane entity normally shows that entity's canonical conversation in the contextual sidecar. A user may pin one conversation so it remains temporarily persistent while the main Plane surface browses other entities. Unpinning returns the sidecar to the currently viewed entity's conversation. | \_\_/10    |
| C9  | When a conversation is pinned, the interface clearly distinguishes browse context from conversation context, such as `Viewing B` and `Conversation A`.                                                                                                                                                       | \_\_/10    |

## Agent Identity and Team Model

| ID  | Confirmed decision                                                                                                                                              | Importance |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| A1  | Named agents are durable Plane teammates with profiles, memberships, permissions, memory, skills, and attributable history.                                     | \_\_/10    |
| A2  | Several agents may share visible ownership of work, with a designated coordinator responsible for delegation, reconciliation, and escalation.                   | \_\_/10    |
| A3  | A coordinator may design any needed agent team. A human previews the complete team manifest and explicitly deploys it.                                          | \_\_/10    |
| A4  | Coordinator-created agents persist after the slice and hibernate automatically when idle, preserving identity and learning without consuming runtime resources. | \_\_/10    |
| A5  | Agent autonomy is graduated by project and capability: observe, suggest, act with approval, or act automatically.                                               | \_\_/10    |
| A6  | The coordinator may declare agent execution complete, but submits the outcome to a human for formal acceptance.                                                 | \_\_/10    |
| A7  | Agents use dedicated scoped identities and credentials where supported. Delegated human credentials are explicit and temporary.                                 | \_\_/10    |
| A8  | Admins govern templates, allowed models, tools, policies, and providers.                                                                                        | \_\_/10    |
| A9  | Workspace admins configure model providers or local models; agent templates operate within those policies.                                                      | \_\_/10    |
| A10 | Wake-up triggers include assignments, mentions, coordinator delegation, approved schedules, and governed Plane events. Ambient monitoring is opt-in.            | \_\_/10    |

## Memory, Skills, and Learning

| ID  | Confirmed decision                                                                                                                                                                                                                                           | Importance |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------- |
| M1  | Memory is layered and scoped: organization policy, project knowledge, agent memory and skills, and private user preferences remain distinct.                                                                                                                 | \_\_/10    |
| M2  | Preserve Hermes's automatic learning loop: post-run memory capture, skill creation and improvement, and recoverable curation or archival.                                                                                                                    | \_\_/10    |
| M3  | Automatically learned skills remain local to the agent until a human promotes them into a shared template.                                                                                                                                                   | \_\_/10    |
| M4  | Durable agent memory and skills live in Plane-governed storage; disposable run containers do not become the system of record. Plane can materialize lossless Hermes-compatible files such as `MEMORY.md`, `USER.md`, and skill packages for agent execution. | \_\_/10    |

## Data, Audit, and Runtime Architecture

| ID  | Confirmed decision                                                                                                                                                                                                       | Importance |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------- |
| T1  | Plane/Postgres remains authoritative. Buzz-style collaboration is implemented as native Plane domain data and events.                                                                                                    | \_\_/10    |
| T2  | Messages, agent actions, approvals, and tool receipts are append-only. Authorized redaction hides content while retaining the redaction event.                                                                           | \_\_/10    |
| T3  | Each run retains a reproducible audit envelope: instructions, context references, model and skill versions, tool inputs and outputs, approvals, artifacts, costs, and concise decision summaries, with secrets redacted. | \_\_/10    |
| T4  | Agent execution runs in a separate service co-located with Plane on the same VPS or local deployment.                                                                                                                    | \_\_/10    |
| T5  | Tool execution uses a disposable container per run with explicit mounts, network policy, secrets, limits, and cleanup.                                                                                                   | \_\_/10    |
| T6  | The initial non-Plane tool foundation is browser, files, sandboxed terminal, web research, and MCP connectors.                                                                                                           | \_\_/10    |

## Plane MCP and Code Mode

| ID  | Confirmed decision                                                                                                                  | Importance |
| --- | ----------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| X1  | Agents access Plane through an MCP server, never through direct database access.                                                    | \_\_/10    |
| X2  | The MCP catalog exposes semantic Plane operations plus searchable resources rather than mirroring every REST endpoint.              | \_\_/10    |
| X3  | Adopt Cloudflare's Code Mode `search` and `execute` pattern while keeping execution self-hosted.                                    | \_\_/10    |
| X4  | Model-written TypeScript executes inside the local disposable run container.                                                        | \_\_/10    |
| X5  | Authentication remains in host callbacks. Every operation passes through Plane authorization, approval policy, and audit recording. | \_\_/10    |

## Decisions Deliberately Deferred

| ID  | Open decision                                                                                          | Current constraint                                                                                                                                                                                                                                                                                   | Importance |
| --- | ------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| D1  | Extend `apps/live` into a modular conversation gateway or create a dedicated real-time service.        | Requires a focused architecture session.                                                                                                                                                                                                                                                             | \_\_/10    |
| D2  | Consume Hermes as a pinned upstream core behind an adapter or maintain a Plane-specific fork.          | Decide from a technical evaluation, not preference.                                                                                                                                                                                                                                                  | \_\_/10    |
| D3  | Define per-slice model, time, compute, tool, and concurrency budgets.                                  | Reuse Hermes/Buzz low-level limits first; product policy is premature.                                                                                                                                                                                                                               | \_\_/10    |
| D4  | Define the exact Plane conversation/event schema and migration mechanics.                              | Must preserve existing comments and additive upgrades.                                                                                                                                                                                                                                               | \_\_/10    |
| D5  | Define the detailed Code Mode catalog, sandbox API, approval interception, and replay semantics.       | TypeScript, local execution, semantic MCP, and host-side authorization are fixed.                                                                                                                                                                                                                    | \_\_/10    |
| D6  | Define the final north-star metric.                                                                    | Desired outcome is inspectable, self-coordinated agent work that a human accepts as done.                                                                                                                                                                                                            | \_\_/10    |
| D7  | Decide the canonical representation and synchronization rules for content shared by people and agents. | Plane currently stores structured rich text; agents work naturally with files. Preserve Plane-specific structure and a lossless raw source where needed, while exposing deterministic Markdown file projections to agents. Do not assume that every Plane object must become a canonical `.md` file. | \_\_/10    |
| D8  | Resolve the conversation sidecar's layout relationship with existing work-item surfaces.               | Work-item detail already has a right-side properties rail; comments appear in the mixed Activity feed; side-peek is a 50%-width overlay containing details, widgets, properties, and Activity sequentially. Do not add a second permanent right rail without redesigning these relationships.        | \_\_/10    |
| D9  | Define how an active conversation becomes aware of human-made entity changes.                          | Candidate: compact, collapsible activity receipts showing actor and semantic change summary, with expandable before-and-after detail. Avoid converting every field mutation into a normal chat message.                                                                                              | \_\_/10    |

## Dedicated Design Tasks

| Design task             | Scope                                                                                                  | Status       |
| ----------------------- | ------------------------------------------------------------------------------------------------------ | ------------ |
| Real-time topology      | Plane Live versus a dedicated conversation service                                                     | Created      |
| Hermes boundary         | Adapter versus fork, persistence, lifecycle, and recovery                                              | Created      |
| Code Mode MCP           | Local TypeScript search/execute architecture                                                           | Created      |
| Agent governance        | Capabilities, resource controls, sprawl, revocation, and retention                                     | Created      |
| Conversation navigation | Sidecar layout, single-conversation pinning, browse-versus-conversation context, and activity receipts | In interview |

## Working Constraints

| Constraint           | Value                                                                                             |
| -------------------- | ------------------------------------------------------------------------------------------------- |
| Current Plane branch | `add-agents`                                                                                      |
| Implementation state | No implementation authorized by this interview                                                    |
| Decision process     | Resolve architecture interactively; ask one material decision at a time                           |
| Reuse preference     | Reuse engines, algorithms, components, and tests where boundaries fit; avoid unnecessary rewrites |
