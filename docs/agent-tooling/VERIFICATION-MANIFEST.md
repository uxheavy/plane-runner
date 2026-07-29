# Verification Manifest: Plane Agent Tooling v1

## Status and change control

Proposed. Freeze and obtain recorded user approval before implementation begins.

After freeze, changes require both recorded user approval and an independent review. The implementation lane may implement checks but cannot solely qualify the verifier or execute the final independent proof.

## Evidence contract

Every check records:

- Check ID and manifest version.
- Plane and Hermes commit IDs.
- Integration-lock, catalog, adapter, prompt, fixture, runtime, container, and configuration digests.
- Resolved provider and model.
- UTC start and end timestamps.
- Exact command and exit code.
- Full immutable log location and digest.
- Environment type and prerequisites.
- Pass, fail, skip, and xpass counts.
- Oracle and expected assertions.
- Whether mocks are permitted.
- Reviewer or executor identity.
- Disposition of every failure.

A summary without underlying immutable logs is insufficient.

## Check inventory

| ID     | Check                                    | Oracle                                                                                                                                                                   | Environment                                     | Mocks                                | Required evidence                              |
| ------ | ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------- | ------------------------------------ | ---------------------------------------------- |
| VM-001 | Documentation and manifest consistency   | No accepted/open contradictions; required rows and owners present                                                                                                        | Clean Plane checkout                            | No                                   | Validator log                                  |
| VM-002 | Deterministic catalog generation         | Repeated generation produces identical catalog digest                                                                                                                    | Clean Plane checkout                            | No                                   | Digests and diff                               |
| VM-003 | Contract and schema matrix               | Every approved operation validates success and structured failures                                                                                                       | Plane test stack                                | Unit-layer only                      | Full matrix log                                |
| VM-004 | Authorization matrix                     | Every relevant role, membership, object, revoked-agent, and cross-workspace boundary matches Plane policy                                                                | Plane test stack                                | No policy mocks in integration proof | Matrix and audit readback                      |
| VM-005 | Approval matrix                          | Allow, deny, timeout, concurrent sibling, group preflight, and restart failure behave as specified                                                                       | Plane plus real Hermes                          | No in final layer                    | Events, state, and audit                       |
| VM-006 | Audit durability                         | Intent and outcome exist for invalid, denied, pending, approved, failed, unknown, and successful attempts; injected audit failure follows approved fail semantics        | Plane test stack                                | Failure injection allowed            | Database/API readback and logs                 |
| VM-007 | Mutation safety                          | Retry, lost response, duplicate delivery, race, and ambiguous result create no unapproved duplicate side effects                                                         | Plane plus Hermes                               | Network fault injection allowed      | Object counts and invocation records           |
| VM-008 | Result and artifact limits               | Per-result and cumulative limits, bounded reads, expiry, cleanup, hashes, and summaries hold                                                                             | Plane plus Hermes                               | Generated payloads allowed           | Size and cleanup evidence                      |
| VM-009 | TypeScript isolate security              | Canary secrets stay hidden; callback identity cannot be spoofed; controlled DNS/HTTP, loopback, metadata, filesystem, subprocess, and package probes are blocked         | Release isolate                                 | No bypass mocks                      | Probe matrix and host traces                   |
| VM-010 | Confused-deputy protection               | Callback is bound host-side to exact run, agent, tenant, operation budgets, and correlation; sibling and replay attacks fail                                             | Release isolate plus gateway                    | No                                   | Negative-test log                              |
| VM-011 | Concurrency and load                     | Ordering, approval waits, retry races, rate limits, approved concurrency, duration, p95/p99, and recovery targets pass                                                   | Release-like stack                              | No                                   | Metrics and traces                             |
| VM-012 | External MCP inventory and compatibility | Every current Python MCP operation has approved disposition and pinned real clients pass                                                                                 | Real MCP clients plus gateway                   | No                                   | Inventory, client versions, transcripts        |
| VM-013 | Mandatory live project planning          | Frozen prompt through real Luna Hermes produces exact tagged artifacts after separate approval and no control-project leak                                               | Authenticated Plane dev server plus real Hermes | None                                 | Transcript, traces, UI/API and audit readbacks |
| VM-014 | Extensive live evaluation                | All 50 retained authenticated trials meet release gates without fallback                                                                                                 | Authenticated Plane dev server plus real Hermes | None                                 | Trial ledger and aggregate report              |
| VM-015 | Operator lifecycle                       | Provision, permissions, credential issue/store/rotate/revoke, old-credential denial, approval configuration, audit lookup, kill switches, recovery, and rollback succeed | Release-like stack                              | No                                   | Exercise logs and readbacks                    |
| VM-016 | Production provenance                    | Reviewed commits map to build artifacts, deployment IDs, migrations, catalogs, runtime, and enabled configuration                                                        | CI and deployment systems                       | No                                   | Signed or immutable provenance records         |
| VM-017 | Production canary and rollback           | Real Hermes permitted and denied canaries, audit, feature controls, and last-known-good rollback pass                                                                    | Production                                      | None                                 | Deployment and readback evidence               |
| VM-018 | Documentation negative control           | Removing a required manifest field makes VM-001 fail                                                                                                                     | Isolated fixture                                | Controlled mutation required         | Expected failing log                           |
| VM-019 | Authorization negative control           | Deliberate policy mismatch makes VM-004 fail                                                                                                                             | Isolated test fixture                           | Controlled mutation required         | Expected failing log                           |
| VM-020 | Model fallback negative control          | Deliberate fallback or wrong model makes live verifier fail                                                                                                              | Isolated harness configuration                  | Controlled misconfiguration required | Expected failing log                           |
| VM-021 | Audit negative control                   | Suppressed audit outcome makes VM-006 fail                                                                                                                               | Isolated failure fixture                        | Controlled fault required            | Expected failing log                           |

## Mandatory live-project oracle

- Use one frozen initial prompt and no human steering except an authenticated approval response.
- Use a separately authorized human approver rather than the test agent.
- Use a separate verifier principal for Plane API and UI readback.
- Add a unique non-authoritative run tag to expected artifacts.
- Prove zero planning writes before approval.
- Trace actual native tool calls.
- Trace actual `docs`, `search`, and `execute` calls.
- Preserve generated TypeScript and its digest.
- Trace concurrent safe reads and every inner gateway call.
- Verify exactly one tagged parent, three tagged children, and one tagged source comment after approval.
- Replay the same stable invocation keys and verify counts remain unchanged.
- Verify audit for pending approval, approval, success, retry, denial, and any failure.
- Verify no inaccessible control-project object data appears in model-visible output, logs, artifacts, or audit summaries.
- Probe credential isolation using a harmless host-only canary rather than the real credential.
- Probe controlled DNS/HTTP destinations, loopback, metadata endpoints, filesystem, subprocess, and package access.
- Revoke or rotate the test credential after the exercise and verify the old credential fails.
- Execute and verify cleanup, or explicitly preserve tagged fixtures through an approved retention record.

## Primary entry point

The final command is pending implementation. It must be version-controlled, run from clean pinned checkouts, invoke every required check, and fail non-zero for any failure, skip, xpass, wrong digest, wrong provider, wrong model, missing evidence, or unapproved exception.

The final verifier must be executed independently from clean Plane and Hermes checkouts. It must prove its own sensitivity by passing VM-018 through VM-021 as expected failures before its positive result is accepted.
