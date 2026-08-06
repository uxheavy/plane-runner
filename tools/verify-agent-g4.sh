#!/usr/bin/env bash

set -Eeuo pipefail
export PYTHONDONTWRITEBYTECODE=1

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="${ROOT_DIR}/tools/agent-g4-manifest.json"
G3_BASE_COMMIT="9b4bad0b0b54c90c8d25e9af5f086971e6b9c93a"
MCP_COMMIT="2dc152e136d7ad952b901e5fe9364a37487297ba"
SDK_COMMIT="7d2faf3b7ef5409e292ba0a3c7015e59f93c5889"
HERMES_COMMIT="e573a46611e2cb988f1ab43ad34cd8cc3b2cb659"
RUNTIME_IMAGE_DIGEST="sha256:51b50bec143e12c22fa92f8b101629d37ae263f2784c9bb3747eaea45978092e"
API_TEST_IMAGE="${PLANE_API_TEST_IMAGE:-plane-g3-external-client-api-tests:prepared}"
RUNTIME_IMAGE="${PLANE_G4_RUNTIME_IMAGE:-${API_TEST_IMAGE}}"
MODE="${PLANE_G4_MODE:-offline}"
CURRENT_STEP="preflight"
STAGE_COUNT=0
STACK_STARTED=0
CREATED_API_LOG_DIR=0
OFFLINE_STATUS="not_run"
G4_PROJECT_NAME="plane-agent-g4-verify-$$-${RANDOM}"
G4_NETWORK_NAME="${G4_PROJECT_NAME}_test_env"
G4_TEMP_PARENT="${ROOT_DIR}/tmp"
G4_TEMP_PARENT_CREATED=0
if [[ ! -d "${G4_TEMP_PARENT}" ]]; then
    mkdir -p -- "${G4_TEMP_PARENT}"
    G4_TEMP_PARENT_CREATED=1
fi
EVIDENCE_DIR="$(mktemp -d "${G4_TEMP_PARENT}/plane-agent-g4.XXXXXX")"
G4_RUNTIME_LOG_DIR="${EVIDENCE_DIR}/runtime-logs"
COMMUNITY_COMPOSE_CONFIG="${EVIDENCE_DIR}/community-compose.json"

