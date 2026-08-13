#!/usr/bin/env bash

set -Eeuo pipefail
umask 077

ROOT_DIR="$(pwd)"
PROJECT="plane-agent-g4-live-${PPID}-${RANDOM}"
NETWORK="${PROJECT}_test_env"
EGRESS="${PROJECT}_egress"
RUNTIME="${PROJECT}-agent-runtime"
CREDENTIAL_STATE_VOLUME="${PROJECT}_agent_runtime_credential_state"
CREDENTIAL_STATE_TARGET="/run/plane-agent-credentials"
CREDENTIAL_STATE_FILE="${CREDENTIAL_STATE_TARGET}/revocations.json"
TMP_ROOT="${ROOT_DIR}/tmp"
RUN_DIR="${TMP_ROOT}/${PROJECT}"
EVIDENCE_FILE="${RUN_DIR}/evidence.json"
ERROR_FILE="${RUN_DIR}/sanitized-error.log"
RUNTIME_SECRET_FILE="${RUN_DIR}/runtime-secret"
PROVIDER_SECRET_FILE="${RUN_DIR}/provider-credentials"
RUN_DIR_CREATED=0
CREDENTIAL_STATE_VOLUME_CREATED=0
LIVE_INVOKE_SOURCE="${ROOT_DIR}/tools/agent-g4-live-invoke.py"
MANIFEST_INPUT="${PLANE_G4_LIVE_MANIFEST:-${ROOT_DIR}/tools/agent-g4-manifest.json}"
LIVE_AUTHORITY="${PLANE_G4_LIVE_AUTHORITY:?validated live authority path is required}"
LIVE_CONFIG="${PLANE_G4_LIVE_CONFIG:?validated live config path is required}"
LIVE_COMMAND="${PLANE_G4_LIVE_COMMAND:?validated live command is required}"
RUNTIME_CHILD_ENVIRONMENT_JSON='{"HOME":"/tmp","HERMES_HOME":"/tmp/hermes-home","LANG":"C.UTF-8","LC_ALL":"C.UTF-8","PATH":"/usr/local/bin:/usr/bin:/bin","PYTHONPATH":"/tmp:/opt:/opt/hermes","PYTHONSAFEPATH":"1","PYTHONUNBUFFERED":"1"}'
G4_CANDIDATE="$(git rev-parse HEAD)"
G4_EXPECTED_CANDIDATE="${PLANE_G4_EXPECTED_CANDIDATE:?operator-supplied exact wrapper SHA is required}"
[[ "${G4_EXPECTED_CANDIDATE}" =~ ^[0-9a-f]{40}$ ]] || {
    printf 'event=agent.g4.live-runner status=failed expected=full_external_expected_candidate_sha actual=invalid suggestion=set_Plane_G4_EXPECTED_CANDIDATE\n' >&2
    exit 2
}
[[ "${G4_CANDIDATE}" == "${G4_EXPECTED_CANDIDATE}" ]] || {
    printf 'event=agent.g4.live-runner status=failed expected=HEAD=external_expected_candidate actual=head_mismatch suggestion=use_the_exact_authorized_wrapper\n' >&2
    exit 2
}

MANIFEST="$(python3 - "${ROOT_DIR}" "${MANIFEST_INPUT}" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
candidate = Path(sys.argv[2])
if not candidate.is_absolute():
    candidate = root / candidate

try:
    resolved = candidate.resolve(strict=True)
except (OSError, RuntimeError):
    raise SystemExit("manifest_path_missing_or_unresolvable")

durable = root / "tools" / "agent-g4-manifest.json"
disposable_root = root / "tmp"
if resolved != durable and not resolved.is_relative_to(disposable_root):
    raise SystemExit("manifest_path_out_of_scope")
if not resolved.is_file():
    raise SystemExit("manifest_path_not_a_regular_file")
print(resolved)
PY
)" || {
    printf 'event=agent.g4.live-runner status=failed expected=durable-or-owned-disposable-manifest actual=%s suggestion=use-the-default-or-a-regular-manifest-under-repository-tmp\n' \
        "${MANIFEST_INPUT}" >&2
    exit 2
}

