# Plane Agent runtime operations

This runbook covers the disposable, separately configured Plane Agent runtime
boundary. It does not replace Plane's supervisor, assignment, lease, or
terminal-event authority. A runtime process may be replaced after a lease
death, but an `outcome_unknown` invocation must be reconciled by Plane before
any replay.

Keep three ambiguity scopes separate. A provider request becomes
`outcome_unknown` after upstream initiation without a definitive result; the
relay returns a bounded non-retryable error. An invocation becomes
`OUTCOME_UNKNOWN` when Plane must reconcile runtime completion. A Plane
mutation can separately have an `OUTCOME_UNKNOWN` gateway receipt. After
upstream initiation, an unresolved provider request is fail-stop: never retry
the same logical request, and wait for reconciliation or an explicitly
authorized new-invocation policy before later execution.

An applied `outcome_submission` publication requests an immediate
non-cancellation terminal stop of the kernel. That stop ends kernel execution
without recording a Plane cancellation. The first visible Plane terminal event
wins. A late `RuntimeExit`, including `budget_exhausted`, remains visible in
runtime-exit evidence and control diagnostics; it cannot replace or relabel
the product terminal. S00 passes and replays only when one applied
`outcome_submission` terminal is bound to the outcome and the same invocation
has a clean `RuntimeExit.completed`. Invocation state is not enough. The
finite budget remains a safety policy; the numeric model-call allowance is
configuration.

## Omar synthetic operator route

The provider-free handoff descriptor is
`tools/agent-g4-operator-v6.json`. It uses only the existing
`fixture:assigned-work-item` setup and four bounded commissions:

- O01/O03: presentation-only disclosure and SDK bearer-identity failures,
  including invalid, expired, wrong-workspace, and substituted callers;
- O04/O05: runtime-credential rotation, revocation, and expiry across queued
  and active work, plus host-only replay/mismatch boundaries;
- O06/O07: pre-send resume, post-send `outcome_unknown`, one terminal, and
  cumulative budgets;
- O08/O09/O10: hostile runtime ingress, concurrent gateway health/quota, and
  rollback/provenance.

O02 is intentionally absent because its external-client journey is already
closed. The descriptor is validated by the existing scenario parser and live
receipt validator; it does not add an authorization source, runtime authority,
or second verifier. After the coordinator supplies final exact image pins, copy
the descriptor to a fresh owner-only path and pass its SHA-256 with the existing
`PLANE_G4_SCENARIO_DESCRIPTOR` / `PLANE_G4_SCENARIO_SHA256` inputs. No provider
or external workspace is used to stage or validate the descriptor.

The typed JSON ambiguity marker is available only before the relay response
starts. Once a Plane-relay `200` stream has started, downstream body-read
ambiguity is fail-stop at Hermes and the same logical request is not retried.
The relay does not buffer the whole provider response or introduce a new
control-frame protocol for this case.

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
request to the pinned ChatGPT subscription route at `chatgpt.com`; the provider
path `/backend-api/codex/responses`, base URL
`https://chatgpt.com/backend-api/codex/responses`, provider `openai-codex`, and
model `gpt-5.6-luna` remain enforced by the authority/config descriptor. The
bootstrap argument is
`--provider-relay-socket`.

The exact Hermes source commit is now integrated through
`bootstrap → service → serve_once_g1 → HermesKernelAdapter → run_agent.AIAgent`;
no Plane-side client factory or AIAgent patch is used. The candidate image is
pinned in the manifest below. Until a separately authorized live run proves
it, provider/model calls remain unperformed and live G4/G5 remain incomplete.

The live runner reads `PLANE_G4_LIVE_MANIFEST` when set and otherwise uses
`tools/agent-g4-manifest.json`. A disposable exact-candidate API artifact
manifest must be a regular file under the repository-owned `tmp/` directory;
the runner canonicalizes and validates that path before reading credentials or
starting Docker. Authority/config binding, artifact and runtime pins, and the
resulting cleanup remain confined to the runner's generated project/run
resources. Never edit the durable manifest for a disposable artifact rehearsal.

