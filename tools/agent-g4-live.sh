#!/usr/bin/env bash

set -Eeuo pipefail
umask 077

RUNNER_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT_DIR="$(cd -- "${RUNNER_DIR}/.." && pwd -P)"
PROJECT="plane-agent-g4-live-${PPID}-${RANDOM}"
NETWORK="${PROJECT}_test_env"
EGRESS="${PROJECT}_egress"
RUNTIME="${PROJECT}-agent-runtime"
CREDENTIAL_STATE_VOLUME="${PROJECT}_agent_runtime_credential_state"
CREDENTIAL_STATE_TARGET="/run/plane-agent-credentials"
CREDENTIAL_STATE_FILE="${CREDENTIAL_STATE_TARGET}/revocations.json"
PROVIDER_SECRET_VOLUME="${PROJECT}_provider_credentials"
SCENARIO_VOLUME="${PROJECT}_scenario_descriptor"
TMP_ROOT="${ROOT_DIR}/tmp"
RUN_DIR="${TMP_ROOT}/${PROJECT}"
EVIDENCE_FILE="${RUN_DIR}/evidence.json"
ERROR_FILE="${RUN_DIR}/sanitized-error.log"
RUNTIME_SECRET_FILE="${RUN_DIR}/runtime-secret"
PROVIDER_SECRET_FILE="${RUN_DIR}/provider-credentials"
SCENARIO_DESCRIPTOR_PATH_INPUT="${PLANE_G4_SCENARIO_DESCRIPTOR:-}"
SCENARIO_DESCRIPTOR_SHA256="${PLANE_G4_SCENARIO_SHA256:-}"
SCENARIO_ENABLED=0
SCENARIO_VOLUME_CREATED=0
SCENARIO_MOUNT_ARGS=()
SCENARIO_ENV_ARGS=()
LIVE_RESULT_PATH_INPUT="${PLANE_G4_LIVE_RESULT_PATH:-${TMP_ROOT}/${PROJECT}.result}"
RESULT_FILE=""
RUN_DIR_CREATED=0
CREDENTIAL_STATE_VOLUME_CREATED=0
PROVIDER_SECRET_VOLUME_CREATED=0
LIVE_INVOKE_SOURCE="${ROOT_DIR}/tools/agent-g4-live-invoke.py"
MANIFEST_INPUT="${PLANE_G4_LIVE_MANIFEST:-${ROOT_DIR}/tools/agent-g4-manifest.json}"
LIVE_AUTHORITY="${PLANE_G4_LIVE_AUTHORITY:?validated live authority path is required}"
LIVE_CONFIG="${PLANE_G4_LIVE_CONFIG:?validated live config path is required}"
LIVE_COMMAND="${PLANE_G4_LIVE_COMMAND:?validated live command is required}"
RUNTIME_CHILD_ENVIRONMENT_JSON='{"HOME":"/tmp","HERMES_HOME":"/tmp/hermes-home","LANG":"C.UTF-8","LC_ALL":"C.UTF-8","PATH":"/usr/local/bin:/usr/bin:/bin","PYTHONPATH":"/tmp:/opt/plane/agent/dependencies:/opt:/opt/hermes","PYTHONSAFEPATH":"1","PYTHONUNBUFFERED":"1"}'
G4_HOST_CANDIDATE="$(git -C "${ROOT_DIR}" rev-parse HEAD)"
G4_EXPECTED_HOST_CANDIDATE="${PLANE_G4_EXPECTED_CANDIDATE:?operator-supplied exact wrapper SHA is required}"
G4_CANDIDATE="${PLANE_G4_ARTIFACT_CANDIDATE:-${G4_EXPECTED_HOST_CANDIDATE}}"
G4_EXPECTED_CANDIDATE="${G4_CANDIDATE}"
[[ "${G4_EXPECTED_HOST_CANDIDATE}" =~ ^[0-9a-f]{40}$ && "${G4_CANDIDATE}" =~ ^[0-9a-f]{40}$ ]] || {
    printf 'event=agent.g4.live-runner status=failed expected=full_external_expected_candidate_sha actual=invalid suggestion=set_Plane_G4_EXPECTED_CANDIDATE\n' >&2
    exit 2
}
[[ "${G4_HOST_CANDIDATE}" == "${G4_EXPECTED_HOST_CANDIDATE}" ]] || {
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

if [[ -n "${SCENARIO_DESCRIPTOR_PATH_INPUT}" || -n "${SCENARIO_DESCRIPTOR_SHA256}" ]]; then
    if [[ -z "${SCENARIO_DESCRIPTOR_PATH_INPUT}" || -z "${SCENARIO_DESCRIPTOR_SHA256}" ]]; then
        printf '%s\n' 'event=agent.g4.live-runner status=failed expected=scenario-path-and-sha256-pair actual=missing-input suggestion=provide-both-owner-only-scenario-inputs' >&2
        exit 2
    fi
    python3 "${ROOT_DIR}/tools/agent_g4_live_scenario.py" \
        --descriptor "${SCENARIO_DESCRIPTOR_PATH_INPUT}" \
        --sha256 "${SCENARIO_DESCRIPTOR_SHA256}" \
        >/dev/null || {
        printf '%s\n' 'event=agent.g4.live-runner status=failed expected=validated-owner-only-scenario-descriptor actual=validation-failed suggestion=check-version-role-model-prompt-bounds-and-digest' >&2
        exit 2
    }
    SCENARIO_ENABLED=1
fi

G4_G3_BASELINE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["candidateBinding"]["acceptedG3Baseline"])' "${MANIFEST}")"
G4_HERMES="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pins"]["hermesCommit"])' "${MANIFEST}")"
G4_MCP="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pins"]["mcpGitlink"])' "${MANIFEST}")"
G4_SDK="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pins"]["sdkGitlink"])' "${MANIFEST}")"
RUNTIME_IMAGE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pins"]["runtimeImageTag"])' "${MANIFEST}")"
G4_RUNTIME_IMAGE_DIGEST="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pins"]["runtimeImageDigest"])' "${MANIFEST}")"
G4_RUNTIME_IMAGE_REVISION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pins"]["runtimeImageRevision"])' "${MANIFEST}")"
G4_RUNTIME_CONTRACT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pins"]["runtimeContract"])' "${MANIFEST}")"
G4_RUNTIME_SOURCE_DIGEST="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("disposableBinding", {}).get("runtimeSourceDigest", ""))' "${MANIFEST}")"
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
IFS=$'\t' read -r G4_AUTHORITY_ID G4_PERMITTED_CANARY G4_DENIED_CANARY <<<"$(python3 - "${LIVE_AUTHORITY}" <<'PY'
import json
import sys

