# AGENTS.md

## Scope

This file governs `apps/api/plane/agent/` and its descendants.

## Local Responsibility

This package is the Plane-owned importable seam for one Agent system. The
scaffold intentionally retains only the package root plus the `lifecycle` and
`adapters` seams; it does not reserve empty packages for future concepts.

It is a regular importable Python package, not a Django app yet. Do not add
`apps.py`, models, migrations, routes, settings registration, test harnesses,
or chat UI as part of this scaffold.

## Architecture Rules

- `actor` owns the durable Plane principal and authorization facts; `profile`
  owns versioned behavioral/configuration data. Built-in roles are profile data,
  skills, and presentation defaults over one underlying agent system—not
  role-specific engines.
- Assignment/revision, run/invocation, and outcome/review remain separate
  records with independent lifecycles. Conversation and product events are
  Plane-owned records; runtime output is not authoritative by itself.
- `lifecycle` is the one deep cross-record state-transition seam. Application
  services and adapters converge on it; individual concept implementations
  must not grow sibling transition interfaces or mutate other concepts
  directly.
- The retained `adapters` seam remains Plane-owned for the Operation Gateway,
  operation catalog, invocation idempotency, and append-only audit. Future
  child adapter packages must land with real behavior and tests in the same
  change; they share the application rules and must not become a second
  authorization or business-logic implementation.
- Expand operation coverage behind adapters and the catalog. Do not create one
  shallow prompt/runtime module per external operation, including the pinned
  177-tool compatibility surface.
- There is no saved workflow-definition package in this scaffold. Delegation
  is a separate durable concept, not an implicit workflow engine.

## Working Method

Keep this package domain-first and importable. When implementation is
authorized, put legal cross-record transitions behind `lifecycle`, keep
application services request-oriented, and keep transport/runtime integrations
in adapters. Reuse existing Plane authorization and application services
instead of copying their behavior here.

## Current Gotchas

| Gotcha | Why It Matters | Correct Action |
| --- | --- | --- |
| This scaffold is not a Django app. | Registering it or adding migrations would create runtime and schema commitments before the lifecycle contract exists. | Keep it out of `INSTALLED_APPS`; retain only the root/seam markers until implementation is explicitly in scope, and add future concepts only with real behavior. |
| A profile role is not an execution engine. | Role-specific runners would duplicate lifecycle and authorization behavior. | Express built-in roles as Plane-owned data/configuration over the common agent system. |
| The external operation count is not the domain shape. | Mirroring 177 operations as prompt/runtime modules makes discovery shallow and fragments enforcement. | Grow the catalog and adapters behind the shared Plane lifecycle/application rules. |
| Empty package markers are not architecture. | Marker-only concept or subadapter packages create false ownership and shallow seams before behavior exists. | Keep only the retained root, lifecycle, and adapters seams; add future concept packages only with real behavior and tests. |

## Local Verification

From the repository root, verify all retained seams in the repository-supported API
test container:

```sh
docker compose -f docker-compose-test.yml run --rm --build api-tests \
  python -c "import plane.agent; import plane.agent.lifecycle; import plane.agent.adapters"
```

Do not use host `python` or `python3` for this check.

Inspect the final tree and confirm no files were added under
`apps/api/plane/settings/`, `apps/api/plane/db/migrations/`, routes, or UI.
