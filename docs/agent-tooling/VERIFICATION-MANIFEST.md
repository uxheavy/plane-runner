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

| ID     | Check                                    | Oracle                                                                                                                                                                                                                                                                                                                                                  | Environment                                     | Mocks                                | Required evidence                                                            |
| ------ | ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------- | ------------------------------------ | ---------------------------------------------------------------------------- |
| VM-001 | Documentation and manifest consistency   | No accepted/open contradictions; every completion criterion and release row has one current coverage mapping; required rows, named authorities, approvals, owners, promotion/retirement rules, and RESULT fields are present; no numeric threshold is lowered without approval                                                                          | Clean Plane checkout                            | No                                   | Validator log, coverage report, and approval digests                         |
| VM-002 | Deterministic catalog generation         | Repeated generation produces identical catalog digest                                                                                                                                                                                                                                                                                                   | Clean Plane checkout                            | No                                   | Digests and diff                                                             |
| VM-003 | Contract and schema matrix               | Every approved operation validates success and structured failures; property/fuzz suites cover schemas, pagination, idempotency keys, and untrusted operation results                                                                                                                                                                                   | Plane test stack                                | Unit-layer only                      | Full matrix, property, and fuzz logs                                         |
| VM-004 | Authorization matrix                     | Every relevant role, membership, object, revoked-agent, and cross-workspace boundary matches Plane policy                                                                                                                                                                                                                                               | Plane test stack                                | No policy mocks in integration proof | Matrix and audit readback                                                    |
| VM-005 | Autonomous execution matrix              | Authorized calls never pause; denied calls have no effects; no approval route, result state, broker credential, configuration, or persistence model exists; preflight only validates schema, references, authorization, budgets, and concurrency; every supported route crosses application services through the gateway with no direct-database bypass | Plane plus real Hermes                          | No in final layer                    | Routes, dependency inventory, schemas, events, state, and audit              |
| VM-006 | Audit durability                         | Intent and outcome exist for invalid, denied, failed, unknown, and successful attempts; injected audit failure follows approved fail semantics                                                                                                                                                                                                          | Plane test stack                                | Failure injection allowed            | Database/API readback and logs                                               |
| VM-007 | Mutation safety                          | Retry, lost response, duplicate delivery, race, and ambiguous result create no duplicate committed side effects                                                                                                                                                                                                                                         | Plane plus Hermes                               | Network fault injection allowed      | Object counts and invocation records                                         |
| VM-008 | Result and artifact limits               | Every source, wall, call, preflight, inline, final-output, stdout/stderr, preview, artifact-size/read/retention/cleanup, and audit-result boundary in the frozen limit table holds under exact-boundary and property/fuzz payloads                                                                                                                      | Plane plus Hermes                               | Generated payloads allowed           | Boundary matrix, size/property/fuzz logs, and cleanup evidence               |
| VM-009 | TypeScript isolate security              | Successful in-isolate liveness and authorized-callback controls bracket every traced denial probe; secrets stay hidden; DNS/HTTP, loopback, metadata, filesystem, subprocess, package, and spoofing probes fail for intended policy reasons                                                                                                             | Release isolate                                 | No bypass mocks                      | Probe matrix and host traces                                                 |
| VM-010 | Confused-deputy protection               | Callback is bound host-side to exact run, agent, tenant, operation budgets, and correlation; sibling and replay attacks fail                                                                                                                                                                                                                            | Release isolate plus gateway                    | No                                   | Negative-test log                                                            |
| VM-011 | Concurrency and load                     | Ordering, retry races, rate limits, simultaneous runs, approved sustained-load concurrency and duration, p95/p99, error rate, and recovery targets pass                                                                                                                                                                                                 | Release-like stack                              | No                                   | Metrics, traces, and retained soak report                                    |
| VM-012 | External MCP inventory and compatibility | Every pinned Python MCP tool satisfies the exact per-tool records, independent source inventories, set joins, disposition-specific proofs, and trace joins in `MCP-MAPPING-CONTRACT.md`; approved schema-version transitions and pinned real clients pass                                                                                               | Real MCP clients plus gateway                   | No                                   | Content-addressed mapping bundle, schema diffs, client versions, transcripts |
| VM-013 | Mandatory live project planning          | Frozen prompt through real Luna Hermes autonomously produces exact tagged artifacts within its authorized scope and leaks no control-project data; Computer Use verifies Plane and Hermes UI state                                                                                                                                                      | Authenticated Plane dev server plus real Hermes | None                                 | Transcript, traces, Computer Use screenshots, UI/API and audit readbacks     |
| VM-014 | Extensive live evaluation                | All 50 retained authenticated trials meet release gates without fallback; a changed provider revision or model-metadata fingerprint invalidates prior live evidence and requires the complete live suite again                                                                                                                                          | Authenticated Plane dev server plus real Hermes | None                                 | Trial ledger, fingerprint/invalidation record, and aggregate report          |
| VM-015 | Operator lifecycle                       | Provision, permissions, credential issue/store/rotate/revoke, old-credential denial, audit lookup/retention, metrics/traces/alerts, feature and kill switches, incident response, recovery, and rollback runbooks succeed                                                                                                                               | Release-like stack                              | No                                   | Exercise logs, alert evidence, and readbacks                                 |
| VM-016 | Production provenance                    | Named gate authorities and complete RESULT proof resolve reviewed commits through integration lock, build artifacts, deployment IDs, migrations, catalogs, runtime, and enabled configuration                                                                                                                                                           | CI and deployment systems                       | No                                   | Signed or immutable provenance and RESULT records                            |
| VM-017 | Production canary and rollback           | Every frozen rollout cohort, entry condition, observation duration, exit metric, approval field, immediate security trigger, and rolling metric trigger is exercised; real permitted/denied canaries, audit, feature controls, and LKG rollback pass                                                                                                    | Production                                      | None                                 | Promotion, deployment, trigger, and readback evidence                        |
| VM-018 | Documentation negative controls          | Removing a required manifest field, changing one source requirement without updating its coverage digest, or lowering a numeric threshold without matching recorded approval makes VM-001 fail for the intended row                                                                                                                                     | Isolated manifest fixtures                      | Controlled mutation required         | Expected failing logs and positive control                                   |
| VM-019 | Authorization negative control           | Deliberate policy mismatch makes VM-004 fail                                                                                                                                                                                                                                                                                                            | Isolated test fixture                           | Controlled mutation required         | Expected failing log                                                         |
| VM-020 | Model fallback negative control          | Deliberate fallback or wrong model makes live verifier fail                                                                                                                                                                                                                                                                                             | Isolated harness configuration                  | Controlled misconfiguration required | Expected failing log                                                         |
| VM-021 | Audit negative control                   | Suppressed audit outcome makes VM-006 fail                                                                                                                                                                                                                                                                                                              | Isolated failure fixture                        | Controlled fault required            | Expected failing log                                                         |
| VM-022 | MCP mapping negative controls            | Each isolated mutation in `MCP-MAPPING-CONTRACT.md` makes VM-012 fail for its exact intended tool, branch, edge, graph, route, semantic mapping, behavior/capability, evidence, schema-transition, disposition-policy, or trace invariant                                                                                                               | Isolated mapping fixtures                       | Controlled mapping mutation required | Expected failing logs and positive control                                   |
| VM-023 | Verifier aggregation negative controls   | A non-recursive outer qualifier substitutes a signed synthetic failing, missing, ignored, or false-pass result for each final required VM-001 through VM-023 slot in turn; the primary entry point fails for that exact check, including its VM-023 result slot                                                                                         | Isolated verifier-result fixtures               | Controlled result mutation required  | Per-check expected failure logs and positive control                         |

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
| Verifier sensitivity and independence | VM-018 through VM-023 plus final clean-checkout execution |

