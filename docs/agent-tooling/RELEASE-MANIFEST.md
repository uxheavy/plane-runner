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

| ID        | Workflow                          | Required result                                                                                                                                       | Status                   |
| --------- | --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------ |
| RM-WF-001 | Broad project-planning acceptance | Real Luna-powered Hermes run creates exactly one parent release plan, three child work items, and one source-linked comment after approval            | Accepted scope           |
| RM-WF-002 | Denied control project            | Structured denial with zero control-project object leakage                                                                                            | Accepted scope           |
| RM-WF-003 | Mutation retry                    | Same invocation keys leave planning-artifact counts unchanged                                                                                         | Accepted scope           |
| RM-WF-004 | Generated-code isolation          | Harmless canary and controlled egress probes prove credential, filesystem, subprocess, package, and network restrictions                              | Accepted scope           |
| RM-WF-005 | External MCP compatibility        | Every current Python MCP operation receives an approved disposition and selected real clients pass live compatibility                                 | Required; inventory open |
| RM-WF-006 | Operator lifecycle                | Provision, permission, credential issue/store/rotate/revoke, approval configuration, audit lookup, kill switch, recovery, and rollback exercises pass | Required                 |
| RM-WF-007 | Production canary                 | Real Hermes permitted and denied workflows pass against the deployed artifact with audit and feature-control readback                                 | Required                 |

## Pilot operation inventory

Exact operation IDs and versions must be generated from the Plane API and existing MCP inventory before approval. Names below describe required capabilities and are not yet stable contract IDs.

| Capability                                    | Contract operation ID/version | Eager native tool | Code Mode | External MCP disposition | Status   |
| --------------------------------------------- | ----------------------------- | ----------------- | --------- | ------------------------ | -------- |
| Resolve workspace context                     | Pending inventory             | Pending           | Required  | Pending                  | Blocking |
| Resolve project context                       | Pending inventory             | Pending           | Required  | Pending                  | Blocking |
| Read current cycle                            | Pending inventory             | Pending           | Required  | Pending                  | Blocking |
| Search and list work items                    | Pending inventory             | Pending           | Required  | Pending                  | Blocking |
| Read one work item                            | Pending inventory             | Pending           | Required  | Pending                  | Blocking |
| Read relationships, priorities, and ownership | Pending inventory             | Pending           | Required  | Pending                  | Blocking |
| Create parent work item                       | Pending inventory             | Pending           | Required  | Pending                  | Blocking |
| Create child work item                        | Pending inventory             | Pending           | Required  | Pending                  | Blocking |
| Create source-linked comment                  | Pending inventory             | Pending           | Required  | Pending                  | Blocking |

No implementation may silently omit a blocking capability. The approved inventory must include every current Python MCP operation as gateway-mapped, intentionally retained with rationale, or explicitly deprecated through an approved compatibility plan.

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