authority = json.load(open(sys.argv[1], encoding="utf-8"))
binding = authority["binding"]
print(
    "\t".join(
        (
            authority["authorityId"],
            binding["canaries"]["permitted"]["id"],
            binding["canaries"]["denied"]["id"],
        )
    )
)
PY
)"
G4_PROVIDER_RELAY_JSON="$(python3 - "${LIVE_AUTHORITY}" <<'PY'
import json
import sys

authority = json.load(open(sys.argv[1], encoding="utf-8"))
relay = authority.get("providerRelay")
if not isinstance(relay, dict):
    raise SystemExit("authority_provider_relay_missing")
print(json.dumps(relay, sort_keys=True, separators=(",", ":")))
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
runtime_image_id="$(docker image inspect "${RUNTIME_IMAGE}" --format '{{.Id}}' 2>/dev/null)" || {
    printf '%s\n' 'event=agent.g4.live-runner status=failed expected=manifest-bound-runtime-image-available actual=image-unavailable suggestion=build-the-selected-runtime-artifact-from-the-same-candidate' >&2
    exit 2
}
[[ "${runtime_image_id}" == "${G4_RUNTIME_IMAGE_DIGEST}" ]] || {
    printf '%s\n' "event=agent.g4.live-runner status=failed expected=runtime-image-digest=${G4_RUNTIME_IMAGE_DIGEST} actual=${runtime_image_id} suggestion=use-the-manifest-bound-runtime-artifact" >&2
    exit 2
}
runtime_hermes_label="$(docker image inspect "${RUNTIME_IMAGE}" --format '{{index .Config.Labels "org.uxheavy.plane.hermes.commit"}}')"
runtime_hermes_remote_label="$(docker image inspect "${RUNTIME_IMAGE}" --format '{{index .Config.Labels "org.uxheavy.plane.hermes.remote"}}')"
runtime_source_label="$(docker image inspect "${RUNTIME_IMAGE}" --format '{{index .Config.Labels "org.uxheavy.plane.runtime.revision"}}')"
runtime_source_digest_label="$(docker image inspect "${RUNTIME_IMAGE}" --format '{{index .Config.Labels "org.uxheavy.plane.runtime.source.sha256"}}')"
runtime_contract_label="$(docker image inspect "${RUNTIME_IMAGE}" --format '{{index .Config.Labels "org.uxheavy.plane.runtime.contract"}}')"
[[ "${runtime_hermes_label}" == "${G4_HERMES}" && "${runtime_hermes_remote_label}" == "https://github.com/uxheavy/hermes-agent.git" && "${runtime_source_label}" == "${G4_RUNTIME_IMAGE_REVISION}" && "${runtime_contract_label}" == "${G4_RUNTIME_CONTRACT}" && "${api_source_label}" == "${runtime_source_label}" ]] || {
    printf '%s\n' 'event=agent.g4.live-runner status=failed expected=api-runtime-hermes-source-contract-labels-bound actual=label-mismatch suggestion=build-api-and-runtime-from-one-candidate' >&2
    exit 2
}
if [[ -n "${G4_RUNTIME_SOURCE_DIGEST}" && "${runtime_source_digest_label}" != "${G4_RUNTIME_SOURCE_DIGEST}" ]]; then
    printf '%s\n' 'event=agent.g4.live-runner status=failed expected=runtime-source-hash-bound actual=source-digest-mismatch suggestion=use-the-disposable-runtime-manifest-output' >&2
    exit 2