The durable `candidateBinding.mode=exact-single-child` contract is intentionally
narrow: with no `disposableBinding`, the selected `HEAD` must have exactly one
parent and that parent must equal `candidateBinding.parentCommit`. An advanced
dogfood branch is rejected during config-only preflight, before provider-source
read, Docker, relay, DNS, or product mutation. For
`candidateBinding.mode=disposable-exact-candidate`, use the existing
`tools/build-agent-runtime-image.py` path to build and attest the exact API and
runtime candidate, then point the runner at the generated manifest; a complete
`disposableBinding` must bind its API/runtime revisions to `HEAD` and retain the
Hermes and image pins. For example, from the clean candidate checkout:

```sh
G4_CANDIDATE="$(git rev-parse HEAD)"
G4_HERMES_REVISION="<exact-clean-hermes-sha>"
G4_MCP_REVISION="<exact-clean-mcp-sha>"
G4_SDK_REVISION="<exact-clean-sdk-sha>"
python3 tools/build-agent-runtime-image.py \
  --hermes-checkout /path/to/hermes-agent \
  --hermes-revision "${G4_HERMES_REVISION}" \
  --plane-revision "${G4_CANDIDATE}" \
  --api-image "${G4_API_IMAGE}" \
  --mcp-revision "${G4_MCP_REVISION}" \
  --sdk-revision "${G4_SDK_REVISION}" \
  --manifest-out "${PWD}/tmp/plane-agent-g4-disposable-${G4_CANDIDATE}.json"
PLANE_G4_LIVE_MANIFEST="${PWD}/tmp/plane-agent-g4-disposable-${G4_CANDIDATE}.json" \
  tools/agent-g4-live.sh
```

The builder's existing `--hermes-donor-image` mode is equivalent when the
manifest-bound sealed Hermes image is the selected source. Do not hand-edit the
durable manifest, and do not treat a missing disposable binding as proof for an
advanced candidate.

The default invocation has no scenario environment and remains the S00
worker/profile/assignment contract. A user-testing commission may supply one
owner-only descriptor and its exact digest:

```sh
PLANE_G4_SCENARIO_DESCRIPTOR="${PWD}/tmp/worker-scenario.json" \
PLANE_G4_SCENARIO_SHA256="$(shasum -a 256 "${PWD}/tmp/worker-scenario.json" | awk '{print $1}')" \
tools/agent-g4-live.sh
```

The versioned `plane.agent-scenario/v1` descriptor supports `worker`, `manager`,
and `operator` identities. It contains only the Plane actor role, immutable
profile instructions/model policy, assignment target/objective/acceptance and
context references, a bounded prompt, and optional bounded evidence predicates.
The optional typed `setup` block adds finite preconditions, related actor
descriptors, one parent/child lineage binding, and one cron/timezone schedule;
`controls` adds one continuation or revision input, cancellation timing, and a
finite fault selection. These fields are setup/readback inputs, not a workflow
definition or permission grant. `expected` may additionally name bounded
durable-record and product-event counts. The runner compares these predicates
with its existing Plane operation-audit, terminal-event, and publication
readback before publishing scenario evidence.
The reserved target `fixture:assigned-work-item` resolves to the real issue
created by the existing live invocation; other target references remain exact.
The runner validates the owner-only non-symlink path, digest, schema, fields,
role/model, bounds, and credential-like values before reading the provider
source, starting relay/runtime or network/DNS, making a provider request, or
mutating Plane. It stages the descriptor into a task-owned read-only Docker
volume and records the scenario ID and descriptor digest in retained evidence.
Scenario/profile data changes behavior and tool presentation only; the live
Plane actor and its permissions remain separately provisioned authority. The
descriptor has no credentials, executable hooks, imports/shell, workflow DSL,
bootstrap operations, or alternate permission allowlist.

The identity/expectation projection in a descriptor looks like this (the
required profile, assignment, and prompt fields remain unchanged):

```json
{"scenarioId":"worker","actor":{"role":"worker"},"expected":{"operationOutcomes":[{"operationId":"work_item.read","outcome":"success"}],"evidenceKinds":["audit"]}}
```

Manager descriptors use `actor.role: "delegator"` and may bind
`setup.lineage.parentActorRef` to `actor:primary`; Operator descriptors use
`actor.role: "worker"` and may bind a related worker as the child. The
descriptor parser rejects unknown fields, forbidden values, invalid role
bindings, and continuation/revision conflicts. A descriptor cannot change
Plane authorization; live authorization and the existing S00 gate remain final.

