# Durable Goal: Plane Agent Tooling to Production

## Outcome

Deliver Plane's agent-tooling architecture as a production-ready, independently verified system:

- Plane-native agents use native semantic Plane tools.
- Plane-native agents use self-hosted TypeScript composition with progressively discovered Plane operations; final model-facing tool names remain a catalog decision.
- Native tools, Code Mode callbacks, and the supported external MCP compatibility path share the Plane Operation Gateway.
- Plane identity, live authorization, mutation safety, bounded results, versioning, and append-only auditing hold for every operation.
- Generated code receives neither Plane credentials nor direct database access.
- Operators have rollout controls, observability, credential procedures, incident runbooks, and rollback evidence.
- The approved production rollout is completed and verified.

## Audience and destinations

- Plane-native agent users and workspace administrators.
- External agents using Plane's supported Python MCP compatibility interface.
- Plane and Hermes maintainers and production operators.
- Canonical program state lives in `/Users/nqh/Desktop/CODES/plane/docs/agent-tooling/`.
- Plane implementation lives in `/Users/nqh/Desktop/CODES/plane`.
- Hermes integration lives in `/Users/nqh/Desktop/CODES/hermes-agent`.
- External MCP compatibility lives in the `external/plane-mcp-server` submodule sourced from `uxheavy/plane-mcp-server`.
- Shared Python gateway transport lives in the `external/plane-python-sdk` submodule sourced from `uxheavy/plane-python-sdk`.

## Baseline

Observed on 2026-07-29:

- Plane branch `codex/agent-tooling-architecture` contains the product, architecture, delivery, decision, and ADR baseline.
- Plane agent-tooling implementation has not started.
- Hermes already provides native tool registration, Tool Search, concurrent tool execution, session persistence, and oversized-result spill.
- Hermes Code Mode currently executes Python rather than the required TypeScript surface.
- Hermes keeps downstream credentials host-side and scrubs generated-code environments.
- Hermes API caller authentication is currently a shared long-lived bearer credential.
- Plane's existing Python MCP remains the external compatibility interface.

## Material constraints

- Preserve every accepted decision in `decision-register.md` unless a new ADR explicitly supersedes it.
- Prefer the smallest architecture that satisfies the production gates.
- Reuse Hermes mechanisms when their boundaries fit.
- Keep Plane authorization as the sole entitlement authority.
- Use one revocable Plane credential per dedicated agent identity initially.
- Do not add direct database access for agents.
- Do not expose Plane credentials to generated TypeScript.
- Do not add runtime human-confirmation prompts for otherwise-authorized agent operations.
- Preserve external Python MCP compatibility during migration.
- Keep observable contracts additive unless an approved compatibility plan says otherwise.
- Preserve unrelated user changes in every repository.
- Run the mandatory live and evaluation harness through Hermes provider `openai-codex`.
- Pin the mandatory live and evaluation harness to model `gpt-5.6-luna`.
- Use the locally authenticated ChatGPT subscription without copying its credentials into Plane, generated code, logs, fixtures, or result artifacts.
- Treat any silent provider or model fallback as a verifier failure.
- Obtain explicit user approval for `APPROVAL-MANIFEST.md` before implementation begins.
- Treat `RELEASE-MANIFEST.md` and `VERIFICATION-MANIFEST.md` as non-normative design references rather than implementation gates.
- Require every production requirement in the approved `APPROVAL-MANIFEST.md` to pass or carry an explicitly approved exception.
- Pin compatible Plane, Hermes, official MCP, and Plane Python SDK commits plus generated-contract digests in a cross-repository integration lock.

## Non-goals

- Replacing Plane's user, membership, role, or object-permission model.
- Building a second tool-specific permission system.
- Adding run-bound capability-token infrastructure to the initial release.
- Rewriting Hermes mechanisms that already satisfy the contract.
- Automatically pushing, merging, deploying, purchasing services, or mutating shared environments without approval.

## Completion criteria

### Product and contract

- Named pilot and general-availability workflows are documented.
- Numeric success and reliability targets are approved.
- Supported operations have stable typed contracts and structured errors.
- OpenAPI generation and curated overlay produce a deterministic searchable catalog.
- Eager native-tool promotion and retirement rules are documented.
- The approved release manifest freezes exact workflows, operations, eager tools, MCP dispositions, versions, cohorts, and numeric gates.
- The approved verification manifest maps every completion criterion to an independently observable check and oracle.

