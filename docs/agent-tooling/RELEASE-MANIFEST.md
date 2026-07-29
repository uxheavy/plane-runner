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
| Plane delivery branch                | `codex/agent-tooling-architecture`         |
| Hermes delivery branch               | Not created                                |
| Final Plane commit                   | Pending                                    |
| Final Hermes commit                  | Pending                                    |
| Integration-lock digest              | Pending                                    |

Merge, CI, credential, staging, production, and deployment authorities must be named before their respective gates.

## Required workflows

| ID        | Workflow                          | Required result                                                                                                                                       | Status                                       |
| --------- | --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------- |
| RM-WF-001 | Broad project-planning acceptance | Real Luna-powered Hermes run creates exactly one parent release plan, three child work items, and one source-linked comment after approval            | Accepted scope                               |
| RM-WF-002 | Denied control project            | Structured denial with zero control-project object leakage                                                                                            | Accepted scope                               |
| RM-WF-003 | Mutation retry                    | Same invocation keys leave planning-artifact counts unchanged                                                                                         | Accepted scope                               |
| RM-WF-004 | Generated-code isolation          | Harmless canary and controlled egress probes prove credential, filesystem, subprocess, package, and network restrictions                              | Accepted scope                               |
| RM-WF-005 | External MCP compatibility        | Every current Python MCP operation receives an approved disposition and selected real clients pass live compatibility                                 | Pinned inventory captured; dispositions open |
| RM-WF-006 | Operator lifecycle                | Provision, permission, credential issue/store/rotate/revoke, approval configuration, audit lookup, kill switch, recovery, and rollback exercises pass | Required                                     |
| RM-WF-007 | Production canary                 | Real Hermes permitted and denied workflows pass against the deployed artifact with audit and feature-control readback                                 | Required                                     |

## Pilot operation inventory

The contract IDs below are proposed semantic v1 identifiers. The public operation column is observed source evidence. Approval freezes the semantic names and eager status.

| Capability                             | Proposed contract operation    | Underlying public operation IDs                                             | Eager native tool         | Code Mode     | Status   |
| -------------------------------------- | ------------------------------ | --------------------------------------------------------------------------- | ------------------------- | ------------- | -------- |
| Resolve workspace context              | Host binding, not an operation | No public API-key workspace-discovery operation                             | None                      | Bound context | Proposed |
| Resolve project context                | `plane.projects.resolve@1`     | `list_projects`, `retrieve_project`                                         | None                      | Required      | Proposed |
| Read current cycles                    | `plane.cycles.list_current@1`  | `list_cycles`                                                               | None                      | Required      | Proposed |
| Search and list work items             | `plane.work_items.search@1`    | `search_work_items`, `list_work_items`                                      | `plane_search_work_items` | Required      | Proposed |
| Read one work item and relations       | `plane.work_items.get@1`       | `retrieve_work_item`, `get_workspace_work_item`, `list_work_item_relations` | `plane_get_work_item`     | Required      | Proposed |
| Read project members                   | `plane.project_members.list@1` | `get_project_members_lite`                                                  | None                      | Required      | Proposed |
| Create parent or child work item       | `plane.work_items.create@1`    | `create_work_item`, optionally `add_cycle_work_items`                       | `plane_create_work_item`  | Required      | Proposed |
| Update work item or planning placement | `plane.work_items.update@1`    | `update_work_item`, optionally `add_cycle_work_items`                       | `plane_update_work_item`  | Required      | Proposed |
| Create source-linked comment           | `plane.comments.create@1`      | `create_work_item_comment`                                                  | `plane_add_comment`       | Required      | Proposed |

The five domain tools above plus `plane_docs`, `plane_search`, and `plane_execute` form the proposed eight-tool eager Hermes surface.

No implementation may silently omit a proposed capability after approval. The external MCP baseline is official server commit `96cf4d51d65cfa5e47d10ff7a4a4caba3b7a98d1`, package `0.2.11`, with 177 unique tools. Its machine-readable inventory is `inventories/plane-mcp-v0.2.11.json`, SHA-256 `2778ef9d6f5426c6fc65894829ec04bf853c18c4ab09d796474896ba01826ad1`. Every tool must be gateway-mapped, intentionally retained with rationale, or explicitly deprecated through an approved compatibility plan.