The authority and config carry the same canonical `providerRelay` projection.
The runner's config-only preflight requires that projection and exact equality
before it reads or stages the provider source. It forwards the validated
authority projection to the API invocation, so the success or runtime-failure
receipt cannot drift from the preflight contract. A relay-free failure receipt
is accepted only when its bounded facts prove that no runtime or provider
receipt existed; missing or mismatched relay data remains a standalone
validation failure.

For the live runner, the validated owner-only provider source is copied into a
fresh task-owned Docker volume through the Docker client's stdin path. The
preflight container verifies the volume file as a regular `0600` file within
the 64 KiB bound, and the API invocation mounts that volume read-only at
`/run/secrets`. The generated runtime secret uses a separate sibling mount at
`/run/plane-agent-runtime-secret`; it is not nested under the read-only
provider mount. The invocation helper is streamed to the API container's
stdin rather than bind-mounted. This avoids the nested `/run/secrets`
mountpoint failure and avoids requiring Docker Desktop or Colima to see the
runner's source checkout. The runner removes the provider volume and staged
host files during the same exact-project cleanup; no provider credential
enters argv, environment, logs, image layers, or generated evidence.

### Live runner result handoff

The live runner preserves its bounded stdout receipt before destroying the
disposable run directory. Set `PLANE_G4_LIVE_RESULT_PATH` to a new absolute
destination when the caller needs a stable path; its existing parent must be
owned by the caller and have no group/world permissions. If omitted, the
runner creates a fresh `*.result` file under the repository-owned `tmp/`
directory. Existing destinations and symlinks are refused. The published file
is owner-only (`0600`) and is made visible atomically, so callers never read a
partially written final result.

The result file bytes are exactly one schema-controlled JSON receipt: the
existing `EVIDENCE_FILE` object when the API reached its evidence boundary, or
the finite `plane-agent-g4/live-runner-failure/v1` receipt for a failure before
that boundary. Human failure status is written to stderr and is never
prepended to the result, so callers can parse the result with one JSON decode.
The raw `ERROR_FILE`, runtime transcript, model text, credentials, and host
paths are never copied to the result file.

The user-testing caller owns acknowledgment: after the runner exits, read and
hash the result file, validate the bounded receipt, then delete that exact
file. The runner has already removed its containers, volumes, network, staged
secret, and `RUN_DIR`; the result file is the only handoff artifact and is not
removed by runner cleanup. A failed read, hash, validation, or delete is an
unacknowledged result and must use a fresh destination for the next run.

The S00 live invocation performs exactly one eligible replay inside the API
invocation, after the primary has fully succeeded and before disposable
teardown. Eligibility requires one applied `outcome_submission` terminal and a
clean completed runtime exit. A failed, missing, or `outcome_unknown` exit
never enters the replay branch. An eligible replay reuses the same
invocation/idempotency identity with provider credentials disabled, so the
existing terminal-invocation short circuit must return zero runtime frames.
The bounded pass receipt records the validated authority ID, authority-derived
canary IDs, the ordered redacted `s00Gate` projection, and a semantic SHA-256
digest over the complete bounded receipt body. It also records ordered provider
attempts, all seven allowlisted operation summaries, RuntimeExit, runtime event
counts, transcript-evidence status and event IDs/count, explicit publication
refs, and zero deltas for provider attempts, child dispatch, invocations, receipts,
audits, usage, outcomes, publications, terminal events, and semantic effects.
`not_observed` with `not_required` is valid only for the applied
terminal-publication profile. It records no transcript payload and does not
claim that ordinary assistant text occurred. A required ordinary-text proof
must report `observed` evidence.
Failure receipts use the same gate projection and digest contract with
not-evaluated canaries. The standalone validator recomputes the digest and
rejects missing, tampered, mismatched, secret-bearing, or oversized receipts.
Failed or `outcome_unknown` primaries never enter this replay branch.

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
manifest. The current Plane deployable service candidate is the exact source
`c51776e041ecfa6a316eb18674723e8a889bec2d`; the final candidate is
exactly one metadata wrapper child of that source. The previously accepted G3
candidate is Plane commit `7c9d35f4c324865c27c84da5016be2c84e460bcc`.
Its immutable API artifact is
`plane-agent-api:g4-v66-c51776e0` at
`sha256:63700bf885812178cbbc3984dc77f104a8f806ab4d189abc4b1e27338144c1bb`,
and its runtime artifact is
`plane-agent-runtime:hermes-d6938038-g4-v66-c51776e0` at
`sha256:4d85056905b7623960336d204e2ceb6cc9257a5c191e2aa6aece7b82c6704653`.
The API is source-bound to `c51776e041ecfa6a316eb18674723e8a889bec2d`; the
runtime remains source-bound to `c51776e041ecfa6a316eb18674723e8a889bec2d`,
with runtime contract `plane.agent-runtime/v1` and API contract
`plane.operation/v1`.

