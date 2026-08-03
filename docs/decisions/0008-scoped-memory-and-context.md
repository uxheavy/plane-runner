# ADR-0008: Scope Plane Agent memory and context explicitly

## Status

Proposed

## Date

2026-08-03

## Context

Plane Agent needs organizational knowledge, project context, user preferences, role instructions, and prior-run learning. A single company-wide mutable memory text would mix authority, audience, provenance, and retention. Automatically promoting agent-generated candidates into shared memory would also allow stale or incorrect output to become organization-wide instruction.

The Freeform design proposes memory gardeners but does not yet establish what may be remembered, who approves it, or which agents may consume it.

## Decision

Model durable context as typed entries with explicit scope, provenance, owner, visibility, timestamps, and lifecycle. Initial scopes are workspace, project, agent profile, user preference, assignment, and run. A user-preference entry carries its subject user and is assembled only for an authorized context in which that user's preferences apply. It is never merged into agent, project, or workspace memory merely because the same agent interacted with that user.

Plane-governed storage is authoritative for durable memory, skills, definitions, versions, promotion state, and access decisions. Hermes may provide retrieval, ranking, compaction, automatic candidate capture, skill creation or improvement, and execution behind Plane adapters.

Disposable Hermes and run files are projections, never the source of truth. Plane may materialize lossless Hermes-compatible `MEMORY.md`, subject-bound `USER.md`, and skill packages for execution. A `USER.md` projection contains only preferences for the authorized subject user of that runtime context; it does not accumulate preferences across users. Plane-specific structured or rich-text data stays structured where that representation matters; agents may receive deterministic Markdown and file projections instead of making every Plane object canonically a `.md` file.

Preserve Hermes's automatic learning loop as agent-scoped candidate memory and skills under Plane governance. Local capture and improvement may proceed, but promotion into shared templates, project, workspace, or organization scopes requires human governance. “No automatic promotion” does not mean disabling learning.

For the first vertical slice, resolve curated workspace and profile instructions, assignment context references, conversation segments, artifact links, and bounded agent-scoped learning candidates. Memory gardeners and shared promotion workflows remain deferred until governance and evaluation evidence exist.

## Alternatives considered

### One shared company memory document

- Benefit: simple retrieval and editing.
- Cost: unclear authority, leakage risk, conflicts, and poor provenance.
- Rejected: organizational context has materially different scopes.

### Let every agent maintain private unstructured memory

- Benefit: autonomous personalization.
- Cost: administrators cannot inspect, govern, or reliably reproduce behavior.
- Rejected: native Plane agents require auditable context.

### Disable durable memory permanently

- Benefit: strongest reproducibility.
- Cost: agents cannot accumulate curated organizational knowledge.
- Rejected: useful durable context is a product requirement, but promotion must be governed.

## Consequences

- Context assembly requires deterministic precedence and budget rules.
- Runs record the resolved context references and versions they consumed.
- Memory visibility follows Plane authorization and does not create a parallel entitlement system.
- File projections require deterministic round-trip, provenance, conflict, and reconciliation rules.
- Automatic learning remains recoverable and agent-scoped until a governed promotion occurs.
- The promotion, conflict-resolution, retention, and deletion contracts remain open before acceptance.