fi

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

safe_docker_failure_reason() {
    python3 - "${ERROR_FILE}" <<'PY'
from pathlib import Path
import sys

try:
    text = Path(sys.argv[1]).read_bytes()[:8192].decode("utf-8", errors="replace").lower()
except OSError:
    print("unavailable")
    raise SystemExit(0)

if "read-only file system" in text and ("mountpoint" in text or "mount" in text):
    print("docker_mount_target_read_only")
elif "invalid mount config" in text or "invalid mount specification" in text:
    print("docker_mount_invalid")
elif "bind source path does not exist" in text or (
    "no such file or directory" in text and ("mount" in text or "bind" in text)
):
    print("docker_mount_source_unavailable")
elif "permission denied" in text and ("mount" in text or "bind" in text):
    print("docker_mount_permission_denied")
elif "network-scoped aliases" in text or "network is not connected" in text:
    print("docker_network_configuration_invalid")
elif "unable to find image" in text or "pull access denied" in text:
    print("docker_image_unavailable")
elif "failed to create task" in text or "oci runtime" in text:
    print("docker_container_start_failed")
else:
    print("docker_precontainer_failure")
PY
}

validate_result_path() {
    python3 - "${LIVE_RESULT_PATH_INPUT}" "${RUN_DIR}" <<'PY'
import os
import stat
import sys
from pathlib import Path

candidate = Path(sys.argv[1])
run_dir = Path(os.path.abspath(sys.argv[2]))
if not candidate.is_absolute() or any(ord(char) < 0x20 or ord(char) == 0x7F for char in str(candidate)):
    raise SystemExit(1)
candidate = Path(os.path.abspath(candidate))
parent = Path(os.path.abspath(candidate.parent))
try:
    resolved_parent = parent.resolve(strict=True)
except (OSError, RuntimeError):
    raise SystemExit(1)
if candidate == run_dir or run_dir in candidate.parents or resolved_parent == run_dir:
    raise SystemExit(1)
try:
    metadata = os.stat(resolved_parent, follow_symlinks=False)
except OSError:
    raise SystemExit(1)
if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
    raise SystemExit(1)
candidate = resolved_parent / candidate.name
try:
    os.lstat(candidate)
except FileNotFoundError:
    pass
except OSError:
    raise SystemExit(1)
else:
    raise SystemExit(1)
print(candidate)
PY
}

