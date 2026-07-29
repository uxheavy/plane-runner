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

Replace each `_/10` placeholder with a score:

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
| C5  | Conversation is the primary collaboration surface. Each agent's role or persona determines how it communicates; Plane imposes no universal human-like voice. Technical run detail remains available through a secondary inspectable view.                                                                    | \_/10      |
| C6  | Agent-produced plans, research, decisions, approvals, and deliverables become Plane-native work artifacts.                                                                                                                                                                                                   | \_/10      |
| C7  | Current-object context is always available. Additional permitted project context is retrieved on demand with citations rather than loading all parent history.                                                                                                                                               | \_/10      |
| C8  | Opening a Plane entity normally shows that entity's canonical conversation in the contextual sidecar. A user may pin one conversation so it remains temporarily persistent while the main Plane surface browses other entities. Unpinning returns the sidecar to the currently viewed entity's conversation. | \_/10      |
| C9  | When a conversation is pinned, the interface clearly distinguishes browse context from conversation context, such as `Viewing B` and `Conversation A`.                                                                                                                                                       | \_/10      |

## Agent Identity and Team Model

| ID  | Confirmed decision                                                                                                                                              | Importance |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| A1  | Named agents are durable Plane teammates with profiles, memberships, permissions, memory, skills, and attributable history.                                     | \_/10      |
| A2  | Several agents may share visible ownership of work, with a designated coordinator responsible for delegation, reconciliation, and escalation.                   | \_/10      |
| A3  | A coordinator may design any needed agent team. A human previews the complete team manifest and explicitly deploys it.                                          | \_/10      |
| A4  | Coordinator-created agents persist after the slice and hibernate automatically when idle, preserving identity and learning without consuming runtime resources. | \_/10      |
| A5  | Agent autonomy is graduated by project and capability: observe, suggest, or act automatically within configured scope.                                          | \_/10      |
| A6  | The coordinator may declare agent execution complete, but submits the outcome to a human for formal acceptance.                                                 | \_/10      |
| A7  | Agents use dedicated scoped identities and credentials where supported. Delegated human credentials are explicit and temporary.                                 | \_/10      |
| A8  | Admins govern templates, allowed models, tools, policies, and providers.                                                                                        | \_/10      |
| A9  | Workspace admins configure model providers or local models; agent templates operate within those policies.                                                      | \_/10      |
| A10 | Wake-up triggers include assignments, mentions, coordinator delegation, approved schedules, and governed Plane events. Ambient monitoring is opt-in.            | \_/10      |

## Memory, Skills, and Learning

| ID  | Confirmed decision                                                                                                                                                                                                                                           | Importance |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------- |
| M1  | Memory is layered and scoped: organization policy, project knowledge, agent memory and skills, and private user preferences remain distinct.                                                                                                                 | \_/10      |
| M2  | Preserve Hermes's automatic learning loop: post-run memory capture, skill creation and improvement, and recoverable curation or archival.                                                                                                                    | \_/10      |
| M3  | Automatically learned skills remain local to the agent until a human promotes them into a shared template.                                                                                                                                                   | \_/10      |
| M4  | Durable agent memory and skills live in Plane-governed storage; disposable run containers do not become the system of record. Plane can materialize lossless Hermes-compatible files such as `MEMORY.md`, `USER.md`, and skill packages for agent execution. | \_/10      |

## Data, Audit, and Runtime Architecture

| ID  | Confirmed decision                                                                                                                                                                                            | Importance |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| T1  | Plane/Postgres remains authoritative. Buzz-style collaboration is implemented as native Plane domain data and events.                                                                                         | \_/10      |
| T2  | Messages, agent actions, team-deployment decisions, outcome-acceptance decisions, and tool receipts are append-only. Authorized redaction hides content while retaining the redaction event.                  | \_/10      |
| T3  | Each run retains a reproducible audit envelope: instructions, context references, model and skill versions, tool inputs and outputs, artifacts, costs, and concise decision summaries, with secrets redacted. | \_/10      |
| T4  | Agent execution runs in a separate service co-located with Plane on the same VPS or local deployment.                                                                                                         | \_/10      |
| T5  | Tool execution uses a disposable container per run with explicit mounts, network policy, secrets, limits, and cleanup.                                                                                        | \_/10      |
| T6  | The initial non-Plane tool foundation is browser, files, sandboxed terminal, web research, and MCP connectors.                                                                                                | \_/10      |

