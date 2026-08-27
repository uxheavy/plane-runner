# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from __future__ import annotations

import hashlib
import os
import shlex
import signal
import subprocess
import time
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
SUPPORT = TOOLS / "agent-g4-live-support.sh"


def _environment(path: Path, overrides: dict[str, str] | None = None) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "PLANE_G4_LIVE_CAPACITY_LEASE_PATH": str(path),
            "PLANE_G4_LIVE_CAPACITY_LEASE_TIMEOUT_SECONDS": "3",
            "PLANE_G4_LIVE_CAPACITY_LEASE_POLL_SECONDS": "0.02",
        }
    )
    if overrides:
        environment.update(overrides)
    return environment


def start_support(path: Path, body: str, *, overrides: dict[str, str] | None = None) -> subprocess.Popen[str]:
    return subprocess.Popen(
        ["bash", "-c", f'source "{SUPPORT}"\nlive_capacity_lease_start_evidence() {{ printf test-start; }}\n{body}'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_environment(path, overrides),
        start_new_session=True,
    )


def stop_support(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate(timeout=2)


def run_support(
    path: Path,
    body: str,
    *,
    timeout: float = 5,
    overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    process = start_support(path, body, overrides=overrides)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        stop_support(process)
        raise
    return subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)


@pytest.fixture
def spawned_processes():
    processes: list[subprocess.Popen[str]] = []

    def spawn(path: Path, body: str) -> subprocess.Popen[str]:
        process = start_support(path, body)
        processes.append(process)
        return process

    yield spawn
    for process in processes:
        stop_support(process)


def wait_for(path: Path, timeout: float = 2) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for {path}")


def test_concurrent_waiters_enter_one_at_a_time(tmp_path: Path, spawned_processes) -> None:
    lease = tmp_path / "lease"
    log = tmp_path / "entries.log"
    holder = spawned_processes(
        lease,
        f"""
trap 'live_capacity_lease_release' EXIT
live_capacity_lease_acquire
printf '%s\\n' holder-enter >> '{log}'
sleep 0.45
printf '%s\\n' holder-exit >> '{log}'
""",
    )
    wait_for(lease)
    wait_for(lease / "owner")
    waiters = [
        spawned_processes(
            lease,
            f"""
live_capacity_lease_acquire
printf '%s\\n' waiter-{index}-enter >> '{log}'
sleep 0.08
printf '%s\\n' waiter-{index}-exit >> '{log}'
live_capacity_lease_release
""",
        )
        for index in (1, 2)
    ]

    holder_stdout, holder_stderr = holder.communicate(timeout=3)
    waiter_results = [waiter.communicate(timeout=3) for waiter in waiters]
    assert holder.returncode == 0, holder_stdout + holder_stderr
    assert all(waiter.returncode == 0 for waiter in waiters), waiter_results
    entries = log.read_text(encoding="utf-8").splitlines()
    assert entries[0:2] == ["holder-enter", "holder-exit"]
    assert entries[2:] in (
        ["waiter-1-enter", "waiter-1-exit", "waiter-2-enter", "waiter-2-exit"],
        ["waiter-2-enter", "waiter-2-exit", "waiter-1-enter", "waiter-1-exit"],
    )
    assert not lease.exists()


def test_waiter_timeout_does_not_enter_or_emit_a_provider_attempt(tmp_path: Path, spawned_processes) -> None:
    lease = tmp_path / "lease"
    entered = tmp_path / "entered"
    holder = spawned_processes(
        lease,
        """
trap 'live_capacity_lease_release' EXIT
live_capacity_lease_acquire
sleep 0.5
""",
    )
    wait_for(lease / "owner")
    contender = run_support(
        lease,
        f'live_capacity_lease_acquire; status=$?; if [[ $status -eq 0 ]]; then printf entered > "{entered}"; fi; exit $status',
        overrides={
            "PLANE_G4_LIVE_CAPACITY_LEASE_TIMEOUT_SECONDS": "0",
            "PLANE_G4_LIVE_CAPACITY_LEASE_POLL_SECONDS": "0.01",
        },
    )
    holder.communicate(timeout=3)
    assert contender.returncode == 75, contender.stderr
    assert "capacity_lease_timeout" in contender.stderr
    assert not entered.exists()
    assert not lease.exists()


def test_dead_pid_owner_is_recovered(tmp_path: Path) -> None:
    lease = tmp_path / "lease"
    lease.mkdir(mode=0o700)
    owner = lease / "owner"
    owner.write_text("version=1\npid=9999999999\nstart=Mon Jan 1 00:00:00 2000\n", encoding="utf-8")
    owner.chmod(0o600)

    result = run_support(
        lease,
        "live_capacity_lease_acquire\nlive_capacity_lease_release",
    )
    assert result.returncode == 0, result.stderr
    assert not lease.exists()


def test_missing_ignored_capacity_parent_is_created(tmp_path: Path) -> None:
    lease = tmp_path / "ignored-tmp" / "lease"

    result = run_support(lease, "live_capacity_lease_acquire\nlive_capacity_lease_release")

    assert result.returncode == 0, result.stderr
    assert lease.parent.is_dir()
    assert not lease.exists()


def test_timeout_can_reenter_after_holder_releases(tmp_path: Path, spawned_processes) -> None:
    lease = tmp_path / "lease"
    holder = spawned_processes(
        lease,
        "trap 'live_capacity_lease_release' EXIT\nlive_capacity_lease_acquire\nsleep 0.25",
    )
    wait_for(lease / "owner")
    result = run_support(
        lease,
        "live_capacity_lease_acquire || first=$?\n"
        "[[ ${first:-0} -eq 75 ]] || exit 91\n"
        "sleep 0.35\n"
        "live_capacity_lease_acquire\n"
        "live_capacity_lease_release",
        overrides={
            "PLANE_G4_LIVE_CAPACITY_LEASE_TIMEOUT_SECONDS": "0",
            "PLANE_G4_LIVE_CAPACITY_LEASE_POLL_SECONDS": "0.01",
        },
    )
    holder.communicate(timeout=3)

    assert result.returncode == 0, result.stderr
    assert "capacity_lease_timeout" in result.stderr
    assert not lease.exists()


def test_release_runs_on_failure_and_signal(tmp_path: Path, spawned_processes) -> None:
    failure_lease = tmp_path / "failure-lease"
    failed = run_support(
        failure_lease,
        "trap 'live_capacity_lease_release' EXIT\nlive_capacity_lease_acquire\nexit 23",
    )
    assert failed.returncode == 23
    assert not failure_lease.exists()

    signal_lease = tmp_path / "signal-lease"
    ready = tmp_path / "signal-ready"
    signaled = spawned_processes(
        signal_lease,
        f"""
trap 'live_capacity_lease_release; exit 143' TERM INT
trap 'live_capacity_lease_release' EXIT
live_capacity_lease_acquire
printf ready > '{ready}'
while :; do sleep 1; done
""",
    )
    wait_for(ready)
    os.killpg(signaled.pid, signal.SIGTERM)
    signaled.communicate(timeout=3)
    assert not signal_lease.exists()


def test_owner_metadata_is_bounded_and_contains_only_pid_start_evidence(tmp_path: Path) -> None:
    lease = tmp_path / "lease"
    result = run_support(
        lease,
        "live_capacity_lease_acquire\nwc -c < \"${LIVE_CAPACITY_LEASE_PATH}/owner\"\ncat \"${LIVE_CAPACITY_LEASE_PATH}/owner\"\nlive_capacity_lease_release",
    )
    assert result.returncode == 0, result.stderr
    assert int(result.stdout.splitlines()[0]) <= 256
    assert "pid=" in result.stdout
    assert "start=" in result.stdout


def test_bounded_stderr_digest_is_stable_and_redacts_secrets(tmp_path: Path) -> None:
    raw_stderr = "RuntimeError provider_token=must-not-persist https://provider.invalid/path\n"
    expected_digest = hashlib.sha256(raw_stderr.encode()).hexdigest()
    outputs = []
    for index in (1, 2):
        error_file = tmp_path / f"error-{index}.log"
        digest_file = tmp_path / f"digest-{index}.sha256"
        command = f"printf %s {shlex.quote(raw_stderr)} >&2; exit 23"
        result = run_support(
            tmp_path / f"lease-{index}",
            f'live_run_bounded_stderr "{error_file}" "{digest_file}" bash -c {shlex.quote(command)}; status=$?; printf "status=%s\\n" "$status"; cat "{error_file}"; cat "{digest_file}"',
        )
        assert result.returncode == 0, result.stderr
        assert "status=23" in result.stdout
        assert result.stdout.strip().splitlines()[-1] == expected_digest
        assert error_file.read_text(encoding="utf-8") == (
            "error_class=RuntimeError\nreason_category=docker_precontainer_failure\n"
            "missing_path_class=unclassified\nchild_phase=unknown\n"
        )
        outputs.append(result.stdout)

    assert outputs[0] == outputs[1]
    assert raw_stderr not in outputs[0]


def test_bounded_stderr_retains_only_a_valid_missing_module_identifier(tmp_path: Path) -> None:
    error_file = tmp_path / "error.log"
    digest_file = tmp_path / "digest.sha256"
    raw_stderr = (
        "Traceback (most recent call last):\n"
        "ModuleNotFoundError: No module named 'plane_runtime.bridge_v2'\n"
        "provider_token=must-not-persist\n"
    )
    command = f"printf %s {shlex.quote(raw_stderr)} >&2; exit 1"
    result = run_support(
        tmp_path / "lease",
        f'live_run_bounded_stderr "{error_file}" "{digest_file}" bash -c {shlex.quote(command)}; cat "{error_file}"',
    )
    assert result.returncode == 0, result.stderr
    assert error_file.read_text(encoding="ascii") == (
        "error_class=ModuleNotFoundError\n"
        "reason_category=docker_precontainer_failure\n"
        "missing_path_class=unclassified\n"
        "child_phase=unknown\n"
        "missing_module=plane_runtime.bridge_v2\n"
    )
    assert "must-not-persist" not in result.stdout


def test_bounded_stderr_classifies_runtime_contract_failure_without_provider_details(tmp_path: Path) -> None:
    error_file = tmp_path / "error.log"
    digest_file = tmp_path / "digest.sha256"
    raw_stderr = "RuntimeContractError: /run/secrets/provider-token provider_token=must-not-persist\n"
    command = f"printf %s {shlex.quote(raw_stderr)} >&2; exit 125"
    result = run_support(
        tmp_path / "lease",
        f'live_run_bounded_stderr "{error_file}" "{digest_file}" bash -c {shlex.quote(command)}; cat "{error_file}"',
    )
    assert result.returncode == 0, result.stderr
    bounded = error_file.read_text(encoding="ascii")
    assert "error_class=RuntimeContractError\n" in bounded
    assert "reason_category=runtime_contract_failure\n" in bounded
    assert "/run/secrets/provider-token" not in result.stdout
    assert "provider_token=must-not-persist" not in result.stdout


@pytest.mark.parametrize(
    ("marker", "missing_path_class", "child_phase"),
    (
        ("FileNotFoundError: [Errno 2] No such file: /run/plane-scenario/agent_g4_manager_route.py", "scenario_module_artifact", "scenario_import"),
        ("ModuleNotFoundError: No module named 'agent_g4_manager_route'", "scenario_module_artifact", "scenario_import"),
        ("FileNotFoundError: [Errno 2] No such file: plane_runtime.g1_runtime_image.bootstrap", "runtime_executable", "runtime_start"),
        ("FileNotFoundError: [Errno 2] No such file: /run/secrets/plane_agent_provider_credentials", "secret_mount", "secret_bind"),
        ("FileNotFoundError: [Errno 2] No such file: /workspace/apps/api/manage.py", "api_startup", "api_startup"),
        ("FileNotFoundError: [Errno 2] No such file: /tmp/child-worker", "unclassified", "unknown"),
    ),
)
def test_bounded_stderr_classifies_only_allowlisted_missing_boundaries(
    tmp_path: Path, marker: str, missing_path_class: str, child_phase: str
) -> None:
    error_file = tmp_path / "error.log"
    digest_file = tmp_path / "digest.sha256"
    command = f"printf %s {shlex.quote(marker)} >&2; exit 1"
    result = run_support(
        tmp_path / "lease",
        f'live_run_bounded_stderr "{error_file}" "{digest_file}" bash -c {shlex.quote(command)}',
    )
    assert result.returncode == 1
    bounded = error_file.read_text(encoding="ascii")
    assert f"missing_path_class={missing_path_class}\n" in bounded
    assert f"child_phase={child_phase}\n" in bounded
    assert marker not in bounded


def test_bounded_stderr_keeps_boundary_projection_free_of_paths_and_secrets(tmp_path: Path) -> None:
    error_file = tmp_path / "error.log"
    digest_file = tmp_path / "digest.sha256"
    raw_stderr = "FileNotFoundError: /run/secrets/provider-token provider_token=do-not-retain\n"
    command = f"printf %s {shlex.quote(raw_stderr)} >&2; exit 1"
    result = run_support(
        tmp_path / "lease",
        f'live_run_bounded_stderr "{error_file}" "{digest_file}" bash -c {shlex.quote(command)}; cat "{error_file}"',
    )
    assert result.returncode == 0, result.stderr
    assert "missing_path_class=secret_mount" in result.stdout
    assert "/run/secrets/provider-token" not in result.stdout
    assert "do-not-retain" not in result.stdout


def test_bounded_stderr_extracts_only_validated_setup_error_marker(tmp_path: Path) -> None:
    marker = (
        'event=agent.g4.live.setup-failure/v1 '
        'setupError={"id":"setup:lineage:IntegrityError","stage":"lineage",'
        '"errorClass":"IntegrityError","counters":{"actors":5,"profiles":5,'
        '"assignments":1,"lineageAssignments":0,"schedules":0,"scheduleFires":0}}\n'
    )
    error_file = tmp_path / "error.log"
    digest_file = tmp_path / "digest.sha256"
    command = f"printf %s {shlex.quote(marker)} >&2; exit 1"
    result = run_support(
        tmp_path / "lease",
        f'live_run_bounded_stderr "{error_file}" "{digest_file}" bash -c {shlex.quote(command)}; cat "{error_file}"',
    )
    assert result.returncode == 0, result.stderr
    assert (
        'setup_error={"counters":{"actors":5,"assignments":1,"lineageAssignments":0,'
        '"profiles":5,"scheduleFires":0,"schedules":0},"errorClass":"IntegrityError",'
        '"id":"setup:lineage:IntegrityError","stage":"lineage"}'
    ) in result.stdout
    assert "private/secret" not in result.stdout


def test_bounded_stderr_discards_malformed_setup_error_marker(tmp_path: Path) -> None:
    marker = 'event=agent.g4.live.setup-failure/v1 setupError={"id":"setup:lineage:/secret"}\n'
    error_file = tmp_path / "error.log"
    digest_file = tmp_path / "digest.sha256"
    command = f"printf %s {shlex.quote(marker)} >&2; exit 1"
    result = run_support(
        tmp_path / "lease",
        f'live_run_bounded_stderr "{error_file}" "{digest_file}" bash -c {shlex.quote(command)}; cat "{error_file}"',
    )
    assert result.returncode == 0, result.stderr
    assert "setup_error=" not in result.stdout
