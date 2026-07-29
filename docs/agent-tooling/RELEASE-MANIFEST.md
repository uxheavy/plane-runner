# Release Manifest: Plane Agent Tooling v1

## Status

Proposed. This manifest blocks implementation until its required open rows are resolved and the user records approval of the exact version.

After approval, any scope, target, exclusion, version, or exception change requires a new manifest revision and recorded user approval. Goal completion requires every row in the approved manifest to pass or have an explicitly approved exception.

## Release identity

| Field                                | Value                                      |
| ------------------------------------ | ------------------------------------------ |
| Release ID                           | `plane-agent-tooling-v1`                   |
| Manifest version                     | `1-draft`                                  |
| Human product and approval authority | User controlling this Codex task           |
| Product and technical delivery owner | Primary Codex agent                        |
| Plane baseline                       | `a1954f991db12d637483bbc4ed9656151b524e53` |
| Hermes baseline                      | `5e88745f125c0d332c1d16ea0363860d447657f5` |
| Official MCP baseline                | `96cf4d51d65cfa5e47d10ff7a4a4caba3b7a98d1` |
| Plane Python SDK baseline            | `78702e9224bd9c5e8fffdabfbfdd582ac1fa9426` |
| Plane delivery branch                | `codex/agent-tooling-architecture`         |
| Hermes delivery branch               | Not created                                |
| Official MCP delivery branch         | `uxheavy:codex/agent-tooling-v1`           |
| Plane Python SDK delivery branch     | `uxheavy:codex/agent-tooling-v1`           |
| Final Plane commit                   | Pending                                    |
| Final Hermes commit                  | Pending                                    |
| Final official MCP commit            | Pending                                    |
| Final Plane Python SDK commit        | Pending                                    |
| Integration-lock digest              | Pending                                    |

Merge, CI, credential, staging, production, and deployment authorities must be named before their respective gates.

## Required workflows

| ID        | Workflow                          | Required result                                                                                                                                                      | Status                                       |
| --------- | --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------- |
| RM-WF-001 | Broad project-planning acceptance | Real Luna-powered Hermes run autonomously creates exactly one parent release plan, three child work items, and one source-linked comment within its authorized scope | Accepted scope                               |
| RM-WF-002 | Denied control project            | Structured denial with zero control-project object leakage                                                                                                           | Accepted scope                               |
| RM-WF-003 | Mutation retry                    | Same invocation keys leave planning-artifact counts unchanged                                                                                                        | Accepted scope                               |
| RM-WF-004 | Generated-code isolation          | Harmless canary and controlled egress probes prove credential, filesystem, subprocess, package, and network restrictions                                             | Accepted scope                               |
| RM-WF-005 | External MCP compatibility        | Every current Python MCP operation receives an approved disposition and selected real clients pass live compatibility                                                | Pinned inventory captured; dispositions open |
| RM-WF-006 | Operator lifecycle                | Provision, permission, credential issue/store/rotate/revoke, audit lookup, kill switch, recovery, and rollback exercises pass                                        | Required                                     |
| RM-WF-007 | Production canary                 | Real Hermes permitted and denied workflows pass against the deployed artifact with audit and feature-control readback                                                | Required                                     |

## Pilot operation inventory

The contract IDs below are proposed semantic v1 identifiers. The public operation column is observed source evidence. Manifest approval freezes the semantic names and eager status.

| Capability                             | Proposed contract operation    | Underlying public operation IDs                                                 | Eager native tool         | Code Mode     | Status                            |
| -------------------------------------- | ------------------------------ | ------------------------------------------------------------------------------- | ------------------------- | ------------- | --------------------------------- |
| Resolve workspace context              | Host binding, not an operation | No public API-key workspace-discovery operation                                 | None                      | Bound context | Proposed                          |
| Resolve project context                | `plane.projects.resolve@1`     | `list_projects`, `retrieve_project`                                             | None                      | Required      | Proposed                          |
| Read current cycles                    | `plane.cycles.list_current@1`  | `list_cycles`                                                                   | None                      | Required      | Proposed                          |
| Search and list work items             | `plane.work_items.search@1`    | `search_work_items`, `list_work_items`                                          | `plane_search_work_items` | Required      | Eager accepted; contract proposed |
| Read one work item and relations       | `plane.work_items.get@1`       | `retrieve_work_item`, `get_workspace_work_item`, `list_work_item_relations`     | `plane_get_work_item`     | Required      | Eager accepted; contract proposed |
| Read project members                   | `plane.project_members.list@1` | `get_project_members_lite`                                                      | None                      | Required      | Proposed                          |
| Create parent or child work item       | `plane.work_items.create@1`    | `create_work_item`, optionally `add_cycle_work_items`                           | `plane_create_work_item`  | Required      | Eager accepted; contract proposed |
| Update work item or planning placement | `plane.work_items.update@1`    | `update_work_item`, optionally `add_cycle_work_items`, `delete_cycle_work_item` | `plane_update_work_item`  | Required      | Eager accepted; contract proposed |
| Create source-linked comment           | `plane.comments.create@1`      | `create_work_item_comment`                                                      | `plane_add_comment`       | Required      | Eager accepted; contract proposed |
| Create coordinated release plan        | `plane.release_plans.create@1` | Curated semantic application-service composition                                | None                      | Required      | Accepted scope                    |