## Plane MCP and Code Mode

| ID  | Confirmed decision                                                                                                     | Importance |
| --- | ---------------------------------------------------------------------------------------------------------------------- | ---------- |
| X1  | Agents access Plane through an MCP server, never through direct database access.                                       | \_/10      |
| X2  | The MCP catalog exposes semantic Plane operations plus searchable resources rather than mirroring every REST endpoint. | \_/10      |
| X3  | Adopt Cloudflare's Code Mode `search` and `execute` pattern while keeping execution self-hosted.                       | \_/10      |
| X4  | Model-written TypeScript executes inside the local disposable run container.                                           | \_/10      |
| X5  | Authentication remains in host callbacks. Every operation passes through Plane authorization and audit recording.      | \_/10      |

## Decisions Deliberately Deferred

| ID  | Open decision                                                                                          | Current constraint                                                                                                                                                                                                                                                                                   | Importance |
| --- | ------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| D1  | Extend `apps/live` into a modular conversation gateway or create a dedicated real-time service.        | Requires a focused architecture session.                                                                                                                                                                                                                                                             | \_/10      |
| D2  | Consume Hermes as a pinned upstream core behind an adapter or maintain a Plane-specific fork.          | Decide from a technical evaluation, not preference.                                                                                                                                                                                                                                                  | \_/10      |
| D3  | Define per-slice model, time, compute, tool, and concurrency budgets.                                  | Reuse Hermes/Buzz low-level limits first; product policy is premature.                                                                                                                                                                                                                               | \_/10      |
| D4  | Define the exact Plane conversation/event schema and migration mechanics.                              | Must preserve existing comments and additive upgrades.                                                                                                                                                                                                                                               | \_/10      |
| D5  | Define the detailed Code Mode catalog, sandbox API, idempotency, and replay semantics.                 | TypeScript, local execution, semantic MCP, and host-side authorization are fixed.                                                                                                                                                                                                                    | \_/10      |
| D6  | Define the final north-star metric.                                                                    | Desired outcome is inspectable, self-coordinated agent work that a human accepts as done.                                                                                                                                                                                                            | \_/10      |
| D7  | Decide the canonical representation and synchronization rules for content shared by people and agents. | Plane currently stores structured rich text; agents work naturally with files. Preserve Plane-specific structure and a lossless raw source where needed, while exposing deterministic Markdown file projections to agents. Do not assume that every Plane object must become a canonical `.md` file. | \_/10      |
| D8  | Resolve the conversation sidecar's layout relationship with existing work-item surfaces.               | Work-item detail already has a right-side properties rail; comments appear in the mixed Activity feed; side-peek is a 50%-width overlay containing details, widgets, properties, and Activity sequentially. Do not add a second permanent right rail without redesigning these relationships.        | \_/10      |
| D9  | Define how an active conversation becomes aware of human-made entity changes.                          | Candidate: compact, collapsible activity receipts showing actor and semantic change summary, with expandable before-and-after detail. Avoid converting every field mutation into a normal chat message.                                                                                              | \_/10      |

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
| Current Plane branch | `codex/agent-tooling-architecture`                                                                |
| Implementation state | No implementation authorized by this interview                                                    |
| Decision process     | Resolve architecture interactively; ask one material decision at a time                           |
| Reuse preference     | Reuse engines, algorithms, components, and tests where boundaries fit; avoid unnecessary rewrites |

## Plane Tooling Architecture Interview Ledger

This ledger supersedes conflicting assumptions in the earlier `Plane MCP and Code Mode` section.

### Confirmed Decisions