cleanup() {
    local status=$?
    local cleanup_status=0
    local reason_category=unavailable
    local error_class=unavailable
    if [[ "${status}" -ne 0 ]]; then
        if [[ "${status}" -eq 125 ]]; then
            reason_category="$(safe_docker_failure_reason)"
        fi
        error_class="$(safe_error_class)"
    fi
    if [[ -n "${RESULT_FILE}" ]] && ! python3 "${ROOT_DIR}/tools/agent-g4-live-result.py" \
        --destination "${RESULT_FILE}" \
        --evidence "${EVIDENCE_FILE}" \
        --status "${status}" \
        --phase "${LIVE_PHASE}" \
        --error-class "${error_class}" \
        --reason-category "${reason_category}" >/dev/null; then
        printf '%s\n' 'event=agent.g4.live-runner status=failed phase=result-persistence expected=owner-only-atomic-result actual=persist-failed' >&2
        cleanup_status=1
    elif [[ -n "${RESULT_FILE}" ]]; then
        cat "${RESULT_FILE}"
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
    if [[ "${PROVIDER_SECRET_VOLUME_CREATED}" -eq 1 ]]; then
        if ! docker volume rm "${PROVIDER_SECRET_VOLUME}" >/dev/null 2>&1; then
            printf 'event=agent.g4.live-runner status=failed phase=cleanup expected=provider-secret-volume-removed actual=volume-removal-failed\n' >&2
            cleanup_status=1
        fi
        PROVIDER_SECRET_VOLUME_CREATED=0
    fi
    if [[ "${SCENARIO_VOLUME_CREATED}" -eq 1 ]]; then
        if ! docker volume rm "${SCENARIO_VOLUME}" >/dev/null 2>&1; then
            printf 'event=agent.g4.live-runner status=failed phase=cleanup expected=scenario-volume-removed actual=volume-removal-failed\n' >&2
            cleanup_status=1
        fi
        SCENARIO_VOLUME_CREATED=0
    fi
    if [[ "${RUN_DIR_CREATED}" -eq 1 && -d "${RUN_DIR}" && ! -L "${RUN_DIR}" ]]; then
        rm -f -- "${RUNTIME_SECRET_FILE}" || true
        rm -f -- "${PROVIDER_SECRET_FILE}" || true
        rm -rf -- "${RUN_DIR}"
    fi
    if [[ "${cleanup_status}" -ne 0 && "${status}" -eq 0 ]]; then
        status=1
    fi
    exit "${status}"
}
trap cleanup EXIT INT TERM

LIVE_PHASE=checkout-bind-preflight
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
RESULT_FILE="$(validate_result_path 2>/dev/null)" || {
    printf '%s\n' 'event=agent.g4.live-runner status=failed expected=fresh-owner-only-result-path actual=unsafe-or-colliding-path suggestion=provide-a-new-owner-only-result-path' >&2
    exit 2
}
mkdir -m 700 -- "${RUN_DIR}" || {
    printf '%s\n' 'event=agent.g4.live-runner status=failed expected=invocation-run-directory actual=unavailable suggestion=use-the-repository-owned-tmp-root' >&2
    exit 2
}
RUN_DIR_CREATED=1
python3 -c 'import secrets; print(secrets.token_urlsafe(48), end="")' >"${RUNTIME_SECRET_FILE}" || {
    printf '%s\n' 'event=agent.g4.live-runner status=failed phase=checkout-bind-preflight expected=owner-only-runtime-secret actual=staging-failed suggestion=use-a-writable-repository-owned-tmp-root' >&2
    exit 2
}
chmod 600 "${RUNTIME_SECRET_FILE}" || {
    printf '%s\n' 'event=agent.g4.live-runner status=failed phase=checkout-bind-preflight expected=owner-only-runtime-secret actual=permission-failed suggestion=use-a-writable-repository-owned-tmp-root' >&2
    exit 2
}

if ! docker run --rm --network none \
    --mount type=bind,src="${RUNTIME_SECRET_FILE}",dst=/run/secrets/plane_agent_runtime,readonly \
    --entrypoint python3 "${API_IMAGE}" -c '
import os
import stat

