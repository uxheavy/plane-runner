# AGENTS.md

## Scope

This file governs `apps/api/plane/agent/` and its descendants.

## Local Responsibility

This package is the Plane-owned importable seam for one Agent system. The
implemented lifecycle and adapter services coordinate the durable Agent
records in `plane.db.models` and the shared Operation Gateway; they do not
create a second Django app or a second product model.

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
  directly. Its migrations are owned by `plane.db` and remain separate from
  the importable package.
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
| The importable package is not a Django app. | Registering `plane.agent` would create a duplicate model/migration owner. | Keep models and migrations in `plane.db.models.agent` and `apps/api/plane/db/migrations/`; keep `plane.agent` focused on lifecycle and adapter services. |
| A profile role is not an execution engine. | Role-specific runners would duplicate lifecycle and authorization behavior. | Express built-in roles as Plane-owned data/configuration over the common agent system. |
| The external operation count is not the domain shape. | Mirroring 177 operations as prompt/runtime modules makes discovery shallow and fragments enforcement. | Grow the catalog and adapters behind the shared Plane lifecycle/application rules. |
| Marker-only packages are not architecture. | Marker-only concept or subadapter packages create false ownership and shallow seams before behavior exists. | Keep only the retained root package initializer and lifecycle/adapters seams; add future concept packages only with real behavior and tests. |

## Local Verification

From the repository root, first run `./setup.sh` as the repository prerequisite,
then verify the lifecycle and adapter seams plus their targeted tests in the
repository-supported API test container:

```sh
docker compose -f docker-compose-test.yml run --rm --build api-tests \
  python -c "import plane.agent; import plane.agent.lifecycle; import plane.agent.adapters; from plane.db.models import AgentActor"
```

Do not use host `python` or `python3` for this check.

Inspect the final tree and confirm no models were added under `plane.agent`
itself, no second authorization seam exists, and no chat/composer/thread/
inbox/sidecar/transcript/navigation UI was added.
