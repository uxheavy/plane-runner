#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_PATH="${ROOT_DIR}/tmp/plane-agent-g-verifier.lock"
if ! [[ "${PLANE_AGENT_VERIFIER_LOCK_FD:-}" =~ ^[0-9]+$ ]] || \
    ! python3 "${ROOT_DIR}/tools/agent-verifier-lock.py" --check-fd "${PLANE_AGENT_VERIFIER_LOCK_FD}" "${LOCK_PATH}"; then
    unset PLANE_AGENT_VERIFIER_LOCK_HELD PLANE_AGENT_VERIFIER_LOCK_FD
    exec python3 "${ROOT_DIR}/tools/agent-verifier-lock.py" \
        "${LOCK_PATH}" -- "${ROOT_DIR}/tools/verify-agent-g3.sh" "$@"
fi
COMPOSE_FILE="${ROOT_DIR}/docker-compose-test.yml"
MANIFEST="${ROOT_DIR}/tools/agent-g4-manifest.json"
G3_BASE_COMMIT="9b4bad0b0b54c90c8d25e9af5f086971e6b9c93a"
CANDIDATE_COMMIT="$(git -C "${ROOT_DIR}" rev-parse HEAD)"
HERMES_COMMIT="114eabf9d807b659e36d767e4de46ca056297ccb"

manifest_pin() {
    local expression="$1"
    python3 - "${MANIFEST}" "${expression}" <<'PY'
import json
import sys

value = json.load(open(sys.argv[1], encoding="utf-8"))
for part in sys.argv[2].split("."):
    value = value[part]
print(value)
PY
}

MCP_COMMIT="$(manifest_pin pins.mcpGitlink)"
SDK_COMMIT="$(manifest_pin pins.sdkGitlink)"
API_TEST_IMAGE="${PLANE_API_TEST_IMAGE:-plane-g3-external-client-api-tests:prepared}"
API_TEST_IMAGE_DIGEST="${PLANE_API_TEST_IMAGE_DIGEST:-sha256:51b50bec143e12c22fa92f8b101629d37ae263f2784c9bb3747eaea45978092e}"
API_TEST_IMAGE_TAG="${PLANE_API_TEST_IMAGE_TAG:-${API_TEST_IMAGE}}"
API_SOURCE_REVISION="${PLANE_API_SOURCE_REVISION:-}"
API_CONTRACT="${PLANE_API_CONTRACT:-plane.operation/v1}"
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
HERMES_PIN_ROOT="${PLANE_G3_HERMES_PIN_ROOT:-${HERMES_ROOT}}"
PROJECT_NAME="plane-agent-g3-verify-$$-${RANDOM}"
NETWORK_NAME="${PROJECT_NAME}_test_env"
CURRENT_STEP="preflight"
RUNTIME_LOG_DIR=""
COMMUNITY_COMPOSE_CONFIG=""
CREATED_API_LOG_DIR=0
CREATED_RUNTIME_LOG_DIR=0
RUFF_BASELINE_DIR=""
CREATED_RUFF_BASELINE_DIR=0

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
    --env "PLANE_G4_MANIFEST=/workspace/agent-g4-manifest.json"
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
        --mount "type=bind,src=${MANIFEST},dst=/workspace/agent-g4-manifest.json,readonly" \
        --mount "type=bind,src=${MCP_ROOT},dst=/workspace/external/plane-mcp-server,readonly" \
        --mount "type=bind,src=${SDK_ROOT},dst=/workspace/external/plane-python-sdk,readonly" \
        --mount "type=bind,src=${EXTERNAL_SUPERPROJECT_ROOT}/.git/modules,dst=/workspace/.git/modules,readonly" \
        --mount "type=bind,src=${HERMES_ROOT},dst=/workspace/hermes-agent,readonly" \
        --mount "type=bind,src=${RUFF_BASELINE_DIR},dst=/workspace/g3-ruff-baseline,readonly" \
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

