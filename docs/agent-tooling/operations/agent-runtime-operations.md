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
docker compose --env-file deployments/cli/community/variables.env \
  -f deployments/cli/community/docker-compose.yml config --quiet
docker compose --env-file deployments/cli/community/variables.env \
  -f deployments/cli/community/docker-compose.yml ps agent-runtime
```

The runtime has an internal-only Docker network shared with API/worker for the
authenticated dispatch and host callback seams. It has no published host
port. Its health endpoint is checked from inside the disposable container:

```sh
docker compose --env-file deployments/cli/community/variables.env \
  -f deployments/cli/community/docker-compose.yml exec agent-runtime \
  python3 -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8080/health/live", timeout=2).read().decode())'
docker compose --env-file deployments/cli/community/variables.env \
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
docker compose exec agent-runtime python3 -c '
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
docker compose logs --tail=100 agent-runtime
docker inspect --format '{{json .State.Health}}' "$(docker compose ps -q agent-runtime)"
```

Check whether the status is `dependency_failure`, `draining`, or
`outcome_unknown`; do not interpret a missing child result as success. Check
the safety-stop marker and the Compose resource/security settings before
restarting. Runtime process diagnostics are capped; request and response
frames are canonical JSON and no ambient parent environment is inherited.

## Rollback

The runtime image and command are configuration, not a database migration.
Pin the previously validated image tag, resolve Compose again, then replace
only the runtime service:

```sh
docker compose -f deployments/cli/community/docker-compose.yml \
  up -d --no-deps --force-recreate agent-runtime
```

Do not replay an invocation merely because the container was replaced. Plane's
supervisor must establish lease ownership and reconcile any
`outcome_unknown` state first. Exactly one Plane terminal event remains the
authority.

## Restore and reconciliation

Restore the disposable runtime marker and container state only after the
incident is understood. Re-check the runtime checkout/image identity, command,
resource policy, and readiness. Reconcile every affected invocation from
Plane's durable state; mark cancellation and lease death through the existing
supervisor paths. A completed transport-ledger frame may be read only for the
same invocation digest; a running or outcome-unknown ledger entry is never a
blind replay authorization.

## Evidence cleanup

Use a disposable Compose project and remove it after collecting the required
bounded evidence:

```sh
docker compose -f deployments/cli/community/docker-compose.yml down -v --remove-orphans
```

Remove any local safety-stop marker and temporary ledger created for the test.
Confirm that shell history, command output, container logs, and test artifacts
contain no secret value. Never delete a production ledger or evidence store as
part of this disposable cleanup.