GIT_COMMON_DIR="$(git -C "${ROOT_DIR}" rev-parse --git-common-dir)"
if [[ "${GIT_COMMON_DIR}" != /* ]]; then
    GIT_COMMON_DIR="${ROOT_DIR}/${GIT_COMMON_DIR}"
fi
GIT_COMMON_DIR="$(cd -- "${GIT_COMMON_DIR}" && pwd)"
GIT_COMMON_PARENT="$(dirname -- "${GIT_COMMON_DIR}")"
if [[ -d "${GIT_COMMON_PARENT}/plane/.git/modules" ]]; then
    DEFAULT_EXTERNAL_SUPERPROJECT_ROOT="${GIT_COMMON_PARENT}/plane"
elif [[ -d "${GIT_COMMON_PARENT}/.git/modules" ]]; then
    DEFAULT_EXTERNAL_SUPERPROJECT_ROOT="${GIT_COMMON_PARENT}"
else
    DEFAULT_EXTERNAL_SUPERPROJECT_ROOT="${ROOT_DIR}"
fi
EXTERNAL_SUPERPROJECT_ROOT="${PLANE_EXTERNAL_SUPERPROJECT_ROOT:-${DEFAULT_EXTERNAL_SUPERPROJECT_ROOT}}"
MCP_ROOT="${PLANE_MCP_EXTERNAL_ROOT:-${EXTERNAL_SUPERPROJECT_ROOT}/external/plane-mcp-server}"
SDK_ROOT="${PLANE_SDK_EXTERNAL_ROOT:-${EXTERNAL_SUPERPROJECT_ROOT}/external/plane-python-sdk}"
HERMES_ROOT="${PLANE_HERMES_EXTERNAL_ROOT:-${EXTERNAL_SUPERPROJECT_ROOT}/../hermes-agent}"

case "${1:-}" in
    "") ;;
    --mode)
        MODE="${2:-}"
        shift 2
        ;;
    --offline)
        MODE="offline"
        shift
        ;;
    --live)
        MODE="live"
        shift
        ;;
    *)
        printf 'event=agent.g4.preflight status=failed expected=offline_or_live_mode actual=unknown_argument suggestion=use_--offline_or_--live\n' >&2
        exit 2
        ;;
esac
[[ "$#" -eq 0 ]] || {
    printf 'event=agent.g4.preflight status=failed expected=no_extra_arguments actual=extra_arguments suggestion=use_one_mode_flag\n' >&2
    exit 2
}
[[ "${MODE}" == "offline" || "${MODE}" == "live" ]] || {
    printf 'event=agent.g4.preflight status=failed expected=offline_or_live_mode actual=%s suggestion=use_--offline_or_--live\n' "${MODE}" >&2
    exit 2
}

emit() {
    local event="$1"
    local status="$2"
    shift 2
    printf 'event=agent.g4.%s status=%s' "${event}" "${status}"
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

live_configuration_is_explicit() {
    [[ -n "${PLANE_G4_LIVE_AUTHORITY:-}" && -f "${PLANE_G4_LIVE_AUTHORITY}" ]] || return 1
    [[ -n "${PLANE_G4_LIVE_CONFIG:-}" && -f "${PLANE_G4_LIVE_CONFIG}" ]] || return 1
    [[ -n "${PLANE_G4_LIVE_COMMAND:-}" ]]
}

live_configuration_required() {
    emit "live-boundary" external_required "exit_code=2" \
        "expected=explicit_authority_config_and_live_command" \
        "actual=not_configured" \
        "required=PLANE_G4_LIVE_AUTHORITY,PLANE_G4_LIVE_CONFIG,PLANE_G4_LIVE_COMMAND" \
        "suggestion=provide_the_named_authority_config_and_command"
}

check_candidate_clean() {
    local status dirty="" line path
    status="$(git -C "${ROOT_DIR}" status --porcelain=v1 --untracked-files=all)"
    while IFS= read -r line; do
        [[ -z "${line}" ]] && continue
        path="${line:3}"
        [[ "${path}" == ".codex/config.toml" ]] && continue
        dirty+="${line};"
    done <<< "${status}"
    [[ -z "${dirty}" ]] || fail "clean candidate checkout excluding .codex/config.toml" "dirty=${dirty}" "commit or remove candidate changes"
}

check_candidate_identity() {
    local actual expected
    actual="$(git -C "${ROOT_DIR}" rev-parse HEAD)" || fail "candidate commit is readable" "git rev-parse failed" "inspect the candidate checkout"
    expected="${PLANE_G4_CANDIDATE_COMMIT:-${actual}}"
    [[ "${actual}" == "${expected}" ]] || fail "candidate HEAD=${expected}" "actual=${actual}" "rerun against the exact candidate commit"
    git -C "${ROOT_DIR}" merge-base --is-ancestor "${G3_BASE_COMMIT}" "${actual}" || fail "candidate descends from G3 base=${G3_BASE_COMMIT}" "candidate=${actual}" "use the integrated G3 candidate history"
    CANDIDATE_COMMIT="${actual}"
}

pin_external_tree() {
    local label="$1" root="$2" expected="$3" actual status
    [[ -d "${root}" ]] || fail "${label} checkout exists" "missing=${root}" "set the ${label} checkout override"
    actual="$(git -C "${root}" rev-parse HEAD)" || fail "${label} checkout is readable" "git failed" "inspect ${root}"
    [[ "${actual}" == "${expected}" ]] || fail "${label} HEAD=${expected}" "actual=${actual}" "use the authoritative pinned checkout"
    status="$(git -C "${root}" status --porcelain=v1 --untracked-files=all)"
    [[ -z "${status}" ]] || fail "${label} checkout is clean" "dirty=${root}" "do not run against modified external code"
    emit "external.${label}.pin" passed "root=${root}" "head=${actual}"
}

check_gitlinks() {
    local mcp_link sdk_link
    mcp_link="$(git -C "${ROOT_DIR}" ls-tree "${CANDIDATE_COMMIT}" external/plane-mcp-server)"
    sdk_link="$(git -C "${ROOT_DIR}" ls-tree "${CANDIDATE_COMMIT}" external/plane-python-sdk)"
    [[ "${mcp_link}" == *"${MCP_COMMIT}"$'\texternal/plane-mcp-server' ]] || fail "MCP gitlink=${MCP_COMMIT}" "${mcp_link}" "inspect the integrated Plane tree"
    [[ "${sdk_link}" == *"${SDK_COMMIT}"$'\texternal/plane-python-sdk' ]] || fail "SDK gitlink=${SDK_COMMIT}" "${sdk_link}" "inspect the integrated Plane tree"
}

check_image() {
    local image="$1" expected="$2" actual
    actual="$(docker image inspect "${image}" --format '{{.Id}}' 2>/dev/null)" || fail "prepared image ${image} is available offline" "image unavailable" "prepare the pinned image locally; this verifier never pulls"
    [[ "${actual}" == "${expected}" ]] || fail "image ${image} digest=${expected}" "actual=${actual}" "use the authoritative prepared image"
    docker run --rm --network none --entrypoint sh "${image}" -c '
        set -eu
        command -v python >/dev/null
        command -v pytest >/dev/null
        command -v ruff >/dev/null
        python -c "import django, psycopg, pytest"
    ' >/dev/null 2>&1 || fail "offline API/runtime dependencies are prepared in ${image}" "dependency probe failed" "prepare the pinned local image without installing during verification"
}

validate_manifest() {
    python3 - "${MANIFEST}" "${ROOT_DIR}" "${CANDIDATE_COMMIT}" "${MCP_COMMIT}" "${SDK_COMMIT}" "${HERMES_COMMIT}" "${RUNTIME_IMAGE_DIGEST}" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

manifest_path, root_value, candidate, mcp, sdk, hermes, image_digest = sys.argv[1:]
root = Path(root_value)
manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
assert manifest["manifestVersion"] == "plane-agent-g4/v1"
assert manifest["pins"] == {
    "hermesCommit": hermes,
    "mcpGitlink": mcp,
    "sdkGitlink": sdk,
    "runtimeImageDigest": image_digest,
}
required_stages = {
    "preflight",
    "g3-prerequisite",
    "static-scope",
    "g4-runtime-contracts",
    "g4-cross-process",
    "g4-runtime-red-team",
    "g4-gateway-workload",
    "g4-operator-readback",
    "g4-production-configuration",
    "live-boundary",
    "cleanup",
}
assert set(manifest["stages"]) == required_stages
for relative in (*manifest["authority"], *manifest["contracts"], *manifest["scripts"], manifest["runbook"], *manifest["offlineFixtures"]):
    assert (root / relative).exists(), relative
for relative in manifest["pytestPaths"]:
    assert (root / "apps/api" / relative).exists(), relative
runbook_text = (root / manifest["runbook"]).read_text(encoding="utf-8")
for marker in manifest["runbookEvidence"]:
    assert marker in runbook_text, f"runbook evidence missing: {marker}"
for relative in manifest["retiredDocuments"]:
    assert not (root / relative).exists(), f"retired document restored: {relative}"
    result = subprocess.run(
        ["git", "-C", str(root), "cat-file", "-e", f"{candidate}:{relative}"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, f"retired document present in candidate: {relative}"
for relative in manifest["pytestPaths"]:
    text = (root / "apps/api" / relative).read_text(encoding="utf-8")
    for marker in ("pytest.skip", "pytest.xfail", "@pytest.mark.xfail", "importorskip"):
        assert marker not in text, f"suppression marker in required G4 test {relative}: {marker}"
print(f"manifest=validated stages={len(manifest['stages'])} pytest_paths={len(manifest['pytestPaths'])} retired_absent={len(manifest['retiredDocuments'])}")
PY
}

run_logged() {
    local stage="$1"
    shift
    local log="${EVIDENCE_DIR}/${stage}.log"
    local exit_code
    set +e
    "$@" >"${log}" 2>&1
    exit_code=$?
    set -e
    if [[ "${exit_code}" -ne 0 ]]; then
        tail -80 "${log}" >&2 || true
        fail "stage ${stage} exits 0" "exit_code=${exit_code}" "inspect the stage evidence and fix the first failure"
    fi
    if rg -n -i '(^|[[:space:]])[0-9]+ (skipped|deselected|xfailed|xpassed)|(^|[[:space:]])(xfail|xpass)([[:space:]]|$)' "${log}" >/dev/null; then
        tail -80 "${log}" >&2 || true
        fail "stage ${stage} has no skipped, deselected, or xfail tests" "test suppression detected" "select and pass every required test"
    fi
    STAGE_COUNT=$((STAGE_COUNT + 1))
    emit "${stage}" passed "exit_code=${exit_code}" "evidence=complete"
}

static_scope() {
    python3 "${ROOT_DIR}/tools/check-agent-settings-reuse.py" "${G3_BASE_COMMIT}" "${CANDIDATE_COMMIT}"
    git -C "${ROOT_DIR}" diff --check "${G3_BASE_COMMIT}" "${CANDIDATE_COMMIT}"
    gitleaks detect --no-banner --redact --source "${ROOT_DIR}" --log-opts "${G3_BASE_COMMIT}..${CANDIDATE_COMMIT}" --exit-code 1
}

compose() {
    PLANE_TEST_ENV_FILE="${ROOT_DIR}/apps/api/.env.example" \
        docker compose -p "${G4_PROJECT_NAME}" -f "${ROOT_DIR}/docker-compose-test.yml" "$@"
}

wait_for_services() {
    local container attempt state
    for attempt in $(seq 1 60); do
        state=healthy
        for container in \
            "${G4_PROJECT_NAME}-test-db-1" \
            "${G4_PROJECT_NAME}-test-redis-1" \
            "${G4_PROJECT_NAME}-test-mq-1" \
            "${G4_PROJECT_NAME}-test-minio-1"; do
            if ! docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${container}" 2>/dev/null | grep -qx healthy; then
                state=starting
            fi
        done
        if [[ "${state}" == "healthy" ]]; then
            return 0
        fi
        sleep 1
    done
    return 1
}

API_ENV=(
    --env "DJANGO_SETTINGS_MODULE=plane.settings.test"
    --env "PYTHONPYCACHEPREFIX=/tmp/g4-pycache"
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
    --env "PLANE_AUDIT_ENFORCE_ROLE_SEPARATION=0"
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
        --network "${G4_NETWORK_NAME}" \
        "${API_ENV[@]}" \
        --entrypoint /bin/sh \
        --mount "type=bind,src=${ROOT_DIR}/apps/api,dst=/workspace/apps/api,readonly" \
        --mount "type=bind,src=${ROOT_DIR}/packages/agent-runtime-contract,dst=/workspace/packages/agent-runtime-contract,readonly" \
        --mount "type=bind,src=${MCP_ROOT},dst=/workspace/external/plane-mcp-server,readonly" \
        --mount "type=bind,src=${SDK_ROOT},dst=/workspace/external/plane-python-sdk,readonly" \
        --mount "type=bind,src=${EXTERNAL_SUPERPROJECT_ROOT}/.git/modules,dst=/workspace/.git/modules,readonly" \
        --mount "type=bind,src=${HERMES_ROOT},dst=/workspace/hermes-agent,readonly" \
        --mount "type=bind,src=${G4_RUNTIME_LOG_DIR},dst=/workspace/apps/api/plane/logs" \
        --mount "type=bind,src=${COMMUNITY_COMPOSE_CONFIG},dst=/tmp/community-compose.json,readonly" \
        --workdir /workspace/apps/api \
        "${API_TEST_IMAGE}" -c 'exec "$@"' -- "$@"
}

setup_g4_stack() {
    mkdir -p -- "${G4_RUNTIME_LOG_DIR}"
    env \
        CORS_ALLOWED_ORIGINS=http://localhost \
        LIVE_SERVER_SECRET_KEY=compose-test-key \
        SECRET_KEY=compose-test-key \
        PLANE_AGENT_RUNTIME_IMAGE="${RUNTIME_IMAGE}" \
        docker compose -f "${ROOT_DIR}/deployments/cli/community/docker-compose.yml" config --format json \
        >"${COMMUNITY_COMPOSE_CONFIG}" || return 1
    [[ -s "${COMMUNITY_COMPOSE_CONFIG}" ]] || return 1
    STACK_STARTED=1
    if [[ ! -d "${ROOT_DIR}/apps/api/plane/logs" ]]; then
        mkdir -p -- "${ROOT_DIR}/apps/api/plane/logs"
        CREATED_API_LOG_DIR=1
    fi
    compose up --pull never -d test-db test-redis test-mq test-minio >/dev/null || return 1
    wait_for_services || return 1
    run_api sh -c '
        set -Eeuo pipefail
        export PYTHONPATH=/workspace/apps/api${PYTHONPATH:+:${PYTHONPATH}}
        python manage.py bootstrap_operation_gateway_audit --phase=before-migrate
        python manage.py migrate --noinput --verbosity 0
        python manage.py bootstrap_operation_gateway_audit --phase=after-migrate
    '
}

g4_pytest() {
    local path="$1"
    run_api pytest \
        -p plane.tests.g3_no_skips \
        --migrations \
        -q \
        -o 'addopts=--strict-markers --reuse-db' \
        -o cache_dir=/tmp/g4-pytest \
        "${path}"
}

g4_runtime_contracts() {
    setup_g4_stack || return 1
    g4_pytest plane/tests/unit/agent/test_g4_runtime_boundary.py
}

cleanup() {
    local status=$?
    local cleanup_status=0
    trap - EXIT INT TERM
    if [[ "${STACK_STARTED}" -eq 1 ]]; then
        compose down -v --remove-orphans >/dev/null 2>&1 || cleanup_status=1
    fi
    if [[ "${CREATED_API_LOG_DIR}" -eq 1 ]]; then
        rm -rf -- "${ROOT_DIR}/apps/api/plane/logs"
    fi
    if [[ -d "${EVIDENCE_DIR}" ]]; then
        rm -rf -- "${EVIDENCE_DIR}"
    fi
    if [[ "${G4_TEMP_PARENT_CREATED}" -eq 1 ]]; then
        rmdir -- "${G4_TEMP_PARENT}" 2>/dev/null || cleanup_status=1
    fi
    if [[ "${status}" -eq 0 || "${status}" -eq 2 ]]; then
        check_candidate_clean || cleanup_status=1
    fi
    if [[ "${cleanup_status}" -ne 0 ]]; then
        emit "cleanup" failed "expected=task-owned_containers_and_temp_files_removed" "actual=cleanup_failed" "suggestion=inspect_Docker_and_temp_state" >&2
        [[ "${status}" -ne 0 ]] || status=1
    else
        STAGE_COUNT=$((STAGE_COUNT + 1))
        emit "cleanup" passed "exit_code=0" "evidence=worktree_and_task_resources_checked"
    fi
    if [[ "${status}" -eq 2 ]]; then
        emit "complete" external_required "exit_code=2" "stage_count=${STAGE_COUNT}" "offline=${OFFLINE_STATUS}" "live=explicit_authority_required"
    elif [[ "${status}" -eq 0 ]]; then
        emit "complete" passed "exit_code=0" "stage_count=${STAGE_COUNT}" "mode=${MODE}" "candidate=${CANDIDATE_COMMIT}"
    else
        emit "complete" failed "exit_code=${status}" "stage_count=${STAGE_COUNT}" "failed_stage=${CURRENT_STEP}" >&2
    fi
    exit "${status}"
}

trap cleanup EXIT
trap 'exit 130' INT TERM

if [[ "${MODE}" == "live" ]] && ! live_configuration_is_explicit; then
    CURRENT_STEP="live-boundary"
    live_configuration_required
    exit 2
fi
if [[ -n "${G3_TEST_PATHS_OVERRIDE:-}" ]]; then
    CURRENT_STEP="preflight"
    emit "preflight" failed "expected=G3_TEST_PATHS_OVERRIDE unset" "actual=noncanonical_override_present" "suggestion=invoke_verify-agent-g3.sh_directly_for_subset_diagnostics" >&2
    exit 1
fi

command -v docker >/dev/null 2>&1 || fail "Docker is available" "docker_unavailable" "enable the local Docker runtime"
command -v git >/dev/null 2>&1 || fail "Git is available" "git_unavailable" "install Git"
command -v gitleaks >/dev/null 2>&1 || fail "gitleaks is available" "gitleaks_unavailable" "install gitleaks locally"
command -v python3 >/dev/null 2>&1 || fail "Python 3 is available" "python3_unavailable" "install Python 3"
docker compose version >/dev/null 2>&1 || fail "Docker Compose is available" "compose_unavailable" "enable Docker Compose"

CURRENT_STEP="preflight"
check_candidate_clean
check_candidate_identity
check_gitlinks
pin_external_tree mcp "${MCP_ROOT}" "${MCP_COMMIT}"
pin_external_tree sdk "${SDK_ROOT}" "${SDK_COMMIT}"
pin_external_tree hermes "${HERMES_ROOT}" "${HERMES_COMMIT}"
[[ -d "${EXTERNAL_SUPERPROJECT_ROOT}/.git/modules" ]] || fail "external git module metadata is mounted" "missing=${EXTERNAL_SUPERPROJECT_ROOT}/.git/modules" "set PLANE_EXTERNAL_SUPERPROJECT_ROOT"
check_image "${API_TEST_IMAGE}" "${RUNTIME_IMAGE_DIGEST}"
check_image "${RUNTIME_IMAGE}" "${RUNTIME_IMAGE_DIGEST}"
validate_manifest
STAGE_COUNT=$((STAGE_COUNT + 1))
emit "preflight" passed "exit_code=0" "candidate=${CANDIDATE_COMMIT}" "hermes=${HERMES_COMMIT}" "mcp=${MCP_COMMIT}" "sdk=${SDK_COMMIT}" "runtime_image_digest=${RUNTIME_IMAGE_DIGEST}"

CURRENT_STEP="g3-prerequisite"
run_logged g3-prerequisite env \
    -u G3_TEST_PATHS_OVERRIDE \
    PLANE_API_TEST_IMAGE="${API_TEST_IMAGE}" \
    PLANE_EXTERNAL_SUPERPROJECT_ROOT="${EXTERNAL_SUPERPROJECT_ROOT}" \
    PLANE_MCP_EXTERNAL_ROOT="${MCP_ROOT}" \
    PLANE_SDK_EXTERNAL_ROOT="${SDK_ROOT}" \
    PLANE_HERMES_EXTERNAL_ROOT="${HERMES_ROOT}" \
    PLANE_AGENT_RUNTIME_IMAGE="${RUNTIME_IMAGE}" \
    "${ROOT_DIR}/tools/verify-agent-g3.sh"

CURRENT_STEP="static-scope"
run_logged static-scope static_scope

CURRENT_STEP="g4-runtime-contracts"
run_logged g4-runtime-contracts g4_runtime_contracts

CURRENT_STEP="g4-cross-process"
run_logged g4-cross-process g4_pytest plane/tests/unit/agent/test_g4_runtime_cross_process.py

CURRENT_STEP="g4-runtime-red-team"
run_logged g4-runtime-red-team env \
    PLANE_G4_RUNTIME_IMAGE="${RUNTIME_IMAGE}" \
    PLANE_G4_RUNTIME_IMAGE_DIGEST="${RUNTIME_IMAGE_DIGEST}" \
    PLANE_G4_RUNTIME_CODE_ROOT="${ROOT_DIR}/apps/api" \
    python3 "${ROOT_DIR}/tools/agent-g4-runtime-red-team.py"

CURRENT_STEP="g4-gateway-workload"
run_logged g4-gateway-workload g4_pytest plane/tests/contract/api/test_operation_gateway_g4.py

CURRENT_STEP="g4-operator-readback"
run_logged g4-operator-readback g4_pytest plane/tests/contract/api/test_agent_operator_readback_g4.py

CURRENT_STEP="g4-production-configuration"
run_logged g4-production-configuration g4_pytest plane/tests/contract/api/test_agent_runtime_production.py

CURRENT_STEP="live-boundary"
OFFLINE_STATUS="passed"
if [[ "${MODE}" == "live" ]]; then
    if ! live_configuration_is_explicit; then
        live_configuration_required
        exit 2
    fi
    run_logged live-boundary env PLANE_G4_OFFLINE=0 PLANE_G4_NO_MODEL_FALLBACK=1 bash -lc "${PLANE_G4_LIVE_COMMAND}"
else
    STAGE_COUNT=$((STAGE_COUNT + 1))
    emit "live-boundary" passed "exit_code=0" "mode=offline" "live_evaluation=not_requested"
fi

exit 0
