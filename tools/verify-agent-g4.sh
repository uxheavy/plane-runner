#!/usr/bin/env bash

set -Eeuo pipefail
export PYTHONDONTWRITEBYTECODE=1

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="${ROOT_DIR}/tools/agent-g4-manifest.json"
G3_BASE_COMMIT="7c9d35f4c324865c27c84da5016be2c84e460bcc"
MCP_COMMIT="2dc152e136d7ad952b901e5fe9364a37487297ba"
SDK_COMMIT="7d2faf3b7ef5409e292ba0a3c7015e59f93c5889"
HERMES_COMMIT="e573a46611e2cb988f1ab43ad34cd8cc3b2cb659"
RUNTIME_IMAGE_TAG="plane-agent-runtime:hermes-e573a466-g4-ff8cd9c5"
RUNTIME_IMAGE_DIGEST="sha256:8bd10066b99077a60e8a1fda7630fd47a1a59da687aac3d87a80704cd34a7741"
RUNTIME_IMAGE_REVISION="ff8cd9c548ae73a587e9caacb960616bd9964e8b"
RUNTIME_CONTRACT="plane.agent-runtime/v1"
API_TEST_IMAGE="${PLANE_API_TEST_IMAGE:-plane-g3-external-client-api-tests:prepared}"
RUNTIME_IMAGE="${PLANE_G4_RUNTIME_IMAGE:-${RUNTIME_IMAGE_TAG}}"
MODE="${PLANE_G4_MODE:-offline}"
CANDIDATE_PARENT_COMMIT="$(python3 - "${MANIFEST}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle)["candidateBinding"]["parentCommit"])
PY
)"
CURRENT_STEP="preflight"
STAGE_COUNT=0
STACK_STARTED=0
CREATED_API_LOG_DIR=0
OFFLINE_STATUS="not_run"
CURRENT_LOG=""
RED_TEAM_STAGE_ENTERED=0
RED_TEAM_LABEL_KEY="com.uxheavy.plane.agent-g4-runtime"
RED_TEAM_LABEL_VALUE="true"
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
    if [[ -n "${CURRENT_LOG}" && -f "${CURRENT_LOG}" ]]; then
        emit "${CURRENT_STEP}.failure-log" captured "log_sha256=$(shasum -a 256 "${CURRENT_LOG}" | awk '{print $1}')" >&2
        python3 "${ROOT_DIR}/tools/summarize_agent_g4.py" --print-sanitized-log "${CURRENT_LOG}" >&2 || true
    fi
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

