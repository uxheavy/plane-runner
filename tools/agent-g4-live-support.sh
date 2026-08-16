#!/usr/bin/env bash

LIVE_CAPACITY_LEASE_PATH="${PLANE_G4_LIVE_CAPACITY_LEASE_PATH:-${SHARED_REPOSITORY_ROOT:?shared repository root is required}/tmp/plane-agent-g4-live-capacity}"
LIVE_CAPACITY_LEASE_TIMEOUT_SECONDS="${PLANE_G4_LIVE_CAPACITY_LEASE_TIMEOUT_SECONDS:-180}"
LIVE_CAPACITY_LEASE_POLL_SECONDS="${PLANE_G4_LIVE_CAPACITY_LEASE_POLL_SECONDS:-1}"
LIVE_CAPACITY_LEASE_HELD="${LIVE_CAPACITY_LEASE_HELD:-0}"
LIVE_CAPACITY_LEASE_OWNER_METADATA="${LIVE_CAPACITY_LEASE_OWNER_METADATA:-}"
LIVE_CAPACITY_LEASE_HELD_METADATA="${LIVE_CAPACITY_LEASE_HELD_METADATA:-}"

live_capacity_lease_start_evidence() {
    local pid="$1"
    local evidence
    evidence="$(ps -p "${pid}" -o lstart= 2>/dev/null | awk '{$1=$1; print}' | cut -c1-80)" || return 1
    [[ "${evidence}" =~ ^[[:alnum:]][[:alnum:][:space:]:+.-]{0,79}$ ]] || return 1
    printf '%s' "${evidence}"
}

live_capacity_lease_read_owner() {
    local owner_file="${LIVE_CAPACITY_LEASE_PATH}/owner"
    local owner_bytes metadata line version= pid= start= line_count=0
    [[ -f "${owner_file}" && ! -L "${owner_file}" ]] || return 1
    owner_bytes="$(wc -c <"${owner_file}" 2>/dev/null)" || return 1
    owner_bytes="${owner_bytes//[[:space:]]/}"
    [[ "${owner_bytes}" =~ ^[0-9]+$ && "${owner_bytes}" -le 256 ]] || return 1
    if ! metadata="$(<"${owner_file}")"; then
        return 1
    fi
    while IFS= read -r line; do
        ((line_count += 1))
        case "${line}" in
            version=1) version=1 ;;
            pid=*) pid="${line#pid=}" ;;
            start=*) start="${line#start=}" ;;
            *) return 1 ;;
        esac
    done <<<"${metadata}"
    [[ "${line_count}" -eq 3 && "${version}" == 1 ]] || return 1
    [[ "${pid}" =~ ^[1-9][0-9]{0,9}$ && -n "${start}" ]] || return 1
    LIVE_CAPACITY_LEASE_OWNER_METADATA="${metadata}"
    LIVE_CAPACITY_LEASE_OWNER_PID="${pid}"
    LIVE_CAPACITY_LEASE_OWNER_START="${start}"
}

live_capacity_lease_owner_is_live() {
    local pid="$1"
    local expected_start="$2"
    local actual_start
    kill -0 "${pid}" 2>/dev/null || return 1
    actual_start="$(live_capacity_lease_start_evidence "${pid}")" || return 1
    [[ "${actual_start}" == "${expected_start}" ]]
}

live_capacity_lease_recover_stale() {
    local expected_metadata="$1"
    local quarantine_path current_metadata
    live_capacity_lease_read_owner || return 1
    current_metadata="${LIVE_CAPACITY_LEASE_OWNER_METADATA}"
    [[ "${current_metadata}" == "${expected_metadata}" ]] || return 1
    quarantine_path="${LIVE_CAPACITY_LEASE_PATH}.stale-$$-${RANDOM}"
    mv -- "${LIVE_CAPACITY_LEASE_PATH}" "${quarantine_path}" 2>/dev/null || return 1
    rm -f -- "${quarantine_path}/owner" || return 1
    rmdir -- "${quarantine_path}" || return 1
}

