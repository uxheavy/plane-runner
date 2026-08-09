#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/docker-compose-test.yml"
G3_BASE_COMMIT="9b4bad0b0b54c90c8d25e9af5f086971e6b9c93a"
CANDIDATE_COMMIT="$(git -C "${ROOT_DIR}" rev-parse HEAD)"
MCP_COMMIT="2dc152e136d7ad952b901e5fe9364a37487297ba"
MCP_INVENTORY_COMMIT="96cf4d51d65cfa5e47d10ff7a4a4caba3b7a98d1"
SDK_COMMIT="7d2faf3b7ef5409e292ba0a3c7015e59f93c5889"
HERMES_COMMIT="114eabf9d807b659e36d767e4de46ca056297ccb"
API_TEST_IMAGE="${PLANE_API_TEST_IMAGE:-plane-g3-external-client-api-tests:prepared}"
API_TEST_IMAGE_DIGEST="sha256:51b50bec143e12c22fa92f8b101629d37ae263f2784c9bb3747eaea45978092e"
GIT_COMMON_DIR="$(git -C "${ROOT_DIR}" rev-parse --git-common-dir)"
if [[ "${GIT_COMMON_DIR}" != /* ]]; then
    GIT_COMMON_DIR="${ROOT_DIR}/${GIT_COMMON_DIR}"
fi
GIT_COMMON_DIR="$(cd -- "${GIT_COMMON_DIR}" && pwd)"
DEFAULT_SUPERPROJECT_ROOT="$(dirname -- "${GIT_COMMON_DIR}")"
EXTERNAL_SUPERPROJECT_ROOT="${PLANE_EXTERNAL_SUPERPROJECT_ROOT:-${DEFAULT_SUPERPROJECT_ROOT}}"
MCP_ROOT="${PLANE_MCP_EXTERNAL_ROOT:-${EXTERNAL_SUPERPROJECT_ROOT}/external/plane-mcp-server}"
SDK_ROOT="${PLANE_SDK_EXTERNAL_ROOT:-${EXTERNAL_SUPERPROJECT_ROOT}/external/plane-python-sdk}"
HERMES_ROOT="${PLANE_HERMES_EXTERNAL_ROOT:-${EXTERNAL_SUPERPROJECT_ROOT}/../hermes-agent}"
PROJECT_NAME="plane-agent-g3-verify-$$-${RANDOM}"
NETWORK_NAME="${PROJECT_NAME}_test_env"
CURRENT_STEP="preflight"
RUNTIME_LOG_DIR=""
COMMUNITY_COMPOSE_CONFIG=""
CREATED_API_LOG_DIR=0
CREATED_RUNTIME_LOG_DIR=0

emit() {
    local event="$1"
    local status="$2"
    shift 2
    printf 'event=agent.g3.%s status=%s' "${event}" "${status}"
    for field in "$@"; do
        printf ' %s' "${field}"
    done
    printf '\n'
}

fail() {
    local expected="$1"
    local actual="$2"
    local suggestion="$3"
    emit "${CURRENT_STEP}" failed "expected=${expected}" "actual=${actual}" "suggestion=${suggestion}" >&2
    exit 1
}

compose() {
    PLANE_TEST_ENV_FILE="${ROOT_DIR}/apps/api/.env.example" \
        docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" "$@"
}

check_candidate() {
    local status dirty="" line path
    status="$(git -C "${ROOT_DIR}" status --porcelain=v1 --untracked-files=all)"
    while IFS= read -r line; do
        [[ -z "${line}" ]] && continue
        path="${line:3}"
        [[ "${path}" == ".codex/config.toml" ]] && continue
        dirty+="${line};"
    done <<< "${status}"
    [[ -z "${dirty}" ]] || fail "clean candidate checkout excluding .codex/config.toml" "dirty=${dirty}" "run the verifier from a committed candidate"
    [[ "$(git -C "${ROOT_DIR}" rev-parse HEAD)" == "${CANDIDATE_COMMIT}" ]] || fail "candidate HEAD=${CANDIDATE_COMMIT}" "HEAD changed during verification" "rerun from a stable commit"
    git -C "${ROOT_DIR}" merge-base --is-ancestor "${G3_BASE_COMMIT}" "${CANDIDATE_COMMIT}" || fail "candidate descends from G3 base=${G3_BASE_COMMIT}" "candidate=${CANDIDATE_COMMIT}" "run against the integrated G3 candidate history"
    emit "commit.range" passed "base=${G3_BASE_COMMIT}" "candidate=${CANDIDATE_COMMIT}"
}

pin_external_tree() {
    local label="$1"
    local root="$2"
    local expected="$3"
    local actual
    [[ -d "${root}" ]] || fail "${label} checkout exists" "missing=${root}" "set the ${label} root override"
    actual="$(git -C "${root}" rev-parse HEAD)" || fail "${label} checkout is readable" "git failed" "inspect ${root}"
    [[ "${actual}" == "${expected}" ]] || fail "${label} HEAD=${expected}" "actual=${actual}" "use the authoritative pinned checkout"
    [[ -z "$(git -C "${root}" status --short)" ]] || fail "${label} checkout is clean" "dirty=${root}" "do not run against modified client code"
    emit "external.${label}.pin" passed "root=${root}" "head=${actual}"
}

check_gitlinks() {
    local mcp_link sdk_link
    mcp_link="$(git -C "${ROOT_DIR}" ls-tree "${CANDIDATE_COMMIT}" external/plane-mcp-server)"
    sdk_link="$(git -C "${ROOT_DIR}" ls-tree "${CANDIDATE_COMMIT}" external/plane-python-sdk)"
    [[ "${mcp_link}" == *"${MCP_COMMIT}"$'\texternal/plane-mcp-server' ]] || fail "MCP gitlink=${MCP_COMMIT}" "${mcp_link}" "inspect the integrated Plane tree"
    [[ "${sdk_link}" == *"${SDK_COMMIT}"$'\texternal/plane-python-sdk' ]] || fail "SDK gitlink=${SDK_COMMIT}" "${sdk_link}" "inspect the integrated Plane tree"
    emit "plane.gitlinks" passed "candidate=${CANDIDATE_COMMIT}" "mcp=${MCP_COMMIT}" "sdk=${SDK_COMMIT}"
}

check_mcp_inventory() {
    python3 - "${MCP_ROOT}" "${MCP_INVENTORY_COMMIT}" <<'PY'
import json
import sys
from collections import Counter
from pathlib import Path

root = Path(sys.argv[1])
expected_source = sys.argv[2]
registry = json.loads((root / "plane_mcp" / "gateway_registry.json").read_text(encoding="utf-8"))
assert registry["source"]["commit"] == expected_source, registry["source"]
assert registry["tool_count"] == 177, registry["tool_count"]
assert len(registry["actions"]) == 177
assert Counter(row["registration"] for row in registry["actions"].values()) == Counter(
    {"gateway": 86, "unsupported": 90, "local": 1}
)
print("event=agent.g3.external.inventory status=passed tool_count=177 gateway=86 unsupported=90 local=1 source=" + expected_source)
PY
}

wait_for_services() {
    local container status attempt
    for attempt in $(seq 1 60); do
        status=healthy
        for container in \
            "${PROJECT_NAME}-test-db-1" \
            "${PROJECT_NAME}-test-redis-1" \
            "${PROJECT_NAME}-test-mq-1" \
            "${PROJECT_NAME}-test-minio-1"; do
            if ! docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${container}" 2>/dev/null | grep -qx healthy; then
                status=starting
            fi
        done
        if [[ "${status}" == healthy ]]; then
            emit "stack.health" passed "project=${PROJECT_NAME}"
            return
        fi
        sleep 1
    done
    fail "four healthy isolated dependencies" "health timeout" "inspect ${PROJECT_NAME} logs"
}

API_ENV=(
    --env "DJANGO_SETTINGS_MODULE=plane.settings.test"
    --env "PYTHONPYCACHEPREFIX=/tmp/g3-pycache"
    --env "APP_BASE_URL=http://testserver"
    --env "WEB_URL=http://testserver"
    --env "POSTGRES_HOST=test-db"
    --env "POSTGRES_USER=plane"
    --env "POSTGRES_PASSWORD=plane"
    --env "POSTGRES_DB=plane"
    --env "DATABASE_URL=postgresql://plane:plane@test-db:5432/plane"
    --env "DATABASE_RUNTIME_URL=postgresql://plane:plane@test-db:5432/plane"
    --env "DATABASE_MIGRATION_URL=postgresql://plane:plane@test-db:5432/plane"
    --env "PLANE_DB_PROVISIONER_MODE=1"
    --env "PLANE_AUDIT_RUNTIME_ROLE=plane_runtime"
    --env "PLANE_AUDIT_RUNTIME_PASSWORD=runtime-probe"
    --env "PLANE_AUDIT_MIGRATION_ROLE=plane_migrator"
    --env "PLANE_AUDIT_MIGRATION_PASSWORD=migration-probe"
    --env "PLANE_AUDIT_PROVISIONER_ROLE=plane"
    --env "PLANE_AUDIT_ENFORCE_ROLE_SEPARATION=1"
    --env "REDIS_HOST=test-redis"
    --env "REDIS_URL=redis://test-redis:6379/"
    --env "RABBITMQ_HOST=test-mq"
    --env "RABBITMQ_PORT=5672"
    --env "RABBITMQ_USER=plane"
    --env "RABBITMQ_PASSWORD=plane"
    --env "RABBITMQ_VHOST=plane"
    --env "AWS_S3_ENDPOINT_URL=http://test-minio:9000"
    --env "AWS_ACCESS_KEY_ID=access-key"
    --env "AWS_SECRET_ACCESS_KEY=secret-key"
    --env "AWS_S3_BUCKET_NAME=uploads"
    --env "EMAIL_HOST=test-smtp.invalid"
    --env "PLANE_MCP_EXTERNAL_ROOT=/workspace/external/plane-mcp-server"
    --env "PLANE_SDK_EXTERNAL_ROOT=/workspace/external/plane-python-sdk"
    --env "PLANE_G2_HERMES_CHECKOUT=/workspace/hermes-agent"
    --env "PLANE_G2_HERMES_DEPENDENCY_PATH=/workspace/hermes-agent/plane_runtime/g1_runtime_image"
    --env "PLANE_COMMUNITY_COMPOSE_CONFIG=/tmp/community-compose.json"
    --env "API_KEY_RATE_LIMIT=8192/minute"
)

run_api() {
    docker run --rm \
        --network "${NETWORK_NAME}" \
        "${API_ENV[@]}" \
        --entrypoint /bin/sh \
        --mount "type=bind,src=${ROOT_DIR}/apps/api,dst=/workspace/apps/api,readonly" \
        --mount "type=bind,src=${ROOT_DIR}/packages/agent-runtime-contract,dst=/workspace/packages/agent-runtime-contract,readonly" \
        --mount "type=bind,src=${MCP_ROOT},dst=/workspace/external/plane-mcp-server,readonly" \
        --mount "type=bind,src=${SDK_ROOT},dst=/workspace/external/plane-python-sdk,readonly" \
        --mount "type=bind,src=${EXTERNAL_SUPERPROJECT_ROOT}/.git/modules,dst=/workspace/.git/modules,readonly" \
        --mount "type=bind,src=${HERMES_ROOT},dst=/workspace/hermes-agent,readonly" \
        --mount "type=bind,src=${RUNTIME_LOG_DIR},dst=/workspace/apps/api/plane/logs" \
        --mount "type=bind,src=${COMMUNITY_COMPOSE_CONFIG},dst=/tmp/community-compose.json,readonly" \
        --workdir /workspace/apps/api \
        "${API_TEST_IMAGE}" -c 'exec "$@"' -- "$@"
}

G3_TEST_PATHS=(
    plane/tests/unit/agent/test_host_rpc.py
    plane/tests/unit/agent/test_l7_governance.py
    plane/tests/unit/agent/test_lifecycle.py
    plane/tests/unit/agent/test_memory_skills_schedules.py
    plane/tests/unit/agent/test_runtime_contract.py
    plane/tests/unit/agent/test_runtime_supervisor.py
    plane/tests/unit/agent/test_runtime_transport.py
    plane/tests/unit/agent/test_provider_egress.py
    plane/tests/unit/agent/test_tools.py
    plane/tests/contract/api/test_agent_admin.py
    plane/tests/contract/api/test_agent_context_migrations.py
    plane/tests/contract/api/test_agent_g1_integration.py
    plane/tests/contract/api/test_agent_g2_host_binding.py
    plane/tests/contract/api/test_agent_input_migrations.py
    plane/tests/contract/api/test_agent_tools_gateway.py
    plane/tests/contract/api/test_operation_gateway.py
    plane/tests/contract/api/test_operation_gateway_authority.py
    plane/tests/contract/api/test_operation_gateway_external_clients.py
    plane/tests/contract/api/test_operation_gateway_mcp.py
    plane/tests/contract/api/test_operation_gateway_migrations.py
    plane/tests/contract/api/test_production_runtime_configuration.py
)
if [[ -n "${G3_TEST_PATHS_OVERRIDE:-}" ]]; then
    read -r -a G3_TEST_PATHS <<< "${G3_TEST_PATHS_OVERRIDE}"
fi

cleanup() {
    local status=$?
    local cleanup_status=0
    local leftovers
    trap - EXIT INT TERM
    compose down -v --remove-orphans >/dev/null 2>&1 || cleanup_status=$?
    if [[ -n "${RUNTIME_LOG_DIR}" && -d "${RUNTIME_LOG_DIR}" ]]; then
        rm -rf -- "${RUNTIME_LOG_DIR}"
    fi
    if [[ ${CREATED_API_LOG_DIR} -eq 1 ]]; then
        rmdir -- "${ROOT_DIR}/apps/api/plane/logs" 2>/dev/null || true
    fi
    leftovers="$(docker ps -aq --filter "label=com.docker.compose.project=${PROJECT_NAME}")$(docker network ls -q --filter "label=com.docker.compose.project=${PROJECT_NAME}")"
    if [[ -n "${leftovers}" ]]; then
        cleanup_status=1
    fi
    if [[ ${cleanup_status} -ne 0 ]]; then
        emit "cleanup" failed "project=${PROJECT_NAME}" "suggestion=inspect task-owned Compose resources" >&2
        [[ ${status} -ne 0 ]] || status=${cleanup_status}
    else
        emit "cleanup" passed "project=${PROJECT_NAME}"
    fi
    exit "${status}"
}

check_api_test_image() {
    local image_id
    image_id="$(docker image inspect "${API_TEST_IMAGE}" --format '{{.Id}}' 2>/dev/null)" || fail "prepared API test image=${API_TEST_IMAGE}" "image unavailable" "build or select a local prepared image with PLANE_API_TEST_IMAGE"
    [[ "${image_id}" == "${API_TEST_IMAGE_DIGEST}" ]] || fail "prepared API test image digest=${API_TEST_IMAGE_DIGEST}" "actual=${image_id}" "use the authoritative offline image; this verifier never rebuilds or pulls images"
    docker run --rm --network none --entrypoint sh "${API_TEST_IMAGE}" -c '
        set -eu
        command -v python >/dev/null
        command -v pytest >/dev/null
        command -v ruff >/dev/null
        python -c "import django, psycopg, pytest"
    ' || fail "offline API test dependencies are prepared in ${API_TEST_IMAGE}" "dependency probe failed" "prepare the image locally; this verifier never installs dependencies"
    emit "api-image" passed "image=${API_TEST_IMAGE}" "digest=${image_id}" "network=none" "dependency_source=prepared-local"
}

trap cleanup EXIT
trap 'exit 130' INT TERM

command -v docker >/dev/null 2>&1 || fail "Docker is available" "docker is unavailable" "enable Docker"
command -v git >/dev/null 2>&1 || fail "Git is available" "git is unavailable" "install Git"
check_api_test_image

CURRENT_STEP="candidate-range"
check_candidate

CURRENT_STEP="source-pins"
pin_external_tree mcp "${MCP_ROOT}" "${MCP_COMMIT}"
pin_external_tree sdk "${SDK_ROOT}" "${SDK_COMMIT}"
pin_external_tree hermes "${HERMES_ROOT}" "${HERMES_COMMIT}"
check_gitlinks
check_mcp_inventory
[[ -d "${EXTERNAL_SUPERPROJECT_ROOT}/.git/modules" ]] || fail "external git module metadata is mounted" "missing metadata" "set PLANE_EXTERNAL_SUPERPROJECT_ROOT to the gitlink superproject"

CURRENT_STEP="static-scope"
python3 "${ROOT_DIR}/tools/check-agent-settings-reuse.py" "${G3_BASE_COMMIT}" "${CANDIDATE_COMMIT}"
git -C "${ROOT_DIR}" diff --check "${G3_BASE_COMMIT}" "${CANDIDATE_COMMIT}"
gitleaks detect --no-banner --redact --source "${ROOT_DIR}" --log-opts "${G3_BASE_COMMIT}..${CANDIDATE_COMMIT}" --exit-code 1
emit "static-scope" passed "base=${G3_BASE_COMMIT}" "candidate=${CANDIDATE_COMMIT}" "settings_reuse=passed" "secret_scan=base_to_candidate_passed" "diff_check=base_to_candidate_passed"

CURRENT_STEP="migration-chain"
PLANE_API_TEST_IMAGE="${API_TEST_IMAGE}" "${ROOT_DIR}/tools/verify-api-migrations.sh"
emit "migration-chain" passed "apply=passed" "reverse_to=0138" "reapply=passed" "drift=passed" "leaf=0142"

CURRENT_STEP="start-stack"
if [[ ! -d "${ROOT_DIR}/apps/api/plane/logs" ]]; then
    mkdir -p -- "${ROOT_DIR}/apps/api/plane/logs"
    CREATED_API_LOG_DIR=1
fi
RUNTIME_LOG_DIR="${ROOT_DIR}/.g3-runtime-logs-${PROJECT_NAME}"
mkdir -p -- "${RUNTIME_LOG_DIR}"
CREATED_RUNTIME_LOG_DIR=1
COMMUNITY_COMPOSE_CONFIG="${RUNTIME_LOG_DIR}/community-compose.json"
CURRENT_STEP="resolve-community-compose"
env CORS_ALLOWED_ORIGINS=http://localhost LIVE_SERVER_SECRET_KEY=compose-test-key SECRET_KEY=compose-test-key \
    docker compose -f "${ROOT_DIR}/deployments/cli/community/docker-compose.yml" config --format json \
    > "${COMMUNITY_COMPOSE_CONFIG}" \
    || fail "resolved community Compose configuration" "docker compose config failed" "inspect the pinned community deployment"
[[ -s "${COMMUNITY_COMPOSE_CONFIG}" ]] || fail "resolved community Compose configuration" "empty config" "inspect the community deployment source"
emit "community-compose" passed "config=${COMMUNITY_COMPOSE_CONFIG}" "credential_topology=host_resolved_mounted_readonly"
compose up --pull never -d test-db test-redis test-mq test-minio >/dev/null
wait_for_services

CURRENT_STEP="g3-api-and-client-suite"
run_api sh -c "
set -Eeuo pipefail
export RUFF_CACHE_DIR=/tmp/g3-ruff-cache
export PYTHONPATH=/workspace/apps/api${PYTHONPATH:+:${PYTHONPATH}}
python manage.py bootstrap_operation_gateway_audit --phase=before-migrate
python manage.py migrate --noinput --verbosity 0
python manage.py bootstrap_operation_gateway_audit --phase=after-migrate
python -m plane.operation_gateway.mcp.registry_generator plane/operation_gateway/mcp/manifest.json --check plane/operation_gateway/mcp/adapter_registry.json
ruff check plane/agent plane/operation_gateway plane/tests/unit/agent plane/tests/contract/api
ruff format --check plane/tests/contract/api/test_operation_gateway_mcp.py plane/tests/contract/api/test_operation_gateway_external_clients.py
python -m compileall -q plane/agent plane/operation_gateway plane/tests/unit/agent plane/tests/contract/api
python manage.py shell -c 'from django.db import connection; from django.db.migrations.executor import MigrationExecutor; e=MigrationExecutor(connection); leaves=set(e.loader.graph.leaf_nodes(\"db\")); applied=set(e.recorder.applied_migrations()); assert leaves == {(\"db\", \"0142_runtime_provider_attempts\")}; assert not leaves-applied; print(\"event=agent.g3.api.migration_leaf status=passed leaf=0142\")'
PLANE_AUDIT_ENFORCE_ROLE_SEPARATION=0 pytest -p plane.tests.g3_no_skips --migrations -q -o addopts='--strict-markers --reuse-db' -o cache_dir=/tmp/g3-pytest ${G3_TEST_PATHS[*]}
"
emit "g3-api-and-client-suite" passed "test_files=${#G3_TEST_PATHS[@]}" "external_mcp=${MCP_COMMIT}" "external_sdk=${SDK_COMMIT}" "hermes=${HERMES_COMMIT}" "result_limit=8192"

CURRENT_STEP="complete"
emit "complete" passed "base=${G3_BASE_COMMIT}" "candidate=${CANDIDATE_COMMIT}" "migration_leaf=0142" "mcp=177:86:90:1" "result_boundary=8192/8193" "readiness=ready_for_single_sol_medium_g3_assessment"