# Authority/config validation is the egress boundary. It must complete before
# reading the provider source, creating a network, starting a relay/runtime, or
# invoking any API command. The runtime environment below is derived from the
# same validated provider descriptor; it is never a second policy input.
python3 "${ROOT_DIR}/tools/validate_agent_g4_live.py" \
    --authority "${LIVE_AUTHORITY}" \
    --config "${LIVE_CONFIG}" \
    --manifest "${MANIFEST}" \
    --candidate "${G4_CANDIDATE}" \
    --expected-candidate "${G4_EXPECTED_CANDIDATE}" \
    --command "${LIVE_COMMAND}" \
    --config-only >/dev/null

G4_G3_BASELINE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["candidateBinding"]["acceptedG3Baseline"])' "${MANIFEST}")"
G4_HERMES="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pins"]["hermesCommit"])' "${MANIFEST}")"
G4_MCP="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pins"]["mcpGitlink"])' "${MANIFEST}")"
G4_SDK="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pins"]["sdkGitlink"])' "${MANIFEST}")"
RUNTIME_IMAGE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pins"]["runtimeImageTag"])' "${MANIFEST}")"
G4_RUNTIME_IMAGE_DIGEST="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pins"]["runtimeImageDigest"])' "${MANIFEST}")"
G4_RUNTIME_IMAGE_REVISION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pins"]["runtimeImageRevision"])' "${MANIFEST}")"
G4_RUNTIME_CONTRACT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pins"]["runtimeContract"])' "${MANIFEST}")"
G4_API_IMAGE_TAG="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pins"]["apiArtifact"]["imageTag"])' "${MANIFEST}")"
G4_API_IMAGE_DIGEST="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pins"]["apiArtifact"]["imageDigest"])' "${MANIFEST}")"
G4_API_SOURCE_REVISION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pins"]["apiArtifact"]["sourceRevision"])' "${MANIFEST}")"
G4_API_CONTRACT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pins"]["apiArtifact"]["contract"])' "${MANIFEST}")"
API_IMAGE="${G4_API_IMAGE_TAG}"
LIVE_PHASE=initialization

PROVIDER_DESCRIPTOR_JSON="$(python3 - "${LIVE_CONFIG}" <<'PY'
import json
import sys

provider = dict(json.load(open(sys.argv[1], encoding="utf-8"))["provider"])
provider.pop("fallbackUsed", None)
print(json.dumps(provider, sort_keys=True, separators=(",", ":")))
PY
)"
IFS=$'\t' read -r G4_PROVIDER_NAME G4_PROVIDER_MODEL G4_PROVIDER_BASE_URL G4_PROVIDER_HOST G4_PROVIDER_PATH \
    G4_PROVIDER_CREDENTIAL_SOURCE G4_PROVIDER_CREDENTIAL_REF G4_PROVIDER_CREDENTIAL_NAME \
    <<<"$(python3 - "${PROVIDER_DESCRIPTOR_JSON}" <<'PY'
import json
import sys

provider = json.loads(sys.argv[1])
print("\t".join(provider[key] for key in (
    "name", "model", "baseUrl", "host", "path", "credentialSource", "credentialRef", "credentialName"
)))
PY
)"
PROVIDER_SECRET_SOURCE="${PLANE_G4_PROVIDER_SECRET_SOURCE:?configured provider source is required}"
PLANE_TEST_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48), end="")')"

api_image_id="$(docker image inspect "${API_IMAGE}" --format '{{.Id}}' 2>/dev/null)" || {
    printf '%s\n' 'event=agent.g4.live-runner status=failed expected=manifest-bound-api-image-available actual=image-unavailable suggestion=prepare-the-exact-immutable-api-artifact' >&2
    exit 2
}
[[ "${api_image_id}" == "${G4_API_IMAGE_DIGEST}" ]] || {
    printf '%s\n' "event=agent.g4.live-runner status=failed expected=api-image-digest=${G4_API_IMAGE_DIGEST} actual=${api_image_id} suggestion=use-the-manifest-bound-api-artifact" >&2
    exit 2
}
api_source_label="$(docker image inspect "${API_IMAGE}" --format '{{index .Config.Labels "org.uxheavy.plane.api.source.revision"}}')"
api_contract_label="$(docker image inspect "${API_IMAGE}" --format '{{index .Config.Labels "org.uxheavy.plane.api.contract"}}')"
api_artifact_label="$(docker image inspect "${API_IMAGE}" --format '{{index .Config.Labels "org.uxheavy.plane.api.artifact"}}')"
[[ "${api_source_label}" == "${G4_API_SOURCE_REVISION}" && "${api_contract_label}" == "${G4_API_CONTRACT}" && "${api_artifact_label}" == "plane-agent-api-g4" ]] || {
    printf '%s\n' 'event=agent.g4.live-runner status=failed expected=api-image-source-contract-artifact-labels-bound actual=label-mismatch suggestion=use-the-exact-immutable-api-artifact' >&2
    exit 2
}

