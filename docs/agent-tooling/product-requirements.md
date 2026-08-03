# Product Requirements

## Problem

Plane agents need to drive assigned outcomes through Plane without receiving database access or credentials. A general-purpose Hermes personality and large flat tool list do not feel like a native Plane teammate, while an ungoverned code-execution surface can bypass product authorization and auditing.

Plane already has an external Python MCP server. Plane-native agents backed by the forked Hermes kernel do not need the latency and lifecycle cost of an internal MCP hop, but both internal and external integrations should converge on the same supported Plane operations.

## Users

### Plane-native agents

Agents managed by Plane and executed by a forked Hermes kernel. They receive a Plane-native behavioral profile, native semantic tools for common work, and TypeScript composition for broader available operations. Users and models do not experience Hermes as a separate product.

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
- Common workflows should be simple without restricting advanced composition.
- Initial tool context should contain a small universal Plane work core plus assignment-relevant operation schemas.
- Other available operations outside the initial context should remain discoverable.
- Failure must be explicit, structured, and safe to retry only when proven safe.
- The first release should be narrow enough to validate but complete enough to exercise production risks.

## Pilot options

| Option             | Benefit                                                                         | Cost                                               |
| ------------------ | ------------------------------------------------------------------------------- | -------------------------------------------------- |
| End-to-end slice   | Validates reads, controlled writes, audit, native tools, and Code Mode together | Requires mutation safety before pilot              |
| Read-only first    | Lowest initial operational risk                                                 | Does not validate idempotency or unknown outcomes  |
| Broad catalog beta | Reaches more workflows immediately                                              | Multiplies contract, testing, and incident surface |

Selected: a broader end-to-end project-planning workflow. A real Hermes run analyzes a seeded project's release readiness, composes a parent plan and coordinated child work items, autonomously writes the plan, proves idempotency and audit correlation, and demonstrates denial against an inaccessible control project.

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
