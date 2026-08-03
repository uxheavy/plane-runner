# AGENTS.md

## Scope

This file governs `apps/api/plane/agent/adapters/` and its descendants.

## Local Responsibility

This retained seam is Plane-owned for the Operation Gateway, operation
catalog, invocation idempotency, and append-only audit. Future child adapters
must land with real behavior and tests; they translate transport or storage
concerns and do not own a second authorization model or duplicate Plane
business logic.

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

From the repository root, verify the retained adapters seam in the
repository-supported API test container:

```sh
docker compose -f docker-compose-test.yml run --rm --build api-tests \
  python -c "import plane.agent.adapters"
```

Do not add child-package imports until a child adapter has real behavior and
tests. Confirm no adapter imports a chat UI, saved workflow definition, or
direct runtime-kernel state.