Before this verification manifest can be approved, `REQUIREMENT-COVERAGE.md` must map every completion criterion, primary-verifier obligation, completion-proof field, and every row in the approved release manifest to at least one check, one observable oracle, and one immutable evidence record. The documentation validator fails when a source requirement is missing, duplicated, stale, or has zero checks.

## Mandatory live-project oracles

- Use one frozen initial prompt and no human steering for the autonomous run.
- Use a separate verifier principal for Plane API and UI readback.
- Add a unique non-authoritative run tag to expected artifacts.
- Prove authorized operations create no pending human-confirmation state.
- Trace actual native tool calls.
- Trace actual `docs`, `search`, and `execute` calls.
- Preserve generated TypeScript and its digest.
- Trace concurrent safe reads and every inner gateway call.
- Verify exactly one tagged parent, three tagged children, and one tagged source comment after autonomous execution.
- Replay the same stable invocation keys and verify counts remain unchanged.
- Verify audit for authorization, success, retry, denial, and any failure.
- Verify no inaccessible control-project object data appears in model-visible output, logs, artifacts, or audit summaries.
- Probe credential isolation using a harmless host-only canary rather than the real credential.
- Probe controlled DNS/HTTP destinations, loopback, metadata endpoints, filesystem, subprocess, and package access.
- Revoke or rotate the test credential after the exercise and verify the old credential fails.
- Execute and verify cleanup, or explicitly preserve tagged fixtures through an approved retention record.

