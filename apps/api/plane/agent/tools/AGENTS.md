# AGENTS.md

## Scope

This file governs `apps/api/plane/agent/tools/` and its descendants.

## Local Responsibility

This folder owns the Plane-native semantic tool facade: the canonical
operation catalog, presentation-only eager disclosure, progressive discovery,
and thin adapters that terminate at `plane.operation_gateway`.

## Architecture Rules

- The catalog describes operation names, schemas, bounds, and presentation; it
  never grants or denies access.
- `search_workspace` is the universal eager work-core operation. All other
  supported operations remain globally discoverable, even when not eager.
- Mutations keep semantic operation identities. Do not add a generic write
  operation or a second operation allowlist.
- Every adapter call must use `OperationGateway`; do not call Plane views,
  serializers, models, or external APIs directly from a model-facing tool.

## Local Verification

Run the focused agent tool unit tests and the gateway contract tests from the
repository-supported API test container. Confirm the catalog digest is stable,
all catalog entries are discoverable, and denied calls do not mutate state.
