# AGENTS.md

## Scope

This file governs `apps/api/plane/agent/lifecycle/`.

## Local Responsibility

`lifecycle` is the one deep Plane-owned interface for legal state transitions
that span actor/profile, assignment/revision, run/invocation, outcome/review,
conversation/events, delegation, schedules, and evaluation. The durable
concepts remain separate; this seam coordinates their transitions.

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
- Do not add parallel transition interfaces to individual durable-concept
  packages.

## Local Verification

From the repository root, first run `./setup.sh` as the repository prerequisite,
then verify the retained lifecycle seam in the repository-supported API test
container:

```sh
docker compose -f docker-compose-test.yml run --rm --build api-tests \
  python -c "import plane.agent.lifecycle"
```

The package must contain no Django models, migrations, routes, or
runtime-provider imports.