metadata = os.stat("/run/secrets/plane_agent_runtime", follow_symlinks=False)
if not stat.S_ISREG(metadata.st_mode):
    raise SystemExit(1)
if stat.S_IMODE(metadata.st_mode) != 0o600:
    raise SystemExit(1)
' >/dev/null 2>&1; then
    printf 'event=agent.g4.live-runner status=failed phase=checkout-bind-preflight expected=checkout-root-docker-bind-visible actual=runtime-secret-bind-unavailable root=%s suggestion=run-from-a-Docker-visible-checkout-under-the-Plane-project-root\n' \
        "${ROOT_DIR}" >&2
    exit 2
fi

if [[ "${SCENARIO_ENABLED}" -eq 1 ]]; then
    LIVE_PHASE=scenario-staging
    if docker volume inspect "${SCENARIO_VOLUME}" >/dev/null 2>&1; then
        printf '%s\n' 'event=agent.g4.live-runner status=failed expected=new-task-owned-scenario-volume actual=volume-name-already-exists suggestion=retry-with-a-fresh-live-run' >&2
        exit 2
    fi
    docker volume create \
        --label com.uxheavy.plane.agent-g4-scenario=true \
        --label "com.uxheavy.plane.agent-g4-project=${PROJECT}" \
        "${SCENARIO_VOLUME}" >/dev/null
    SCENARIO_VOLUME_CREATED=1
    docker run --rm -i --network none \
        --mount type=volume,src="${SCENARIO_VOLUME}",dst=/run/plane-scenario,volume-nocopy \
        --entrypoint python3 "${API_IMAGE}" -c '
import os
import stat
import sys

payload = sys.stdin.buffer.read(131073)
if len(payload) > 131072:
    raise SystemExit(1)
fd = os.open(
    "/run/plane-scenario/descriptor.json",
    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
    0o600,
)
try:
    os.fchmod(fd, 0o600)
    offset = 0
    while offset < len(payload):
        offset += os.write(fd, payload[offset:])
    os.fsync(fd)
finally:
    os.close(fd)
metadata = os.stat("/run/plane-scenario/descriptor.json", follow_symlinks=False)
if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
    raise SystemExit(1)
' <"${SCENARIO_DESCRIPTOR_PATH_INPUT}" >/dev/null 2>&1
    docker run --rm -i --network none \
        --mount type=volume,src="${SCENARIO_VOLUME}",dst=/run/plane-scenario,volume-nocopy \
        --entrypoint python3 "${API_IMAGE}" -c '
import os
import shutil
import stat

destination = "/run/plane-scenario/agent_g4_live_scenario.py"
fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "wb", closefd=False) as output:
        shutil.copyfileobj(os.fdopen(0, "rb", closefd=False), output, 65536)
    os.fsync(fd)
finally:
    os.close(fd)
metadata = os.stat(destination, follow_symlinks=False)
if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
    raise SystemExit(1)
' <"${ROOT_DIR}/tools/agent_g4_live_scenario.py" >/dev/null 2>&1
    docker run --rm --network none \
        --mount type=volume,src="${SCENARIO_VOLUME}",dst=/run/plane-scenario,readonly,volume-nocopy \
        --entrypoint python3 "${API_IMAGE}" -c '
import hashlib
import sys

payload = open("/run/plane-scenario/descriptor.json", "rb").read(131073)
if len(payload) > 131072 or hashlib.sha256(payload).hexdigest() != sys.argv[1]:
    raise SystemExit(1)
' "${SCENARIO_DESCRIPTOR_SHA256}" >/dev/null 2>&1
    docker run --rm -i --network none \
        --mount type=volume,src="${SCENARIO_VOLUME}",dst=/run/plane-scenario,volume-nocopy \
        --entrypoint python3 "${API_IMAGE}" -c '
import os
import shutil
import stat

destination = "/run/plane-scenario/agent_g4_worker_route.py"
fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "wb", closefd=False) as output:
        shutil.copyfileobj(os.fdopen(0, "rb", closefd=False), output, 65536)
    os.fsync(fd)
finally:
    os.close(fd)
metadata = os.stat(destination, follow_symlinks=False)
if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
    raise SystemExit(1)
