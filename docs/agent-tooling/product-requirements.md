# Product Requirements

## Problem

Plane agents need to drive assigned outcomes through Plane without receiving database access or credentials. A general-purpose execution personality and large flat tool list do not feel like a native Plane teammate, while an ungoverned code-execution surface can bypass product authorization and auditing.

Plane already has an external Python MCP server. Plane agents do not need the latency and lifecycle cost of an internal MCP hop, but internal and external integrations should converge on the same supported Plane operations.

## Users

### Plane-native agents

Agents managed by Plane. They receive a Plane-owned behavioral profile, exactly one role, native semantic operations for common work, and TypeScript composition for broader available operations. Users and models experience one Plane Agent product.

### External agents

Third-party clients using the supported Plane MCP server through OAuth or personal access tokens.

### Plane administrators and operators

People who configure agent identities, permissions, credentials, retention, and operational limits.

### Auditors

People who investigate what an agent attempted, what Plane allowed, and what changed.

## Required outcomes

- An internal agent can discover supported Plane operations without loading the full catalog into model context.
- An internal agent begins with Plane identity, assignment, current context, and available-operation metadata rather than a generic everyday-agent posture. Plane authorization remains live and final.
- An internal agent does not inherit the `hermes-cli` default tool catalog.
- An internal agent can use common Plane operations as direct native tools.
- An internal agent can compose multiple supported operations in model-written TypeScript.
- Generated code cannot access Plane credentials.
- Generated code cannot bypass Plane authorization.
- Every attempted operation produces correlated audit evidence.
- Large results do not exhaust the model context window.
- Mutations are safely retryable when idempotency is available.
- Ambiguous mutation outcomes are reported explicitly.
- External MCP compatibility remains supported during migration.

## Agent model and roles

Plane uses one underlying Agent product/runtime model. Every configured agent has exactly one role. The built-in roles are worker, delegator, gardener, chief of staff, HR, and evaluator; workspace administrators may define additional custom single roles on the same model.

- Every human automatically receives one chief-of-staff agent. It operates only within that human's current live Plane permissions.
- The dedicated delegator dynamically plans each case, automatically assigns unclaimed work to humans or agents, and records why. Workers and ordinary specialist agents do not freely delegate.
- Approved schedules create normal assignments and runs. There is no saved or versioned workflow-definition product; the delegator plans each case dynamically.
- Gardeners may maintain multiple agents and curate private memory and skills across sessions. Knowledge is never copied between agents. Gardener improvements may apply automatically, but every revision is immutable and rollbackable.
- HR proposes agent creation, change, or retirement; a workspace administrator approves the proposal.
- Evaluators review every agent outcome before a human accepts or returns it. Human acceptance remains final.

## Non-goals

- Direct agent access to the Plane database.
- Replacing Plane's existing permission model.
- Creating a second tool-specific permission model.
- Giving generated code ambient network access.
- Giving generated code package-installation or subprocess access.
- Replacing the external Python MCP server in the initial release.
- Adding runtime human-confirmation prompts for otherwise-authorized agent operations.
- Exposing every operation as an eager native tool.

## Product principles

- Plane remains the authority for identity, membership, roles, and object permissions.
- Native tools improve ergonomics rather than confer privilege.
- The complete supported operation catalog remains discoverable.
- Full Plane integration/action coverage is required before the non-UI program is complete.
- Common Plane work should be simple without restricting advanced composition.
- Initial tool context should contain a small universal Plane work core plus assignment-relevant operation schemas.
- Other available operations outside the initial context should remain discoverable.
- Failure must be explicit, structured, and safe to retry only when proven safe.
- The first release should be narrow enough to validate but complete enough to exercise production risks.
- Adaptive disclosure keeps the complete catalog discoverable without exposing every schema in the initial context.
- Required administration reuses existing Plane settings surfaces; no new settings framework is introduced.
- After verification, rollout may proceed in stages despite there being no current users; automated safety stops remain mandatory.

## Pilot options

| Option             | Benefit                                                                         | Cost                                               |
| ------------------ | ------------------------------------------------------------------------------- | -------------------------------------------------- |
| End-to-end slice   | Validates reads, controlled writes, audit, native tools, and Code Mode together | Requires mutation safety before pilot              |
| Read-only first    | Lowest initial operational risk                                                 | Does not validate idempotency or unknown outcomes  |
| Broad catalog beta | Reaches more workflows immediately                                              | Multiplies contract, testing, and incident surface |

Selected: a broader end-to-end project-planning scenario. A real Plane Agent analyzes a seeded project's release readiness, composes a parent plan and coordinated child work items, autonomously writes the plan, proves idempotency and audit correlation, and demonstrates denial against an inaccessible control project.

## Success measures

Exact targets remain open. The production scorecard must include:

| Measure                               | Production expectation                       |
| ------------------------------------- | -------------------------------------------- |
| Authorization bypasses                | Zero tolerated                               |
| Missing audit events                  | Zero tolerated for every attempted operation |
| Unknown mutation outcomes             | Measured and visible                         |
| Tool-call success rate                | Target to be set from pilot baseline         |
| End-to-end task completion            | Target to be set for named pilot workflows   |
| Gateway latency overhead              | Target to be set after read-only benchmark   |
| Model-visible result size             | Always bounded                               |
| Credential exposure to generated code | Zero tolerated                               |