## Extensive live-evaluation ledger

Every authenticated trial, including setup failures and model failures after dispatch, receives an immutable ledger row. No row may be deleted or reclassified out of the denominator.

Each row records:

- scenario and fixture IDs;
- fresh-seed digest;
- trial and stable invocation IDs;
- Plane and Hermes release commits and artifact digests;
- provider, model, endpoint adapter, model metadata, prompt, tool-schema, runtime, isolate, and configuration digests;
- UTC timestamps and wall-clock duration;
- complete workflow verdict;
- authorization, credential, isolation, duplicate-mutation, and audit violation counters;
- Plane object and audit readback references;
- transcript, generated TypeScript, trace, screenshot, and log digests;
- failure class and reviewed disposition.

The aggregate verifier recomputes all release metrics from ledger rows and raw evidence. A manually entered aggregate is insufficient.

`EVALUATION-SCENARIOS.md` defines the exact scenario contracts and live-trial allocation. Manifest approval freezes both documents together.

## Negative-control qualification

- VM-018 separately removes one required manifest field, changes one source requirement without its coverage digest, and lowers one numeric threshold without approval; each isolated mutation must make VM-001 fail for the expected reason.
- VM-019 changes one authorization expectation in an isolated fixture and must make VM-004 fail for the expected principal/object pair.
- VM-020 resolves either the wrong provider or wrong model in an isolated run and must make the live verifier fail before the trial can count.
- VM-021 suppresses one required audit outcome in an isolated failure-injection stack and must make VM-006 fail for the expected invocation.
- VM-022 independently mutates every exact MCP mapping dimension named in `MCP-MAPPING-CONTRACT.md` and must make VM-012 fail for the exact intended validator invariant rather than an unrelated setup error.
- VM-023 uses an outer harness that is not itself one of the primary entry point's input results. It first validates a signed positive set for VM-001 through VM-023, then substitutes a failing, missing, ignored, and false-pass signed result for each slot in turn; the primary entry point must reject every mutation for that exact check without recursively invoking VM-023.
- The verifier itself passes only when each negative control produces its expected failure and the unmodified positive fixture passes.
- A negative control that fails for an unrelated setup error does not qualify the verifier.

## Clean-checkout execution contract

The final entry point must:

1. Verify clean Plane, Hermes, official MCP, and Plane Python SDK checkouts at the exact integration-lock commits.
2. Resolve release artifacts by immutable digest rather than rebuilding an unpinned candidate.
3. Validate release, verification, catalog, adapter, prompt, fixture, runtime, model-metadata, and configuration digests before tests run.
4. Execute VM-018 through VM-023 and qualify their expected failures.
5. Execute VM-001 through VM-017 with no skips or xpasses.
6. Recompute live metrics from all retained trial rows.
7. Emit a signed or content-addressed result index linking every raw evidence object.
8. Exit non-zero for missing evidence, digest mismatch, unapproved exception, wrong provider/model, check failure, skip, xpass, or negative-control sensitivity failure.

## Primary entry point

The proposed final command is `./scripts/agent-tooling/verify-release --integration-lock <approved-lock> --evidence <immutable-evidence-index>`. Its path and arguments are frozen by manifest approval even though the executable is pending implementation.

The final verifier must be executed independently from clean Plane, Hermes, official MCP, and Plane Python SDK checkouts at the exact integration-lock commits. It must prove its own sensitivity by passing VM-018 through VM-023 as expected failures before its positive result is accepted.