' <"${ROOT_DIR}/tools/agent_g4_worker_route.py" >/dev/null 2>&1
    docker run --rm -i --network none \
        --mount type=volume,src="${SCENARIO_VOLUME}",dst=/run/plane-scenario,volume-nocopy \
        --entrypoint python3 "${API_IMAGE}" -c '
import os
import shutil
import stat

destination = "/run/plane-scenario/agent_g4_worker_route_observations.py"
fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "wb", closefd=False) as output:
        shutil.copyfileobj(os.fdopen(0, "rb", closefd=False), output, 65536)
    os.fsync(fd)
finally:
    os.close(fd)
metadata = os.stat(destination, follow_symlinks=False)
if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
    raise SystemExit(1)
' <"${ROOT_DIR}/tools/agent_g4_worker_route_observations.py" >/dev/null 2>&1
    docker run --rm -i --network none \
        --mount type=volume,src="${SCENARIO_VOLUME}",dst=/run/plane-scenario,volume-nocopy \
        --entrypoint python3 "${API_IMAGE}" -c '
import os
import shutil
import stat

destination = "/run/plane-scenario/agent_g4_manager_route.py"
fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "wb", closefd=False) as output:
        shutil.copyfileobj(os.fdopen(0, "rb", closefd=False), output, 65536)
    os.fsync(fd)
finally:
    os.close(fd)
metadata = os.stat(destination, follow_symlinks=False)
if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
    raise SystemExit(1)
' <"${ROOT_DIR}/tools/agent_g4_manager_route.py" >/dev/null 2>&1
    SCENARIO_MOUNT_ARGS=(
        --mount
        "type=volume,src=${SCENARIO_VOLUME},dst=/run/plane-scenario,readonly,volume-nocopy"
    )
    SCENARIO_ENV_ARGS=(
        --env
        "G4_SCENARIO_DESCRIPTOR=/run/plane-scenario/descriptor.json"
        --env
        "G4_SCENARIO_SHA256=${SCENARIO_DESCRIPTOR_SHA256}"
        --env
        "PYTHONPATH=/run/plane-scenario:/workspace/apps/api"
    )
fi
LIVE_PHASE=credential-staging
PROVIDER_SECRET_SOURCE="${PLANE_G4_PROVIDER_SECRET_SOURCE:?configured provider source is required}"
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
if docker volume inspect "${PROVIDER_SECRET_VOLUME}" >/dev/null 2>&1; then
    printf '%s\n' 'event=agent.g4.live-runner status=failed expected=new-task-owned-provider-secret-volume actual=volume-name-already-exists suggestion=retry-with-a-fresh-live-run' >&2
    exit 2
fi
docker volume create \
    --label com.uxheavy.plane.agent-g4-provider-secret=true \
    --label "com.uxheavy.plane.agent-g4-project=${PROJECT}" \
    "${PROVIDER_SECRET_VOLUME}" >/dev/null
PROVIDER_SECRET_VOLUME_CREATED=1

docker run --rm -i --network none \
    --mount type=volume,src="${PROVIDER_SECRET_VOLUME}",dst=/run/secrets,volume-nocopy \
    --entrypoint python3 "${API_IMAGE}" -c '
import os
import stat
import sys

MAX_PROVIDER_SECRET_BYTES = 64 * 1024
destination = "/run/secrets/plane_agent_provider_credentials"
payload = sys.stdin.buffer.read(MAX_PROVIDER_SECRET_BYTES + 1)
if len(payload) > MAX_PROVIDER_SECRET_BYTES:
    raise SystemExit(1)

destination_fd = None
try:
    destination_fd = os.open(
        destination,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
    )
    os.fchmod(destination_fd, 0o600)
    view = memoryview(payload)
    while view:
        written = os.write(destination_fd, view)
        if written <= 0:
            raise OSError("provider credential handoff made no progress")
        view = view[written:]
    os.fsync(destination_fd)
finally:
    if destination_fd is not None:
        os.close(destination_fd)

metadata = os.stat("/run/secrets/plane_agent_provider_credentials", follow_symlinks=False)
if not stat.S_ISREG(metadata.st_mode):
    raise SystemExit(1)
if stat.S_IMODE(metadata.st_mode) != 0o600:
    raise SystemExit(1)
