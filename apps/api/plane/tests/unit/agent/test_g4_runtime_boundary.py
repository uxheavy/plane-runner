from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from types import SimpleNamespace

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
    validate_credential_lease_metadata,
)
from plane.agent.runtime import credentials as runtime_credentials
from plane.agent.runtime.provider_egress import ProviderRelayError
from plane.agent.runtime.service import RuntimeDispatchExecutor, _RuntimeHTTPServer


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
    configuration = AgentRuntimeConfiguration.from_environment(
        _runtime_environment(PLANE_AGENT_RUNTIME_CREDENTIAL_RESOLVER="command:/run/secrets/resolve-runtime-credential")
    )
    assert configuration.credential_resolver.endswith("resolve-runtime-credential")
    assert configuration.public_summary()["credentialResolverConfigured"] is True
    with pytest.raises(RuntimeConfigurationError, match="not accepted"):
        AgentRuntimeConfiguration.from_environment(
            _runtime_environment(PLANE_AGENT_RUNTIME_CREDENTIALS_JSON='{"api_key":"never-in-settings"}')
        )


def test_g4_deployment_credential_resolver_is_fixed_path_bounded_and_allowlisted(monkeypatch, tmp_path):
    source = tmp_path / "provider.env"
    source.write_text("# operator-owned\nOTHER=value\nXAI_API_KEY=provider-secret\n", encoding="utf-8")
    monkeypatch.setattr(runtime_credentials, "DEPLOYMENT_CREDENTIAL_SOURCE_PATH", str(source))

    assert runtime_credentials.resolve_deployment_credential("runtime") == {"api_key": "provider-secret"}
    with pytest.raises(RuntimeCredentialError, match="not allowed"):
        runtime_credentials.resolve_deployment_credential("provider")

    source.write_text('{"XAI_API_KEY":"json-secret"}', encoding="utf-8")
    assert runtime_credentials.resolve_deployment_credential("runtime") == {"api_key": "json-secret"}
    source.write_text("XAI_API_KEY=first\nXAI_API_KEY=second\n", encoding="utf-8")
    with pytest.raises(RuntimeCredentialError, match="duplicate"):
        runtime_credentials.resolve_deployment_credential("runtime")


def test_g4_deployment_credential_resolver_rejects_oversized_or_malformed_sources(monkeypatch, tmp_path):
    source = tmp_path / "provider.env"
    monkeypatch.setattr(runtime_credentials, "DEPLOYMENT_CREDENTIAL_SOURCE_PATH", str(source))
    source.write_text("XAI_API_KEY=\n", encoding="utf-8")
    with pytest.raises(RuntimeCredentialError):
        runtime_credentials.resolve_deployment_credential("runtime")
    source.write_text("not-an-assignment\n", encoding="utf-8")
    with pytest.raises(RuntimeCredentialError):
        runtime_credentials.resolve_deployment_credential("runtime")
    source.write_bytes(b"XAI_API_KEY=" + b"x" * (runtime_credentials._DEPLOYMENT_CREDENTIAL_MAX_BYTES + 1))
    with pytest.raises(RuntimeCredentialError, match="oversized"):
        runtime_credentials.resolve_deployment_credential("runtime")


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


def test_g4_runtime_credential_operator_state_invalidates_active_leases_across_processes(tmp_path):
    now = [100.0]
    state_file = tmp_path / "credential-revocations.json"
    source = {"provider": {"TOKEN": "disposable-token-1"}}
    broker = RuntimeCredentialBroker(source, ttl_seconds=60, clock=lambda: now[0], state_file=state_file)
    lease, _ = broker.issue(agent_ref="agent-1", credential_ref="provider", invocation_ref="invocation-1")

    operator = RuntimeCredentialBroker(lambda _ref: {}, clock=lambda: now[0], state_file=state_file)
    assert operator.revoke_invocation("invocation-1") == 0
    with pytest.raises(RuntimeCredentialError, match="revoked"):
        broker.resolve(lease.lease_id, agent_ref="agent-1", invocation_ref="invocation-1")

    next_lease, _ = broker.issue(agent_ref="agent-1", credential_ref="provider", invocation_ref="invocation-2")
    assert operator.rotate("provider") == 1
    with pytest.raises(RuntimeCredentialError, match="revoked|rotated"):
        broker.resolve(next_lease.lease_id, agent_ref="agent-1", invocation_ref="invocation-2")

    expiring, _ = broker.issue(agent_ref="agent-1", credential_ref="provider", invocation_ref="invocation-3")
    now[0] = expiring.expires_at
    with pytest.raises(RuntimeCredentialError, match="expired"):
        broker.resolve(expiring.lease_id, agent_ref="agent-1", invocation_ref="invocation-3")