live_capacity_lease_acquire() {
    local parent_path="${LIVE_CAPACITY_LEASE_PATH%/*}"
    local timeout_seconds="${LIVE_CAPACITY_LEASE_TIMEOUT_SECONDS}"
    local poll_seconds="${LIVE_CAPACITY_LEASE_POLL_SECONDS}"
    local deadline owner_metadata owner_start owner_file
    [[ -n "${parent_path}" ]] || parent_path=/
    [[ "${LIVE_CAPACITY_LEASE_PATH}" == /* && "${LIVE_CAPACITY_LEASE_PATH}" != / ]] || return 2
    [[ -d "${parent_path}" && ! -L "${parent_path}" ]] || return 2
    [[ "${timeout_seconds}" =~ ^[0-9]+$ && "${timeout_seconds}" -le 900 ]] || return 2
    [[ "${poll_seconds}" =~ ^[0-9]+([.][0-9]+)?$ ]] || return 2
    awk -v value="${poll_seconds}" 'BEGIN { exit !(value <= 60) }' || return 2
    [[ "${LIVE_CAPACITY_LEASE_HELD}" -eq 0 ]] && : || return 0

    deadline=$((SECONDS + timeout_seconds))
    while :; do
        [[ ! -L "${LIVE_CAPACITY_LEASE_PATH}" ]] || return 2
        if mkdir -m 700 -- "${LIVE_CAPACITY_LEASE_PATH}" 2>/dev/null; then
            owner_file="${LIVE_CAPACITY_LEASE_PATH}/owner"
            owner_start="$(live_capacity_lease_start_evidence "$$")" || {
                rmdir -- "${LIVE_CAPACITY_LEASE_PATH}" || true
                return 2
            }
            owner_metadata="version=1
pid=$$
start=${owner_start}"
            if ! (umask 077; set -C; printf '%s\n' "${owner_metadata}" >"${owner_file}") 2>/dev/null; then
                rm -f -- "${owner_file}" || true
                rmdir -- "${LIVE_CAPACITY_LEASE_PATH}" || true
                return 2
            fi
            chmod 600 "${owner_file}" || {
                rm -f -- "${owner_file}" || true
                rmdir -- "${LIVE_CAPACITY_LEASE_PATH}" || true
                return 2
            }
            LIVE_CAPACITY_LEASE_HELD=1
            LIVE_CAPACITY_LEASE_HELD_METADATA="${owner_metadata}"
            return 0
        fi

        [[ -d "${LIVE_CAPACITY_LEASE_PATH}" ]] || return 2
        if live_capacity_lease_read_owner; then
            owner_metadata="${LIVE_CAPACITY_LEASE_OWNER_METADATA}"
            if ! live_capacity_lease_owner_is_live "${LIVE_CAPACITY_LEASE_OWNER_PID}" "${LIVE_CAPACITY_LEASE_OWNER_START}"; then
                live_capacity_lease_recover_stale "${owner_metadata}" || true
                continue
            fi
        fi
        if ((SECONDS >= deadline)); then
            printf '%s\n' 'event=agent.g4.live-capacity status=waiting-timeout expected=one-heavy-live-journey actual=capacity_lease_timeout suggestion=wait-for-the-active-journey-to-finish' >&2
            return 75
        fi
        sleep "${poll_seconds}" || return 2
    done
}

live_capacity_lease_release() {
    local owner_file="${LIVE_CAPACITY_LEASE_PATH}/owner"
    [[ "${LIVE_CAPACITY_LEASE_HELD}" -eq 1 ]] || return 0
    live_capacity_lease_read_owner || return 1
    [[ "${LIVE_CAPACITY_LEASE_OWNER_METADATA}" == "${LIVE_CAPACITY_LEASE_HELD_METADATA}" ]] || return 1
    rm -f -- "${owner_file}" || return 1
    rmdir -- "${LIVE_CAPACITY_LEASE_PATH}" || return 1
    LIVE_CAPACITY_LEASE_HELD=0
    LIVE_CAPACITY_LEASE_OWNER_METADATA=
    LIVE_CAPACITY_LEASE_HELD_METADATA=
}

live_capture_stderr() {
    local error_file="$1"
    local digest_file="$2"
    python3 -c "$(cat <<'PY'
from __future__ import annotations

import hashlib
import os
import stat
import sys

MAX_SAMPLE_BYTES = 8192
ERROR_CLASSES = (
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
DOCKER_REASONS = {
    "docker_mount_target_read_only",
    "docker_mount_invalid",
    "docker_mount_source_unavailable",
    "docker_mount_permission_denied",
    "docker_network_configuration_invalid",
    "docker_image_unavailable",
    "docker_container_start_failed",
    "docker_precontainer_failure",
}


def write_owner_only(path: str, payload: bytes) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
    )
    try:
        os.fchmod(descriptor, 0o600)
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    metadata = os.stat(path, follow_symlinks=False)
    if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
        raise SystemExit(2)


digest = hashlib.sha256()
sample = bytearray()
while True:
    chunk = sys.stdin.buffer.read(65536)
    if not chunk:
        break
    digest.update(chunk)
    if len(sample) < MAX_SAMPLE_BYTES:
        sample.extend(chunk[: MAX_SAMPLE_BYTES - len(sample)])

text = bytes(sample).decode("utf-8", errors="replace")
error_class = next((name for name in ERROR_CLASSES if name in text), "unspecified")
lowered = text.lower()
if "read-only file system" in lowered and ("mountpoint" in lowered or "mount" in lowered):
    reason = "docker_mount_target_read_only"
elif "invalid mount config" in lowered or "invalid mount specification" in lowered:
    reason = "docker_mount_invalid"
elif "bind source path does not exist" in lowered or (
    "no such file or directory" in lowered and ("mount" in lowered or "bind" in lowered)
):
    reason = "docker_mount_source_unavailable"
elif "permission denied" in lowered and ("mount" in lowered or "bind" in lowered):
    reason = "docker_mount_permission_denied"
elif "network-scoped aliases" in lowered or "network is not connected" in lowered:
    reason = "docker_network_configuration_invalid"
elif "unable to find image" in lowered or "pull access denied" in lowered:
    reason = "docker_image_unavailable"
elif "failed to create task" in lowered or "oci runtime" in lowered:
    reason = "docker_container_start_failed"
else:
    reason = "docker_precontainer_failure"

if reason not in DOCKER_REASONS:
    raise SystemExit(2)
write_owner_only(
    sys.argv[1],
    f"error_class={error_class}\nreason_category={reason}\n".encode("ascii"),
)
write_owner_only(sys.argv[2], f"{digest.hexdigest()}\n".encode("ascii"))
PY
)" "${error_file}" "${digest_file}"
}

live_run_bounded_stderr() {
    local error_file="$1"
    local digest_file="$2"
    local fifo_path="${error_file}.fifo-$$-${RANDOM}"
    local command_status=0
    local capture_status=0
    shift 2
    (umask 077; mkfifo "${fifo_path}") || return 2
    live_capture_stderr "${error_file}" "${digest_file}" <"${fifo_path}" &
    local capture_pid=$!
    "${@}" 2>"${fifo_path}" || command_status=$?
    wait "${capture_pid}" || capture_status=$?
    rm -f -- "${fifo_path}"
    if [[ "${command_status}" -eq 0 && "${capture_status}" -ne 0 ]]; then
        return 70
    fi
    return "${command_status}"
}

live_stderr_sha256() {
    local digest_file="$1"
    local digest_value
    if [[ -f "${digest_file}" && ! -L "${digest_file}" ]]; then
        digest_value="$(<"${digest_file}")"
        if [[ "${digest_value}" =~ ^[0-9a-f]{64}$ ]]; then
            printf '%s' "${digest_value}"
            return 0
        fi
    fi
    printf '%s' e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
}