| ID   | Confirmed decision                                                                                    | Importance |
| ---- | ----------------------------------------------------------------------------------------------------- | ---------- |
| PX1  | External agents access Plane through MCP.                                                             | \_/10      |
| PX2  | Plane's existing Python MCP server remains supported for external clients.                            | \_/10      |
| PX3  | The existing Python MCP server is the compatibility interface for external agent ecosystems.          | \_/10      |
| PX4  | Plane-native Hermes agents access Plane through native Hermes tools.                                  | \_/10      |
| PX5  | Plane-native Hermes agents receive direct semantic Plane tools.                                       | \_/10      |
| PX6  | Plane-native Hermes agents receive native Code Mode tools.                                            | \_/10      |
| PX7  | Common Plane operations are exposed as direct tools.                                                  | \_/10      |
| PX8  | Direct tools are an ergonomic convenience.                                                            | \_/10      |
| PX9  | Direct tools do not define a separate security tier.                                                  | \_/10      |
| PX10 | Code Mode exposes a documentation discovery surface.                                                  | \_/10      |
| PX11 | Code Mode exposes a searchable operation catalog.                                                     | \_/10      |
| PX12 | Code Mode exposes TypeScript execution over supported Plane operations.                               | \_/10      |
| PX13 | The operation catalog covers the complete supported agent-facing Plane API.                           | \_/10      |
| PX14 | The searchable operation catalog is identical for every Plane identity.                               | \_/10      |
| PX15 | Catalog visibility does not prove that an identity may execute an operation.                          | \_/10      |
| PX16 | Plane's live authorization model decides whether each operation may execute.                          | \_/10      |
| PX17 | Plane workspace membership contributes to operation authorization.                                    | \_/10      |
| PX18 | Plane project roles contribute to operation authorization.                                            | \_/10      |
| PX19 | Plane object-level permissions contribute to operation authorization.                                 | \_/10      |
| PX20 | The tooling layer does not maintain a second operation allowlist that duplicates Plane authorization. | \_/10      |
| PX21 | Plane-native agents act through dedicated Plane identities.                                           | \_/10      |
| PX22 | Credentials remain in trusted host callbacks.                                                         | \_/10      |
| PX23 | Model-written code never receives Plane credentials.                                                  | \_/10      |
| PX24 | Every Plane tool path crosses one Plane Operation Gateway.                                            | \_/10      |
| PX25 | Native direct tools cross the Plane Operation Gateway.                                                | \_/10      |
| PX26 | Native Code Mode operations cross the Plane Operation Gateway.                                        | \_/10      |
| PX27 | External MCP operations cross the Plane Operation Gateway.                                            | \_/10      |
| PX28 | Agents never access Plane's database directly.                                                        | \_/10      |
| PX29 | Plane authorization is evaluated for every operation.                                                 | \_/10      |
| PX30 | Plane authorization is the final runtime allow-or-deny decision for agent operations.                 | \_/10      |
| PX31 | Each inner Code Mode operation is independently authorized.                                           | \_/10      |
| PX32 | Authorized agent operations execute without a human-confirmation state.                               | \_/10      |
| PX33 | Every operation produces append-only audit evidence.                                                  | \_/10      |
| PX34 | Code Mode execution is self-hosted.                                                                   | \_/10      |
| PX35 | Model-written TypeScript runs inside the disposable container assigned to its agent run.              | \_/10      |
| PX36 | The existing Python MCP tool contracts inform the native direct-tool design.                          | \_/10      |
| PX37 | Existing Python MCP tool names may be preserved when they improve compatibility.                      | \_/10      |
| PX38 | External MCP clients retain OAuth or personal-access-token authentication.                            | \_/10      |
| PX39 | Plane agents execute authorized operations autonomously.                                              | \_/10      |
| PX40 | V1 has no runtime human-confirmation prompts for Plane agent operations.                              | \_/10      |
| PX41 | V1 has no approval-broker credential or pending operation-approval state.                             | \_/10      |

### Open Decisions