safe_error_class() {
    python3 - "${ERROR_FILE}" <<'PY'
from pathlib import Path
import sys

allowed = (
    "ImproperlyConfigured",
    "CommandError",
    "RuntimeError",
    "OperationalError",
    "ConnectionError",
    "TimeoutError",
    "ModuleNotFoundError",
    "ImportError",
    "PermissionError",
    "FileNotFoundError",
)
try:
    text = Path(sys.argv[1]).read_text(errors="replace")
except OSError:
    print("unavailable")
else:
    for name in allowed:
        if name in text:
            print(name)
            break
    else:
        print("unspecified")
PY
}

cleanup() {
    local status=$?
    local cleanup_status=0
    if [[ "${status}" -ne 0 ]]; then
        printf 'event=agent.g4.live-runner.failure phase=%s error_class=%s exit_code=%s\n' \
            "${LIVE_PHASE}" "$(safe_error_class)" "${status}"
    fi
    if [[ -s "${EVIDENCE_FILE}" ]]; then
        cat "${EVIDENCE_FILE}"
    fi
    docker rm -f "${RUNTIME}" >/dev/null 2>&1 || true
    docker network rm "${EGRESS}" >/dev/null 2>&1 || true
    PLANE_TEST_ENV_FILE="${ROOT_DIR}/apps/api/.env.example" \
        docker compose -p "${PROJECT}" -f "${ROOT_DIR}/docker-compose-test.yml" down -v --remove-orphans >/dev/null 2>&1 || true
    if [[ "${CREDENTIAL_STATE_VOLUME_CREATED}" -eq 1 ]]; then
        if ! docker volume rm "${CREDENTIAL_STATE_VOLUME}" >/dev/null 2>&1; then
            printf 'event=agent.g4.live-runner status=failed phase=cleanup expected=credential-state-volume-removed actual=volume-removal-failed\n' >&2
            cleanup_status=1
        fi
        CREDENTIAL_STATE_VOLUME_CREATED=0
    fi
    if [[ "${RUN_DIR_CREATED}" -eq 1 && -d "${RUN_DIR}" && ! -L "${RUN_DIR}" ]]; then
        rm -f -- "${PROVIDER_SECRET_FILE}" || true
        rm -rf -- "${RUN_DIR}"
    fi
    if [[ "${cleanup_status}" -ne 0 && "${status}" -eq 0 ]]; then
        status=1
    fi
    exit "${status}"
}
trap cleanup EXIT INT TERM

LIVE_PHASE=credential-staging
if [[ ! -d "${TMP_ROOT}" ]]; then
    mkdir -m 700 -- "${TMP_ROOT}" || {
        printf '%s\n' 'event=agent.g4.live-runner status=failed expected=repository-owned-tmp-root actual=unavailable suggestion=use-a-writable-repository-owned-tmp-root' >&2
        exit 2
    }
fi
if [[ -L "${TMP_ROOT}" ]]; then
    printf '%s\n' 'event=agent.g4.live-runner status=failed expected=owner-only-non-symlink-tmp-root actual=unsafe suggestion=use-a-real-repository-owned-tmp-root' >&2
    exit 2
