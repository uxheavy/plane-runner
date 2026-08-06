from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

from plane.agent.code_mode.contracts import SandboxPolicy
from plane.agent.runtime import (
    AgentRuntimeConfiguration,
    CredentialLease,
    RuntimeConfigurationError,
    RuntimeCredentialBroker,
    RuntimeCredentialError,
    RuntimeHealthStatus,
    RuntimeProcessPolicy,
    RuntimeSafetyController,
    RuntimeSafetyStopError,
)
from plane.agent.runtime.service import _RuntimeHTTPServer


def _runtime_environment(**overrides: str) -> dict[str, str]:
    environment = {
        "PLANE_AGENT_RUNTIME_URL": "http://agent-runtime:8080",
        "PLANE_AGENT_RUNTIME_SECRET": "r" * 40,
    }
    environment.update(overrides)
    return environment


def test_g4_runtime_configuration_fails_closed_for_missing_invalid_and_placeholder_values():
    with pytest.raises(RuntimeConfigurationError, match="PLANE_AGENT_RUNTIME_URL"):
        AgentRuntimeConfiguration.from_environment({"PLANE_AGENT_RUNTIME_SECRET": "r" * 40})
    with pytest.raises(RuntimeConfigurationError, match="absolute HTTP"):
        AgentRuntimeConfiguration.from_environment(_runtime_environment(PLANE_AGENT_RUNTIME_URL="agent-runtime:8080"))
    with pytest.raises(RuntimeConfigurationError, match="at least 32"):
        AgentRuntimeConfiguration.from_environment(_runtime_environment(PLANE_AGENT_RUNTIME_SECRET="too-short"))
    with pytest.raises(RuntimeConfigurationError):
        AgentRuntimeConfiguration.from_environment(
            _runtime_environment(PLANE_AGENT_RUNTIME_SECRET="change-this-runtime-password")
        )
    with pytest.raises(RuntimeConfigurationError, match="network policy"):
        AgentRuntimeConfiguration.from_environment(_runtime_environment(PLANE_AGENT_RUNTIME_NETWORK_POLICY="internet"))


def test_g4_runtime_configuration_rejects_credential_shaped_child_environment_and_duplicate_json_keys():
    with pytest.raises(RuntimeConfigurationError, match="credential-shaped"):
        AgentRuntimeConfiguration.from_environment(
            _runtime_environment(PLANE_AGENT_RUNTIME_ENVIRONMENT_JSON='{"AWS_SECRET_ACCESS_KEY":"x"}')
        )
    with pytest.raises(RuntimeConfigurationError, match="JSON object"):
        AgentRuntimeConfiguration.from_environment(
            _runtime_environment(PLANE_AGENT_RUNTIME_ENVIRONMENT_JSON='{"PATH":"/bin","PATH":"/usr/bin"}')
        )


def test_g4_runtime_configuration_reads_a_single_line_secret_file_without_accepting_both_sources(tmp_path):
    secret_path = tmp_path / "runtime-secret"
    secret_path.write_text("f" * 40, encoding="utf-8")
    environment = _runtime_environment(
        PLANE_AGENT_RUNTIME_SECRET="",
        PLANE_AGENT_RUNTIME_SECRET_FILE=str(secret_path),
    )
    assert AgentRuntimeConfiguration.from_environment(environment).shared_secret == "f" * 40
    with pytest.raises(RuntimeConfigurationError, match="mutually exclusive"):
        AgentRuntimeConfiguration.from_environment(
            _runtime_environment(PLANE_AGENT_RUNTIME_SECRET_FILE=str(secret_path))
        )
    secret_path.write_text("f" * 40 + "\n", encoding="utf-8")
    with pytest.raises(RuntimeConfigurationError, match="one secret line"):
        AgentRuntimeConfiguration.from_environment(
            {
                "PLANE_AGENT_RUNTIME_URL": "http://agent-runtime:8080",
                "PLANE_AGENT_RUNTIME_SECRET_FILE": str(secret_path),
            }
        )


def test_g4_runtime_safety_controller_has_stable_readback_and_one_way_stop(tmp_path):
    controller = RuntimeSafetyController(configured=True, stop_file=tmp_path / "safety-stop")
    assert controller.health().status == "configured"
    ready = controller.mark_ready()
    assert isinstance(ready, RuntimeHealthStatus)
    assert ready.status == "ready"
    assert ready.as_dict() == {
        "protocol": "plane.agent-runtime/v1",
        "status": "ready",
        "configured": True,
        "ready": True,
        "draining": False,
        "stopped": False,
        "dependencyOk": True,
        "safetyStop": False,
        "activeInvocations": 0,
        "reason": None,
    }
    active = controller.begin_invocation()
    assert active.active_invocations == 1
    draining = controller.request_safety_stop("local incident")
    assert draining.status == "draining"
    assert draining.safety_stop is True
    with pytest.raises(RuntimeSafetyStopError):
        controller.begin_invocation()
    assert controller.finish_invocation().active_invocations == 0
    assert controller.mark_stopped("replacement requested").status == "stopped"
    assert controller.health().safety_stop is True