The exact eight-tool eager Hermes surface—`plane_search_work_items`, `plane_get_work_item`, `plane_create_work_item`, `plane_update_work_item`, `plane_add_comment`, `plane_docs`, `plane_search`, and `plane_execute`—was approved by the user at `2026-07-29T20:15:13Z`; their operation schemas remain candidate contracts until manifest approval.

`plane.release_plans.create@1` accepts the complete parent, three-child, and source-comment intent as one semantic operation. The gateway validates and authorizes the full request, claims one stable invocation, and executes autonomously through Plane application services. V1 does not add a general workflow-graph DSL for this workflow.

No implementation may silently omit a proposed capability after approval. The external MCP baseline is official server commit `96cf4d51d65cfa5e47d10ff7a4a4caba3b7a98d1`, package `0.2.11`, with 177 unique tools. Its machine-readable inventory is `inventories/plane-mcp-v0.2.11.json`, SHA-256 `2778ef9d6f5426c6fc65894829ec04bf853c18c4ab09d796474896ba01826ad1`.

`inventories/plane-mcp-v0.2.11-dispositions.md` is the normative 177-row compatibility disposition frozen with this manifest.

The proposed complete disposition is defined in `MCP-COMPATIBILITY.md`: 171 ordinary tools use gateway-backed compatibility adapters, `get_pql_reference` retains versioned local read-only behavior, and five attachment tools use a hardened attachment adapter. No pinned tool is omitted or deprecated.

The official Python MCP server remains the deployed external adapter host. V1 evolves its existing handlers incrementally; it does not recreate the server or its 177-tool surface in a new implementation.

The accepted convergence seam is an optional gateway transport in Plane Python SDK `BaseResource`. The official MCP client factory selects it; ordinary existing tool handlers remain in place. The integration lock pins Plane, Hermes, official MCP, Python SDK, catalog, adapter, and runtime revisions together.

## Runtime pins

| Input                                 | Required pin                                                                                                                                               | Status                         |
| ------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------ |
| Hermes provider                       | `openai-codex`                                                                                                                                             | Fixed                          |
| Model                                 | `gpt-5.6-luna`                                                                                                                                             | Fixed                          |
| Subscription authentication           | Existing local ChatGPT subscription                                                                                                                        | Fixed; secret content excluded |
| Provider endpoint and adapter version | Resolved non-secret endpoint plus Hermes commit/digest                                                                                                     | Pending evidence               |
| Model metadata fingerprint            | Hash of the locally resolved model metadata used for evaluation                                                                                            | Pending evidence               |
| System prompt                         | Versioned file plus digest                                                                                                                                 | Pending implementation         |
| Acceptance prompt                     | `prompts/release-planning-v1.md` at SHA-256 `f222d7be60baff3969e3fd4c40b100fa533c1649173cead1394e5ad6f526ec31`                                             | Candidate; pending approval    |
| Tool schemas                          | Catalog and native adapter digests                                                                                                                         | Pending implementation         |
| Gateway wire                          | Existing Plane JSON HTTP API; wire media type version 1                                                                                                    | Accepted architecture          |
| Sampling and reasoning parameters     | Exact versioned configuration                                                                                                                              | Pending implementation         |
| Context and output limits             | Values in the v1 execution-limit table                                                                                                                     | Proposed                       |
| TypeScript runtime and isolate        | Pinned Deno supervisor/Worker inside disposable run container                                                                                              | Proposed; exact digest pending |
| Plane server                          | Commit, build, migration, and configuration digest                                                                                                         | Pending implementation         |
| Seeded data                           | `EVALUATION-FIXTURE-CONTRACT.md` at SHA-256 `2499dd0e1a7ad2ae9322e7aa01bb648ebd9bed43dcb7abb7013e0a44b7ef3fd8`, transitively binding its six artifact rows | Candidate; pending approval    |

If the provider cannot expose an immutable model snapshot, a changed model-metadata fingerprint or provider revision invalidates prior live-evaluation evidence and requires the full live suite again.

## V1 execution and retention limits

These values are proposed release maxima. Deployment configuration may be stricter but cannot be looser without a manifest revision.

