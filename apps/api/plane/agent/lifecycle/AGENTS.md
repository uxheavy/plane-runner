# AGENTS.md

## Scope

This file governs `apps/api/plane/agent/lifecycle/`.

## Local Responsibility

`lifecycle` is the one deep Plane-owned interface for legal state transitions
that span actor/profile, assignment/revision, run/invocation, outcome/review,
conversation/events, delegation, schedules, and evaluation. The durable
concepts remain separate in `plane.db.models.agent`; this seam coordinates
their transitions and does not become a second Django app.

## Working Method

Keep callers request-oriented and the transition surface small. Application
services enter this seam, while persistence, runtime observations, gateway
adapters, idempotency, and audit remain replaceable implementations behind the
same application rules. Test cross-record invariants through this seam rather
than exposing transition helpers from each record package.

## Current Gotchas

- Do not turn lifecycle into a saved workflow-definition or graph DSL.
- Runtime/kernel output is an observation until Plane validates it and applies
  a legal product transition.
- The versioned `plane.agent-runtime/v1` artifacts are the runtime-consumed
  contract files; preserve their exact bytes and manifest digests.
- Do not add parallel transition interfaces to individual durable-concept
  records or packages.

## Local Verification

From the repository root, first run `./setup.sh` as the repository prerequisite,
then verify the retained lifecycle seam in the repository-supported API test
container:

```sh
docker compose -f docker-compose-test.yml run --rm --build api-tests \
  python -c "import plane.agent.lifecycle"
```

The package itself must contain no Django models, migrations, routes, or
runtime-provider imports; durable models/migrations remain in the canonical
`plane.db` app and the runtime crosses the versioned contract seam.