validate_live_configuration() {
    if ! python3 "${ROOT_DIR}/tools/validate_agent_g4_live.py" \
        --authority "${PLANE_G4_LIVE_AUTHORITY}" \
        --config "${PLANE_G4_LIVE_CONFIG}" \
        --manifest "${MANIFEST}" \
        --candidate "${CANDIDATE_COMMIT}" \
        --command "${PLANE_G4_LIVE_COMMAND}" \
        --config-only >/dev/null; then
        fail "live authority and config are exact and valid" "live_configuration_invalid" "inspect the structured authority/config contract"
    fi
    emit "live-boundary.preflight" passed "config=validated" "offline=not_run" "command_binding=validated"
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
    local actual parent_line parent_count parent
    actual="$(git -C "${ROOT_DIR}" rev-parse HEAD)" || fail "candidate commit is readable" "git rev-parse failed" "inspect the candidate checkout"
    [[ -z "${PLANE_G4_CANDIDATE_COMMIT:-}" ]] || fail "candidate is bound by the committed manifest" "candidate_override_present" "remove PLANE_G4_CANDIDATE_COMMIT; use the committed evidence wrapper"
    parent_line="$(git -C "${ROOT_DIR}" rev-list --parents -n 1 "${actual}")"
    read -r _ parent parent_count <<< "${parent_line}"
    [[ -n "${parent}" && -z "${parent_count}" ]] || fail "candidate is a single-parent evidence wrapper" "merge_or_root_commit" "run from the exact committed wrapper candidate"
    [[ "${parent}" == "${CANDIDATE_PARENT_COMMIT}" ]] || fail "candidate immediate parent=${CANDIDATE_PARENT_COMMIT}" "actual_parent=${parent}" "rerun from the exact candidate wrapper commit"
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

check_api_test_image() {
    local image="$1"
    docker image inspect "${image}" --format '{{.Id}}' >/dev/null 2>&1 || fail "prepared API test image ${image} is available offline" "image unavailable" "prepare the pinned API test image locally; this verifier never pulls"
    docker run --rm --network none --entrypoint sh "${image}" -c '
        set -eu
        command -v python >/dev/null
        command -v pytest >/dev/null
        command -v ruff >/dev/null
        python -c "import django, psycopg, pytest"
    ' >/dev/null 2>&1 || fail "offline API test dependencies are prepared in ${image}" "dependency probe failed" "prepare the API test image without installing during verification"
}

check_runtime_image() {
    local image="$1" expected="$2" actual hermes_revision runtime_revision runtime_contract
    actual="$(docker image inspect "${image}" --format '{{.Id}}' 2>/dev/null)" || fail "prepared image ${image} is available offline" "image unavailable" "prepare the pinned image locally; this verifier never pulls"
    [[ "${actual}" == "${expected}" ]] || fail "image ${image} digest=${expected}" "actual=${actual}" "use the authoritative prepared image"
    hermes_revision="$(docker image inspect "${image}" --format '{{index .Config.Labels "org.uxheavy.plane.hermes.commit"}}')"
    runtime_revision="$(docker image inspect "${image}" --format '{{index .Config.Labels "org.uxheavy.plane.runtime.revision"}}')"
    runtime_contract="$(docker image inspect "${image}" --format '{{index .Config.Labels "org.uxheavy.plane.runtime.contract"}}')"
    [[ "${hermes_revision}" == "${HERMES_COMMIT}" ]] || fail "runtime image Hermes revision=${HERMES_COMMIT}" "actual=${hermes_revision}" "use the image built from the pinned Hermes commit"
    [[ "${runtime_revision}" == "${RUNTIME_IMAGE_REVISION}" ]] || fail "runtime image Plane revision=${RUNTIME_IMAGE_REVISION}" "actual=${runtime_revision}" "use the image built from the integrated runtime source"
    [[ "${runtime_contract}" == "${RUNTIME_CONTRACT}" ]] || fail "runtime image contract=${RUNTIME_CONTRACT}" "actual=${runtime_contract}" "use the authoritative runtime contract image"
    docker run --rm --network none --entrypoint sh "${image}" -c '
        set -eu
        command -v python >/dev/null
        command -v pytest >/dev/null
        python -c "import django, psycopg, pytest"
    ' >/dev/null 2>&1 || fail "offline runtime dependencies are prepared in ${image}" "dependency probe failed" "prepare the pinned local runtime image without installing during verification"
}

validate_manifest() {
    python3 - "${MANIFEST}" "${ROOT_DIR}" "${CANDIDATE_COMMIT}" "${G3_BASE_COMMIT}" "${CANDIDATE_PARENT_COMMIT}" "${MCP_COMMIT}" "${SDK_COMMIT}" "${HERMES_COMMIT}" "${RUNTIME_IMAGE_TAG}" "${RUNTIME_IMAGE_DIGEST}" "${RUNTIME_IMAGE_REVISION}" "${RUNTIME_CONTRACT}" <<'PY'
import hashlib
import json
import subprocess
import sys
from pathlib import Path

manifest_path, root_value, candidate, g3, candidate_parent, mcp, sdk, hermes, image_tag, image_digest, image_revision, runtime_contract = sys.argv[1:]
root = Path(root_value)
manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
sys.path.insert(0, str(root / "tools"))
from validate_agent_g4_live import validate_rollback_fixture

assert manifest["manifestVersion"] == "plane-agent-g4/v1"
assert manifest["candidateBinding"] == {
    "mode": "exact-single-child",
    "acceptedG3Baseline": g3,
    "parentCommit": candidate_parent,
    "candidateCommitSource": "git-head-with-exact-parent",
    "rejectDescendants": True,
}
assert manifest["rollbackBinding"] == {
    "fixture": "apps/api/plane/tests/fixtures/agent_g4_rollback_pins.json",
    "currentParentField": "candidateBinding.parentCommit",
    "acceptedBaselineField": "candidateBinding.acceptedG3Baseline",
    "acceptedEvidence": "tools/verify-agent-g3.sh",
    "services": ["api", "worker", "beat-worker", "supervisor", "agent-runtime"],
}
assert manifest["pins"] == {
    "hermesCommit": hermes,
    "mcpGitlink": mcp,
    "sdkGitlink": sdk,
    "runtimeImageTag": image_tag,
    "runtimeImageDigest": image_digest,
    "runtimeImageRevision": image_revision,
    "runtimeContract": runtime_contract,
}
assert manifest["liveContract"] == {
    "authoritySchema": "tools/agent-g4-live-authority.schema.json",
    "configSchema": "tools/agent-g4-live-config.schema.json",
    "evidenceSchema": "tools/agent-g4-live-evidence.schema.json",
    "evidenceVersion": "plane-agent-g4/live-evidence/v1",
    "bindingFields": [
        "candidateCommit",
        "g3Baseline",
        "hermesCommit",
        "mcpGitlink",
        "sdkGitlink",
        "runtimeImageTag",
        "runtimeImageDigest",
        "runtimeImageRevision",
        "runtimeContract",
    ],
    "providerModelSource": "authority.binding.provider",
    "thresholdsSource": "authority.binding.thresholds",
    "fallbackAllowed": False,
    "requiredCanaries": ["permitted", "denied"],
    "requiredReadbacks": ["audit", "version"],
    "commandBinding": "sha256-of-exact-PLANE_G4_LIVE_COMMAND",
}
assert manifest["cleanup"] == {
    "redTeamResourceLabels": {"com.uxheavy.plane.agent-g4-runtime": "true"},
    "assertZeroLabeledResources": True,
}
required_stages = {
    "preflight",
    "g3-prerequisite",
    "static-scope",
    "g4-runtime-contracts",
    "g4-cross-process",
    "g4-runtime-service",
    "g4-runtime-red-team",
    "g4-gateway-workload",
    "g4-rollback",
    "g4-operator-readback",
    "g4-production-configuration",
    "live-boundary",
    "cleanup",
}
assert set(manifest["stages"]) == required_stages
for relative in (*manifest["authority"], *manifest["contracts"], *manifest["scripts"], manifest["runbook"], *manifest["offlineFixtures"]):
    assert (root / relative).exists(), relative
for relative in manifest["verifierTests"]:
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
for name, evidence in manifest["offlineEvidence"].items():
    path = root / evidence["path"]
    assert path.exists(), evidence["path"]
    contents = path.read_bytes()
    assert hashlib.sha256(contents).hexdigest() == evidence["sha256"], f"offline evidence changed: {name}"
    test_path = root / "apps/api" / evidence["testPath"]
    assert test_path.exists(), evidence["testPath"]
    text = test_path.read_text(encoding="utf-8")
    if "testName" in evidence:
        assert f"def {evidence['testName']}" in text, f"required offline test missing: {evidence['testName']}"
    for marker in evidence.get("requiredMarkers", []):
        assert marker in text, f"required offline marker missing: {marker}"
validate_rollback_fixture(root / manifest["rollbackBinding"]["fixture"], root, manifest)
print(f"manifest=validated stages={len(manifest['stages'])} pytest_paths={len(manifest['pytestPaths'])} retired_absent={len(manifest['retiredDocuments'])} offline_evidence={len(manifest['offlineEvidence'])} candidate_parent={candidate_parent}")
PY
}

run_logged() {
    local stage="$1"
    shift
    local log="${EVIDENCE_DIR}/${stage}.log"
    local exit_code summary live_contract
    CURRENT_LOG="${log}"
    set +e
    "$@" >"${log}" 2>&1
    exit_code=$?
    set -e
    if [[ "${exit_code}" -ne 0 ]]; then
        fail "stage ${stage} exits 0" "exit_code=${exit_code}" "inspect the stage evidence and fix the first failure"
    fi
    if rg -n -i '(^|[[:space:]])[0-9]+ (skipped|deselected|xfailed|xpassed)|(^|[[:space:]])(xfail|xpass)([[:space:]]|$)' "${log}" >/dev/null; then
        fail "stage ${stage} has no skipped, deselected, or xfail tests" "test suppression detected" "select and pass every required test"
    fi
    if [[ "${stage}" == "live-boundary" ]]; then
        if ! live_contract="$(python3 "${ROOT_DIR}/tools/validate_agent_g4_live.py" \
            --authority "${PLANE_G4_LIVE_AUTHORITY}" \
            --config "${PLANE_G4_LIVE_CONFIG}" \
            --manifest "${MANIFEST}" \
            --evidence "${log}" \
            --candidate "${CANDIDATE_COMMIT}" \
            --command "${PLANE_G4_LIVE_COMMAND}")"; then
            fail "live command emits validated G4 evidence" "live_evidence_contract_failed" "inspect the sanitized live evidence"
        fi
    fi
    summary="$(python3 "${ROOT_DIR}/tools/summarize_agent_g4.py" "${log}")" || fail "stage ${stage} summary is machine-readable" "summary_failed" "inspect the stage output"
    read -r -a summary_fields <<< "${summary}"
    STAGE_COUNT=$((STAGE_COUNT + 1))
    if [[ -n "${live_contract:-}" ]]; then
        emit "${stage}" passed "exit_code=${exit_code}" "evidence=complete" "${summary_fields[@]}" "${live_contract}"
    else
        emit "${stage}" passed "exit_code=${exit_code}" "evidence=complete" "${summary_fields[@]}"
    fi
    CURRENT_LOG=""
}

static_scope() {
    python3 "${ROOT_DIR}/tools/check-agent-settings-reuse.py" "${G3_BASE_COMMIT}" "${CANDIDATE_COMMIT}"
    python3 - "${ROOT_DIR}/docker-compose-local.yml" "${ROOT_DIR}/deployments/cli/community/docker-compose.yml" <<'PY'
from pathlib import Path
import sys

local = Path(sys.argv[1]).read_text(encoding="utf-8")
community = Path(sys.argv[2]).read_text(encoding="utf-8")
assert community.count("  agent-runtime:\n") == 1, "community compose must own one agent-runtime service"
assert '    entrypoint: ["python3", "-m", "plane.agent.runtime.service"]' in community
assert "    command: []" in community
assert local.count("  agent-runtime:\n") == 1, "local compose must expose one agent-runtime extension"
runtime = local.split("  agent-runtime:\n", 1)[1].split("\n  migrator:", 1)[0]
assert "extends:\n      file: ./deployments/cli/community/docker-compose.yml\n      service: agent-runtime" in runtime
assert "image:" not in runtime
assert "entrypoint:" not in runtime
assert "command:" not in runtime
print("local topology reuse proof passed: community_owner=1 local_extension=1 entrypoint=canonical")
PY
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
    run_api sh -c '
        set -Eeuo pipefail
        export PYTHONPATH=/workspace/apps/api${PYTHONPATH:+:${PYTHONPATH}}
        exec pytest \
            -p plane.tests.g3_no_skips \
            --migrations \
            -q \
            -o "addopts=--strict-markers --reuse-db" \
            -o cache_dir=/tmp/g4-pytest \
            "$1"
    ' -- "${path}"
}

g4_pytest_targeted() {
    local path="$1"
    local expression="$2"
    run_api sh -c '
        set -Eeuo pipefail
        export PYTHONPATH=/workspace/apps/api${PYTHONPATH:+:${PYTHONPATH}}
        exec pytest \
            -p plane.tests.g3_no_skips \
            --migrations \
            -q \
            -o "addopts=--strict-markers --reuse-db" \
            -o cache_dir=/tmp/g4-pytest \
            -k "$2" \
            "$1"
    ' -- "${path}" "${expression}"
}

g4_gateway_workload() {
    run_api sh -c '
        set -Eeuo pipefail
        export PYTHONPATH=/workspace/apps/api${PYTHONPATH:+:${PYTHONPATH}}
        export PLANE_G4_LOAD_JSON=1
        exec pytest \
            -p plane.tests.g3_no_skips \
            --migrations \
            -s \
            -q \
            -o "addopts=--strict-markers --reuse-db" \
            -o cache_dir=/tmp/g4-pytest \
            "$1"
    ' -- plane/tests/contract/api/test_operation_gateway_g4.py
}

g4_production_configuration() {
    pnpm check:local-dev:agent
    run_api sh -c '
        set -Eeuo pipefail
        export PYTHONPATH=/workspace/apps/api${PYTHONPATH:+:${PYTHONPATH}}
        exec pytest \
            -p plane.tests.g3_no_skips \
            --migrations \
            -q \
            -o "addopts=--strict-markers --reuse-db" \
            -o cache_dir=/tmp/g4-pytest \
            "$@"
    ' -- \
        plane/tests/contract/api/test_agent_runtime_production.py \
        plane/tests/contract/api/test_local_runtime_configuration.py
}

g4_rollback() {
    run_api sh -c '
        set -Eeuo pipefail
        export PYTHONPATH=/workspace/apps/api${PYTHONPATH:+:${PYTHONPATH}}
        pytest \
            -p plane.tests.g3_no_skips \
            --migrations \
            -q \
            -o "addopts=--strict-markers --reuse-db" \
            -o cache_dir=/tmp/g4-pytest \
            plane/tests/contract/api/test_agent_g4_rollback_drill.py
        python -c '\''
import json
from plane.operation_gateway.rollback_drill import run_rollback_drill
result = run_rollback_drill()
print(json.dumps({"event": "agent.g4.rollback", **result}, sort_keys=True))
raise SystemExit(0 if result["passes"] else 1)
'\''
    '
}

g4_runtime_contracts() {
    setup_g4_stack || return 1
    g4_pytest plane/tests/unit/agent/test_g4_runtime_boundary.py
}

check_labeled_redteam_resources() {
    local label="${RED_TEAM_LABEL_KEY}=${RED_TEAM_LABEL_VALUE}"
    local containers networks volumes leftovers
    containers="$(docker ps -aq --filter "label=${label}")"
    networks="$(docker network ls -q --filter "label=${label}")"
    volumes="$(docker volume ls -q --filter "label=${label}")"
    leftovers="${containers}${networks}${volumes}"
    if [[ -n "${leftovers}" ]]; then
        emit "cleanup.red-team" failed "expected=zero_labeled_red_team_resources" "actual=resources_remain" "label=${label}" "suggestion=inspect_and_remove_only_the_labeled_task_resources" >&2
        return 1
    fi
    emit "cleanup.red-team" passed "label=${label}" "containers=0" "networks=0" "volumes=0"
}

cleanup() {
    local status=$?
    local cleanup_status=0
    trap - EXIT INT TERM
    if [[ "${STACK_STARTED}" -eq 1 ]]; then
        compose down -v --remove-orphans >/dev/null 2>&1 || cleanup_status=1
    fi
    if [[ "${RED_TEAM_STAGE_ENTERED}" -eq 1 ]]; then
        check_labeled_redteam_resources || cleanup_status=1
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
        emit "cleanup" passed "exit_code=0" "evidence=worktree_and_task_resources_checked" \
            "collected=1" "passed=1" "failed=0" "skipped=0" "xfail=0" "deselected=0" "duration_ms=0" "migration_leaf=not_applicable" \
            "workload_throughput=na" "workload_latency_p95_ms=na" "workload_latency_p99_ms=na" "workload_error_rate=na" "workload_saturation=na" \
            "workload_queue_p95_ms=na" "workload_sustained_duration_s=na" "workload_requests=na" "workload_workers=na" "workload_agents=na" \
            "resource_cpu_pct=na" "resource_cpu_seconds=na" "resource_memory_mb=na" "resource_db_connections=na" "resource_io_mb=na" "evidence_sha256=cleanup-checked"
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
check_api_test_image "${API_TEST_IMAGE}"
[[ "${RUNTIME_IMAGE}" == "${RUNTIME_IMAGE_TAG}" ]] || fail "runtime image tag=${RUNTIME_IMAGE_TAG}" "actual=${RUNTIME_IMAGE}" "use the committed runtime image tag or an explicitly reviewed equivalent"
check_runtime_image "${RUNTIME_IMAGE}" "${RUNTIME_IMAGE_DIGEST}"
validate_manifest
STAGE_COUNT=$((STAGE_COUNT + 1))
emit "preflight" passed "exit_code=0" "candidate=${CANDIDATE_COMMIT}" "hermes=${HERMES_COMMIT}" "mcp=${MCP_COMMIT}" "sdk=${SDK_COMMIT}" "runtime_image_tag=${RUNTIME_IMAGE_TAG}" "runtime_image_digest=${RUNTIME_IMAGE_DIGEST}" "runtime_image_revision=${RUNTIME_IMAGE_REVISION}" "runtime_contract=${RUNTIME_CONTRACT}" \
    "collected=1" "passed=1" "failed=0" "skipped=0" "xfail=0" "deselected=0" "duration_ms=0" "migration_leaf=not_applicable" \
    "workload_throughput=na" "workload_latency_p95_ms=na" "workload_latency_p99_ms=na" "workload_error_rate=na" "workload_saturation=na" \
    "workload_queue_p95_ms=na" "workload_sustained_duration_s=na" "workload_requests=na" "workload_workers=na" "workload_agents=na" \
    "resource_cpu_pct=na" "resource_cpu_seconds=na" "resource_memory_mb=na" "resource_db_connections=na" "resource_io_mb=na" "evidence_sha256=preflight-bound"

if [[ "${MODE}" == "live" ]]; then
    CURRENT_STEP="live-boundary"
    if ! live_configuration_is_explicit; then
        live_configuration_required
        exit 2
    fi
    validate_live_configuration
fi

if [[ ! -d "${ROOT_DIR}/apps/api/plane/logs" ]]; then
    mkdir -p -- "${ROOT_DIR}/apps/api/plane/logs"
    CREATED_API_LOG_DIR=1
fi

CURRENT_STEP="g3-prerequisite"
run_logged g3-prerequisite env \
    -u G3_TEST_PATHS_OVERRIDE \
    PLANE_API_TEST_IMAGE="${API_TEST_IMAGE}" \
    PLANE_EXTERNAL_SUPERPROJECT_ROOT="${EXTERNAL_SUPERPROJECT_ROOT}" \
    PLANE_MCP_EXTERNAL_ROOT="${MCP_ROOT}" \
    PLANE_SDK_EXTERNAL_ROOT="${SDK_ROOT}" \
    PLANE_HERMES_EXTERNAL_ROOT="${HERMES_ROOT}" \
    "${ROOT_DIR}/tools/verify-agent-g3.sh"

CURRENT_STEP="static-scope"
run_logged static-scope static_scope

CURRENT_STEP="g4-runtime-contracts"
run_logged g4-runtime-contracts g4_runtime_contracts

CURRENT_STEP="g4-cross-process"
run_logged g4-cross-process g4_pytest plane/tests/unit/agent/test_g4_runtime_cross_process.py

CURRENT_STEP="g4-runtime-service"
run_logged g4-runtime-service g4_pytest \
    plane/tests/unit/agent/test_runtime_supervisor.py

CURRENT_STEP="g4-runtime-red-team"
RED_TEAM_STAGE_ENTERED=1
run_logged g4-runtime-red-team env \
    PLANE_G4_RUNTIME_IMAGE="${RUNTIME_IMAGE}" \
    PLANE_G4_RUNTIME_IMAGE_DIGEST="${RUNTIME_IMAGE_DIGEST}" \
    PLANE_G4_RUNTIME_CODE_ROOT="${ROOT_DIR}/apps/api" \
    python3 "${ROOT_DIR}/tools/agent-g4-runtime-red-team.py"

CURRENT_STEP="g4-gateway-workload"
run_logged g4-gateway-workload g4_gateway_workload

CURRENT_STEP="g4-rollback"
run_logged g4-rollback g4_rollback

CURRENT_STEP="g4-operator-readback"
run_logged g4-operator-readback g4_pytest plane/tests/contract/api/test_agent_operator_readback_g4.py

CURRENT_STEP="g4-production-configuration"
run_logged g4-production-configuration g4_production_configuration

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
    emit "live-boundary" passed "exit_code=0" "mode=offline" "live_evaluation=not_requested" \
        "collected=1" "passed=1" "failed=0" "skipped=0" "xfail=0" "deselected=0" "duration_ms=0" "migration_leaf=not_applicable" \
        "workload_throughput=na" "workload_latency_p95_ms=na" "workload_latency_p99_ms=na" "workload_error_rate=na" "workload_saturation=na" \
        "workload_queue_p95_ms=na" "workload_sustained_duration_s=na" "workload_requests=na" "workload_workers=na" "workload_agents=na" \
        "resource_cpu_pct=na" "resource_cpu_seconds=na" "resource_memory_mb=na" "resource_db_connections=na" "resource_io_mb=na" "evidence_sha256=offline-not-run"
fi

exit 0
