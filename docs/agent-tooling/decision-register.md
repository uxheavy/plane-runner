# Decision Register

Each row contains one decision. Importance is intentionally left as `_/10` for product ranking.

## Accepted

| ID      | Decision                                                                                              | Importance |
| ------- | ----------------------------------------------------------------------------------------------------- | ---------- |
| ATD-001 | External agents access Plane through MCP.                                                             | \_/10      |
| ATD-002 | Plane's existing Python MCP server remains supported.                                                 | \_/10      |
| ATD-004 | Plane-native agents receive direct semantic Plane tools.                                              | \_/10      |
| ATD-005 | Plane-native agents receive TypeScript Code Mode.                                                     | \_/10      |
| ATD-009 | Common Plane operations are eager native tools.                                                       | \_/10      |
| ATD-010 | Remaining supported Plane operations are progressively discoverable.                                  | \_/10      |
| ATD-011 | Direct tools are an ergonomic surface rather than a security tier.                                    | \_/10      |
| ATD-012 | Every authenticated agent client can discover the complete supported operation/action catalog.          | \_/10      |
| ATD-013 | Catalog visibility does not imply execution permission.                                               | \_/10      |
| ATD-014 | Plane's live authorization model decides every operation.                                             | \_/10      |
| ATD-015 | The tooling layer does not duplicate Plane authorization with an operation allowlist.                 | \_/10      |
| ATD-016 | Plane-native agents have dedicated Plane identities.                                                  | \_/10      |
| ATD-017 | Each Plane-native agent has one revocable Plane credential.                                           | \_/10      |
| ATD-018 | Hermes stores Plane agent credentials in trusted host state.                                          | \_/10      |
| ATD-019 | Generated TypeScript never receives Plane credentials.                                                | \_/10      |
| ATD-020 | The initial architecture does not mint run-bound capability tokens.                                   | \_/10      |
| ATD-021 | The initial architecture does not mint per-operation credentials.                                     | \_/10      |
| ATD-022 | Native direct tools cross the Plane Operation Gateway.                                                | \_/10      |
| ATD-023 | Native Code Mode operations cross the Plane Operation Gateway.                                        | \_/10      |
| ATD-024 | External MCP operations converge on the Plane Operation Gateway.                                      | \_/10      |
| ATD-025 | Agents never access Plane's database directly.                                                        | \_/10      |
| ATD-026 | The Plane Operation Gateway initially lives inside the Plane API service.                             | \_/10      |
| ATD-027 | The supported catalog starts from Plane's public OpenAPI surface.                                     | \_/10      |
| ATD-028 | A curated overlay enriches generated operation schemas.                                               | \_/10      |
| ATD-029 | Explicit agent-native operations may supplement the public API.                                       | \_/10      |
| ATD-030 | Private UI and session routes are not automatically agent-facing.                                     | \_/10      |
| ATD-039 | Explicitly declared groups may be preflighted before concurrent dispatch.                             | \_/10      |
| ATD-040 | Concurrent groups return per-operation outcomes.                                                      | \_/10      |
| ATD-041 | Concurrent groups are not represented as database transactions.                                       | \_/10      |
| ATD-042 | Supported mutations use idempotency when available.                                                   | \_/10      |
| ATD-043 | An indeterminate non-idempotent mutation returns `outcome_unknown`.                                   | \_/10      |
| ATD-044 | `outcome_unknown` is never retried blindly.                                                           | \_/10      |
| ATD-045 | Model-visible results are always bounded.                                                             | \_/10      |
| ATD-046 | Oversized authoritative results may be stored as temporary artifacts.                                 | \_/10      |
| ATD-047 | Temporary artifacts are readable through bounded read tools.                                          | \_/10      |
| ATD-048 | Durable audit does not retain bulky full results by default.                                          | \_/10      |
| ATD-049 | Durable audit retains a result hash and bounded summary.                                              | \_/10      |
| ATD-050 | Every attempted operation produces append-only audit evidence.                                        | \_/10      |
| ATD-051 | Model-written TypeScript runs inside a disposable runtime-invocation container.                       | \_/10      |
| ATD-052 | Model-written TypeScript runs in a restricted child isolate.                                          | \_/10      |
| ATD-053 | The child isolate has no ambient network access.                                                      | \_/10      |
| ATD-054 | The child isolate has no package-installation access.                                                 | \_/10      |
| ATD-055 | The child isolate has no subprocess access.                                                           | \_/10      |
| ATD-056 | The child isolate has no unrelated filesystem access.                                                 | \_/10      |
| ATD-057 | The child isolate reaches Plane only through credential-free host RPC.                                | \_/10      |
| ATD-058 | Audit metadata pins exact catalog and adapter versions.                                               | \_/10      |
| ATD-059 | Audit metadata pins the TypeScript runtime version.                                                   | \_/10      |
| ATD-060 | External MCP compatibility is versioned independently from native tool ergonomics.                    | \_/10      |
| ATD-061 | The first pilot is a broader end-to-end project-planning scenario.                                    | \_/10      |
| ATD-062 | Goal completion requires a real Hermes run against the authenticated Plane development server.        | \_/10      |
| ATD-063 | The mandatory live Hermes acceptance cannot use a mocked Plane Operation Gateway.                     | \_/10      |
| ATD-064 | The live pilot creates one parent release plan and three coordinated child work items.                | \_/10      |
| ATD-065 | The live pilot proves a structured denial against an inaccessible control project.                    | \_/10      |
| ATD-066 | Counted live acceptance runs use the locally authenticated ChatGPT subscription.                      | \_/10      |
| ATD-067 | Counted live acceptance runs use Hermes provider `openai-codex`.                                      | \_/10      |
| ATD-068 | Counted live acceptance runs use model `gpt-5.6-luna`.                                                | \_/10      |
| ATD-069 | Provider or model fallback fails live acceptance.                                                     | \_/10      |
| ATD-070 | The evaluation manifest contains at least 50 distinct scenarios.                                      | \_/10      |
| ATD-071 | Production approval requires at least 50 authenticated live Hermes evaluation runs.                   | \_/10      |
| ATD-072 | Computer Use provides user-visible Plane and Hermes acceptance evidence.                              | \_/10      |
| ATD-075 | Final verification must pass qualified negative controls.                                             | \_/10      |
| ATD-076 | Final verification runs independently from clean Plane and Hermes checkouts.                          | \_/10      |
| ATD-077 | Goal completion requires every general-availability rollout stage.                                    | \_/10      |
| ATD-078 | The external MCP inventory gives every current operation an approved disposition.                     | \_/10      |
| ATD-079 | Audit durability covers every attempted operation outcome.                                            | \_/10      |
| ATD-080 | The Code Mode callback channel is host-bound against cross-run and identity spoofing.                 | \_/10      |
| ATD-081 | The core gateway exposes one request-bound operation-execution seam.                                  | \_/10      |
| ATD-082 | Read-only catalog search and description use a separate discovery interface.                          | \_/10      |
| ATD-083 | Idempotency, reconciliation, result, and audit lifecycle remain internal to the gateway.              | \_/10      |
| ATD-084 | The architecture chooses the least custom code that still satisfies approved production gates.        | \_/10      |
| ATD-085 | Plane's official Python MCP server remains the external adapter host.                                 | \_/10      |
| ATD-086 | Existing MCP handlers migrate incrementally to the shared gateway rather than being recreated.        | \_/10      |
| ATD-087 | The v1 release-plan write is one curated semantic gateway operation.                                  | \_/10      |
| ATD-088 | V1 does not add a general workflow-graph DSL.                                                         | \_/10      |
| ATD-089 | The official MCP server reaches the gateway through one optional shared Plane Python SDK transport.   | \_/10      |
| ATD-090 | Cross-process gateway calls use one versioned JSON HTTP adapter in Plane's existing API service.      | \_/10      |
| ATD-094 | Plane agents execute authorized operations autonomously by default.                                   | \_/10      |
| ATD-097 | V1 has no runtime human-confirmation prompts for agent operations.                                    | \_/10      |
| ATD-106 | The fork exposes a Plane-native runtime profile.                                                      | \_/10      |
| ATD-107 | Hermes is the hidden execution kernel rather than the agent's product identity.                       | \_/10      |
| ATD-108 | The Plane-native profile does not inherit the `hermes-cli` model-facing tool catalog.                 | \_/10      |
| ATD-109 | Every model-facing tool is redesigned from natural Plane workflows and vocabulary.                    | \_/10      |
| ATD-110 | Every Plane agent receives a small universal Plane work core in its initial tool context.             | \_/10      |
| ATD-111 | Initial tool context adds operation schemas relevant to the profile and current assignment.           | \_/10      |
| ATD-112 | Other available operations remain progressively discoverable.                                         | \_/10      |
| ATD-113 | The universal Plane work core exposes one `search_workspace` tool across Plane object types.          | \_/10      |
| ATD-114 | Specialized domain searches remain discoverable for advanced filters and projections.                 | \_/10      |
| ATD-115 | Plane Agent is the product abstraction; Hermes is not exposed as a separate product.                  | \_/10      |
| ATD-116 | Plane owns durable agent identity, profile, assignment, run, conversation, artifact, and history.     | \_/10      |
| ATD-117 | The `uxheavy` Hermes fork is maintained as Plane Agent's hidden execution kernel.                     | \_/10      |
| ATD-118 | One underlying Plane Agent model uses exactly one role per configured agent; roles are declarative and versioned rather than separate runtime implementations. | \_/10      |
| ATD-119 | An assignment is a durable commission to produce an outcome; the submission is the reviewable result. | \_/10      |
| ATD-120 | Plane is authoritative for assignment, run, outcome, conversation, artifact, and history state.       | \_/10      |
| ATD-121 | Mutations remain explicit semantic operations rather than one universal mutation tool.                | \_/10      |
| ATD-122 | The first vertical slice proves one agent completing one assigned outcome.                            | \_/10      |
| ATD-123 | Actor authorization, behavioral profile versions, and tool availability/disclosure are separate.      | \_/10      |
| ATD-124 | A Plane run may span kernel invocations, sessions, processes, or restarts.                            | \_/10      |
| ATD-125 | Plane-governed storage is authoritative; Hermes-compatible files are execution projections.           | \_/10      |
| ATD-126 | Agent memory and skills remain private to one agent; gardener improvements are immutable and rollbackable, and no knowledge is copied between agents. | \_/10      |
| ATD-127 | Plane records exactly one visible terminal product event for every terminal runtime invocation: outcome, failure, blocker, or cancellation. | \_/10      |
| ATD-128 | Built-in Agent roles are worker, delegator, gardener, chief of staff, HR, and evaluator.              | \_/10      |
| ATD-129 | Workspace administrators may define additional custom single roles on the same Agent model.          | \_/10      |
| ATD-130 | Every human automatically receives one chief-of-staff Agent restricted to that human's live permissions. | \_/10      |
| ATD-131 | A dedicated delegator dynamically plans each case, assigns unclaimed work to humans or Agents, and records assignment rationale. | \_/10      |
| ATD-132 | Worker and ordinary specialist Agents do not freely delegate.                                      | \_/10      |
| ATD-133 | Saved or versioned workflow definitions and a workflow-definition delivery lane are out of scope; each case is planned dynamically. | \_/10      |
| ATD-134 | Approved schedules create normal assignments and runs through the standard lifecycle.                | \_/10      |
| ATD-135 | HR proposes Agent creation, change, and retirement; a workspace administrator approves each proposal. | \_/10      |
| ATD-136 | An evaluator reviews every Agent outcome before human acceptance or return; human acceptance remains final. | \_/10      |
| ATD-137 | Full Plane integration/action coverage is required before the non-UI program is finished.             | \_/10      |
| ATD-138 | Adaptive disclosure controls eager schemas without reducing global catalog discoverability or operation coverage. | \_/10      |
| ATD-139 | Required administration reuses existing Plane settings surfaces; no new settings framework is created. | \_/10      |
| ATD-140 | After verification, rollout may be staged despite no current users, and automated safety stops remain mandatory. | \_/10      |
| ATD-141 | The approval manifest is the implementation gate; no runtime, application, or verification implementation begins before explicit approval and G0. | \_/10      |
| ATD-142 | Internal Agent calls use dedicated Agent identity; external MCP calls preserve the authenticated human or integration caller. | \_/10      |
| ATD-143 | ADR-0008, ADR-0009, and ADR-0010 are accepted decisions before their implementation lanes begin.   | \_/10      |
| ATD-144 | Terminal cancellation and blocker are distinct visible Plane events; waiting for input is non-terminal. | \_/10      |