if metadata.st_size > 64 * 1024:
    raise SystemExit(1)
' <"${PROVIDER_SECRET_FILE}" >/dev/null 2>&1

LIVE_PHASE=compose

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
    --env PLANE_DB_MIGRATION_MODE=1 \
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

# The runtime image is a separate process boundary. Prove its service and the
# narrow Plane-owned Code Mode wire contract import before paying the startup
# wait; classify only the finite import error class so an image omission cannot
# become an opaque generic runtime-health failure.
LIVE_PHASE=runtime-start
if ! docker run --rm --network none --read-only --user 65532:65532 --entrypoint python3 "${RUNTIME_IMAGE}" \
    -c 'import plane.agent.runtime.service; import plane.agent.code_mode.contracts; import plane_runtime.g1_runtime_image.bootstrap' \
    2>&1 | python3 -c '
import sys

payload = sys.stdin.buffer.read(8193)
if len(payload) > 8192:
    payload = payload[:8192]
if b"ModuleNotFoundError" in payload or b"No module named" in payload:
    sys.stdout.write("ModuleNotFoundError\\n")
elif b"ImportError" in payload:
    sys.stdout.write("ImportError\\n")
else:
    sys.stdout.write("RuntimeError\\n")
' >"${ERROR_FILE}"; then
    printf '%s\n' 'event=agent.g4.live-runner status=failed phase=runtime-start expected=runtime-image-service-imports actual=runtime-image-import-unavailable suggestion=refreeze-runtime-with-the-plane-code-mode-contracts' >&2
    exit 1
fi

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
docker run --rm -i --network "${NETWORK}" --hostname api --network-alias api \
    "${SCENARIO_MOUNT_ARGS[@]}" \
    --mount type=bind,src="${RUNTIME_SECRET_FILE}",dst=/run/plane-agent-runtime-secret,readonly \
    --mount type=volume,src="${CREDENTIAL_STATE_VOLUME}",dst="${CREDENTIAL_STATE_TARGET}",volume-nocopy \
    --mount type=volume,src="${PROVIDER_SECRET_VOLUME}",dst=/run/secrets,readonly,volume-nocopy \
    --env DJANGO_SETTINGS_MODULE=plane.settings.production \
    --env PYTHONUNBUFFERED=1 \
    --env SECRET_KEY="${PLANE_TEST_SECRET}" \
    --env APP_BASE_URL=http://api:8000 \
    --env WEB_URL=http://api:8000 \
    --env DATABASE_URL=postgresql://plane:plane@test-db:5432/plane \
    --env DATABASE_RUNTIME_URL=postgresql://plane:plane@test-db:5432/plane \
    --env REDIS_HOST=test-redis \
    --env REDIS_URL=redis://test-redis:6379/ \
    --env RABBITMQ_HOST=test-mq \
    --env AMQP_URL=amqp://plane:plane@test-mq:5672/plane \
    --env PLANE_AGENT_RUNTIME_URL=http://agent-runtime:8080 \
    --env PLANE_AGENT_RUNTIME_HOST_URL=http://api:8091 \
    --env PLANE_AGENT_RUNTIME_HOST_BIND=0.0.0.0 \
    --env PLANE_AGENT_RUNTIME_HOST_PORT=8091 \
    --env PLANE_AGENT_RUNTIME_DISPATCH_PATH=/v1/runtime/dispatch \
    --env PLANE_AGENT_RUNTIME_SECRET_FILE=/run/plane-agent-runtime-secret \
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
    --env G4_PROVIDER_RELAY_JSON="${G4_PROVIDER_RELAY_JSON}" \
    --env G4_AUTHORITY_ID="${G4_AUTHORITY_ID}" \
    --env G4_PERMITTED_CANARY="${G4_PERMITTED_CANARY}" \
    --env G4_DENIED_CANARY="${G4_DENIED_CANARY}" \
    "${SCENARIO_ENV_ARGS[@]}" \
    "${API_IMAGE}" python - <"${LIVE_INVOKE_SOURCE}" >"${EVIDENCE_FILE}" 2>"${ERROR_FILE}"

test -s "${EVIDENCE_FILE}"
