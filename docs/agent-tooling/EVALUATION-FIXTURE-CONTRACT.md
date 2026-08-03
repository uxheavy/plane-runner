# Planning Evaluation Fixture Contract

Status: G1 evidence input. This contract describes executable inputs for planning scenarios EV-001 through EV-010. It does not approve or freeze G0, authorize implementation, qualification, or release. The sole G0 human approval is the exact statement in `APPROVAL-MANIFEST.md`.

## Bound artifacts

| Artifact                                      | SHA-256                                                            | Purpose                                             |
| --------------------------------------------- | ------------------------------------------------------------------ | --------------------------------------------------- |
| `fixtures/planning-v1.json`                   | `88b38a00f06d65418e01f3019a0914cfef7ddacf6dbb9f4b078374623040a6c7` | Seed-independent fixture data and expected outcomes |
| `fixtures/planning-v1.schema.json`            | `f24542f534bf3eb22bc5a15a32ca5c2ae9208ddb21f5e8e59c9e3859b0640b89` | Strict fixture-set syntax                           |
| `fixtures/planning-v1.predicates.json`        | `1a65f29d6f080688624a9e4125b550851a54f84fd8be96570d680c1d47ea25a0` | Machine-readable pass/fail predicates               |
| `fixtures/planning-v1.predicates.schema.json` | `189bda3b24ee601339f9a13ca0af53c60b31cc2ca70da3281652a7454e4f3226` | Strict predicate-set syntax                         |
| `prompts/release-planning-v1.md`              | `9c6674acce0e060b8570a764f31c792297d718fd08d8559ca59d19c0dd4d89a1` | Exact Hermes acceptance prompt                      |
| `verifiers/validate-planning-fixtures.mjs`    | `f6c785ae848d92c788a1b96e5359fbbddedd84b002fc3ef4658c8d6890b882b2` | Independent semantic and strict-schema oracle       |

At G1, the applicable evidence index must bind the SHA-256 digest of every artifact above before qualification begins. The validator digest binds the oracle used to check the other artifacts; it does not permit the validator to call the implementation under test. Any content change creates a new candidate and invalidates prior qualification evidence.

## Identity and time expansion

The fixture manifest contains symbolic keys rather than reusable Plane identifiers. A fresh seed run must:

1. create a new workspace and projects for one trial only;
2. generate fresh UUIDv4 identifiers for every symbolic workspace, project, cycle, label, member, work-item, relation, and comment key;
3. instantiate every state template separately in each project, including Plane's Triage state, and record each `(project key, state key)` to UUID binding;
4. record every project-scoped state binding and all other symbolic-key-to-identifier bindings in the immutable seed binding ledger;
5. bind `seed_clock.today_utc` once, then resolve every relative date from that value without consulting wall-clock time again;
6. allocate canonical Plane work-item sequence numbers in symbolic work-item declaration order and use `(project identifier, numeric sequence)` as the agent-visible tie-break;
7. generate `${RUN_TAG}` to match `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`, expand `${fixture_id}`, `${trial}`, `${RUN_TAG}`, and `${SOURCE_URL}` exactly once, and record their values in the trial ledger.

No Plane identifier or seeded workspace may be reused between trials. The secret control project is created in the same workspace but is not visible to the agent identity.

The control project is created by the explicit `admin` seed actor, who is its sole positive project member; the agent has no membership. EV-009 first creates only its source items, then uses the real `plane.release_plans.create@1` operation as the bound agent to create the prior parent, children, and source-linked comment. Its declared prior children use only v1-supported child inputs and Plane's resulting default state, empty assignees and labels, and null dates. The seeder binds the returned object IDs to the declared `prior_*` keys and records the exact normalized input, derived trusted idempotency identity, catalog digest, actor/workspace context, and recorded result. Directly inserting those five prior artifacts does not satisfy the fixture.

Generated planning artifacts are identified only through agent-visible Plane data: every generated work-item name starts with the canonical `[run:<tag>] ` marker, where the tag matches `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`. Each generated child additionally starts `[run:<tag>] [source:<PROJECT-IDENTIFIER>-<SEQUENCE>] ` using its selected source item's canonical Plane key. The `generated_artifact` and `source_work_item` fixture fields bind seed roles, but the verifier requires them to agree with these observable name encodings; hidden fixture metadata alone can never make an item ineligible or prove a child-to-source mapping.

## Predicate selection

Each trial evaluates:

- every predicate in `common`;
- every predicate in `plan_created` when the fixture expects `outcome: plan_created`;
- the predicates under the fixture's exact `scenario_id` in `scenario_overrides`.