## Superseded

| ID      | Superseded decision                                                                  | Replacement                                                              | Importance |
| ------- | ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------ | ---------- |
| ATD-073 | An approved release manifest is a pre-implementation gate that freezes scope and numeric gates. | ATD-141 makes `APPROVAL-MANIFEST.md` the sole implementation-start approval; the release manifest is an evidence input. | \_/10 |
| ATD-074 | An independently reviewed verification manifest is a pre-implementation gate that freezes checks and oracles. | ATD-141 makes `APPROVAL-MANIFEST.md` the sole implementation-start approval; the verification manifest is an evidence input. | \_/10 |
| ATS-001 | Pause Code Mode by releasing the container and replaying prior calls after approval. | ATD-097 removes runtime operation approvals.                             | \_/10      |
| ATS-002 | Mint a short-lived assertion for every Hermes run.                                   | ATD-017 uses one revocable credential per Plane agent identity.          | \_/10      |
| ATS-003 | Evaluate a separate runtime approval policy for agent operations.                    | ATD-094 and ATD-097 use autonomous execution within Plane authorization. | \_/10      |
| ATS-004 | Reuse Hermes's live approval lifecycle for Plane operations.                         | ATD-097 removes runtime human-confirmation prompts.                      | \_/10      |
| ATS-005 | Persist or resume pending Plane operation approvals.                                 | ATD-097 removes pending runtime approvals.                               | \_/10      |
| ATS-006 | Continue admitted siblings while one Plane operation waits for approval.             | ATD-097 removes approval waits; ATD-039 retains group preflight.         | \_/10      |
| ATS-007 | Submit decisions through a separate Hermes broker credential.                        | ATD-097 removes the approval decision path and credential.               | \_/10      |
| ATS-008 | Allow administrators to configure optional operation prompts.                        | ATD-097 removes all runtime operation prompts.                           | \_/10      |
| ATS-009 | Resume the exact Hermes tool call after a Plane approval decision.                   | ATD-097 removes runtime approval decisions and resume behavior.          | \_/10      |
| ATS-010 | Plane-native agents use the inherited native Hermes tool surface.                    | ATD-106 through ATD-109 define a Plane-native runtime profile.           | \_/10      |
| ATS-011 | Code Mode exposes `plane_docs`.                                                      | ATD-106 through ATD-109 reopen the Plane-native tool catalog.            | \_/10      |
| ATS-012 | Code Mode exposes `plane_search`.                                                    | ATD-106 through ATD-109 reopen the Plane-native tool catalog.            | \_/10      |
| ATS-013 | Code Mode exposes `plane_execute`.                                                   | ATD-106 through ATD-109 reopen the Plane-native tool catalog.            | \_/10      |
| ATS-014 | `plane_search_work_items` is fixed as an eager v1 tool.                              | ATD-106 through ATD-109 reopen the eager surface.                        | \_/10      |
| ATS-015 | `plane_get_work_item` is fixed as an eager v1 tool.                                  | ATD-106 through ATD-109 reopen the eager surface.                        | \_/10      |
| ATS-016 | `plane_create_work_item` is fixed as an eager v1 tool.                               | ATD-106 through ATD-109 reopen the eager surface.                        | \_/10      |
| ATS-017 | `plane_update_work_item` is fixed as an eager v1 tool.                               | ATD-106 through ATD-109 reopen the eager surface.                        | \_/10      |
| ATS-018 | `plane_add_comment` is fixed as an eager v1 tool.                                    | ATD-106 through ATD-109 reopen the eager surface.                        | \_/10      |
| ATS-019 | `plane_docs` is fixed as an eager v1 tool.                                           | ATD-106 through ATD-109 reopen the eager surface.                        | \_/10      |
| ATS-020 | `plane_search` is fixed as an eager v1 tool.                                         | ATD-106 through ATD-109 reopen the eager surface.                        | \_/10      |
| ATS-021 | `plane_execute` is fixed as an eager v1 tool.                                        | ATD-106 through ATD-109 reopen the eager surface.                        | \_/10      |