### Plane Operation Gateway

- All supported native, Code Mode, and migrated MCP operations cross the gateway.
- The gateway derives the acting agent from its credential.
- Live Plane authorization runs for every operation.
- Idempotency, result shaping, version metadata, and append-only audit are enforced.
- No supported operation bypasses Plane application services through direct database access.
- Audit intent and outcome durability covers invalid, unauthorized, execution-failed, unknown, and successful attempts.
- Injected audit-storage failures follow an approved fail-closed or durable-outbox policy without unaudited successful mutation.

### Hermes and TypeScript Code Mode

- The Plane-native runtime profile exposes the approved eager Plane-domain tools while Hermes remains the hidden execution kernel.
- Deferred operations are discoverable through Tool Search and Code Mode.
- The approved progressive-discovery and TypeScript-composition interfaces are implemented with their frozen names and schemas.
- Generated code runs in the disposable runtime-invocation container inside the approved restricted child isolate.
- Generated code has no ambient Plane credentials, arbitrary network, package installation, subprocess, or unrelated filesystem access.
- Credential-free host callbacks retain Hermes tool IDs, middleware, concurrency, and Plane audit correlation.
- The local callback channel is bound host-side to the exact run, agent, tenant, operation budgets, and correlation identifiers.
- Generated code cannot supply authoritative identity or correlation fields.
- Sibling-process, cross-run replay, and forged-callback attempts fail.

### Reliability and safety

- Pilot mutations have tested idempotency or explicit `outcome_unknown` behavior.
- Unknown non-idempotent outcomes are never retried blindly.
- Model-visible per-result and cumulative output are bounded.
- Oversized results use temporary bounded-read artifacts with verified cleanup.
- Authorization, sandbox, concurrency, interruption, timeout, retry, and container-death test matrices pass.
- External MCP compatibility tests pass for approved clients and operations.

### Mandatory live Hermes acceptance

- A real Hermes process runs against the authenticated Plane development server.
- Hermes uses the locally authenticated ChatGPT subscription through provider `openai-codex`.
- Hermes uses the exact canonical model ID `gpt-5.6-luna`.
- Run evidence records the resolved provider and model.
- A run resolved to any fallback provider or model fails acceptance.
- The run uses a dedicated Plane test-agent identity and host-held credential.
- The run uses the real Plane Operation Gateway rather than a mocked gateway.
- A seeded allowed project contains a current cycle, representative open work items, blockers, dependencies, priorities, and ownership gaps.
- A seeded control project is inaccessible to the test agent.
- Hermes is asked to analyze release readiness without modifying the seeded source work items.
- Hermes uses native tools for common project context.
- Hermes uses TypeScript Code Mode to discover, filter, and compose the broader project analysis.
- Independent reads execute concurrently where safe.
- Hermes proposes one parent release-plan work item and three coordinated child work items for the highest-impact actions.
- The broad write executes autonomously after authorization.
- Plane creates exactly one parent work item, exactly three child work items, and exactly one source-linked planning comment.
- Retrying the same stable invocations creates no duplicate planning artifacts.
- Hermes returns links to every created Plane object.
- Plane UI or API readback verifies content, hierarchy, project placement, and source references.
- Plane audit readback correlates agent identity, Hermes run, turn, tool calls, invocations, operations, and affected object IDs.
- A real attempt to access the control project returns a structured denial without object-data leakage.
- A generated-TypeScript probe confirms Plane credentials are unavailable.
- A generated-TypeScript probe confirms Plane cannot be reached except through the host callback.
- The complete prompts, run IDs, created object IDs, readbacks, audit references, and cleanup procedure are recorded in `RESULT.md`.

### Operations and rollout

- Metrics, traces, alerts, feature flags, mutation and Code Mode kill switches, credential rotation, audit retention, incident response, and rollback runbooks exist.
- Load and latency targets pass at the approved production profile.
- Realistic agent workflow evaluations meet their approved targets.
- A clean-state rollback rehearsal succeeds.
- Each controlled rollout stage has recorded evidence and approval.
- Production verification succeeds after deployment.

