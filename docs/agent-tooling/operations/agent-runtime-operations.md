# Plane Agent runtime operations

This runbook covers the disposable, separately configured Plane Agent runtime
boundary. It does not replace Plane's supervisor, assignment, lease, or
terminal-event authority. A runtime process may be replaced after a lease
death, but an `outcome_unknown` invocation must be reconciled by Plane before
any replay.

## Runtime-owned health and safety-stop interface

The runtime module is deliberately importable without Django or the HTTP
server:

```python
from plane.agent.runtime import RuntimeSafetyController

controller = RuntimeSafetyController(
    configured=True,
    stop_file="/run/plane-agent-runtime/safety-stop",
)
health = controller.health().as_dict()
```

`RuntimeSafetyController.health()` returns `RuntimeHealthStatus`. The stable
`RuntimeHealthStatus.as_dict()` schema is exactly:

```json
{
  "protocol": "plane.agent-runtime/v1",
  "status": "configured|ready|draining|stopped|dependency_failure",
  "configured": true,
  "ready": false,
  "draining": false,
  "stopped": false,
  "dependencyOk": true,
  "safetyStop": false,
  "activeInvocations": 0,
  "reason": null
}
```

`status` is one concrete value, not the pipe-delimited documentation string.
`activeInvocations` is a bounded integer and `reason` is either null or a
bounded, non-secret diagnostic. The controller never returns credentials.

For the T3 operator aggregate, register these exact adapters without moving
state ownership into the aggregate. They are Plane-side clients of the
runtime HTTP owner, not controller instances:

```python
from plane.agent.runtime import (
    RuntimeSafetyController,
    operator_health_readback,
    request_operator_safety_stop,
)

operator_health_readback(workspace_id: str, limit: int) -> dict[str, object]
request_operator_safety_stop(
    workspace_id: str,
    invocation_id: str,
    reason: str,
    idempotency_key: str,
) -> dict[str, object]
```

The health call validates the workspace and bound, then reads the bounded
runtime health endpoint. The stop call sends all four fields to the
authenticated `/safety-stop` endpoint. The runtime binds the idempotency key
to the workspace, invocation, and reason; a matching retry is a replay and a
conflicting retry is rejected. T3 should expose its own operator hook names
`operator_health_readback` and `request_operator_safety_stop` by forwarding to
these runtime-owned adapters.

The T3 safety-stop caller must preserve the Plane lifecycle boundary. Before
calling `request_operator_safety_stop`, or in the same application-level
operation, it must durably record the cancellation/control transition for the
bound invocation using Plane's existing
`plane.agent.runtime.supervisor.request_runtime_cancellation` path with
`invocation`, `reason`, `operator`, and the operator `idempotency_key` (and its
existing audit/idempotency evidence), keyed by the workspace and invocation.
A failed durable write must not call the runtime.
After the durable write succeeds, the caller may send the runtime request as
best-effort enforcement. A runtime timeout or dependency failure must be
reported as external enforcement failure while the durable Plane cancellation
remains authoritative and is reconciled on the next worker/runtime start.

The runtime response labels its local state
`authority: runtime_ephemeral_enforcement` and
`planeLifecycleAuthority: required`. Its in-memory targeted-stop map and
container marker are not durable lifecycle state; a runtime restart may erase
them. Plane must therefore re-read the durable control row and reissue
best-effort enforcement for any still-running invocation after replacement.

## Readiness and bounded diagnostics

Set a disposable value for `PLANE_AGENT_RUNTIME_SECRET` in a local, untracked
environment. Do not put it in `variables.env`, a Compose file, source code, or
logs. The Compose secret is mounted at
`/run/secrets/plane_agent_runtime`; the API and worker receive only that file
path, never the secret as an environment value.

Validate the resolved topology before starting anything:

```sh
docker compose -p plane-g4-load-luna --env-file deployments/cli/community/variables.env \
  -f deployments/cli/community/docker-compose.yml config --quiet
docker compose -p plane-g4-load-luna --env-file deployments/cli/community/variables.env \
  -f deployments/cli/community/docker-compose.yml ps agent-runtime
```

The runtime has an internal-only Docker network shared with API/worker for the
authenticated dispatch and host callback seams. It has no published host
port. Its health endpoint is checked from inside the disposable container:

