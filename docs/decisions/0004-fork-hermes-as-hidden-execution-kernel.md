# ADR-0004: Fork Hermes as the hidden Plane Agent execution kernel

## Status

Accepted

## Date

2026-08-03

## Context

Hermes already supplies useful agent-loop, tool-dispatch, context-management, session, concurrency, and bounded-result mechanisms. Rebuilding those mechanisms would delay the Plane-native product without improving its product boundary. Inheriting Hermes wholesale would instead preserve unrelated personalities, tools, channels, and developer-facing configuration.

## Decision

Maintain an `uxheavy` fork of Hermes as Plane Agent's internal execution kernel.

Reuse kernel mechanisms when their boundaries fit. Hide, adapt, feature-gate, or remove upstream product surfaces that do not serve Plane Agent. Plane supplies a runtime profile compiled from Plane-owned agent and assignment data; the kernel executes that profile without becoming the product identity.

Plane owns definitions and durable control state for profiles, assignments, runs, conversations, agent-private memory, skills, schedules, delegation, artifacts, and outcomes. Hermes may execute model loops, context management, retrieval, learning, skill use, schedules, dynamic delegation, tool dispatch, transcript capture, checkpoints, concurrency, and recovery behind Plane adapters. Those mechanisms never become a second source of truth or a second Plane Agent product model.

A Plane run may span more than one Hermes session, process, or restart. Hermes transcripts and checkpoints are operational inputs to recovery; Plane owns the durable run, conversation, and history record.

Keep Plane-specific integration behind one narrow, versioned runtime adapter so upstream kernel changes do not spread Plane concepts through unrelated Hermes modules. The accepted contract is recorded separately in ADR-0010.

## Alternatives considered

### Build a new agent runtime

- Benefit: complete control and no inherited code.
- Cost: repeats mature execution work and increases time and operational risk.
- Rejected: no current requirement justifies replacing the useful kernel.

### Consume Hermes unchanged as an external service

- Benefit: easier upstream upgrades.
- Cost: its product assumptions and default tool surface become runtime contracts.
- Rejected: Plane needs authority over the runtime profile and product semantics.

### Copy selected Hermes modules into Plane

- Benefit: removes a separate fork.
- Cost: obscures provenance and makes upstream integration difficult.
- Rejected: an explicit fork provides a clearer maintenance boundary.

## Consequences

- The fork has an explicit retained, adapted, disabled, and removed mechanism inventory.
- Upstream sync is deliberate and tested against the Plane runtime profile.
- Plane-facing contracts cannot depend on Hermes-specific configuration or names.
- Hermes sessions, files, transcripts, and checkpoints are never authoritative Plane product state.
- Definitions and control state stay in Plane even when Hermes supplies their execution mechanism.
- Removing unused upstream surfaces is preferred after callers are migrated and verification proves they are unnecessary.