| ID    | Open decision                                                                           | Importance |
| ----- | --------------------------------------------------------------------------------------- | ---------- |
| PXD4  | Define the exact boundary of the supported agent-facing Plane API.                      | \_/10      |
| PXD6  | Define the metadata layered over generated API schemas.                                 | \_/10      |
| PXD7  | Select the initial direct semantic tools.                                               | \_/10      |
| PXD8  | Define how direct tools are promoted from observed agent workflows.                     | \_/10      |
| PXD9  | Define how direct tools are retired from the eager surface.                             | \_/10      |
| PXD10 | Define the isolation boundary around model-written TypeScript inside the run container. | \_/10      |
| PXD11 | Define the capabilities available to model-written TypeScript.                          | \_/10      |
| PXD16 | Define replay behavior after a container restart.                                       | \_/10      |
| PXD17 | Define stable invocation identifiers for retries.                                       | \_/10      |
| PXD18 | Define idempotency requirements for Plane mutations.                                    | \_/10      |
| PXD19 | Define behavior for mutation outcomes that cannot be determined.                        | \_/10      |
| PXD21 | Define per-operation result limits.                                                     | \_/10      |
| PXD22 | Define cumulative execution result limits.                                              | \_/10      |
| PXD23 | Define storage for authoritative results that exceed model-facing limits.               | \_/10      |
| PXD25 | Define native Plane tool versioning.                                                    | \_/10      |
| PXD26 | Define external MCP compatibility versioning.                                           | \_/10      |
| PXD27 | Define TypeScript runtime versioning.                                                   | \_/10      |

## Conversation UX Interview Ledger

This ledger records the latest conversation-navigation and Inbox focus-mode decisions. It supersedes conflicting assumptions in the earlier conversation model.

`Weight` is intentionally blank. Score each decision from `0/10` to `10/10`.

### Product boundaries

| ID  | Decision                                                                                             | Weight |
| --- | ---------------------------------------------------------------------------------------------------- | ------ |
| P1  | Plane remains the product.                                                                           | 10/10  |
| P2  | Plane remains the system of record for work.                                                         | 10/10  |
| P3  | Buzz is a reference and code donor, not a separate product surface.                                  | 10/10  |
| P4  | Natural conversation is primary; technical run inspection is secondary.                              | 10/10  |
| P5  | Unless explicitly changed here, Plane behavior and domain semantics follow the current Plane source. | 10/10  |
| P6  | Unless explicitly changed here, channel and thread behavior follows the current Buzz source.         | 10/10  |

### Conversation modes

| ID  | Decision                                                             | Weight |
| --- | -------------------------------------------------------------------- | ------ |
| M1  | Plane supports socially anchored channels and chat.                  | 7/10   |
| M2  | Plane supports entity-owned comments.                                | 8/10   |
| M3  | Work items own durable comments.                                     | 9/10   |
| M7  | Channels support broad and cross-cutting coordination.               | 10/10  |
| M8  | Comments preserve artifact-specific decisions and history.           | 10/10  |
| M9  | Channel discussion is not automatically copied into entity comments. | 10/10  |
| M10 | Conversations can begin without a Plane artifact.                    | 10/10  |
| M11 | Plane artifacts do not automatically own conversations or threads.   | 10/10  |
| M12 | Conversations and threads can reference multiple Plane artifacts.    | 10/10  |

### Layout and navigation

| ID  | Decision                                                                        | Weight |
| --- | ------------------------------------------------------------------------------- | ------ |
| L1  | Structured work remains the primary screen.                                     | 9/10   |
| L2  | Conversation accompanies work in a side panel.                                  | 8/10   |
| L3  | The conversation panel is persistent.                                           | 7/10   |
| L4  | The conversation panel is collapsible.                                          | 10/10  |
| L5  | The conversation panel is resizable.                                            | 10/10  |
| L6  | Opening chat does not navigate away from the current work.                      | 8/10   |
| L7  | Opening a thread does not navigate away from the current work.                  | 8/10   |
| L8  | Comments, channels, and threads share one auxiliary panel.                      | 3/10   |
| L9  | A thread expands inside the auxiliary panel, not into another column.           | 5/10   |
| L10 | Browse context and conversation context are independent.                        | ?/10   |
| L11 | One channel or thread may remain pinned while the user browses.                 | 9/10   |
| L12 | When browse and conversation contexts differ, the panel labels them separately. | ?/10   |

### Channels and threads

