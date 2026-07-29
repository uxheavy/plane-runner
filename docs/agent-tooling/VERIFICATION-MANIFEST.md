# Verification Manifest: Plane Agent Tooling v1

## Status and change control

Proposed. Freeze and obtain recorded user approval before implementation begins.

After freeze, changes require both recorded user approval and an independent review. The implementation lane may implement checks but cannot solely qualify the verifier or execute the final independent proof.

## Evidence contract

Every check records:

- Check ID and manifest version.
- Plane, Hermes, official MCP, and Plane Python SDK commit IDs.
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

## Verifier ownership and independence

| Responsibility                 | Qualification                                                    | Independence rule                                                       | Status             |
| ------------------------------ | ---------------------------------------------------------------- | ----------------------------------------------------------------------- | ------------------ |
| Verifier implementation        | Quality lane with access to both pinned repositories             | May not approve its own oracle changes                                  | Pending assignment |
| Security qualification         | Reviewer who did not implement the isolate or authorization path | Must review VM-004, VM-006, VM-009, VM-010, and their negative controls | Pending assignment |
| Final clean-checkout execution | Executor using fresh checkouts and release artifacts             | Must not use an implementation worktree or unpublished local patch      | Pending assignment |
| Product acceptance             | User controlling this Codex task                                 | Approves frozen manifests, exceptions, and rollout promotions           | Named              |

The primary implementation agent may create tests and fix failures. It cannot solely qualify negative controls, approve verifier changes, approve exceptions, or supply the final independent execution result.

## Check inventory