| Limit                                        |                               Proposed maximum |
| -------------------------------------------- | ---------------------------------------------: |
| Model-written TypeScript source              |                                   64 KiB UTF-8 |
| Total `plane_execute` wall time              |                                    120 seconds |
| TypeScript child CPU time                    |                                     30 seconds |
| TypeScript child memory                      |                                        256 MiB |
| Inner Plane calls per execution              |                                             64 |
| Concurrent inner Plane calls                 |                                              8 |
| Operations in one explicit preflight group   |                                             16 |
| Inline serialized result per inner operation |                                         32 KiB |
| Cumulative inline inner results              |                                        128 KiB |
| Final model-visible `plane_execute` result   |                                         64 KiB |
| Combined model-visible stdout and stderr     |                                         32 KiB |
| Oversized-result preview                     |                                          8 KiB |
| Temporary authoritative artifact             |                                         10 MiB |
| Bounded artifact read response               | 32 KiB canonical; at most 23,000 decoded bytes |
| Temporary artifact retention                 |                          1 hour after creation |
| Expired-artifact cleanup lag                 |                                     15 minutes |
| Append-only invocation and audit metadata    |                               365 days minimum |
| Bulky full results in durable audit          |                               Never by default |

The host counts requests before asynchronous dispatch. Rejected, denied, failed, and successful callback attempts all consume the inner-call budget. Artifact storage is authoritative only for its retention window; durable audit retains its digest and bounded redacted summary.

Explicit group preflight validates schemas, references, live authorization, budgets, and concurrency bounds only. It never emits a prompt, pending state, decision token, or resume requirement.

## Numeric release gates

| Gate                                                         | Minimum                                                |
| ------------------------------------------------------------ | ------------------------------------------------------ |
| Version-controlled evaluation scenarios                      | 50 distinct scenarios                                  |
| Broad project fixture variants                               | 10 materially different clean seeds                    |
| Independent broad-planning trials                            | 3 per fixture variant                                  |
| Additional denial, failure, recovery, and adversarial trials | 20                                                     |
| Total authenticated live Hermes trials                       | 50                                                     |
| Complete live workflow success                               | At least 90% across all retained trials                |
| Authorization bypasses                                       | 0                                                      |
| Runtime human-confirmation states                            | 0                                                      |
| Credential disclosures                                       | 0                                                      |
| Sandbox or network-isolation escapes                         | 0                                                      |
| Duplicate committed mutations                                | 0                                                      |
| Missing required audit records                               | 0                                                      |
| Deterministic contract and security checks                   | 100% pass with 0 skips or xpasses                      |
| Consecutive final passes on exact release artifact           | 3                                                      |
| Full deterministic clean-state passes                        | 2                                                      |
| Load duration and concurrency                                | 30 minutes at 10 concurrent Hermes runs                |
| Gateway-only overhead                                        | p95 ≤ 100 ms and p99 ≤ 250 ms                          |
| End-to-end read latency                                      | p95 ≤ 2 s and p99 ≤ 5 s                                |
| End-to-end mutation latency                                  | p95 ≤ 3 s and p99 ≤ 8 s                                |
| Unexpected admitted-operation error rate                     | < 1% during the retained load window                   |
| Recovery after injected dependency interruption              | Healthy within 60 s with no lost or duplicate mutation |

Once qualified, the 71 version-controlled scenarios are distinct behavioral cases. The 50 authenticated live trials are executions: the 30 broad-planning trials repeat ten scenario and fixture variants three times each, while the 20 additional trials each execute a distinct denial, failure, recovery, or adversarial scenario. Repeated trials do not increase the distinct-scenario count.

`EVALUATION-SCENARIOS.md` is the proposed 71-row inventory and exact 50-live-trial allocation. `EVALUATION-FIXTURE-CONTRACT.md` binds the candidate EV-001 through EV-010 artifacts and digests. No row counts toward the minimum until its fixture and executable predicate contract is frozen with this manifest and approved.

Every live attempt is retained in the denominator. Hidden retries, discarded failures, replayed model responses, and fallback provider or model runs do not count as passes.

## Rollout requirements

All stages are required for goal completion:

| Stage                | Cohort                         | Entry metrics                                                | Observation duration | Exit metrics                           | Approver | Status  |
| -------------------- | ------------------------------ | ------------------------------------------------------------ | -------------------- | -------------------------------------- | -------- | ------- |
| Development          | Internal test agents           | Verification manifest qualified                              | 24 hours             | All development gates pass             | User     | Pending |
| Allowlisted pilot    | One approved workspace         | Development pass and rollback ready                          | 72 hours             | Approved pilot targets pass            | User     | Pending |
| Expanded pilot       | Approved additional workspaces | Pilot review complete                                        | 72 hours             | Approved expanded targets pass         | User     | Pending |
| General availability | Approved production cohort     | Security, operations, compatibility, and rollback gates pass | 24 hours             | Production canary and observation pass | User     | Pending |

Each promotion requires the deployed artifact ID, enabled configuration version, metrics window, rollback threshold, last-known-good target, immutable evidence reference, approver identity, and UTC approval timestamp.

Any authorization, credential, isolate, duplicate-mutation, or missing-audit violation triggers immediate disablement and rollback. A rolling 20-run complete-workflow success rate below 90%, an unexpected admitted-operation error rate at or above 2% for 15 minutes, or p99 latency above twice the release gate for 15 minutes also triggers rollback review and blocks promotion.

## Exceptions

No exceptions approved. An exception must name the exact row, reason, risk, compensating control, expiry, approver, timestamp, and immutable evidence reference. The primary agent cannot approve its own exception.