```sh
docker compose -p plane-g4-load-luna --env-file deployments/cli/community/variables.env \
  -f deployments/cli/community/docker-compose.yml exec agent-runtime \
  python3 -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8080/health/live", timeout=2).read().decode())'
docker compose -p plane-g4-load-luna --env-file deployments/cli/community/variables.env \
  -f deployments/cli/community/docker-compose.yml exec agent-runtime \
  python3 -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8080/health/ready", timeout=2).read().decode())'
```

`/health/live` proves the process is alive; `/health/ready` returns success
only for `ready`. `configured`, `dependency_failure`, `draining`, and
`stopped` remain visible in the bounded JSON body and are not collapsed into a
false ready result.

The configured child command is fail-closed at both the Plane and launcher
boundaries. Its argv must be the approved Python executable followed by
`-m plane_runtime.g1_runtime_image.bootstrap --once --g1-production`; a
comment, filename containing the module name, or arbitrary extra flag is not
accepted. An invocation-scoped `--plane-host-socket <absolute-path>` extension
is added only by the authenticated host callback bridge.

## Global safety stop and credential revocation

Plane operators target a workspace and invocation through the runtime-owned
HTTP boundary. This does not mutate Plane lifecycle state:

The HTTP boundary uses the mounted secret only for local authorization. Never
echo it while diagnosing. For a disposable container, read the file inside the
container and issue the request there; a 202 response contains only the
health schema:

```sh
docker compose -p plane-g4-load-luna exec agent-runtime python3 -c '
import json, urllib.request
secret = open("/run/secrets/plane_agent_runtime", encoding="utf-8").read().strip()
request = urllib.request.Request(
    "http://127.0.0.1:8080/safety-stop",
    data=json.dumps({
        "workspaceId": "workspace:local",
        "invocationId": "invocation:local",
        "reason": "incident reference INC-LOCAL-001",
        "idempotencyKey": "stop:INC-LOCAL-001",
    }, sort_keys=True, separators=(",", ":")).encode(),
    headers={"Authorization": "Bearer " + secret, "Content-Type": "application/json"},
    method="POST",
)
print(urllib.request.urlopen(request, timeout=2).read().decode())
'
```

`RuntimeCredentialBroker` issues short-lived leases bound to an agent and
invocation. It stores only a digest and lease metadata. Revoke the lease (or
all leases for an invocation) immediately on cancellation or incident. Rotate
the disposable source for a `credential_ref`, call `rotate`, and reject every
old lease. A changed source digest also fails resolution, so source rotation
cannot silently reuse a lease. Real provider credentials are outside this
runbook and must never be used as local proof.

## Incident diagnosis

Capture bounded, redacted evidence:

```sh
docker compose -p plane-g4-load-luna logs --tail=100 agent-runtime
docker inspect --format '{{json .State.Health}}' "$(docker compose -p plane-g4-load-luna ps -q agent-runtime)"
```

Check whether the status is `dependency_failure`, `draining`, or
`outcome_unknown`; do not interpret a missing child result as success. Check
the safety-stop marker and the Compose resource/security settings before
restarting. Runtime process diagnostics are capped; request and response
frames are canonical JSON and no ambient parent environment is inherited.

## Offline production-candidate load thresholds

The canonical threshold fixture is
`apps/api/plane/tests/fixtures/agent_g4_load_thresholds.json`. It is an
offline production-candidate gate for the pinned disposable PostgreSQL stack,
not a live or GA SLO. The live/GA values must be recalibrated from an approved
representative workload before rollout; passing this fixture does not grant
deployment authority.

| Dimension | Candidate threshold | Evidence emitted |
| --- | ---: | --- |
| Workload | 128 requests, 8 workers, 16 agent identities | `requests`, `workers`, `measuredAgentIdentities` |
| Sustained duration | at least 0.75 seconds with 25 ms inter-batch pacing | `sustainedDurationSeconds` |
| Throughput | at least 2 requests/second | `throughputPerSecond` |
| Latency | p95 at most 7,500 ms; p99 at most 10,000 ms | `latencyMs.p95`, `latencyMs.p99` |
| Error rate | 0% unexpected statuses | `errors`, `errorRate` |
| Saturation | at least 1% quota throttling | `throttled`, `saturation` |
| Queueing | p95 executor queue delay at most 750 ms | `queueingMs.p95` |
| Database/resource | at most 24 PostgreSQL sessions, 768 MiB RSS, 90 CPU seconds | `resources` |
| Safety invariants | full correlation/audit coverage, one replay row/effect, quota cleanup | `thresholdResults`, `breaches` |