| ID  | Decision                                                                                                             | Weight  |
| --- | -------------------------------------------------------------------------------------------------------------------- | ------- |
| C1  | Channels are secondary to Plane's work surfaces.                                                                     | 10/10   |
| C2  | Channel messages can reference Plane artifacts.                                                                      | 10/10   |
| C3  | Any channel message can start a thread.                                                                              | 10/10   |
| C4  | Thread discussion remains subordinate to its channel.                                                                | 10/10   |
| C5  | People can choose Create work item from a message or thread action menu.                                             | 10/10   |
| C6  | Promoting discussion into work does not move the discussion.                                                         | 10/10   |
| C7  | Promoted work and its source message or thread retain a durable bidirectional link.                                  | 8/10    |
| C8  | Opening an artifact reference does not switch the active conversation.                                               | 10/10   |
| C9  | Direct creation actions in conversation are limited to work items.                                                   | 6/10    |
| C10 | Create work item opens Plane's existing creation dialog with source content prefilled.                               | 10/10   |
| C11 | Created work appears as a compact artifact card attached beneath its source message, not as a separate system reply. | \_\_/10 |

### Comments and activity

| ID  | Decision                                                                              | Weight |
| --- | ------------------------------------------------------------------------------------- | ------ |
| E1  | Work-item comments remain unchanged from current Plane behavior.                      | 10/10  |
| E2  | Work-item activity history remains unchanged from current Plane behavior.             | 10/10  |
| E3  | Comments and activity remain interleaved in the existing chronological Activity feed. | 10/10  |

### Agents and context

| ID  | Decision                                                                                            | Weight |
| --- | --------------------------------------------------------------------------------------------------- | ------ |
| A1  | Humans and agents participate in the same conversations.                                            | 10/10  |
| A2  | Browsing alone does not wake an agent.                                                              | 10/10  |
| A3  | Property changes alone do not wake an agent.                                                        | 10/10  |
| A4  | Mentions will wake an agent.                                                                        | 10/10  |
| A5  | Assignments will wake an agent.                                                                     | 10/10  |
| A6  | Explicit invocation will wake an agent.                                                             | 10/10  |
| A7  | Agents receive explicitly referenced Plane artifacts as context.                                    | 10/10  |
| A8  | Agent run details remain behind a secondary inspection action.                                      | 10/10  |
| A9  | Agents can invoke Plane tools from channels, threads, and entity conversations.                     | 10/10  |
| A10 | Agent tools can create any supported Plane artifact.                                                | 10/10  |
| A11 | Agent tools can update any supported Plane artifact.                                                | 10/10  |
| A12 | The composer provides a context-picker control.                                                     | 7/10   |
| A13 | Clicking a visible Plane element in context-picker mode adds it to the draft context.               | 7/10   |
| A14 | Dragging over a region in context-picker mode adds that region to the draft context.                | 8/10   |
| A15 | Agents can invoke authorized Plane tools without a user request when configured triggers permit it. | 10/10  |

### State and responsive behavior

| ID  | Decision                                                                                 | Weight |
| --- | ---------------------------------------------------------------------------------------- | ------ |
| S1  | Channel and thread composers keep separate drafts.                                       | 10/10  |
| S2  | Channels and threads keep independent unread state.                                      | 10/10  |
| S3  | Collapsing the panel preserves unread state.                                             | 10/10  |
| S4  | Collapsing the panel preserves drafts and scroll position.                               | 10/10  |
| S5  | On narrow screens, chat mode uses a Slack-like full-screen channel and thread interface. | 10/10  |
| S6  | Closing the responsive conversation surface restores the underlying work state.          | 10/10  |

### Inbox and attention

| ID  | Decision                                                                                                                                                                              | Weight |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| I1  | Plane Inbox is a workspace-wide focus mode that brings attention-requiring contexts to the user.                                                                                      | 10/10  |
| I2  | The unified attention model extends the existing Inbox rather than replacing or removing its current capabilities.                                                                    | 10/10  |
| I3  | Existing work-item notifications continue to open embedded work-item previews inside Inbox.                                                                                           | 10/10  |
| I4  | Conversation notifications can open embedded channel or thread views inside Inbox.                                                                                                    | 10/10  |
| I5  | Embedded conversations are usable focused working surfaces for reading, replying, reacting, attaching context, and managing the thread; channel administration remains outside Inbox. | 10/10  |