### Extensive testing and evaluation

- A version-controlled evaluation manifest covers at least 50 distinct scenarios.
- The manifest covers functional, authorization, mutation, concurrency, sandbox, result, compatibility, observability, rollback, and operator-recovery behavior.
- The mandatory project-planning workflow runs live through Hermes on at least ten materially different seeded project shapes.
- Each seeded project shape passes at least three independent `gpt-5.6-luna` runs.
- At least 20 additional live Luna runs cover denials, partial failure, idempotent retry, ambiguous outcome, large results, and hostile generated code.
- Live evaluation therefore includes at least 50 authenticated Hermes runs before production approval.
- Complete workflow success is at least 90% across all retained live attempts.
- Security-critical expectations tolerate zero authorization bypasses, credential disclosures, sandbox escapes, duplicate committed mutations, or missing required audit records for any attempted operation.
- Deterministic test matrices cover every supported pilot operation and every relevant Plane role or permission boundary.
- Property or fuzz tests cover schema validation, pagination, idempotency keys, result limits, and untrusted operation results.
- Concurrency tests cover simultaneous runs, concurrent inner calls, result ordering, retry races, and rate limiting.
- Compatibility tests cover the approved Python MCP client matrix and schema-version transitions.
- A sustained load or soak run executes at the approved production concurrency and duration.
- Deterministic contract and security matrices pass at 100% with zero skips or xpasses.
- The complete deterministic suite passes twice from clean state.
- The exact release artifact passes three consecutive final verification runs.
- The live Luna acceptance and evaluation suite passes from a fresh Hermes process and freshly seeded Plane fixtures.
- Computer Use verifies the user-visible Plane and Hermes UI state and captures screenshots for the mandatory live acceptance.
- Exact numeric task-success, latency, and load targets are approved before the production gate and cannot be lowered without recorded approval.

## Primary verifier

Before completion, the repositories must expose one documented, version-controlled production-verification entry point callable from a clean checkout. It must fail non-zero when any required Plane contract, backend, Hermes integration, authorization, sandbox, mutation-safety, MCP compatibility, or end-to-end check fails.

The final command and its environment prerequisites must be recorded in `RESULT.md`. Production deployment also requires an authenticated post-deployment readback proving the enabled version, a permitted workflow, a denied workflow, audit correlation, and rollback readiness.

The primary verifier must invoke or require the mandatory live Hermes acceptance scenario. A mocked agent loop, mocked gateway, or database-only fixture assertion cannot satisfy this requirement.

The verifier must assert the resolved Hermes provider is `openai-codex` and the resolved model is `gpt-5.6-luna`. Model availability, authentication failure, or fallback must fail non-zero rather than skip live evaluation.

The frozen system prompt, acceptance prompt, tool schemas, sampling parameters, context limits, seeded-data manifest, Plane, Hermes, official MCP, and Plane Python SDK commits, catalog and adapter digests, Plane configuration, and TypeScript runtime digest must accompany live evidence. A changed provider model fingerprint invalidates prior live evidence and triggers the full live suite again.

Final verification is executed independently from clean checkouts. It records full immutable logs, UTC timestamps, exit codes, dependency and container digests, skip and xpass counts, and reviewer identity.

## Supporting checks

- Plane formatting, lint, type, unit, backend, migration, and targeted integration checks.
- Hermes formatting, lint, unit, integration, and gateway checks.
- Deterministic catalog generation and schema compatibility checks.
- Permission-matrix and revoked-agent tests.
- Autonomous admission, denial-without-effects, concurrent sibling, interruption, and restart-failure tests.
- Credential-exfiltration and sandbox-escape tests.
- Idempotency, ambiguous outcome, and duplicate-delivery tests.
- Result-budget and artifact-expiry tests.
- Representative external MCP client compatibility checks.
- Clean-checkout and clean-state reproduction.
- Evaluation-manifest coverage check for the required 50 scenarios.
- At least 50 authenticated live Hermes runs using `gpt-5.6-luna`.
- Two consecutive clean-state passes of the complete deterministic suite.
- Computer Use screenshots and readbacks for user-visible Plane and Hermes state.

