# ADR-0008: Keep Agent memory and skills private and governable

## Status

Accepted

## Date

2026-08-03

## Context

Plane Agent needs project context, user preferences, role instructions, and prior-run learning. A shared knowledge pool would mix authority, audience, provenance, and retention, and would let one agent's learning leak into another agent's behavior. Plane still needs gardeners who can improve agents across sessions without turning those agents into a shared-memory system.

The product requires explicit private scope, immutable history, and rollback for memory and skill changes. Plane context references may point to authorized Plane records, but they are not copied into another agent's private knowledge.

## Decision

Model durable agent memory and skills as typed, agent-private entries with explicit provenance, owner, timestamps, version, and lifecycle. A gardener may maintain multiple agents, but every read, proposal, and change is evaluated against one target agent at a time. No product operation copies knowledge, memory, or skills from one agent to another. A context reference may point to a Plane workspace, project, assignment, or user preference only when the target agent has the live permission to read it; the reference is not a copy into another agent's private knowledge.

Plane-governed storage is authoritative for durable memory, skills, versions, improvement records, rollback state, and access decisions. The execution kernel may provide retrieval, ranking, compaction, automatic candidate capture, skill creation or improvement, and execution behind Plane adapters.

Disposable runtime and run files are projections, never the source of truth. Plane may materialize lossless `MEMORY.md`, subject-bound `USER.md`, and skill packages for execution. A `USER.md` projection contains only preferences for the authorized subject user of that runtime context; it does not accumulate preferences across users or agents. Plane-specific structured or rich-text data stays structured where that representation matters; agents may receive deterministic Markdown and file projections instead of making every Plane object canonically a `.md` file.

Gardeners may apply approved improvements automatically within the target agent's private memory and skills. Every applied improvement creates an immutable revision with its source, rationale, gardener identity, timestamp, and predecessor. Rollback never rewrites history; it creates a new revision that restores an earlier content state. Automatic improvement does not authorize cross-agent copying or a shared knowledge scope.

For the first vertical slice, resolve role instructions, authorized assignment context references, conversation segments, artifact links, and bounded agent-private learning candidates. Gardener APIs and schedule-triggered runs remain part of the non-UI breadth gate, while their detailed limits and retention rules are implementation contracts.

## Alternatives considered

### One shared company memory document

- Benefit: simple retrieval and editing.
- Cost: unclear authority, leakage risk, conflicts, and poor provenance.
- Rejected: shared knowledge would violate agent-private knowledge and make provenance and rollback ambiguous.

### Let every agent maintain private unstructured memory

- Benefit: autonomous personalization.
- Cost: administrators and gardeners cannot inspect, govern, or reliably reproduce behavior.
- Rejected: private knowledge still needs typed, auditable, reversible governance.

### Let gardeners copy knowledge between agents

- Benefit: faster reuse of successful guidance.
- Cost: breaks privacy, provenance, and independent agent behavior.
- Rejected: no knowledge is copied between agents; gardeners work on each target privately.

### Disable durable memory permanently

- Benefit: strongest reproducibility.
- Cost: agents cannot accumulate curated organizational knowledge.
- Rejected: useful durable context is a product requirement, but it remains agent-private and reversible.

## Consequences

- Context assembly requires deterministic precedence and budget rules under the target agent's live permissions.
- Runs record the resolved context references and versions they consumed.
- Memory visibility follows Plane authorization and does not create a parallel entitlement system.
- File projections require deterministic round-trip, provenance, conflict, and reconciliation rules.
- Automatic learning and gardener improvements remain recoverable, immutable, and agent-scoped.
- Rollback and retention contracts must be tested before the non-UI breadth gate; no shared-memory promotion contract exists in this scope.

### Runtime integration boundary

The pinned Hermes adapter is intentionally not the authority for Plane context.
At the current runtime seam it calls `AIAgent` with `skip_context_files=True`
and `skip_memory=True`; its only `prefill_messages` input is a trusted,
approved continuation checkpoint. `build_model_guidance` carries context
references and assignment metadata, not materialized memory or skill contents,
and the G1 snapshot validator rejects uncontracted snapshot fields. Therefore
the first live context journey uses the existing shared Operation Gateway for a
bounded `agent.context.read` projection. The operation is not a second
authorization model: it binds actor, run, assignment context reference, and
subject to the persisted snapshot, applies the existing memory/skill services
and retention filters, records the normal gateway receipt/audit, and returns
only the bounded deterministic projection. If Hermes later exposes a Plane-
owned context-materialization adapter, this operation should be retired in
favor of that seam.
