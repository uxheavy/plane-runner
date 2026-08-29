# Plane Agent runtime operations

This runbook covers only provider-free verification of the durable runtime boundary. Restricted live execution is external and requires a named approved operational owner.

## Readiness and bounded diagnostics

`tools/verify-agent-g4.sh --offline` requires the manifest-pinned local API and runtime images, the pinned clean Hermes, MCP, and SDK checkouts, and a project virtualenv containing the exact pytest pin from `apps/api/requirements/test.txt`. Set `PLANE_G4_TOOLING_PYTHON` to that virtualenv's Python when it is not `python3`. The verifier rejects a missing or mismatched pytest version before starting. It validates image digests and labels before running tests. Runtime diagnostics remain finite structural fields; raw messages, prompts, arguments, credentials, and provider payloads are not verification evidence.

## Provider-free checks

```sh
python3 -m pytest -q \
  tools/tests/test_agent_g4_operations.py \
  tools/tests/test_build_agent_api_image.py \
  tools/tests/test_runtime_image_builder.py
python3 tools/agent-g4-rollback-drill.py
PLANE_G4_RECEIPT_PATH=/private/tmp/plane-agent-g4-provider-free.json \
  tools/verify-agent-g4.sh --offline
python3 tools/verify-agent-g4-operations.py \
  --verifier-receipt /private/tmp/plane-agent-g4-provider-free.json
```

The receipt schema is `plane-agent-g4/provider-free-verifier-receipt/v1`. It
contains only the exact source candidate, immutable pins, stage names and
statuses, cleanup status, and `providerExecutionInvoked:false`. This field
describes the provider-free verifier mode; it is not a measured provider-attempt count.

The canonical verifier covers:

- G3 API, runtime, gateway, MCP, and SDK contracts;
- API and runtime image identity;
- cross-process runtime transport and supervisor behavior;
- the network-isolated runtime container red-team;
- disposable PostgreSQL gateway load and quota behavior;
- forward-only rollback and reconciliation;
- operator health, safety-stop, and readback behavior;
- production runtime configuration and local topology.

## Global safety stop and credential revocation

Plane owns invocation leases, cancellation, runtime safety-stop state, and the credential revocation journal. The provider-free suites exercise expiry, revocation, cancellation, reconciliation, and no-replay behavior without resolving or using a provider credential.

## Incident diagnosis

Preserve the first failure. Distinguish provider attempt state, runtime exit state, Plane invocation state, and gateway outcome state. An `outcome_unknown` state is reconciled from durable effects and is never blindly replayed.

## Offline production-candidate load thresholds

`apps/api/plane/tests/fixtures/agent_g4_load_thresholds.json` defines the disposable local workload gate. It is a regression threshold, not a production SLO.

## Coordinated rollback

`apps/api/plane/tests/fixtures/agent_g4_rollback_pins.json` binds the current and previous service artifacts. The rollback is forward-only: keep migration `0146`, retain `0145` as the compatibility floor, switch all service pins together, reconcile from durable effect/audit/outcome state, and never replay an ambiguous mutation.

The API, worker, gateway, and runtime image source revision is
`150d5b6d85c8da81d641c84a2d47909364816044`. The verifier receipt records that
runtime source separately from the clean checkout `HEAD` that executes the
verification. The accepted G3 rollback baseline is
`7c9d35f4c324865c27c84da5016be2c84e460bcc`. The drill validates these manifest
bindings, both API artifact identities, every service artifact
kind/digest/contract, and both migration blobs before executing.

```sh
python3 tools/agent-g4-rollback-drill.py
```

The drill uses a temporary SQLite database, performs no external writes, and must report `passes:true` with cleanup complete.

## Evidence cleanup

The verifier removes its task-owned Compose resources, logs, and temporary directories. The red-team separately asserts that no resource carrying its dedicated label remains. Provider-free verification does not retain provider-run receipts or raw logs.