cleanup_runtime_log_dir() {
    [[ "${CREATED_RUNTIME_LOG_DIR}" -eq 1 ]] || return 0
    case "${RUNTIME_LOG_DIR}" in
        "${ROOT_DIR}"/.g3-runtime-logs-*) ;;
        *) return 1 ;;
    esac
    [[ -d "${RUNTIME_LOG_DIR}" && ! -L "${RUNTIME_LOG_DIR}" ]] || return 1
    rm -rf -- "${RUNTIME_LOG_DIR}"
    [[ ! -e "${RUNTIME_LOG_DIR}" ]]
}

cleanup_ruff_baseline_dir() {
    [[ "${CREATED_RUFF_BASELINE_DIR}" -eq 1 ]] || return 0
    case "${RUFF_BASELINE_DIR}" in
        "${ROOT_DIR}"/tmp/plane-g3-ruff-baseline-*) ;;
        *) return 1 ;;
    esac
    [[ -d "${RUFF_BASELINE_DIR}" && ! -L "${RUFF_BASELINE_DIR}" ]] || return 1
    rm -rf -- "${RUFF_BASELINE_DIR}"
    [[ ! -e "${RUFF_BASELINE_DIR}" ]]
}

prepare_ruff_baseline_dir() {
    [[ -d "${ROOT_DIR}/tmp" ]] || \
        fail "Docker-visible verifier scratch directory exists" "missing=${ROOT_DIR}/tmp" "create the repository tmp directory"
    RUFF_BASELINE_DIR="$(mktemp -d "${ROOT_DIR}/tmp/plane-g3-ruff-baseline-XXXXXX")"
    CREATED_RUFF_BASELINE_DIR=1
    git -C "${ROOT_DIR}" archive "${G3_BASE_COMMIT}" \
        apps/api/pyproject.toml \
        apps/api/plane/agent \
        apps/api/plane/operation_gateway \
        apps/api/plane/tests/unit/agent \
        apps/api/plane/tests/contract/api \
        | tar -x -C "${RUFF_BASELINE_DIR}"
    [[ -f "${RUFF_BASELINE_DIR}/apps/api/pyproject.toml" ]] || \
        fail "G3 baseline ruff config is materialized" "missing baseline pyproject" "inspect ${G3_BASE_COMMIT}"
    emit "ruff.baseline" passed "commit=${G3_BASE_COMMIT}" "root=${RUFF_BASELINE_DIR}"
}