| ID     | Check                                    | Oracle                                                                                                                                                                   | Environment                                     | Mocks                                | Required evidence                              |
| ------ | ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------- | ------------------------------------ | ---------------------------------------------- |
| VM-001 | Documentation and manifest consistency   | No accepted/open contradictions; required rows and owners present                                                                                                        | Clean Plane checkout                            | No                                   | Validator log                                  |
| VM-002 | Deterministic catalog generation         | Repeated generation produces identical catalog digest                                                                                                                    | Clean Plane checkout                            | No                                   | Digests and diff                               |
| VM-003 | Contract and schema matrix               | Every approved operation validates success and structured failures                                                                                                       | Plane test stack                                | Unit-layer only                      | Full matrix log                                |
| VM-004 | Authorization matrix                     | Every relevant role, membership, object, revoked-agent, and cross-workspace boundary matches Plane policy                                                                | Plane test stack                                | No policy mocks in integration proof | Matrix and audit readback                      |
| VM-005 | Optional approval-policy matrix          | Default `not_required`, configured approve-once, deny, timeout, concurrent sibling, semantic preflight, and restart failure behave as specified                          | Plane plus real Hermes                          | No in final layer                    | Events, state, and audit                       |
| VM-006 | Audit durability                         | Intent and outcome exist for invalid, denied, pending, approved, failed, unknown, and successful attempts; injected audit failure follows approved fail semantics        | Plane test stack                                | Failure injection allowed            | Database/API readback and logs                 |
| VM-007 | Mutation safety                          | Retry, lost response, duplicate delivery, race, and ambiguous result create no unapproved duplicate side effects                                                         | Plane plus Hermes                               | Network fault injection allowed      | Object counts and invocation records           |
| VM-008 | Result and artifact limits               | Per-result and cumulative limits, bounded reads, expiry, cleanup, hashes, and summaries hold                                                                             | Plane plus Hermes                               | Generated payloads allowed           | Size and cleanup evidence                      |
| VM-009 | TypeScript isolate security              | Canary secrets stay hidden; callback identity cannot be spoofed; controlled DNS/HTTP, loopback, metadata, filesystem, subprocess, and package probes are blocked         | Release isolate                                 | No bypass mocks                      | Probe matrix and host traces                   |
| VM-010 | Confused-deputy protection               | Callback is bound host-side to exact run, agent, tenant, operation budgets, and correlation; sibling and replay attacks fail                                             | Release isolate plus gateway                    | No                                   | Negative-test log                              |
| VM-011 | Concurrency and load                     | Ordering, approval waits, retry races, rate limits, approved concurrency, duration, p95/p99, and recovery targets pass                                                   | Release-like stack                              | No                                   | Metrics and traces                             |
| VM-012 | External MCP inventory and compatibility | Every current Python MCP operation has approved disposition and pinned real clients pass                                                                                 | Real MCP clients plus gateway                   | No                                   | Inventory, client versions, transcripts        |
| VM-013 | Mandatory live project planning          | Frozen prompt through real Luna Hermes autonomously produces exact tagged artifacts under default policy and leaks no control-project data                               | Authenticated Plane dev server plus real Hermes | None                                 | Transcript, traces, UI/API and audit readbacks |
| VM-014 | Extensive live evaluation                | All 50 retained authenticated trials meet release gates without fallback                                                                                                 | Authenticated Plane dev server plus real Hermes | None                                 | Trial ledger and aggregate report              |
| VM-015 | Operator lifecycle                       | Provision, permissions, credential issue/store/rotate/revoke, old-credential denial, approval configuration, audit lookup, kill switches, recovery, and rollback succeed | Release-like stack                              | No                                   | Exercise logs and readbacks                    |
| VM-016 | Production provenance                    | Reviewed commits map to build artifacts, deployment IDs, migrations, catalogs, runtime, and enabled configuration                                                        | CI and deployment systems                       | No                                   | Signed or immutable provenance records         |
| VM-017 | Production canary and rollback           | Real Hermes permitted and denied canaries, audit, feature controls, and last-known-good rollback pass                                                                    | Production                                      | None                                 | Deployment and readback evidence               |
| VM-018 | Documentation negative control           | Removing a required manifest field makes VM-001 fail                                                                                                                     | Isolated fixture                                | Controlled mutation required         | Expected failing log                           |
| VM-019 | Authorization negative control           | Deliberate policy mismatch makes VM-004 fail                                                                                                                             | Isolated test fixture                           | Controlled mutation required         | Expected failing log                           |
| VM-020 | Model fallback negative control          | Deliberate fallback or wrong model makes live verifier fail                                                                                                              | Isolated harness configuration                  | Controlled misconfiguration required | Expected failing log                           |
| VM-021 | Audit negative control                   | Suppressed audit outcome makes VM-006 fail                                                                                                                               | Isolated failure fixture                        | Controlled fault required            | Expected failing log                           |

## Completion-criterion coverage

| Goal area                             | Required checks                                           |
| ------------------------------------- | --------------------------------------------------------- |
| Product and contract                  | VM-001, VM-002, VM-003, VM-012                            |
| Plane Operation Gateway               | VM-003, VM-004, VM-005, VM-006, VM-007, VM-008            |
| Hermes and TypeScript Code Mode       | VM-003, VM-005, VM-008, VM-009, VM-010, VM-013            |
| Reliability and safety                | VM-004 through VM-012                                     |
| Mandatory live Hermes acceptance      | VM-013                                                    |
| Extensive evaluation                  | VM-014                                                    |
| Operations and rollout                | VM-011, VM-015, VM-016, VM-017                            |
| Verifier sensitivity and independence | VM-018 through VM-021 plus final clean-checkout execution |

The version-controlled verifier specification must expand this table to a requirement-level matrix. Every normative bullet in `GOAL.md` and every row in the approved release manifest must map to at least one check, one observable oracle, and one immutable evidence record. The documentation validator fails when any requirement has zero checks.

## Mandatory live-project oracles

