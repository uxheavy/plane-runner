# Goal: Deliver the Non-UI Semantic Context Picker

## Observable outcome

Plane has a production-ready, tested semantic context picker foundation that a
separate UI branch can consume without reimplementing selection, domain context,
freshness, permissions, serialization, region capture, or visual fallback logic.

## Baseline

| Item | State at activation |
| --- | --- |
| Branch | `chat-semantic-context-picker-core` |
| Product and architecture | Defined in M0 and ADRs 0001-0002 |
| Implementation | Not started |
| Composer source | Absent from this checkout |
| UI | Owned by a separate user branch and excluded from this goal |
| Open dependency question | React Grab production suitability must pass M1 |

## Required scope

| Milestone | Required deliverable |
| --- | --- |
| M1 | Validate and isolate the React Grab selection primitives in production-like Plane behavior. |
| M2 | Implement versioned contracts, registry, point/region requests, failure types, and contract tests. |
| M3 | Resolve supported Plane entities and allowlisted fields from current client state. |
| M4 | Resolve Tiptap/Yjs blocks, ranges, embeds, and client-live values. |
| M5 | Reauthorize references and resolve canonical values through the existing Django permission model. |
| M6 | Ship fixtures, a dummy composer consumer, contract tests, and an integration guide. |
| M8 | Implement region deduplication and privacy-safe visual fallback infrastructure without presentation UI. |
| Core release verification | Pass the non-UI acceptance suite and produce a complete handoff record. |

## Explicit non-goals

- Composer activation controls, hover overlays, crosshairs, chips, previews, and
  user-facing errors.
- Actual composer transport wiring while its source is unavailable.
- Deployment, rollout infrastructure, analytics dashboards, or multi-user rollout.
- A public plugin system without two real implementations that require it.
- Browser extensions, a new service, or a language outside Plane's existing stack.

## Primary verifier

An automated non-UI integration harness must exercise the same exported contract
used by a future composer:

1. Register nested entity, field, editor, denied, detached, and region targets.
2. Preview without reading values.
3. Capture fresh MobX and Tiptap/Yjs values into JSON-safe version 1 bundles.
4. Hydrate through Django under allowed and denied users.
5. Verify deleted, stale, cancelled, sensitive, and partial-region outcomes.
6. Feed successful bundles into a dummy composer consumer with no Plane UI imports.

The harness must use the production public Interface. Adapter unit tests alone do
not satisfy this verifier.

## Supporting checks

| Check | Required evidence |
| --- | --- |
| Type and lint safety | Relevant package checks plus repository `pnpm check` pass. |
| Core behavior | Deterministic unit and contract tests cover every result variant and invariant. |
| Browser behavior | Production-like tests cover nested targets, portals, ignored surfaces, navigation, unmount, and cleanup. |
| Permissions | Django tests cover workspace roles, projects, private pages, deleted objects, and cross-project references. |
| Privacy | Allowlist and snapshot-denial tests prove that records, secrets, and denied pixels cannot escape. |
| Compatibility | Versioned fixtures parse in a consumer that does not import core Implementations. |
| Durability | ADRs, delivery status, worklog, integration guide, and final result match the implemented behavior. |

Exact commands and their final outputs must be recorded in `RESULT.md`. Any flaky
check requires three consecutive clean-state passes before it counts.

## Iteration loop

1. Read `WORKLOG.md`, current goal state, repository status, and the active milestone.
2. Inspect the relevant Plane source and proven upstream implementation.
3. Implement one reviewable vertical increment behind the accepted Interface.
4. Run the narrowest meaningful verifier, then affected package and regression checks.
5. Record evidence, failures, decisions, and the next action in `WORKLOG.md`.
6. Commit the verified increment as an atomic save point.
7. Continue until the primary verifier and all supporting checks pass.

## Anti-cheating rules

- Do not weaken, skip, delete, or rewrite a verifier merely to make it pass.
- Do not replace production seams with mocks in the primary integration harness.
- Do not narrow supported targets or permission cases without user approval and an ADR.
- Do not attach whole MobX records, arbitrary object paths, or unreviewed editor state.
- Do not treat DOM visibility or client references as authorization.
- Do not label visual fallback semantic or capture denied content as pixels.
- Do not hide failures, ignore unrelated regressions caused by this branch, or claim
  completion from type checks alone.

## Approval gates

Separate user approval is required before:

- pushing, opening or merging a pull request, deploying, or changing shared systems;
- performing external writes, sending messages, or publishing packages;
- changing the accepted product boundary, public wire format, or privacy policy;
- adding persistent visual storage or a new third-party service;
- modifying or merging the user-owned UI branch.

Local code, tests, reversible dependencies, documentation, and commits on this
feature branch are authorized by this goal.

## Blocker standard

Difficulty, a failed approach, a missing optional tool, or an ordinary test failure
is not a blocker. Preserve progress and choose the next safe approach. Mark the
goal blocked only after the same external condition prevents meaningful progress
for three consecutive goal turns and record the smallest action that would unblock
it. Composer absence blocks only actual UI/transport wiring, not the integration kit.

## Completion proof

The goal is complete only when:

- every required milestone has implementation and recorded evidence;
- the primary non-UI integration verifier passes from a clean state;
- all supporting checks pass, including the Django permission suite;
- no unresolved P0/P1 security, privacy, correctness, or integration finding remains;
- `RESULT.md` contains exact commands, outputs, changed contracts, known limitations,
  and the UI-branch handoff;
- the delivery plan and ADRs match the final implementation;
- the feature branch is clean after the final local commit.