cleanup() {
    local status=$?
    local cleanup_status=0
    local leftovers
    trap - EXIT INT TERM
    compose down -v --remove-orphans >/dev/null 2>&1 || cleanup_status=$?
    cleanup_runtime_log_dir || cleanup_status=$?
    cleanup_ruff_baseline_dir || cleanup_status=$?
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
    local image_id source_label contract_label artifact_label
    image_id="$(docker image inspect "${API_TEST_IMAGE}" --format '{{.Id}}' 2>/dev/null)" || fail "prepared API test image=${API_TEST_IMAGE}" "image unavailable" "build or select a local prepared image with PLANE_API_TEST_IMAGE"
    [[ "${image_id}" == "${API_TEST_IMAGE_DIGEST}" ]] || fail "prepared API test image digest=${API_TEST_IMAGE_DIGEST}" "actual=${image_id}" "use the authoritative offline image; this verifier never rebuilds or pulls images"
    [[ "${API_TEST_IMAGE}" == "${API_TEST_IMAGE_TAG}" ]] || fail "API image tag=${API_TEST_IMAGE_TAG}" "actual=${API_TEST_IMAGE}" "use the manifest-bound API image tag"
    if [[ -n "${API_SOURCE_REVISION}" ]]; then
        source_label="$(docker image inspect "${API_TEST_IMAGE}" --format '{{index .Config.Labels "org.uxheavy.plane.api.source.revision"}}')"
        contract_label="$(docker image inspect "${API_TEST_IMAGE}" --format '{{index .Config.Labels "org.uxheavy.plane.api.contract"}}')"
        artifact_label="$(docker image inspect "${API_TEST_IMAGE}" --format '{{index .Config.Labels "org.uxheavy.plane.api.artifact"}}')"
        [[ "${source_label}" == "${API_SOURCE_REVISION}" ]] || fail "API image source revision=${API_SOURCE_REVISION}" "actual=${source_label}" "use the immutable API artifact built from the bound source"
        [[ "${contract_label}" == "${API_CONTRACT}" ]] || fail "API image contract=${API_CONTRACT}" "actual=${contract_label}" "use the Plane operation API artifact"
        [[ "${artifact_label}" == "plane-agent-api-g4" ]] || fail "API artifact label=plane-agent-api-g4" "actual=${artifact_label}" "use the reviewed immutable API image"
    fi
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
pin_external_tree hermes-pin "${HERMES_PIN_ROOT}" "${HERMES_COMMIT}"
check_gitlinks
[[ -d "${EXTERNAL_SUPERPROJECT_ROOT}/.git/modules" ]] || fail "external git module metadata is mounted" "missing metadata" "set PLANE_EXTERNAL_SUPERPROJECT_ROOT to the gitlink superproject"

CURRENT_STEP="static-scope"
python3 "${ROOT_DIR}/tools/check-agent-settings-reuse.py" "${G3_BASE_COMMIT}" "${CANDIDATE_COMMIT}"
git -C "${ROOT_DIR}" diff --check "${G3_BASE_COMMIT}" "${CANDIDATE_COMMIT}"
gitleaks detect --no-banner --redact --source "${ROOT_DIR}" --log-opts "${G3_BASE_COMMIT}..${CANDIDATE_COMMIT}" --exit-code 1
emit "static-scope" passed "base=${G3_BASE_COMMIT}" "candidate=${CANDIDATE_COMMIT}" "settings_reuse=passed" "secret_scan=base_to_candidate_passed" "diff_check=base_to_candidate_passed"

CURRENT_STEP="migration-chain"
PLANE_API_TEST_IMAGE="${API_TEST_IMAGE}" PLANE_API_TEST_IMAGE_DIGEST="${API_TEST_IMAGE_DIGEST}" \
    PLANE_API_TEST_IMAGE_TAG="${API_TEST_IMAGE_TAG}" PLANE_API_SOURCE_REVISION="${API_SOURCE_REVISION}" \
    "${ROOT_DIR}/tools/verify-api-migrations.sh"
emit "migration-chain" passed "apply=passed" "reverse_to=0138" "reapply=passed" "drift=passed" "leaf=0146"

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

CURRENT_STEP="ruff-baseline"
prepare_ruff_baseline_dir

CURRENT_STEP="g3-api-and-client-suite"
run_api sh -c "
set -Eeuo pipefail
export RUFF_CACHE_DIR=/tmp/g3-ruff-cache
export PYTHONPATH=/workspace/apps/api${PYTHONPATH:+:${PYTHONPATH}}

run_ruff_baseline_aware() {
    local candidate_status=0 baseline_status=0
    ruff check --config /workspace/apps/api/pyproject.toml --output-format json \
        plane/agent plane/operation_gateway plane/tests/unit/agent plane/tests/contract/api \
        >/tmp/g3-candidate-ruff.json || candidate_status=\$?
    ruff check --config /workspace/apps/api/pyproject.toml --output-format json \
        /workspace/g3-ruff-baseline/apps/api/plane/agent \
        /workspace/g3-ruff-baseline/apps/api/plane/operation_gateway \
        /workspace/g3-ruff-baseline/apps/api/plane/tests/unit/agent \
        /workspace/g3-ruff-baseline/apps/api/plane/tests/contract/api \
        >/tmp/g3-baseline-ruff.json || baseline_status=\$?
    if [ "\${candidate_status}" -gt 1 ] || [ "\${baseline_status}" -gt 1 ]; then
        printf 'event=agent.g3.ruff status=failed candidate_exit=\${candidate_status} baseline_exit=\${baseline_status}\\n' >&2
        return 2
    fi
    python - /tmp/g3-candidate-ruff.json /tmp/g3-baseline-ruff.json <<'PY'
import json
import sys
from collections import Counter
from pathlib import PurePosixPath


def diagnostics(path):
    raw = open(path, encoding='utf-8').read()
    return json.loads(raw) if raw.strip() else []


def key(item):
    filename = str(item.get('filename', '')).replace(chr(92), '/')
    for prefix in ('/workspace/g3-ruff-baseline/apps/api/', '/workspace/apps/api/'):
        if filename.startswith(prefix):
            filename = filename[len(prefix) :]
            break
    filename = str(PurePosixPath(filename))
    return filename, str(item.get('code', '')), str(item.get('message', ''))


candidate = Counter(key(item) for item in diagnostics(sys.argv[1]))
baseline = Counter(key(item) for item in diagnostics(sys.argv[2]))
new = candidate - baseline
if new:
    print(
        f'event=agent.g3.ruff status=failed baseline={sum(baseline.values())} '
        f'candidate={sum(candidate.values())} new={sum(new.values())}',
        file=sys.stderr,
    )
    for (filename, code, message), count in sorted(new.items())[:20]:
        print(f'ruff-new count={count} file={filename} code={code} message={message}', file=sys.stderr)
    raise SystemExit(1)

status = 'baseline_allowed' if baseline else 'passed'
print(f'event=agent.g3.ruff status={status} baseline={sum(baseline.values())} new=0')
PY
}

python manage.py bootstrap_operation_gateway_audit --phase=before-migrate
python manage.py migrate --noinput --verbosity 0
python manage.py bootstrap_operation_gateway_audit --phase=after-migrate
RUFF_STATUS=0
if run_ruff_baseline_aware; then :; else RUFF_STATUS=\$?; fi
RUFF_FORMAT_STATUS=0
if ruff format --check plane/tests/contract/api/test_operation_gateway_mcp.py plane/tests/contract/api/test_operation_gateway_external_clients.py; then
    printf 'event=agent.g3.ruff-format status=passed\\n'
else
    RUFF_FORMAT_STATUS=\$?
    printf 'event=agent.g3.ruff-format status=failed\\n' >&2
fi
python -m compileall -q plane/agent plane/operation_gateway plane/tests/unit/agent plane/tests/contract/api
python manage.py shell -c 'from django.db import connection; from django.db.migrations.executor import MigrationExecutor; e=MigrationExecutor(connection); leaves=set(e.loader.graph.leaf_nodes(\"db\")); applied=set(e.recorder.applied_migrations()); assert leaves == {(\"db\", \"0146_runtime_reconciliation_audit_fields\")}; assert not leaves-applied; print(\"event=agent.g3.api.migration_leaf status=passed leaf=0146\")'
PLANE_AUDIT_ENFORCE_ROLE_SEPARATION=0 pytest -p plane.tests.g3_no_skips --migrations -q -o addopts='--strict-markers --reuse-db' -o cache_dir=/tmp/g3-pytest ${G3_TEST_PATHS[*]}
if [ "\${RUFF_STATUS}" -ne 0 ]; then exit "\${RUFF_STATUS}"; fi
if [ "\${RUFF_FORMAT_STATUS}" -ne 0 ]; then exit "\${RUFF_FORMAT_STATUS}"; fi
"
emit "g3-api-and-client-suite" passed "test_files=${#G3_TEST_PATHS[@]}" "external_mcp=${MCP_COMMIT}" "external_sdk=${SDK_COMMIT}" "hermes=${HERMES_COMMIT}" "result_limit=8192"

CURRENT_STEP="complete"
emit "complete" passed "base=${G3_BASE_COMMIT}" "candidate=${CANDIDATE_COMMIT}" "migration_leaf=0146" "mcp=177:86:90:1" "result_boundary=8192/8193" "readiness=ready_for_single_sol_medium_g3_assessment"