## Iteration loop

1. Inspect the active goal, worklog, repository state, and next unsatisfied gate.
2. Resolve factual uncertainty from canonical source or primary documentation.
3. Ask the user only when a missing choice changes the product boundary or grants consequential approval.
4. Implement the smallest meaningful vertical increment.
5. Run the strongest relevant verifier and regression checks.
6. Record commands, outputs, failures, decisions, and next action in `WORKLOG.md`.
7. Commit one validated logical change on the correct repository branch.
8. Continue while a safe relevant action remains.

## Anti-cheating rules

- Do not weaken, skip, delete, or narrow a verifier to obtain a pass.
- Do not replace real authorization, sandbox, or gateway behavior with mocks in the production end-to-end proof.
- Do not silently shrink supported workflows or operations.
- Do not count documentation, generated fixtures, or model claims as implemented behavior.
- Do not hide skipped checks, flaky failures, warnings, or unavailable dependencies.
- Do not change numeric targets, compatibility baselines, or completion criteria without recording approval.
- Do not claim production readiness from development-only or single-happy-path evidence.
- Do not count a run using a fallback provider or model toward live evaluation totals.
- Do not reuse one recorded model output as evidence for multiple independent runs.
- Do not omit failed live runs from the evaluation denominator.

## Delivery and release approval gates

These gates govern Codex delivery actions, manifest freeze, rollout promotion, and deployment. They do not add a human-confirmation step to deployed Plane agent operations.

Separate user approval is required before:

- Pushing either repository branch.
- Creating or updating a pull request.
- Merging to a shared branch.
- Applying migrations to a shared environment.
- Enabling the feature for users outside the approved test scope.
- Deploying to staging or production.
- Rotating or revoking shared credentials.
- Deleting or destructively rewriting material data.
- Purchasing or provisioning a paid external service.
- Making an incompatible public API or MCP contract change.
- Approving or revising the release manifest.
- Approving or revising the verification manifest after implementation begins.
- Setting or lowering numeric production thresholds.
- Selecting the final TypeScript isolate and threat boundary.
- Excluding or deprecating an external MCP operation or client.
- Accepting a security exception or residual risk.
- Promoting each rollout stage.

## Delegation and resources

The primary agent owns product scope, integration, conflict resolution, verification, and completion. It may use available skills, tools, MCP servers, installed plugins, and bounded subagents when they materially improve delivery.

Delegated lanes must state their objective, non-goals, file or system ownership, verifier, stop condition, and returned evidence. Independent security and final-verifier reviews must not be performed solely by the implementation lane. No child goal is active initially.

## Blocker standard

Difficulty, uncertainty, long runtime, a failing test, or a useful unanswered investigation is not a blocker. Record the failure and continue with the smallest safe next action.

Mark the durable goal blocked only when the same external condition prevents meaningful progress for the required repeated goal turns and no authorized alternative remains. Record the exact condition, evidence, preserved partial work, and smallest user or external action that would unblock it.

## Completion proof

`RESULT.md` must contain:

- Final Plane, Hermes, official MCP, and Plane Python SDK commit IDs and clean status.
- The production-verification command and complete passing output summary.
- Required focused test commands and results.
- Catalog and public compatibility evidence.
- Security-review findings and their disposition.
- Load, latency, workflow-evaluation, and reliability results.
- Migration and rollback rehearsal evidence.
- Production deployment approval and deployment identifier.
- Post-deployment permitted and denied workflow readbacks.
- Mandatory live Hermes acceptance evidence from the authenticated Plane development server.
- Resolved `openai-codex` provider and `gpt-5.6-luna` model evidence for every counted live run.
- Evaluation manifest, aggregate metrics, and all failed-run dispositions.
- Computer Use screenshots of the final Plane and Hermes acceptance state.
- Correlated audit evidence with secrets redacted.
- Known residual risks and explicit acceptance.
- Approved `APPROVAL-MANIFEST.md` version.
- Independent verifier identity and immutable full-log references.
- Reviewed commits mapped through build artifacts to deployment identifiers and enabled configuration.

The goal may be marked complete only after this evidence exists and every production requirement in the approved `APPROVAL-MANIFEST.md` passes or has an explicitly approved exception.
