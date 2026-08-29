# ADR-0002: Plane agent operations execute autonomously within Plane authorization

## Status

Accepted

## Date

2026-07-29

## Context

ADR-0001 included a separate runtime approval policy and reused Hermes human-confirmation prompts for Plane operations. The user clarified that Plane agents are autonomous: their dedicated Plane identity, workspace membership, project role, and object permissions already define what they may do.

Pausing an otherwise-authorized operation for a human decision would add a second runtime governance system, broker credentials, pending state, timeout and resume behavior, and substantial testing and operational complexity without serving the intended product model.

Human approval of release manifests, rollout promotion, deployment, external writes by the delivery agent, and final outcome acceptance remain separate product and delivery controls.

## Decision

Plane's live authorization is the final runtime allow-or-deny decision for agent operations.

- Authorized operations execute immediately and autonomously.
- Unauthorized operations return a non-leaking denial with no side effect.
- Every inner Code Mode call is authorized independently.
- V1 has no operation-approval policy, human-confirmation prompt, broker credential, pending approval record, approval endpoint, wait timeout, or approval resume protocol.
- Configured agent scope means Plane identity, membership, role, and object permissions; it is not a second tool-specific allowlist.
- Explicit group preflight performs schema, reference, authorization, budget, and concurrency validation only. It never prompts or produces approval state.

This decision supersedes only the runtime operation-approval portions of ADR-0001. The shared gateway, native tools, Code Mode, external MCP compatibility, credential boundary, mutation safety, result limits, audit, and release-governance decisions remain accepted.

## Consequences

- The Plane gateway has fewer states and no `approval_required` result.
- Hermes does not need Plane-specific approval integration.
- Authorization and audit evidence become the central runtime governance proof.
- Tests must prove that authorized calls never pause and unauthorized calls never mutate.
- Tests must also prove that no operation-approval route, schema state, credential, configuration, or persistence model exists.
- Release, rollout, deployment, and outcome-acceptance approvals remain human-controlled and auditable outside the operation execution protocol.
