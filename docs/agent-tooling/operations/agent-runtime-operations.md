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

## Provider egress relay

The trusted `agent-runtime` service also has the canonical
`agent_runtime_egress` network. API, worker, and the child do not join that
network: the child remains under the pinned `network=none`/AF_UNIX-only
process policy. The runtime opens one invocation-scoped AF_UNIX provider relay
under its private temporary directory and owns the pinned provider hostname,
path, model allowlist, TLS, redirect rejection, request/response bounds,
timeouts, streaming cancellation, model-call budget, and audit outcome. This
relay is an internal adapter, not a Plane host or public product endpoint.

The runtime reads the shared revocation journal at
`/run/plane-agent-credentials/revocations.json` and rechecks the invocation
lease before and during a provider stream. The parent keeps the leased
credential in memory for its HTTPS adapter; the relay request, child
environment, bootstrap evidence, transcript, and generated code contain no
real provider credential. The existing Plane host AF_UNIX gateway remains a
separate product-operation boundary.

The existing private credential frame carries only `invocationSocket`, `host`,
`path`, `provider`, and `relayToken`. Hermes' documented constructor seam
creates a fresh HTTP client with an AF_UNIX `uds` transport, logical base URL
`http://plane-provider-relay.invalid/v1`; its HTTP `Host` is the fixed logical
relay host `plane-provider-relay.invalid`. The parent translates that admitted
request to the pinned provider hostname `api.x.ai`; the provider path remains
enforced by the parent relay. The bootstrap argument is
`--provider-relay-socket`.

The exact Hermes source commit is now integrated through
`bootstrap → service → serve_once_g1 → HermesKernelAdapter → run_agent.AIAgent`;
no Plane-side client factory or AIAgent patch is used. The candidate image is
pinned in the manifest below. Until a separately authorized live run proves
it, provider/model calls remain unperformed and live G4/G5 remain incomplete.

## Local development topology

`./setup.sh` copies the local examples and generates the untracked
`.plane-agent-runtime.secret` Compose secret file. Ordinary local development
does not start the runtime image and selects `plane.settings.local` for the
API, worker, beat-worker, and migrator processes:

```sh
docker compose -f docker-compose-local.yml up -d
```

To opt into the separate runtime service, enable the `agent` profile and the
local settings seam together. The local `.env.example` selects the exact
manifest-bound prepared runtime tag and the opt-in checker verifies its image
ID and labels. The community deployment keeps its registry-backed fallback
for deployment environments. The profile uses the internal dispatch network
plus the trusted runtime-only provider-egress network, the
mounted runtime secret, the API/worker host callback endpoints, and the
existing credential-state volume. Its service definition extends the canonical
community deployment service, so image, entrypoint, sandbox, healthcheck, and
credential-mount changes remain owned in one Compose definition:

```sh
pnpm check:local-dev
pnpm check:local-dev:agent
PLANE_AGENT_RUNTIME_ENABLED=1 docker compose --profile agent -f docker-compose-local.yml up -d
docker compose --profile agent -f docker-compose-local.yml ps api worker agent-runtime
docker compose --profile agent -f docker-compose-local.yml exec agent-runtime \
  python3 -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8080/health/ready", timeout=2).read().decode())'
```

If the image cannot be pulled or the secret is absent, only this explicit
agent-mode startup is expected to fail; ordinary Plane services remain
independent of the profile. Do not add provider credentials to the Compose
file or pass them to generated child code. A local runtime invocation still
uses Plane's host-side `RuntimeCredentialBroker`; provider/model calls are
outside this offline topology check.

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

| Dimension          |                                                   Candidate threshold | Evidence emitted                                 |
| ------------------ | --------------------------------------------------------------------: | ------------------------------------------------ |
| Workload           |                          128 requests, 8 workers, 16 agent identities | `requests`, `workers`, `measuredAgentIdentities` |
| Sustained duration |                   at least 0.75 seconds with 25 ms inter-batch pacing | `sustainedDurationSeconds`                       |
| Throughput         |                                            at least 2 requests/second | `throughputPerSecond`                            |
| Latency            |                           p95 at most 7,500 ms; p99 at most 10,000 ms | `latencyMs.p95`, `latencyMs.p99`                 |
| Error rate         |                                                0% unexpected statuses | `errors`, `errorRate`                            |
| Saturation         |                                          at least 1% quota throttling | `throttled`, `saturation`                        |
| Queueing           |                               p95 executor queue delay at most 750 ms | `queueingMs.p95`                                 |
| Database/resource  |           at most 24 PostgreSQL sessions, 768 MiB RSS, 90 CPU seconds | `resources`                                      |
| Safety invariants  | full correlation/audit coverage, one replay row/effect, quota cleanup | `thresholdResults`, `breaches`                   |

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
repaired runner source correction
`e9010dec4adde127b4a7249b06efdd1356e3628e`; the final offline evidence
wrapper is its exact single child. The previously accepted G3 candidate is Plane commit `7c9d35f4c324865c27c84da5016be2c84e460bcc`.
The current binding carries Hermes commit
`114eabf9d807b659e36d767e4de46ca056297ccb`, MCP gitlink
`2dc152e136d7ad952b901e5fe9364a37487297ba`, SDK gitlink
`7d2faf3b7ef5409e292ba0a3c7015e59f93c5889`, runtime image tag
`plane-agent-runtime:hermes-114eabf9-g4-c47ddfe`, runtime image digest
`sha256:b4a701905bae50bef643ef67c3883ef74d8f6ddcde2cf669d1dab50c44999b0c`,
runtime revision/source revision `c47ddfe6174ecd6d66257d8fedbd5d425c7f3172`, and runtime
contract `plane.agent-runtime/v1`. The Plane service revision above is the
repaired source candidate; the runtime image/runtimeRevision source is
`c47ddfe6174ecd6d66257d8fedbd5d425c7f3172`, which was used to build the
candidate image. The wrapper carries only the existing binding, fixture, and
evidence documentation. The live helper is mounted read-only into the
unchanged API image, so no image rebuild or provider invocation is part of
this repair. API, worker, `beat-worker`,
supervisor, and `agent-runtime` each switch their service revision and image
digest to the corresponding current value in that manifest; the operation services retain
`plane.operation/v1` and the runtime services retain `plane.agent-runtime/v1`.
The previous services use immutable image digest
`sha256:51b50bec143e12c22fa92f8b101629d37ae263f2784c9bb3747eaea45978092e`,
the image pin recorded by the accepted G3 verifier. The rollback reasserts
these immutable pins rather than accepting a mutable tag.