The runtime binding carries Hermes commit
`d6938038f35027bb818756f19e03ce702889d210` from the `uxheavy` checkout, MCP gitlink
`c04974ed6624f17b41e63ef8182661929e77e0d3`, and SDK gitlink
`7d2faf3b7ef5409e292ba0a3c7015e59f93c5889`. The runtime image tag is
`plane-agent-runtime:hermes-d6938038-g4-v66-c51776e0`, and the runtime image digest is
`sha256:4d85056905b7623960336d204e2ceb6cc9257a5c191e2aa6aece7b82c6704653`.
The runtime revision is
`c51776e041ecfa6a316eb18674723e8a889bec2d`. The Plane service revision above is
the current executable artifact revision; the runtime image/runtimeRevision source is
`c51776e041ecfa6a316eb18674723e8a889bec2d`. The API image tag is
`plane-agent-api:g4-v66-c51776e0` and the API image digest is
`sha256:63700bf885812178cbbc3984dc77f104a8f806ab4d189abc4b1e27338144c1bb`.
The API source revision is
`c51776e041ecfa6a316eb18674723e8a889bec2d`; the API contract is
`plane.operation/v1`. The exact-image red-team proof
passes the real Hermes loop, progressive `catalog.search`/`catalog.describe`,
verbatim search-result-to-read handoff with target-digest correlation,
`plane.code-mode.execute@1`, authorized read and mutation, exact
`NOT_AUTHORIZED`, authorized versioned assigned-work-item read, one `OutcomeSubmission`, one applied publication, transcript
evidence, idempotency replay, and late post-publication terminal handoff. Its
bounded fixture has 16 planned transport turns plus one terminal stop, 13
gateway records excluding one duplicate-mutation replay, and exactly one
applied publication. The final exact-image bootstrap also completes with one
synthetic relay call and `intent → started → completed`; no provider-backed
acceptance is claimed.

G3, G4, and the live helper execute the image-contained `/workspace/apps/api`
tree; they do not bind-mount a newer host API source tree. API, worker,
`beat-worker`, supervisor, and `agent-runtime` each use the corresponding
current artifact revision and image digest in the manifest. The `previous`
rollback section independently retains the last known-good G3 service
revisions and digests.
The previous services use immutable image digest
`sha256:51b50bec143e12c22fa92f8b101629d37ae263f2784c9bb3747eaea45978092e`,
the image pin recorded by the accepted G3 verifier. The rollback reasserts
these immutable pins rather than accepting a mutable tag.

### Pre-live verifier lifecycle incident

A fresh pre-live root run on wrapper
`0330003e71ffda6076cee807cd8c5f6eb2e11911` passed preflight, the G3
prerequisite at `281/281`, and static scope, then failed before runtime test
process creation at `g4-runtime-contracts`: the Docker bind source
`/tmp/plane-g4-hermes-live-current` had been removed during G3 cleanup even
though the disposable flags were false. The retained failed receipt has
SHA-256
`4e2a96a9fcaa5dccf5a8a1994b008016bf45aa7b8cc5c163f32aabb4cb4f958c` and its
captured failure log has SHA-256
`a412273116e90263dabade32d29e1a2b856e8dde64fe8c047c88850a5bf7bc52`.