Run the real workload in a fresh test stack and retain the single JSON line
for the verifier lane. Repeat the complete cycle at least three times, with
`down -v` between runs:

```sh
docker compose -p plane-g4-load-luna -f docker-compose-test.yml down -v --remove-orphans
docker compose -p plane-g4-load-luna -f docker-compose-test.yml up -d \
  test-db test-redis test-mq test-minio
docker compose -p plane-g4-load-luna -f docker-compose-test.yml run --rm --no-deps \
  -e PLANE_G4_LOAD_JSON=1 --entrypoint /bin/sh api-tests -lc \
  'pip install --no-cache-dir -r requirements/test.txt && pytest -q -s \
  plane/tests/contract/api/test_operation_gateway_g4.py \
  -k postgresql_gateway_workload_measures_real_quota_and_audit_evidence'
docker compose -p plane-g4-load-luna -f docker-compose-test.yml down -v --remove-orphans
```

The command fails on any threshold breach and reports bounded machine-readable
`latencyMs`, `queueingMs`, `resources`, `thresholdResults`, and `breaches`
fields. It refuses a non-test database; do not substitute a simulation or a
shared environment.

## Coordinated rollback

### Trigger and safety stop

Trigger rollback on any load-threshold breach, unexpected gateway error,
audit/readback mismatch, quota leak, migration drift, runtime dependency
failure, or an `outcome_unknown` state that cannot be reconciled from durable
Plane state. Stop accepting new Agent work, stop the beat scheduler, and
record the Plane cancellation/control transition first. Only after that durable
write succeeds, issue the best-effort runtime safety stop. A failed durable
write must not call the runtime. A process or image replacement is never a
replay authorization.

The safety stop remains the Plane lifecycle authority; runtime enforcement is
ephemeral and must be re-read after replacement:

```sh
docker compose -p plane-g4-load-luna -f deployments/cli/community/docker-compose.yml exec agent-runtime \
  python3 -c 'import json,urllib.request; s=open("/run/secrets/plane_agent_runtime").read().strip(); r=urllib.request.Request("http://127.0.0.1:8080/safety-stop", data=json.dumps({"workspaceId":"<workspace>","invocationId":"<invocation>","reason":"<incident>","idempotencyKey":"<stop-key>"}, sort_keys=True, separators=(",", ":")).encode(), headers={"Authorization":"Bearer "+s,"Content-Type":"application/json"}, method="POST"); print(urllib.request.urlopen(r, timeout=2).read().decode())'
```

### Exact pins and migration strategy

`apps/api/plane/tests/fixtures/agent_g4_rollback_pins.json` is the pin
manifest. The current Plane deployable service candidate is the exact
integrated implementation parent Plane commit
`739068b87231558df8c4685c42045f5c91306200`; the previously accepted G3
candidate is Plane commit `7c9d35f4c324865c27c84da5016be2c84e460bcc`.
The current binding carries Hermes commit
`e573a46611e2cb988f1ab43ad34cd8cc3b2cb659`, MCP gitlink
`2dc152e136d7ad952b901e5fe9364a37487297ba`, SDK gitlink
`7d2faf3b7ef5409e292ba0a3c7015e59f93c5889`, runtime image tag
`plane-agent-runtime:hermes-e573a466-g4-872220b`, runtime image digest
`sha256:cb829c0973579602f5b144b547ee023f22680a754cbc06df521d17e57af8b990`,
runtime revision `872220bf23e9b6dfc3421a5fb7537d0bda829703`, and runtime
contract `plane.agent-runtime/v1`. The Plane service revision above is
intentionally distinct from the runtime image/runtimeRevision source
`872220bf23e9b6dfc3421a5fb7537d0bda829703`. API, worker, `beat-worker`,
supervisor, and `agent-runtime` each switch their service revision and image
digest to the corresponding current value in that manifest; the operation services retain
`plane.operation/v1` and the runtime services retain `plane.agent-runtime/v1`.
The previous services use immutable image digest
`sha256:51b50bec143e12c22fa92f8b101629d37ae263f2784c9bb3747eaea45978092e`,
the image pin recorded by the accepted G3 verifier. The rollback reasserts
these immutable pins rather than accepting a mutable tag.

