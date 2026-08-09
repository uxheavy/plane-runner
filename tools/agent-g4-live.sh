#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(pwd)"
PROJECT="plane-agent-g4-live-${PPID}-${RANDOM}"
NETWORK="${PROJECT}_test_env"
EGRESS="${PROJECT}_egress"
RUNTIME="${PROJECT}-agent-runtime"
RUN_DIR="${ROOT_DIR}/tmp/${PROJECT}"
EVIDENCE_FILE="${RUN_DIR}/evidence.json"
ERROR_FILE="${RUN_DIR}/sanitized-error.log"
RUNTIME_SECRET_FILE="${RUN_DIR}/runtime-secret"
PLANE_TEST_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48), end="")')"
API_IMAGE="plane-agent-api:g4-e7b4e02"
PROVIDER_SECRET_SOURCE="${PLANE_G4_PROVIDER_SECRET_SOURCE:?configured provider source is required}"
LIVE_INVOKE_SOURCE="${ROOT_DIR}/tools/agent-g4-live-invoke.py"
MANIFEST="${ROOT_DIR}/tools/agent-g4-manifest.json"
G4_CANDIDATE="$(git rev-parse HEAD)"
G4_G3_BASELINE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["candidateBinding"]["parentCommit"])' "${MANIFEST}")"
G4_HERMES="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pins"]["hermesCommit"])' "${MANIFEST}")"
G4_MCP="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pins"]["mcpGitlink"])' "${MANIFEST}")"
G4_SDK="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pins"]["sdkGitlink"])' "${MANIFEST}")"
RUNTIME_IMAGE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pins"]["runtimeImageTag"])' "${MANIFEST}")"
G4_RUNTIME_IMAGE_DIGEST="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pins"]["runtimeImageDigest"])' "${MANIFEST}")"
G4_RUNTIME_IMAGE_REVISION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pins"]["runtimeImageRevision"])' "${MANIFEST}")"
G4_RUNTIME_CONTRACT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pins"]["runtimeContract"])' "${MANIFEST}")"
LIVE_PHASE=initialization

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
    if [[ "${status}" -ne 0 ]]; then
        printf 'event=agent.g4.live-runner.failure phase=%s error_class=%s exit_code=%s\n' \
            "${LIVE_PHASE}" "$(safe_error_class)" "${status}"
    fi
    docker rm -f "${RUNTIME}" >/dev/null 2>&1 || true
    docker network rm "${EGRESS}" >/dev/null 2>&1 || true
    PLANE_TEST_ENV_FILE="${ROOT_DIR}/apps/api/.env.example" \
        docker compose -p "${PROJECT}" -f "${ROOT_DIR}/docker-compose-test.yml" down -v --remove-orphans >/dev/null 2>&1 || true
    rm -rf -- "${RUN_DIR}"
    exit "${status}"
}
trap cleanup EXIT INT TERM

mkdir -p -- "${RUN_DIR}"
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
    --env REDIS_HOST=test-redis \
    --env REDIS_URL=redis://test-redis:6379/ \
    --env RABBITMQ_HOST=test-mq \
    --env AMQP_URL=amqp://plane:plane@test-mq:5672/plane \
    "${API_IMAGE}" python manage.py bootstrap_operation_gateway_audit --phase=after-migrate >/dev/null 2>&1

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
    --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m \
    --tmpfs /run/plane-agent-runtime:rw,noexec,nosuid,nodev,size=1m \
    --tmpfs /run/plane-agent-credentials:rw,noexec,nosuid,nodev,size=1m \
    --env DJANGO_SETTINGS_MODULE=plane.settings.common \
    --env PLANE_AGENT_RUNTIME_URL=http://agent-runtime:8080 \
    --env PLANE_AGENT_RUNTIME_DISPATCH_PATH=/v1/runtime/dispatch \
    --env PLANE_AGENT_RUNTIME_LEDGER_PATH=/run/plane-agent-runtime/dispatch-ledger.sqlite \
    --env PLANE_AGENT_RUNTIME_SECRET_FILE=/run/secrets/plane_agent_runtime \
    --env PLANE_AGENT_RUNTIME_HEALTH_PATH=/health/ready \
    --env PLANE_AGENT_RUNTIME_SAFETY_STOP_FILE=/run/plane-agent-runtime/safety-stop \
    --env PLANE_AGENT_RUNTIME_NETWORK_POLICY=none \
    --env PLANE_AGENT_RUNTIME_ENVIRONMENT_JSON={} \
    --env PLANE_AGENT_RUNTIME_CREDENTIAL_STATE_FILE=/run/plane-agent-credentials/revocations.json \
    --env 'PLANE_AGENT_RUNTIME_PROVIDER=xai' \
    --env 'PLANE_AGENT_RUNTIME_PROVIDER_HOST=api.x.ai' \
    --env 'PLANE_AGENT_RUNTIME_PROVIDER_PATH=/v1/chat/completions' \
    --env 'PLANE_AGENT_RUNTIME_PROVIDER_MODELS=grok-4' \
    --env 'PLANE_AGENT_RUNTIME_PROVIDER_CREDENTIAL_NAME=api_key' \
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
    --mount type=bind,src="${PROVIDER_SECRET_SOURCE}",dst=/run/secrets/plane_agent_provider_credentials,readonly \
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
    --env PLANE_AGENT_RUNTIME_CREDENTIAL_STATE_FILE=/tmp/g4-live-credential-state.json \
    --env PLANE_AGENT_RUNTIME_COMMAND='python3 -m plane_runtime.g1_runtime_image.bootstrap --once --g1-production' \
    --env PLANE_AGENT_RUNTIME_PROVIDER=xai \
    --env PLANE_AGENT_RUNTIME_PROVIDER_HOST=api.x.ai \
    --env PLANE_AGENT_RUNTIME_PROVIDER_PATH=/v1/chat/completions \
    --env PLANE_AGENT_RUNTIME_PROVIDER_MODELS=grok-4 \
    --env PLANE_AGENT_RUNTIME_PROVIDER_CREDENTIAL_NAME=api_key \
    --env G4_CANDIDATE="${G4_CANDIDATE}" \
    --env G4_G3_BASELINE="${G4_G3_BASELINE}" \
    --env G4_HERMES="${G4_HERMES}" \
    --env G4_MCP="${G4_MCP}" \
    --env G4_SDK="${G4_SDK}" \
    --env G4_RUNTIME_IMAGE_TAG="${RUNTIME_IMAGE}" \
    --env G4_RUNTIME_IMAGE_DIGEST="${G4_RUNTIME_IMAGE_DIGEST}" \
    --env G4_RUNTIME_IMAGE_REVISION="${G4_RUNTIME_IMAGE_REVISION}" \
    --env G4_RUNTIME_CONTRACT="${G4_RUNTIME_CONTRACT}" \
    --env G4_PERMITTED_CANARY=live-permitted-read \
    --env G4_DENIED_CANARY=live-denied-evaluate \
    "${API_IMAGE}" python /tmp/agent-g4-live-invoke.py >"${EVIDENCE_FILE}" 2>"${ERROR_FILE}"

test -s "${EVIDENCE_FILE}"
cat "${EVIDENCE_FILE}"