fi
chmod 700 "${TMP_ROOT}" || {
    printf '%s\n' 'event=agent.g4.live-runner status=failed expected=owner-only-tmp-root actual=unavailable suggestion=use-a-writable-repository-owned-tmp-root' >&2
    exit 2
}
mkdir -m 700 -- "${RUN_DIR}" || {
    printf '%s\n' 'event=agent.g4.live-runner status=failed expected=invocation-run-directory actual=unavailable suggestion=use-the-repository-owned-tmp-root' >&2
    exit 2
}
RUN_DIR_CREATED=1
python3 - "${PROVIDER_SECRET_SOURCE}" "${PROVIDER_SECRET_FILE}" <<'PY' >/dev/null 2>&1 || {
import os
import stat
import sys

MAX_PROVIDER_SECRET_BYTES = 64 * 1024
source_fd = None
destination_fd = None
destination_created = False
committed = False

try:
    source_fd = os.open(
        sys.argv[1],
        os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
    )
    source_stat = os.fstat(source_fd)
    if not stat.S_ISREG(source_stat.st_mode):
        raise SystemExit(10)
    if source_stat.st_size > MAX_PROVIDER_SECRET_BYTES:
        raise SystemExit(11)

    destination_fd = os.open(
        sys.argv[2],
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
    )
    destination_created = True
    os.fchmod(destination_fd, 0o600)

    copied = 0
    while copied <= MAX_PROVIDER_SECRET_BYTES:
        chunk = os.read(source_fd, min(1024 * 1024, MAX_PROVIDER_SECRET_BYTES - copied + 1))
        if not chunk:
            break
        copied += len(chunk)
        if copied > MAX_PROVIDER_SECRET_BYTES:
            raise SystemExit(11)
        view = memoryview(chunk)
        while view:
            written = os.write(destination_fd, view)
            if written <= 0:
                raise OSError("provider credential copy made no progress")
            view = view[written:]

    if copied != source_stat.st_size:
        raise OSError("provider credential changed during copy")
    if stat.S_IMODE(os.fstat(destination_fd).st_mode) != 0o600:
        raise OSError("provider credential mode is not owner-only")
    os.fsync(destination_fd)
    committed = True
finally:
    if destination_fd is not None:
        os.close(destination_fd)
    if source_fd is not None:
        os.close(source_fd)
    if destination_created and not committed:
        try:
            os.unlink(sys.argv[2])
        except FileNotFoundError:
            pass
PY
    printf '%s\n' 'event=agent.g4.live-runner status=failed expected=regular-bounded-owner-only-provider-source actual=staging-failed suggestion=provide-a-readable-non-symlink-file-at-most-64KiB' >&2
    exit 2
}

LIVE_PHASE=credential-bind-preflight
docker run --rm --network none \
    --mount type=bind,src="${PROVIDER_SECRET_FILE}",dst=/run/secrets/plane_agent_provider_credentials,readonly \
    --entrypoint python3 "${API_IMAGE}" -c '
import os
import stat

metadata = os.stat("/run/secrets/plane_agent_provider_credentials", follow_symlinks=False)
if not stat.S_ISREG(metadata.st_mode):
    raise SystemExit(1)
if stat.S_IMODE(metadata.st_mode) != 0o600:
    raise SystemExit(1)
if metadata.st_size > 64 * 1024:
    raise SystemExit(1)
' >/dev/null 2>&1

LIVE_PHASE=compose
python3 -c 'import secrets; print(secrets.token_urlsafe(48), end="")' >"${RUNTIME_SECRET_FILE}"

PLANE_TEST_ENV_FILE="${ROOT_DIR}/apps/api/.env.example" \
    docker compose -p "${PROJECT}" -f "${ROOT_DIR}/docker-compose-test.yml" \
    up -d --wait test-db test-redis test-mq test-minio >/dev/null 2>&1

docker run --rm --network "${NETWORK}" \
    --env DJANGO_SETTINGS_MODULE=plane.settings.test \
    --env POSTGRES_HOST=test-db \
    --env DATABASE_URL=postgresql://plane:plane@test-db:5432/plane \
    --env DATABASE_RUNTIME_URL=postgresql://plane:plane@test-db:5432/plane \
    --env DATABASE_MIGRATION_URL=postgresql://plane:plane@test-db:5432/plane \
    --env PLANE_AUDIT_RUNTIME_ROLE=plane_runtime \
    --env PLANE_AUDIT_GOVERNANCE_ROLE=plane_audit_owner \
    --env PLANE_AUDIT_MIGRATION_ROLE=plane_migrator \
    --env REDIS_HOST=test-redis \
    --env REDIS_URL=redis://test-redis:6379/ \
    --env RABBITMQ_HOST=test-mq \
    --env AMQP_URL=amqp://plane:plane@test-mq:5672/plane \
    "${API_IMAGE}" python manage.py bootstrap_operation_gateway_audit --phase=before-migrate >/dev/null 2>&1