def test_provider_relay_configuration_and_public_lease_metadata_are_parent_only(tmp_path):
    configuration = AgentRuntimeConfiguration.from_environment(
        _runtime_environment(
            PLANE_AGENT_RUNTIME_PROVIDER="xai",
            PLANE_AGENT_RUNTIME_PROVIDER_HOST="api.x.ai",
            PLANE_AGENT_RUNTIME_PROVIDER_MODELS="grok-4,grok-4-mini",
            PLANE_AGENT_RUNTIME_CREDENTIAL_STATE_FILE=str(tmp_path / "revocations.json"),
        )
    )
    assert configuration.provider_policy is not None
    assert configuration.provider_policy.provider == "xai"
    assert configuration.provider_policy.host == "api.x.ai"
    assert configuration.provider_policy.models == ("grok-4", "grok-4-mini")
    assert configuration.provider_policy.path == "/v1/chat/completions"

    now = [100.0]
    broker = RuntimeCredentialBroker(
        {"provider": {"api_key": "parent-only-provider-secret"}},
        ttl_seconds=60,
        clock=lambda: now[0],
        state_file=tmp_path / "revocations.json",
    )
    lease, credentials = broker.issue(
        agent_ref="agent-1", credential_ref="provider", invocation_ref="invocation-1"
    )
    metadata = lease.public_metadata()
    assert "parent-only-provider-secret" not in json.dumps(metadata)
    assert "credentialDigest" not in metadata
    validate_credential_lease_metadata(
        metadata,
        invocation_ref="invocation-1",
        state_file=tmp_path / "revocations.json",
        clock=lambda: now[0],
    )
    assert credentials == {"api_key": "parent-only-provider-secret"}
    broker.revoke_invocation("invocation-1")
    with pytest.raises(RuntimeCredentialError, match="revoked"):
        validate_credential_lease_metadata(
            metadata,
            invocation_ref="invocation-1",
            state_file=tmp_path / "revocations.json",
            clock=lambda: now[0],
        )


def test_g4_runtime_service_accepts_the_bound_chatgpt_codex_route_before_child_dispatch(monkeypatch, tmp_path):
    configuration = AgentRuntimeConfiguration.from_environment(
        _runtime_environment(
            PLANE_AGENT_RUNTIME_PROVIDER="openai-codex",
            PLANE_AGENT_RUNTIME_PROVIDER_HOST="chatgpt.com",
            PLANE_AGENT_RUNTIME_PROVIDER_PATH="/backend-api/codex/responses",
            PLANE_AGENT_RUNTIME_PROVIDER_MODELS="gpt-5.6-luna",
            PLANE_AGENT_RUNTIME_CREDENTIAL_STATE_FILE=str(tmp_path / "revocations.json"),
        )
    )
    controller = RuntimeSafetyController(configured=True, stop_file=tmp_path / "stop")
    controller.mark_ready()
    executor = RuntimeDispatchExecutor(configuration, controller)
    relay = SimpleNamespace(descriptor=SimpleNamespace(socket_path=tmp_path / "provider.sock"), close=lambda: None)
    monkeypatch.setattr(executor, "open_provider_relay", lambda **_kwargs: relay)
    monkeypatch.setattr(
        "plane.agent.runtime.service.PlaneHostServer",
        lambda **_kwargs: SimpleNamespace(start=lambda: None, close=lambda: None),
    )
    monkeypatch.setattr(
        "plane.agent.runtime.service._hermes_bootstrap_payload",
        lambda *_args, **_kwargs: (b"payload", "run:codex", "invocation:codex", "digest"),
    )
    monkeypatch.setattr(executor._transport, "dispatch_payload", lambda **_kwargs: ("completed",))

    assert executor._execute(
        {
            "runId": "run:codex",
            "runtimePolicy": {"model": {"provider": "openai-codex", "model": "gpt-5.6-luna"}},
        },
        {"invocationId": "invocation:codex", "correlationId": "correlation:codex"},
        "digest",
        credentials={"provider": "openai-codex"},
        credential_lease={"leaseId": "lease:codex"},
        allowance=1,
        host_url="http://plane-api:8091",
        host_token="host-token",
    ) == ("completed",)


@pytest.mark.parametrize(
    ("provider", "host", "path", "model", "message"),
    (
        ("xai", "api.x.ai", "/v1/chat/completions", "gpt-5.6-luna", "configured provider route"),
        ("openai-codex", "api.x.ai", "/v1/chat/completions", "gpt-5.6-luna", "provider egress route is invalid"),
        ("openai-codex", "chatgpt.com", "/v1/chat/completions", "gpt-5.6-luna", "provider egress route is invalid"),
        ("openai-codex", "chatgpt.com", "/backend-api/codex/responses", "gpt-5.5", "GPT-5.6 family"),
    ),
)
def test_g4_runtime_policy_rejects_wrong_provider_wire_or_model_before_dispatch(
    provider, host, path, model, message, tmp_path
):
    with pytest.raises((RuntimeConfigurationError, ProviderRelayError), match=message):
        configuration = AgentRuntimeConfiguration.from_environment(
            _runtime_environment(
                PLANE_AGENT_RUNTIME_PROVIDER=provider,
                PLANE_AGENT_RUNTIME_PROVIDER_HOST=host,
                PLANE_AGENT_RUNTIME_PROVIDER_PATH=path,
                PLANE_AGENT_RUNTIME_PROVIDER_MODELS=model,
                PLANE_AGENT_RUNTIME_CREDENTIAL_STATE_FILE=str(tmp_path / f"{provider}-revocations.json"),
            )
        )
        executor = object.__new__(RuntimeDispatchExecutor)
        executor.configuration = configuration
        executor._configured_provider_route(
            {"runtimePolicy": {"model": {"provider": "openai-codex", "model": model}}}
        )


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
        with urllib.request.urlopen(f"{url}/health/ready", timeout=2) as response:
            assert response.status == 200
            health = json.loads(response.read())
        assert health["status"] == "ready"
        assert health["safetyStop"] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