## Open

| ID      | Open decision                                                                                    | Importance |
| ------- | ------------------------------------------------------------------------------------------------ | ---------- |
| ATO-003 | Define the first supported operation boundary.                                                   | \_/10      |
| ATO-004 | Define the curated overlay fields.                                                               | \_/10      |
| ATO-005 | Define direct-tool promotion criteria.                                                           | \_/10      |
| ATO-006 | Define eager-tool retirement criteria.                                                           | \_/10      |
| ATO-007 | Define per-operation result thresholds.                                                          | \_/10      |
| ATO-008 | Define cumulative execution result thresholds.                                                   | \_/10      |
| ATO-009 | Define temporary artifact retention.                                                             | \_/10      |
| ATO-010 | Define credential issuance and storage mechanics.                                                | \_/10      |
| ATO-011 | Define credential rotation and revocation operations.                                            | \_/10      |
| ATO-012 | Define catalog compatibility rules.                                                              | \_/10      |
| ATO-013 | Define native tool compatibility rules.                                                          | \_/10      |
| ATO-014 | Define external MCP migration order.                                                             | \_/10      |
| ATO-015 | Define numeric production success targets.                                                       | \_/10      |
| ATO-016 | Define audit retention and redaction periods.                                                    | \_/10      |
| ATO-017 | Define which operation groups benefit from preflight.                                            | \_/10      |
| ATO-018 | Define the exact TypeScript isolate technology.                                                  | \_/10      |
| ATO-019 | Define the exact eager Plane-native tool surface.                                                | \_/10      |
| ATO-020 | Define the progressive-discovery tool surface.                                                   | \_/10      |
| ATO-021 | Define the TypeScript composition tool contract.                                                 | \_/10      |

## Proposed

| ID      | Proposed decision                                                                                                                    | Importance |
| ------- | ------------------------------------------------------------------------------------------------------------------------------------ | ---------- |
| ATP-004 | Run TypeScript in a pinned Deno supervisor/Worker with explicit deny permissions inside the disposable runtime-invocation container. | \_/10      |
| ATP-005 | Use the v1 execution, result, artifact, and audit-retention limits proposed in the release manifest.                                 | \_/10      |
| ATP-006 | Use the proposed 30-minute ten-run load gate and explicit latency, error, and recovery thresholds.                                   | \_/10      |
| ATP-007 | Require 24-hour development, 72-hour allowlisted, 72-hour expanded, and 24-hour GA observation windows.                              | \_/10      |