LIVE_PHASE=migrate
docker run --rm --network "${NETWORK}" \
    --env DJANGO_SETTINGS_MODULE=plane.settings.test \
    --env POSTGRES_HOST=test-db \
    --env DATABASE_URL=postgresql://plane:plane@test-db:5432/plane \
    --env DATABASE_RUNTIME_URL=postgresql://plane:plane@test-db:5432/plane \
    --env DATABASE_MIGRATION_URL=postgresql://plane:plane@test-db:5432/plane \
    --env PLANE_AUDIT_RUNTIME_ROLE=plane_runtime \
    --env PLANE_AUDIT_GOVERNANCE_ROLE=plane_audit_owner \
    --env PLANE_AUDIT_MIGRATION_ROLE=plane_migrator \
    --env REDIS_HOST=test-redis \
    --env REDIS_URL=redis://test-redis:6379/ \
    --env RABBITMQ_HOST=test-mq \
    --env AMQP_URL=amqp://plane:plane@test-mq:5672/plane \
    "${API_IMAGE}" python manage.py migrate --noinput >/dev/null 2>&1

LIVE_PHASE=audit-bootstrap
docker run --rm --network "${NETWORK}" \
    --env DJANGO_SETTINGS_MODULE=plane.settings.test \
    --env POSTGRES_HOST=test-db \
    --env DATABASE_URL=postgresql://plane:plane@test-db:5432/plane \
    --env DATABASE_RUNTIME_URL=postgresql://plane:plane@test-db:5432/plane \
    --env DATABASE_MIGRATION_URL=postgresql://plane:plane@test-db:5432/plane \
    --env PLANE_AUDIT_RUNTIME_ROLE=plane_runtime \
    --env PLANE_AUDIT_GOVERNANCE_ROLE=plane_audit_owner \
    --env PLANE_AUDIT_MIGRATION_ROLE=plane_migrator \
    --env REDIS_HOST=test-redis \
    --env REDIS_URL=redis://test-redis:6379/ \
    --env RABBITMQ_HOST=test-mq \
    --env AMQP_URL=amqp://plane:plane@test-mq:5672/plane \
    "${API_IMAGE}" python manage.py bootstrap_operation_gateway_audit --phase=after-migrate >/dev/null 2>&1

LIVE_PHASE=credential-state-volume
if docker volume inspect "${CREDENTIAL_STATE_VOLUME}" >/dev/null 2>&1; then
    printf '%s\n' 'event=agent.g4.live-runner status=failed expected=new-task-owned-credential-state-volume actual=volume-name-already-exists suggestion=retry-with-a-fresh-live-run' >&2
    exit 2
fi
docker volume create \
    --label com.uxheavy.plane.agent-g4-credential-state=true \
    --label "com.uxheavy.plane.agent-g4-project=${PROJECT}" \
    "${CREDENTIAL_STATE_VOLUME}" >/dev/null
CREDENTIAL_STATE_VOLUME_CREATED=1

docker network create --driver bridge --label com.uxheavy.plane.agent-g4-runtime=true "${EGRESS}" >/dev/null

