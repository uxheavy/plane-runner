# AGENTS.md

## Scope

This file governs `apps/api/plane/agent/adapters/` and its descendants.

## Local Responsibility

These packages reserve Plane-owned seams for the Operation Gateway, operation
catalog, invocation idempotency, and append-only audit. They translate
transport or storage concerns; they do not own a second authorization model or
duplicate Plane business logic.

## Working Method

Route native, runtime, and external compatibility callers through the shared
Plane application/lifecycle rules. Keep adapters thin, request-bound, and
replaceable. Expand long-tail operation coverage through catalog metadata and
adapters rather than adding one prompt/runtime module per external operation.

## Current Gotchas

- The catalog describes availability and presentation; it never grants
  permission. Live Plane authorization remains authoritative.
- Idempotency and audit are common application rules, not optional behavior for
  individual transports.
- The 177-operation compatibility surface is an adapter concern, not 177 new
  Plane modules.

## Local Verification

From `apps/api/`, verify imports for `plane.agent.adapters` and each child
package. Confirm no adapter imports a chat UI, saved workflow definition, or
direct runtime-kernel state.