This was a pre-live infrastructure failure, not a provider result: the
receipt counters are `provider_requests=0`, `live_requests=0`,
`credential_mutations=0`, and `G5_actions=0`; no provider, credential, or G5
boundary was reached, so the run is not `outcome_unknown`. The corrected
ownership rule is structural: G4 treats both caller-supplied current and
independent G3 Hermes checkouts as bind-only inputs, while G3 removes only its
own `.g3-runtime-logs-*` directory after checking the creation flag, namespace,
real-directory, and non-symlink conditions. Recreate or verify both exact
Hermes pins before another offline run; never replay a live invocation.

### Retained authorized pre-container failure

The separately retained explicitly authorized live G4 receipt
`/private/tmp/plane-g4-live-ec777-authorized.8uFekd/receipt.json` has SHA-256
`2013336c367397263ea1d5fdf41e46dfda5ed449c8f0be39913f5c6d5c727861`. It
failed at `api-invocation` with Docker exit 125 because the runner directly
mounted the caller-owned provider source under `/private/tmp`, which was not
bind-visible to Colima. No Plane run, invocation, or evidence object was
created. The receipt counters are `provider_requests=0`, `live_requests=0`,
`credential_mutations=0`, and `G5_actions=0`; cleanup removed zero resources.
This is bounded pre-container failure evidence, not live acceptance or
`outcome_unknown`, and it must never be replayed.

The canonical API artifact build uses `apps/api` as its Docker context because
`apps/api/Dockerfile.g4` copies that context to `/workspace/apps/api`:

```sh
docker build -f apps/api/Dockerfile.g4 \
  --build-arg BASE_API_IMAGE=plane-g3-external-client-api-tests:prepared \
  --build-arg PLANE_API_SOURCE_REVISION="$PLANE_API_SOURCE_REVISION" \
  --build-arg PLANE_API_IMAGE_TAG="$PLANE_API_IMAGE_TAG" \
  --build-arg PLANE_API_MANAGE_SHA256="$PLANE_API_MANAGE_SHA256" \
  --build-arg PLANE_API_READBACK_SHA256="$PLANE_API_READBACK_SHA256" \
  --build-arg PLANE_API_ADMIN_SHA256="$PLANE_API_ADMIN_SHA256" \
  --build-arg PLANE_API_CORRUPTION_TEST_SHA256="$PLANE_API_CORRUPTION_TEST_SHA256" \
  --build-arg PLANE_API_PROVIDER_CONFIG_SHA256="$PLANE_API_PROVIDER_CONFIG_SHA256" \
  apps/api
```

The Dockerfile rejects a repository-root context before labeling an artifact,
requires the executable `manage.py`/`plane` tree without `apps/api` nesting,
checks exact SHA-256 values for the readback, admin, corruption-regression,
and provider-configuration sources, and proves image dependencies with
network-disabled imports. The verifier repeats the executable-path, digest,
full source-label, contract-label, and artifact-label checks.

For final-wrapper integration, the one canonical current-parent field is
`tools/agent-g4-manifest.json:candidateBinding.parentCommit`. Set it to the
wrapper’s immediate parent after all implementation lanes are integrated; the
verifier derives the expected current parent from that field and requires the
materialized fixture `current.planeCommit` and its manifest SHA-256 to agree
before the rollback stage can run. The exact wrapper itself remains an
external operator input, not candidate-controlled metadata.

Migration `db.0146_runtime_reconciliation_audit_fields` is the additive audit
extension to `db.0145_runtime_reconciliation`. Rollback is explicitly
forward-only: keep the database at leaf `0146`, retain migration `0145`, never reverse to `0144`,
and run the prior services only after confirming they
operate with the retained reconciliation state and ignore the 0146 audit
fields. The `0146` migration blob is
`96a5f1cc7064f47812dcbfa63000ab4a0180c526` and its SHA-256 is
`3683fa478b11cee40a4b109ec2f89f6cb2c5aef4b1c8555a5e4d0991ca01de0b`.
The compatibility floor is `0145` (blob
`4755af8136e404b06c21aca2132710dbeda4ed4c`), not a downgrade target.

### Disposable executable drill

The drill performs current-candidate upgrade, creates a representative
`outcome_unknown` operation with an already-committed durable effect, switches
all five service pins/contracts, keeps migrations `0145` and `0146`, reconciles from the
effect/audit/outcome state, releases quota, checks idempotent re-run, and
removes its temporary database. It never connects to Plane or deploys:

```sh
python3 tools/agent-g4-rollback-drill.py
```

The one-line JSON result must contain `passes:true`, empty `breaches`,
`externalWrites:false`, `migrationLeaf:"db.0146_runtime_reconciliation_audit_fields"`,
three audit rows, one outcome, one idempotency row, zero active quota
reservations, and `cleanup.temporaryDatabaseRemoved:true`. This is the
exercised rollback proof; a prose-only rollback is not sufficient.

### Coordinated service switch and verification

For an authorized disposable Compose rehearsal, render and inspect the
resolved configuration with the exact previous pins before replacement, then
switch API, worker, beat-worker, runtime, and the Plane supervisor control
path as one change window. The rollback fixture validates `artifactKind` and
`artifactSourceRevision` per service: API, worker, beat-worker, and the
API-image `python manage.py agent_supervisor` control path use the typed API
artifact; only the standalone `agent-runtime` service uses the typed runtime
artifact. This mapping follows the community Compose service commands and the
live helper's immutable API invocation image:

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
report leaf `0146`, with `0145` retained as its compatibility floor. Read back every affected idempotency record, gateway audit
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
mutable tag, services disagree on the contract, `0145` or `0146` is absent or a reverse
plan appears, audit/outcome/provider-attempt readback is incomplete, a durable effect is not
unique, quota remains active after reconciliation, or runtime enforcement does
not acknowledge the safety stop. Preserve bounded logs and identifiers only;
never include a runtime secret or provider credential.

### Verifier authority, exclusion, and retained receipt

The historical accepted-baseline-to-candidate Gitleaks scan traverses the
immutable superseded wrapper `9ff8b952872e9201e2f0f2e8c6621c273d33f49b`, whose
manifest had one non-secret Git revision value under the former flat
`apiSourceRevision` field. Gitleaks fingerprinted that finding as
`9ff8b952872e9201e2f0f2e8c6621c273d33f49b:tools/agent-g4-manifest.json:generic-api-key:47`.
That exact fingerprint alone is recorded in the repository `.gitleaksignore`;
it is not a file, rule, pattern, or value-family suppression. Current
provenance uses the typed `pins.apiArtifact.sourceRevision` field, and the
contract tests run the historical and current scans plus an unrelated real
`apiKey`-shaped secret to prove the detector remains active.

The offline G3/G4 verifiers share one process-lifetime advisory lock at
`tmp/plane-agent-g-verifier.lock`. The lock is held across the verifier
process via `flock`; a second verifier fails closed before preflight, and no
owner file or PID-reuse cleanup is performed inside the verifier.

Before G3 begins, G4 validates two independent read-only Hermes checkouts:
the current runtime checkout at `d4b32a3e0ac9b528eb6e513274227e18a279906c`
and the accepted G3 checkout at
`114eabf9d807b659e36d767e4de46ca056297ccb`. The G3 prerequisite receives
only the accepted-baseline checkout, while current G4 runtime tests receive
only the current checkout; path equality is rejected as cross-mixing. A
`PLANE_G4_DISPOSABLE_HERMES_ROOT=1` is only a validation switch for caller-owned
disposable paths: it requires the current path to match
`ROOT_DIR/tmp/plane-g4-hermes-*` and the G3 path to match
`ROOT_DIR/tmp/plane-g4-hermes-g3-*`. It never transfers cleanup ownership;
G4/G3 retain both external checkouts, and the external creator removes those
exact non-symlink directories. Both checkouts must
retain the `https://github.com/uxheavy/hermes-agent.git` remote; a local
filesystem clone is not an accepted provenance source even when its commit
and worktree are otherwise exact.

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
An older previously blocked live canary receipt remains retained by SHA-256
`20be555eb93cac98a53ea3c0be1f56d3b6642179b77d9b6acf76ffd23dc76c7a`; that
historical attempt is permanently `outcome_unknown` and must not be replayed.
The later authorized pre-container failure is separately retained by SHA-256
`2013336c367397263ea1d5fdf41e46dfda5ed449c8f0be39913f5c6d5c727861` and has
zero provider/live/credential/G5 action counters.

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