LIVE_PHASE=runtime-start
docker run -d --name "${RUNTIME}" \
    --label com.uxheavy.plane.agent-g4-runtime=true \
    --user 65532:65532 \
    --read-only \
    --init \
    --cap-drop ALL \
    --security-opt no-new-privileges:true \
    --network "${NETWORK}" \
    --network-alias agent-runtime \
    --mount type=bind,src="${RUNTIME_SECRET_FILE}",dst=/run/secrets/plane_agent_runtime,readonly \
    --mount type=volume,src="${CREDENTIAL_STATE_VOLUME}",dst="${CREDENTIAL_STATE_TARGET}",readonly,volume-nocopy \
    --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m \
    --tmpfs /run/plane-agent-runtime:rw,noexec,nosuid,nodev,size=1m \
    --env DJANGO_SETTINGS_MODULE=plane.settings.common \
    --env PLANE_AGENT_RUNTIME_URL=http://agent-runtime:8080 \
    --env PLANE_AGENT_RUNTIME_DISPATCH_PATH=/v1/runtime/dispatch \
    --env PLANE_AGENT_RUNTIME_LEDGER_PATH=/run/plane-agent-runtime/dispatch-ledger.sqlite \
    --env PLANE_AGENT_RUNTIME_SECRET_FILE=/run/secrets/plane_agent_runtime \
    --env PLANE_AGENT_RUNTIME_HEALTH_PATH=/health/ready \
    --env PLANE_AGENT_RUNTIME_SAFETY_STOP_FILE=/run/plane-agent-runtime/safety-stop \
    --env PLANE_AGENT_RUNTIME_NETWORK_POLICY=none \
    --env PLANE_AGENT_RUNTIME_ENVIRONMENT_JSON="${RUNTIME_CHILD_ENVIRONMENT_JSON}" \
    --env PLANE_AGENT_RUNTIME_CREDENTIAL_STATE_FILE="${CREDENTIAL_STATE_FILE}" \
    --env PLANE_AGENT_RUNTIME_PROVIDER="${G4_PROVIDER_NAME}" \
    --env PLANE_AGENT_RUNTIME_PROVIDER_BASE_URL="${G4_PROVIDER_BASE_URL}" \
    --env PLANE_AGENT_RUNTIME_PROVIDER_HOST="${G4_PROVIDER_HOST}" \
    --env PLANE_AGENT_RUNTIME_PROVIDER_PATH="${G4_PROVIDER_PATH}" \
    --env PLANE_AGENT_RUNTIME_PROVIDER_MODELS="${G4_PROVIDER_MODEL}" \
    --env PLANE_AGENT_RUNTIME_PROVIDER_CREDENTIAL_SOURCE="${G4_PROVIDER_CREDENTIAL_SOURCE}" \
    --env PLANE_AGENT_RUNTIME_PROVIDER_CREDENTIAL_REF="${G4_PROVIDER_CREDENTIAL_REF}" \
    --env PLANE_AGENT_RUNTIME_PROVIDER_CREDENTIAL_NAME="${G4_PROVIDER_CREDENTIAL_NAME}" \
    --env PLANE_AGENT_RUNTIME_PROVIDER_DESCRIPTOR_JSON="${PROVIDER_DESCRIPTOR_JSON}" \
    --env PLANE_AGENT_RUNTIME_COMMAND='python3 -m plane_runtime.g1_runtime_image.bootstrap --once --g1-production' \
    --env PLANE_AGENT_RUNTIME_BIND=0.0.0.0 \
    --env PLANE_AGENT_RUNTIME_PORT=8080 \
    --entrypoint python3 \
    "${RUNTIME_IMAGE}" -m plane.agent.runtime.service >/dev/null

docker network connect "${EGRESS}" "${RUNTIME}"

runtime_ready=0
LIVE_PHASE=runtime-health
for _attempt in $(seq 1 90); do
    if docker run --rm --network "${NETWORK}" --entrypoint python3 "${API_IMAGE}" \
        -c 'import urllib.request; urllib.request.urlopen("http://agent-runtime:8080/health/ready", timeout=2)' \
        >/dev/null 2>&1; then
        runtime_ready=1
        break
    fi
    sleep 1
done
test "${runtime_ready}" -eq 1