For final-wrapper integration, the one canonical current-parent field is
`tools/agent-g4-manifest.json:candidateBinding.parentCommit`. Set it to the
wrapper’s immediate parent after all implementation lanes are integrated; the
verifier derives the expected current parent from that field and requires the
materialized fixture `current.planeCommit` and its manifest SHA-256 to agree
before the rollback stage can run. The exact wrapper itself remains an
external operator input, not candidate-controlled metadata.

Migration `db.0142_runtime_provider_attempts` is additive: it adds the
non-secret provider-attempt intent/terminal evidence table. Rollback is
explicitly forward-only: keep the database at leaf `0142`, never reverse to `0141`,
and run the prior services only after confirming they ignore the
provider-attempt evidence. The `0142` migration blob is
`d8d2452445ad96372f917b5819e3ede0c332f560` and its SHA-256 is
`efed3980eb182d138bf13991fefa709c285451c89300cb81faa2a8a31572f9da`.
The compatibility floor is `0141` (blob
`1c6b0e3fb221cccd9ed2631d68cbf10ba5dc399b`), not a downgrade target.

### Disposable executable drill

The drill performs current-candidate upgrade, creates a representative
`outcome_unknown` operation with an already-committed durable effect, switches
all five service pins/contracts, keeps migration `0142`, reconciles from the
effect/audit/outcome state, releases quota, checks idempotent re-run, and
removes its temporary database. It never connects to Plane or deploys:

```sh
python3 tools/agent-g4-rollback-drill.py
```

The one-line JSON result must contain `passes:true`, empty `breaches`,
`externalWrites:false`, `migrationLeaf:"db.0142_runtime_provider_attempts"`,
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
report leaf `0142`. Read back every affected idempotency record, gateway audit
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
mutable tag, services disagree on the contract, `0142` is absent or a reverse
plan appears, audit/outcome/provider-attempt readback is incomplete, a durable effect is not
unique, quota remains active after reconciliation, or runtime enforcement does
not acknowledge the safety stop. Preserve bounded logs and identifiers only;
never include a runtime secret or provider credential.

### Verifier authority, exclusion, and retained receipt

The offline G3/G4 verifiers share one process-lifetime advisory lock at
`tmp/plane-agent-g-verifier.lock`. The lock is held across the verifier
process via `flock`; a second verifier fails closed before preflight, and no
owner file or PID-reuse cleanup is performed inside the verifier.

Before G3 begins, G4 bind-mounts the supplied Hermes checkout into the
prepared API test image with the same read-only Docker contract used by the
runtime test containers and verifies representative source and Git metadata
are readable. A disposable checkout may be marked with
`PLANE_G4_DISPOSABLE_HERMES_ROOT=1` only when its path matches
`ROOT_DIR/tmp/plane-g4-hermes-*`; the existing G4 cleanup then removes that
exact non-symlink directory and verifies it is gone.

G4 requires the operator to provide the exact final wrapper SHA through
`PLANE_G4_EXPECTED_CANDIDATE`. The verifier, live authority validator, and
live invocation each require `HEAD` to equal that external value. The
committed manifest binds only the approved source parent; it does not embed a
self-referential wrapper SHA. Sibling wrappers and descendants therefore do
not satisfy the candidate gate.

Set `PLANE_G4_RECEIPT_PATH` to retain the sanitized verifier receipt and its
`.sha256` sidecar outside disposable cleanup. The receipt contains stage
result lines and exact source, wrapper, image, Hermes, MCP, SDK, and runtime
contract pins, but no raw logs, secrets, credentials, or provider payloads.

The active line has no dispatch-diagnostic JSON field from donor ADR-0011;
its equivalent diagnostic ownership is the Plane-owned
`RuntimeProviderAttempt` identity/fingerprint. Run-detail API and CLI
readbacks validate invocation/run/scope ownership and the stored fingerprint,
and fail closed on corruption. ADR-0011 is therefore not ported as a second
diagnostic representation.

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