def test_g4_runtime_operator_adapters_forward_only_the_owner_snapshot(tmp_path):
    controller = RuntimeSafetyController(configured=True, stop_file=tmp_path / "safety-stop")
    controller.mark_ready()
    assert controller.health().as_dict()["status"] == "ready"
    stopped = controller.request_safety_stop("operator test").as_dict()
    assert stopped["status"] == "draining"
    assert stopped["safetyStop"] is True


def test_g4_runtime_safety_controller_reports_dependency_failure_without_claiming_ready(tmp_path):
    dependency = {"ok": False}
    controller = RuntimeSafetyController(
        configured=True,
        stop_file=tmp_path / "safety-stop",
        dependency_probe=lambda: dependency["ok"],
    )
    assert controller.mark_ready().status == "dependency_failure"
    with pytest.raises(RuntimeSafetyStopError):
        controller.begin_invocation()
    dependency["ok"] = True
    assert controller.mark_ready().status == "ready"


def test_g4_runtime_credential_lease_issuance_binding_revocation_and_rotation():
    source = {"provider": {"TOKEN": "disposable-token-1"}}
    broker = RuntimeCredentialBroker(source, ttl_seconds=60, clock=lambda: 100.0)
    lease, credentials = broker.issue(agent_ref="agent-1", credential_ref="provider")
    assert credentials == {"TOKEN": "disposable-token-1"}
    assert isinstance(lease, CredentialLease)
    assert "disposable-token-1" not in repr(lease)
    bound = broker.bind(lease.lease_id, invocation_ref="invocation-1")
    assert broker.resolve(lease.lease_id, agent_ref="agent-1", invocation_ref="invocation-1") == credentials
    with pytest.raises(RuntimeCredentialError, match="binding"):
        broker.resolve(lease.lease_id, agent_ref="agent-2", invocation_ref="invocation-1")
    revoked = broker.revoke(lease.lease_id)
    assert revoked.revoked_at == 100.0
    with pytest.raises(RuntimeCredentialError, match="revoked"):
        broker.resolve(bound.lease_id, agent_ref="agent-1", invocation_ref="invocation-1")

    next_lease, _ = broker.issue(agent_ref="agent-1", credential_ref="provider", invocation_ref="invocation-2")
    source["provider"] = {"TOKEN": "disposable-token-2"}
    with pytest.raises(RuntimeCredentialError, match="rotated"):
        broker.resolve(next_lease.lease_id, agent_ref="agent-1", invocation_ref="invocation-2")
    generation = broker.rotate("provider")
    assert generation == 3
    with pytest.raises(RuntimeCredentialError, match="revoked"):
        broker.resolve(next_lease.lease_id, agent_ref="agent-1", invocation_ref="invocation-2")


def test_g4_runtime_process_and_code_mode_policies_are_finite_and_networkless():
    process_policy = RuntimeProcessPolicy()
    sandbox = SandboxPolicy()
    assert process_policy.network == "none"
    assert process_policy.cpu_seconds > 0
    assert process_policy.memory_bytes > 0
    assert process_policy.pids_limit > 0
    assert sandbox.network == "none"
    assert sandbox.filesystem == "none"
    assert sandbox.process == "none"
    assert sandbox.cpu_seconds > 0


def test_g4_runtime_http_health_and_safety_stop_boundary(tmp_path):
    configuration = AgentRuntimeConfiguration.from_environment(
        _runtime_environment(PLANE_AGENT_RUNTIME_SAFETY_STOP_FILE=str(tmp_path / "safety-stop"))
    )
    controller = RuntimeSafetyController(configured=True, stop_file=tmp_path / "safety-stop")
    controller.mark_ready()
    server = _RuntimeHTTPServer(("127.0.0.1", 0), controller, configuration)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        with urllib.request.urlopen(f"{url}/health/ready", timeout=2) as response:
            assert response.status == 200
            assert json.loads(response.read())["status"] == "ready"
        request = urllib.request.Request(
            f"{url}/safety-stop",
            data=(
                b'{"idempotencyKey":"stop:test","invocationId":"invocation:test",'
                b'"reason":"test stop","workspaceId":"workspace:test"}'
            ),
            headers={
                "Authorization": f"Bearer {configuration.shared_secret}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            assert response.status == 202
            assert json.loads(response.read())["status"] == "accepted"
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(f"{url}/health/ready", timeout=2)
        assert error.value.code == 503
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