LIVE_PHASE=api-invocation
docker run --rm --network "${NETWORK}" --hostname api --network-alias api \
    --mount type=bind,src="${RUNTIME_SECRET_FILE}",dst=/run/secrets/plane_agent_runtime,readonly \
    --mount type=volume,src="${CREDENTIAL_STATE_VOLUME}",dst="${CREDENTIAL_STATE_TARGET}",volume-nocopy \
    --mount type=bind,src="${PROVIDER_SECRET_FILE}",dst=/run/secrets/plane_agent_provider_credentials,readonly \
    --mount type=bind,src="${LIVE_INVOKE_SOURCE}",dst=/tmp/agent-g4-live-invoke.py,readonly \
    --env DJANGO_SETTINGS_MODULE=plane.settings.production \
    --env PYTHONUNBUFFERED=1 \
    --env SECRET_KEY="${PLANE_TEST_SECRET}" \
    --env APP_BASE_URL=http://api:8000 \
    --env WEB_URL=http://api:8000 \
    --env POSTGRES_HOST=test-db \
    --env POSTGRES_USER=plane \
    --env POSTGRES_PASSWORD=plane \
    --env POSTGRES_DB=plane \
    --env DATABASE_URL=postgresql://plane:plane@test-db:5432/plane \
    --env DATABASE_RUNTIME_URL=postgresql://plane:plane@test-db:5432/plane \
    --env DATABASE_MIGRATION_URL=postgresql://plane:plane@test-db:5432/plane \
    --env REDIS_HOST=test-redis \
    --env REDIS_URL=redis://test-redis:6379/ \
    --env RABBITMQ_HOST=test-mq \
    --env AMQP_URL=amqp://plane:plane@test-mq:5672/plane \
    --env PLANE_AGENT_RUNTIME_URL=http://agent-runtime:8080 \
    --env PLANE_AGENT_RUNTIME_HOST_URL=http://api:8091 \
    --env PLANE_AGENT_RUNTIME_HOST_BIND=0.0.0.0 \
    --env PLANE_AGENT_RUNTIME_HOST_PORT=8091 \
    --env PLANE_AGENT_RUNTIME_DISPATCH_PATH=/v1/runtime/dispatch \
    --env PLANE_AGENT_RUNTIME_SECRET_FILE=/run/secrets/plane_agent_runtime \
    --env PLANE_AGENT_RUNTIME_CREDENTIAL_RESOLVER=command:/usr/local/bin/plane-agent-runtime-credential-resolver \
    --env PLANE_AGENT_RUNTIME_CREDENTIAL_STATE_FILE="${CREDENTIAL_STATE_FILE}" \
    --env PLANE_AGENT_RUNTIME_COMMAND='python3 -m plane_runtime.g1_runtime_image.bootstrap --once --g1-production' \
    --env PLANE_AGENT_RUNTIME_PROVIDER="${G4_PROVIDER_NAME}" \
    --env PLANE_AGENT_RUNTIME_PROVIDER_BASE_URL="${G4_PROVIDER_BASE_URL}" \
    --env PLANE_AGENT_RUNTIME_PROVIDER_HOST="${G4_PROVIDER_HOST}" \
    --env PLANE_AGENT_RUNTIME_PROVIDER_PATH="${G4_PROVIDER_PATH}" \
    --env PLANE_AGENT_RUNTIME_PROVIDER_MODELS="${G4_PROVIDER_MODEL}" \
    --env PLANE_AGENT_RUNTIME_PROVIDER_CREDENTIAL_SOURCE="${G4_PROVIDER_CREDENTIAL_SOURCE}" \
    --env PLANE_AGENT_RUNTIME_PROVIDER_CREDENTIAL_REF="${G4_PROVIDER_CREDENTIAL_REF}" \
    --env PLANE_AGENT_RUNTIME_PROVIDER_CREDENTIAL_NAME="${G4_PROVIDER_CREDENTIAL_NAME}" \
    --env G4_CANDIDATE="${G4_CANDIDATE}" \
    --env G4_EXPECTED_CANDIDATE="${G4_EXPECTED_CANDIDATE}" \
    --env G4_G3_BASELINE="${G4_G3_BASELINE}" \
    --env G4_HERMES="${G4_HERMES}" \
    --env G4_MCP="${G4_MCP}" \
    --env G4_SDK="${G4_SDK}" \
    --env G4_RUNTIME_IMAGE_TAG="${RUNTIME_IMAGE}" \
    --env G4_RUNTIME_IMAGE_DIGEST="${G4_RUNTIME_IMAGE_DIGEST}" \
    --env G4_RUNTIME_IMAGE_REVISION="${G4_RUNTIME_IMAGE_REVISION}" \
    --env G4_RUNTIME_CONTRACT="${G4_RUNTIME_CONTRACT}" \
    --env G4_API_IMAGE_TAG="${G4_API_IMAGE_TAG}" \
    --env G4_API_IMAGE_DIGEST="${G4_API_IMAGE_DIGEST}" \
    --env G4_API_SOURCE_REVISION="${G4_API_SOURCE_REVISION}" \
    --env G4_API_CONTRACT="${G4_API_CONTRACT}" \
    --env G4_PROVIDER_DESCRIPTOR_JSON="${PROVIDER_DESCRIPTOR_JSON}" \
    --env G4_PERMITTED_CANARY=live-permitted-read \
    --env G4_DENIED_CANARY=live-denied-evaluate \
    "${API_IMAGE}" python /tmp/agent-g4-live-invoke.py >"${EVIDENCE_FILE}" 2>"${ERROR_FILE}"

test -s "${EVIDENCE_FILE}"