- Use one frozen initial prompt and no human steering for the autonomous default-policy run.
- Use a separate verifier principal for Plane API and UI readback.
- Add a unique non-authoritative run tag to expected artifacts.
- Prove the default policy returns `not_required` and creates no pending approval.
- Trace actual native tool calls.
- Trace actual `docs`, `search`, and `execute` calls.
- Preserve generated TypeScript and its digest.
- Trace concurrent safe reads and every inner gateway call.
- Verify exactly one tagged parent, three tagged children, and one tagged source comment after autonomous execution.
- Replay the same stable invocation keys and verify counts remain unchanged.
- Verify audit for policy evaluation, success, retry, denial, and any failure.
- Verify no inaccessible control-project object data appears in model-visible output, logs, artifacts, or audit summaries.
- Probe credential isolation using a harmless host-only canary rather than the real credential.
- Probe controlled DNS/HTTP destinations, loopback, metadata endpoints, filesystem, subprocess, and package access.
- Revoke or rotate the test credential after the exercise and verify the old credential fails.
- Execute and verify cleanup, or explicitly preserve tagged fixtures through an approved retention record.

The separate optional-policy live oracle enables one semantic effect prompt with an administrator credential, then uses a separately authorized human approver. Real Hermes runs prove zero writes before the decision, approve-once success, denial with zero writes, timeout with zero writes, same-turn continuation, exact digest binding, and pending/decision audit evidence. This control cannot replace or steer the autonomous default-policy run.

## Extensive live-evaluation ledger

Every authenticated trial, including setup failures and model failures after dispatch, receives an immutable ledger row. No row may be deleted or reclassified out of the denominator.

Each row records:

- scenario and fixture IDs;
- fresh-seed digest;
- trial and stable invocation IDs;
- Plane and Hermes release commits and artifact digests;
- provider, model, endpoint adapter, model metadata, prompt, tool-schema, runtime, isolate, and configuration digests;
- UTC timestamps and wall-clock duration;
- approval decisions and actor identities;
- complete workflow verdict;
- authorization, approval, credential, isolation, duplicate-mutation, and audit violation counters;
- Plane object and audit readback references;
- transcript, generated TypeScript, trace, screenshot, and log digests;
- failure class and reviewed disposition.

The aggregate verifier recomputes all release metrics from ledger rows and raw evidence. A manually entered aggregate is insufficient.

## Negative-control qualification

- VM-018 removes one required manifest field in an isolated copy and must make VM-001 fail for the expected reason.
- VM-019 changes one authorization expectation in an isolated fixture and must make VM-004 fail for the expected principal/object pair.
- VM-020 resolves either the wrong provider or wrong model in an isolated run and must make the live verifier fail before the trial can count.
- VM-021 suppresses one required audit outcome in an isolated failure-injection stack and must make VM-006 fail for the expected invocation.
- The verifier itself passes only when each negative control produces its expected failure and the unmodified positive fixture passes.
- A negative control that fails for an unrelated setup error does not qualify the verifier.

## Clean-checkout execution contract

The final entry point must:

1. Verify clean Plane, Hermes, official MCP, and Plane Python SDK checkouts at the exact integration-lock commits.
2. Resolve release artifacts by immutable digest rather than rebuilding an unpinned candidate.
3. Validate release, verification, catalog, adapter, prompt, fixture, runtime, model-metadata, and configuration digests before tests run.
4. Execute VM-018 through VM-021 and qualify their expected failures.
5. Execute VM-001 through VM-017 with no skips or xpasses.
6. Recompute live metrics from all retained trial rows.
7. Emit a signed or content-addressed result index linking every raw evidence object.
8. Exit non-zero for missing evidence, digest mismatch, unapproved exception, wrong provider/model, check failure, skip, xpass, or negative-control sensitivity failure.

## Primary entry point

The proposed final command is `./scripts/agent-tooling/verify-release --integration-lock <approved-lock> --evidence <immutable-evidence-index>`. Its path and arguments are frozen by manifest approval even though the executable is pending implementation.

The final verifier must be executed independently from clean Plane and Hermes checkouts. It must prove its own sensitivity by passing VM-018 through VM-021 as expected failures before its positive result is accepted.
