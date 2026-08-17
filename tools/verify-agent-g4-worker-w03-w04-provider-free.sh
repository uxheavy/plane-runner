#!/usr/bin/env bash

set -Eeuo pipefail
umask 077

RUNNER_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT_DIR="$(cd -- "${RUNNER_DIR}/.." && pwd -P)"
GIT_COMMON_DIR="$(git -C "${ROOT_DIR}" rev-parse --git-common-dir)"
if [[ "${GIT_COMMON_DIR}" != /* ]]; then
    GIT_COMMON_DIR="${ROOT_DIR}/${GIT_COMMON_DIR}"
fi
GIT_COMMON_DIR="$(cd -- "${GIT_COMMON_DIR}" && pwd -P)"
SHARED_REPOSITORY_ROOT="$(cd -- "${GIT_COMMON_DIR}/.." && pwd -P)"
PLANE_G4_LIVE_CAPACITY_LEASE_PATH="${PLANE_G4_LIVE_CAPACITY_LEASE_PATH:-${SHARED_REPOSITORY_ROOT}/tmp/plane-agent-g4-live-capacity}"
export SHARED_REPOSITORY_ROOT PLANE_G4_LIVE_CAPACITY_LEASE_PATH

source "${RUNNER_DIR}/agent-g4-live-support.sh"

COMPOSE_PROJECT="plane-agent-w03-w04-provider-free-${PPID}"
cleanup() {
    local status=$?
    docker compose -p "${COMPOSE_PROJECT}" -f "${ROOT_DIR}/docker-compose-test.yml" down --rmi local -v >/dev/null 2>&1 || true
    live_capacity_lease_release || true
    exit "${status}"
}
trap cleanup EXIT INT TERM

live_capacity_lease_acquire

python3 -m pytest -q \
    "${ROOT_DIR}/tools/tests/test_agent_g4_live_scenario.py" \
    "${ROOT_DIR}/tools/tests/test_agent_g4_live_support.py"

docker compose -p "${COMPOSE_PROJECT}" -f "${ROOT_DIR}/docker-compose-test.yml" run --rm api-tests pytest -q \
    plane/tests/contract/api/test_agent_tools_gateway.py::test_search_workspace_binds_visible_work_item_to_canonical_read_input \
    plane/tests/contract/api/test_agent_g2_host_binding.py::test_code_mode_search_to_read_preserves_target_and_denies_cross_project \
    plane/tests/contract/api/test_agent_g2_host_binding.py::test_invocation_scoped_socket_executes_typescript_through_the_bound_host \
    plane/tests/contract/api/test_agent_g2_host_binding.py::test_typescript_host_rejects_substitution_expiry_and_capability_escapes \
    plane/tests/contract/api/test_operation_gateway.py::test_mutation_replay_is_stable_and_does_not_repeat_plane_service \
    plane/tests/contract/api/test_operation_gateway.py::test_conflicting_key_denies_without_replaying_mutation \
    plane/tests/unit/agent/test_tools.py::test_code_mode_child_isolate_routes_only_typed_host_callbacks \
    plane/tests/unit/agent/test_tools.py::test_code_mode_child_denies_capability_escape_and_imports \
    plane/tests/unit/agent/test_tools.py::test_code_mode_child_denies_zero_duration_before_spawn \
    plane/tests/unit/agent/test_tools.py::test_code_mode_child_stops_on_cancellation