For final-wrapper integration, the one canonical current-parent field is
`tools/agent-g4-manifest.json:candidateBinding.parentCommit`. Set it to the
wrapper’s immediate parent after all implementation lanes are integrated;
the verifier derives the expected current parent from that field and requires
the materialized fixture `current.planeCommit` and its manifest SHA-256 to
agree before the rollback stage can run.

Migration `db.0141_operationgateway_quotas` is additive: it adds quota fields,
indexes, and the quota bucket table. Rollback is explicitly forward-only:
keep the database at leaf `0141`, never reverse to `0140`, and run the prior
services only after confirming they ignore the additive quota state. The
`0141` migration blob is
`1c6b0e3fb221cccd9ed2631d68cbf10ba5dc399b` and its SHA-256 is
`797d95b90be5041e76cbf60ea27ee8ca0cea6045a6a67fab3a3181c173e1ce9e`.
The compatibility floor is `0140` (blob
`d51561b1d482917ebe533e95c566b9baf5ddef9c`), not a downgrade target.

### Disposable executable drill

The drill performs current-candidate upgrade, creates a representative
`outcome_unknown` operation with an already-committed durable effect, switches
all five service pins/contracts, keeps migration `0141`, reconciles from the
effect/audit/outcome state, releases quota, checks idempotent re-run, and
removes its temporary database. It never connects to Plane or deploys:

```sh
python3 tools/agent-g4-rollback-drill.py
```

The one-line JSON result must contain `passes:true`, empty `breaches`,
`externalWrites:false`, `migrationLeaf:"db.0141_operationgateway_quotas"`,
three audit rows, one outcome, one idempotency row, zero active quota
reservations, and `cleanup.temporaryDatabaseRemoved:true`. This is the
exercised rollback proof; a prose-only rollback is not sufficient.

### Coordinated service switch and verification

For an authorized disposable Compose rehearsal, render and inspect the
resolved configuration with the exact previous pins before replacement, then
switch API, worker, beat-worker, runtime, and the Plane supervisor control
path as one change window:

```sh
docker compose -p plane-g4-load-luna --env-file deployments/cli/community/variables.env \
  -f deployments/cli/community/docker-compose.yml config --quiet
docker compose -p plane-g4-load-luna --env-file deployments/cli/community/variables.env \
  -f deployments/cli/community/docker-compose.yml stop api worker beat-worker agent-runtime
docker compose -p plane-g4-load-luna --env-file deployments/cli/community/variables.env \
  -f deployments/cli/community/docker-compose.yml up -d --no-deps --force-recreate \
  api worker beat-worker agent-runtime
docker compose -p plane-g4-load-luna --env-file deployments/cli/community/variables.env \
  -f deployments/cli/community/docker-compose.yml exec api python manage.py \
  migrate --plan
docker compose -p plane-g4-load-luna --env-file deployments/cli/community/variables.env \
  -f deployments/cli/community/docker-compose.yml ps api worker beat-worker agent-runtime
```

`migrate --plan` must show no reverse operation and the database must still
report leaf `0141`. Read back every affected idempotency record, gateway audit
receipt, durable operation effect/outcome, and quota bucket before permitting
any continuation. A completed effect may be reconciled exactly once; a missing
or conflicting effect is a stop/escalation, never a blind replay.

### Restore, reconciliation, and abort paths

After the incident is understood, re-check all five previous revisions and
digests, the approved command/resource policy, runtime readiness, migration
leaf, and safety-stop state. Reconcile each affected invocation through Plane's
supervisor and outcome readback. Confirm audit/outcome counts, exact
idempotency digest, terminal-event uniqueness, and zero leaked quota
reservations. Re-run the rollback drill and the relevant gateway/migration
contract suites before restoring new work.

Abort and escalate immediately if any pin is missing, a digest resolves to a
mutable tag, services disagree on the contract, `0141` is absent or a reverse
plan appears, audit/outcome readback is incomplete, a durable effect is not
unique, quota remains active after reconciliation, or runtime enforcement does
not acknowledge the safety stop. Preserve bounded logs and identifiers only;
never include a runtime secret or provider credential.

## Evidence cleanup

Use a disposable Compose project and remove it after collecting the required
bounded evidence:

```sh
docker compose -p plane-g4-load-luna -f deployments/cli/community/docker-compose.yml down -v --remove-orphans
```

Remove any local safety-stop marker and temporary ledger created for the test.
Confirm that shell history, command output, container logs, and test artifacts
contain no secret value. Never delete a production ledger or evidence store as
part of this disposable cleanup.