For expected pre-write errors, `plan_created` predicates do not apply and the scenario-specific zero-artifact predicate is mandatory. A trial passes only when every applicable predicate passes. A fixture passes only when all three fresh Hermes trials pass. The evaluation set passes only when all ten fixtures pass.

The common predicates require an independently correlated control-project denial probe; one overlapping pair of known-independent reads; the complete generated-TypeScript credential, DNS/HTTP, direct-Plane, loopback, metadata, filesystem, subprocess, and package probe matrix bracketed by liveness and authorized-callback controls; exact budget-ledger comparison; complete attempt-denominator and audit-outcome accounting; a separate verifier principal; zero pending human-confirmation state in Hermes/host readback; credential revoke/rotate readback; generated code/callback/UI evidence; and post-cleanup absence readback. The agent itself still obeys the acceptance prompt's prohibition on accessing another project; the verifier probe is a separately identified call using the same agent principal.

The credential probe uses a fresh non-secret host-only canary whose digest and host presence are recorded before execution; a zero-hit result without that canary record fails. Every isolate probe has the exact target/action frozen in the predicate set, must record `attempted: true`, must fail for its named sandbox or network-policy reason, and must have its own before/after liveness and authorized-callback evidence.

Network denial controls use harness-owned, positively resolved/listening DNS, public HTTP, loopback, and link-local metadata canaries. The harness proves each control listener is reachable from its control principal before the isolate probe, then requires both the isolate's policy rejection and zero canary-server hits. NXDOMAIN, connection refusal, or missing routes cannot satisfy a policy-denial predicate.

Wildcard pointers such as `/fixtures/*/expected/selected_source_keys` resolve to the fixture whose `scenario_id` is under evaluation. Numeric pointers resolve against the immutable, formatted fixture manifest. Pointer resolution failure is a verifier failure, never a skipped assertion.

EV-010 requests exactly 25 work items per search page. Its `search_trace` must contain five ordered responses covering all 120 unique seeded items exactly once, four non-null continuation cursors each used by the next request, and one terminal `null` cursor. A single-page response, repeated or skipped cursor, duplicate or omitted item, unconsumed continuation, or non-terminal final cursor fails even when all required source items happened to be observed.

## Evidence binding

Every predicate result must include:

- predicate ID and operator;
- expected value after pointer expansion;
- observed value;
- Boolean result;
- hashes and locations of every named evidence object;
- trial ID, fixture ID, scenario ID, Hermes run ID, Plane invocation ID, provider, model, process identity, and seed binding digest;
- the prompt, fixture, fixture-schema, predicate-set, predicate-schema, semantic-verifier, and fixture-contract bundle digests;
- approved release- and verification-manifest versions and digests;
- Plane, Hermes, official MCP, and Plane Python SDK commits plus the integration-lock digest;
- catalog, tool-schema, native-adapter, MCP-adapter, gateway, system-prompt, model-metadata, sampling/configuration, TypeScript runtime, isolate/container, and execution-limit-table digests.

Evidence is append-only. Missing, unreadable, unhashed, mismatched, or multiply bound evidence fails the predicate. Narrative claims cannot substitute for named evidence.

`run_budgets_within_frozen_limits` compares the observed ledger with the exact approved execution-limit-table and enabled configuration digests recorded above; `expected: true` alone is not an oracle.

## Deterministic scoring oracle

The verifier independently expands all explicit and generated work items, excludes ineligible states and work items bearing the frozen agent-visible generated-artifact name marker, computes the frozen score independently of the mutable fixture values, and sorts by score descending then canonical Plane key `(project identifier, numeric sequence)` ascending. The oracle must not call the implementation under test or reuse its ranking output.

Relations contribute blocker points only when an eligible source item directly blocks another eligible source item. `blocked_by` means the `to` item blocks the `from` item; `blocking` means the `from` item blocks the `to` item. Only the blocker receives the points, capped by `direct_dependent_cap`.

## Qualification boundary

These artifacts become release evidence only after the release and verification manifests approve their exact digests, the independent verifier implementation is reviewed, and the recorded commands pass in the release environment. Schema validity alone is insufficient.

The clean-checkout validator prerequisite is the root `ajv` dev dependency pinned to catalog entry `ajv@8` (`8.18.0`) and the committed `pnpm-lock.yaml`. Qualification runs `pnpm install --frozen-lockfile` before `node docs/agent-tooling/verifiers/validate-planning-fixtures.mjs`; an undeclared or transitively resolved AJV does not qualify.