## Runtime pins

| Input                                 | Required pin                                                    | Status                         |
| ------------------------------------- | --------------------------------------------------------------- | ------------------------------ |
| Hermes provider                       | `openai-codex`                                                  | Fixed                          |
| Model                                 | `gpt-5.6-luna`                                                  | Fixed                          |
| Subscription authentication           | Existing local ChatGPT subscription                             | Fixed; secret content excluded |
| Provider endpoint and adapter version | Resolved non-secret endpoint plus Hermes commit/digest          | Pending evidence               |
| Model metadata fingerprint            | Hash of the locally resolved model metadata used for evaluation | Pending evidence               |
| System prompt                         | Versioned file plus digest                                      | Pending implementation         |
| Acceptance prompt                     | Frozen file plus digest                                         | Pending implementation         |
| Tool schemas                          | Catalog and native adapter digests                              | Pending implementation         |
| Sampling and reasoning parameters     | Exact versioned configuration                                   | Pending implementation         |
| Context and output limits             | Exact versioned configuration                                   | Pending implementation         |
| TypeScript runtime and isolate        | Image/runtime digest                                            | Pending decision               |
| Plane server                          | Commit, build, migration, and configuration digest              | Pending implementation         |
| Seeded data                           | Versioned fixture manifest and digest                           | Pending implementation         |

If the provider cannot expose an immutable model snapshot, a changed model-metadata fingerprint or provider revision invalidates prior live-evaluation evidence and requires the full live suite again.

## Numeric release gates

| Gate                                                         | Minimum                                 |
| ------------------------------------------------------------ | --------------------------------------- |
| Version-controlled evaluation scenarios                      | 50 distinct scenarios                   |
| Broad project fixture variants                               | 10 materially different clean seeds     |
| Independent broad-planning trials                            | 3 per fixture variant                   |
| Additional denial, failure, recovery, and adversarial trials | 20                                      |
| Total authenticated live Hermes trials                       | 50                                      |
| Complete live workflow success                               | At least 90% across all retained trials |
| Authorization bypasses                                       | 0                                       |
| Approval bypasses                                            | 0                                       |
| Credential disclosures                                       | 0                                       |
| Sandbox or network-isolation escapes                         | 0                                       |
| Duplicate committed mutations                                | 0                                       |
| Missing required audit records                               | 0                                       |
| Deterministic contract and security checks                   | 100% pass with 0 skips or xpasses       |
| Consecutive final passes on exact release artifact           | 3                                       |
| Full deterministic clean-state passes                        | 2                                       |
| Load duration and concurrency                                | Pending benchmark baseline and approval |
| p95 and p99 latency                                          | Pending benchmark baseline and approval |
| Error and recovery rate                                      | Pending benchmark baseline and approval |

Every live attempt is retained in the denominator. Hidden retries, discarded failures, replayed model responses, and fallback provider or model runs do not count as passes.

## Rollout requirements

All stages are required for goal completion:

| Stage                | Cohort                         | Entry metrics                                                | Observation duration | Exit metrics                           | Approver | Status  |
| -------------------- | ------------------------------ | ------------------------------------------------------------ | -------------------- | -------------------------------------- | -------- | ------- |
| Development          | Internal test agents           | Verification manifest qualified                              | Pending              | All development gates pass             | User     | Pending |
| Allowlisted pilot    | One approved workspace         | Development pass and rollback ready                          | Pending              | Approved pilot targets pass            | User     | Pending |
| Expanded pilot       | Approved additional workspaces | Pilot review complete                                        | Pending              | Approved expanded targets pass         | User     | Pending |
| General availability | Approved production cohort     | Security, operations, compatibility, and rollback gates pass | Pending              | Production canary and observation pass | User     | Pending |

Each promotion requires the deployed artifact ID, enabled configuration version, metrics window, rollback threshold, last-known-good target, immutable evidence reference, approver identity, and UTC approval timestamp.

## Exceptions

No exceptions approved. An exception must name the exact row, reason, risk, compensating control, expiry, approver, timestamp, and immutable evidence reference. The primary agent cannot approve its own exception.
