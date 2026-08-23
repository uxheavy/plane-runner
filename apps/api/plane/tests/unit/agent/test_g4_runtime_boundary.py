from __future__ import annotations

import base64
import json
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
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
    RuntimeDispatchError,
    RuntimeSafetyController,
    RuntimeSafetyStopError,
    runtime_transport_kind,
    validate_credential_lease_metadata,
)
from plane.agent.runtime.config import runtime_settings_from_environment
from plane.agent.runtime import credentials as runtime_credentials
from plane.agent.runtime.provider_egress import ProviderRelayError
from plane.agent.runtime.service import RuntimeDispatchExecutor, _RuntimeHTTPServer


def _synthetic_jwt(*, issued_at: int, expires_at: int, payload: bytes | None = None) -> str:
    encode = lambda value: base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")
    claims = payload or json.dumps({"iat": issued_at, "exp": expires_at}, separators=(",", ":")).encode()
    return f"{encode(b'{}')}.{encode(claims)}.synthetic-signature"


def _runtime_environment(**overrides: str) -> dict[str, str]:
    environment = {
        "PLANE_AGENT_RUNTIME_URL": "http://agent-runtime:8080",
        "PLANE_AGENT_RUNTIME_HOST_URL": "http://plane-api:8000",
        "PLANE_AGENT_RUNTIME_SECRET": "r" * 40,
        "PLANE_AGENT_RUNTIME_HOST_URL": "http://plane-api:8091",
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


def test_g4_packaged_credential_resolver_loads_parser_without_plane_bootstrap(tmp_path):
    resolver = Path(__file__).parents[4] / "bin" / "plane-agent-runtime-credential-resolver"
    source = tmp_path / "provider.env"
    source.write_text("synthetic-provider-secret\n", encoding="utf-8")
    probe = (
        "import importlib.util, json, sys\n"
        "from importlib.machinery import SourceFileLoader\n"
        "loader = SourceFileLoader('resolver', sys.argv[1])\n"
        "spec = importlib.util.spec_from_loader('resolver', loader)\n"
        "resolver = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(resolver)\n"
        "resolver.__file__ = '/usr/local/bin/plane-agent-runtime-credential-resolver'\n"
        "parser = resolver._load_credentials_module()\n"
        "parser.DEPLOYMENT_CREDENTIAL_SOURCE_PATH = sys.argv[2]\n"
        "print(json.dumps(parser.resolve_deployment_credential('runtime'), sort_keys=True))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe, str(resolver), str(source)],
        env={"PATH": "/usr/bin:/bin"},
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == '{"api_key": "synthetic-provider-secret"}'
    assert "plane.settings" not in result.stderr


@pytest.mark.parametrize(
    "source_value",
    (
        "OPENAI_API_KEY=chatgpt-subscription-token\n",
        "chatgpt-subscription-token\n",
        '{"api_key":"chatgpt-subscription-token"}',
    ),
)
def test_g4_deployment_credential_resolver_accepts_provider_neutral_chatgpt_sources(
    monkeypatch, tmp_path, source_value
):
    source = tmp_path / "provider-source"
    monkeypatch.setattr(runtime_credentials, "DEPLOYMENT_CREDENTIAL_SOURCE_PATH", str(source))
    source.write_text(source_value, encoding="utf-8")

    assert runtime_credentials.resolve_deployment_credential("runtime") == {"api_key": "chatgpt-subscription-token"}


@pytest.mark.parametrize(
    "document_shape",
    (False, True),
    ids=("legacy-without-host-metadata", "current"),
)
def test_g4_deployment_credential_resolver_accepts_fresh_codex_auth_document(
    monkeypatch, tmp_path, document_shape
):
    now = runtime_credentials.datetime.fromisoformat("2026-08-07T10:12:00+00:00").timestamp()
    monkeypatch.setattr(runtime_credentials.time, "time", lambda: now)
    document = {
        "last_refresh": "2026-08-01T10:12:00Z",
        "tokens": {
            "access_token": _synthetic_jwt(issued_at=int(now) - 300, expires_at=int(now) + 3600),
            "account_id": "synthetic-account-id",
            "id_token": "synthetic-id-token",
            "refresh_token": "synthetic-refresh-token",
        },
    }
    if document_shape:
        document["OPENAI_API_KEY"] = None
        document["auth_mode"] = "chatgpt"
    source = tmp_path / "auth.json"
    source.write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setattr(runtime_credentials, "DEPLOYMENT_CREDENTIAL_SOURCE_PATH", str(source))

    assert runtime_credentials.resolve_deployment_credential("runtime") == {
        "api_key": document["tokens"]["access_token"]
    }


@pytest.mark.parametrize(
    ("last_refresh", "expected"),
    (
        ("2026-08-07T10:13:01Z", "requires trusted resolver refresh"),
        ("2026-08-07T10:12:00+00:00", "JSON fields are invalid"),
        ("not-a-timestamp", "JSON fields are invalid"),
    ),
    ids=("future", "non-zulu", "malformed"),
)
def test_g4_deployment_credential_resolver_rejects_nonfresh_codex_auth_document(
    monkeypatch, tmp_path, last_refresh, expected
):
    now = runtime_credentials.datetime.fromisoformat("2026-08-07T10:12:00+00:00").timestamp()
    monkeypatch.setattr(runtime_credentials.time, "time", lambda: now)
    source = tmp_path / "auth.json"
    source.write_text(
        json.dumps(
            {
                "last_refresh": last_refresh,
                "tokens": {
                    "access_token": "synthetic-access-token",
                    "account_id": "synthetic-account-id",
                    "id_token": "synthetic-id-token",
                    "refresh_token": "synthetic-refresh-token",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(runtime_credentials, "DEPLOYMENT_CREDENTIAL_SOURCE_PATH", str(source))

    with pytest.raises(runtime_credentials.RuntimeCredentialError, match=expected):
        runtime_credentials.resolve_deployment_credential("runtime")


def test_g4_codex_auth_document_refresh_gap_is_classified_without_leaking_values():
    error = runtime_credentials.RuntimeCredentialError(
        "deployment credential source requires trusted resolver refresh"
    )


@pytest.mark.parametrize(
    "access_token",
    (
        "not-a-jwt",
        _synthetic_jwt(issued_at=1787064000, expires_at=1787063000),
        _synthetic_jwt(issued_at=1787064000, expires_at=1787064060),
        _synthetic_jwt(issued_at=1787060000, expires_at=1788270001),
        _synthetic_jwt(issued_at=0, expires_at=0, payload=b'{"iat":1,"iat":2,"exp":3}'),
        _synthetic_jwt(issued_at=0, expires_at=0, payload=b"{" + b"x" * 8193 + b"}"),
    ),
    ids=("malformed", "expired", "future-iat", "lifetime-too-long", "duplicate-claim", "oversized"),
)
def test_g4_codex_auth_document_rejects_unusable_jwt_lifetime(monkeypatch, tmp_path, access_token):
    now = 1787063898
    monkeypatch.setattr(runtime_credentials.time, "time", lambda: now)
    source = tmp_path / "auth.json"
    source.write_text(json.dumps({
        "last_refresh": "2026-08-01T00:00:00Z",
        "tokens": {
            "access_token": access_token,
            "account_id": "synthetic-account-id",
            "id_token": "synthetic-id-token",
            "refresh_token": "synthetic-refresh-token",
        },
    }), encoding="utf-8")
    monkeypatch.setattr(runtime_credentials, "DEPLOYMENT_CREDENTIAL_SOURCE_PATH", str(source))
    with pytest.raises(runtime_credentials.RuntimeCredentialError, match="requires trusted resolver refresh"):
        runtime_credentials.resolve_deployment_credential("runtime")
    assert runtime_credentials.credential_failure_subreason(error) == (
        "credential_source_requires_refresh"
    )


@pytest.mark.parametrize(
    "mutate",
    (
        lambda document: document["tokens"].pop("access_token"),
        lambda document: document["tokens"].update(access_token=None),
        lambda document: document["tokens"].update(account_id=None),
        lambda document: document["tokens"].update(extra="ambiguous-token"),
        lambda document: document.update(api_key="ambiguous-token"),
        lambda document: document.update(OPENAI_API_KEY="ambiguous-token"),
        lambda document: document.pop("auth_mode"),
        lambda document: document.update(auth_mode="api"),
        lambda document: document.update(auth_mode=1),
        lambda document: document.update(extra="ambiguous-token"),
        lambda document: document.update(last_refresh=None),
    ),
    ids=(
        "missing-access-token",
        "null-access-token",
        "null-account-id",
        "extra-token",
        "extra-top-level",
        "non-null-openai-key",
        "missing-auth-mode",
        "other-auth-mode",
        "non-string-auth-mode",
        "extra-top-level",
        "null-refresh-time",
    ),
)
def test_g4_deployment_credential_resolver_rejects_malformed_ambiguous_or_null_codex_auth_documents(
    monkeypatch, tmp_path, mutate
):
    source = tmp_path / "auth.json"
    document = {
        "OPENAI_API_KEY": None,
        "auth_mode": "chatgpt",
        "last_refresh": "2026-08-13T00:00:00Z",
        "tokens": {
            "access_token": "synthetic-access-token",
            "account_id": "synthetic-account-id",
            "id_token": "synthetic-id-token",
            "refresh_token": "synthetic-refresh-token",
        },
    }
    mutate(document)
    source.write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setattr(runtime_credentials, "DEPLOYMENT_CREDENTIAL_SOURCE_PATH", str(source))

    with pytest.raises(RuntimeCredentialError):
        runtime_credentials.resolve_deployment_credential("runtime")


def test_g4_deployment_credential_resolver_rejects_malformed_duplicate_and_oversized_codex_auth_documents(
    monkeypatch, tmp_path
):
    source = tmp_path / "auth.json"
    monkeypatch.setattr(runtime_credentials, "DEPLOYMENT_CREDENTIAL_SOURCE_PATH", str(source))
    source.write_text('{"OPENAI_API_KEY":null,"last_refresh":"2026-08-13T00:00:00Z",', encoding="utf-8")
    with pytest.raises(RuntimeCredentialError, match="valid JSON"):
        runtime_credentials.resolve_deployment_credential("runtime")

    source.write_text(
        '{"OPENAI_API_KEY":null,"last_refresh":"2026-08-13T00:00:00Z",'
        '"tokens":{"access_token":"first","access_token":"second",'
        '"account_id":"account","id_token":"id","refresh_token":"refresh"}}',
        encoding="utf-8",
    )
    with pytest.raises(RuntimeCredentialError, match="valid JSON"):
        runtime_credentials.resolve_deployment_credential("runtime")

    source.write_text(
        json.dumps(
            {
                "OPENAI_API_KEY": None,
                "last_refresh": "2026-08-13T00:00:00Z",
                "tokens": {
                    "access_token": "x" * (runtime_credentials._DEPLOYMENT_CREDENTIAL_MAX_VALUE_BYTES + 1),
                    "account_id": "synthetic-account-id",
                    "id_token": "synthetic-id-token",
                    "refresh_token": "synthetic-refresh-token",
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeCredentialError, match="oversized"):
        runtime_credentials.resolve_deployment_credential("runtime")


def test_g4_deployment_credential_resolver_rejects_oversized_or_malformed_sources(monkeypatch, tmp_path):
    source = tmp_path / "provider.env"
    monkeypatch.setattr(runtime_credentials, "DEPLOYMENT_CREDENTIAL_SOURCE_PATH", str(source))
    source.write_text("XAI_API_KEY=\n", encoding="utf-8")
    with pytest.raises(RuntimeCredentialError):
        runtime_credentials.resolve_deployment_credential("runtime")
    source.write_text("not-a-token\nsecond-line\n", encoding="utf-8")
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


def test_g4_remote_runtime_secret_file_selects_remote_and_missing_secret_cannot_downgrade(tmp_path):
    secret_path = tmp_path / "runtime-secret"
    secret_path.write_text("f" * 40, encoding="utf-8")
    environment = _runtime_environment(
        PLANE_AGENT_RUNTIME_SECRET="",
        PLANE_AGENT_RUNTIME_SECRET_FILE=str(secret_path),
    )

    settings = runtime_settings_from_environment(environment)

    assert settings["PLANE_AGENT_RUNTIME_SHARED_SECRET"] == "f" * 40
    assert runtime_transport_kind(
        settings["PLANE_AGENT_RUNTIME_URL"],
        settings["PLANE_AGENT_RUNTIME_SHARED_SECRET"],
    ) == "remote"
    with pytest.raises(RuntimeConfigurationError, match="configured together"):
        runtime_transport_kind("http://agent-runtime:8080", "")
    with pytest.raises(RuntimeConfigurationError, match="configured together"):
        runtime_transport_kind("", "f" * 40)


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


def test_g4_runtime_process_observes_plane_revocation_from_shared_state_file(tmp_path):
    state_file = tmp_path / "credential-revocations.json"
    operator = RuntimeCredentialBroker(lambda _ref: {}, clock=lambda: 100.0, state_file=state_file)
    assert operator.revoke_invocation("invocation-1") == 0

    lease_metadata = {
        "leaseId": "lease-1",
        "agentRef": "agent-1",
        "credentialRef": "provider",
        "invocationRef": "invocation-1",
        "generation": 1,
        "issuedAt": 100.0,
        "expiresAt": 160.0,
        "rotationGeneration": 0,
    }
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import json
import sys
from plane.agent.runtime import RuntimeCredentialError, validate_credential_lease_metadata

try:
    validate_credential_lease_metadata(
        json.loads(sys.argv[2]),
        invocation_ref="invocation-1",
        state_file=sys.argv[1],
        clock=lambda: 100.0,
    )
except RuntimeCredentialError as error:
    raise SystemExit(0 if "revoked" in str(error) else 1)
raise SystemExit(2)
""",
            str(state_file),
            json.dumps(lease_metadata, sort_keys=True),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert probe.returncode == 0, probe.stderr


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
    relay = SimpleNamespace(
        descriptor=SimpleNamespace(socket_path=tmp_path / "provider.sock"),
        required_audit_failure=None,
        close=lambda: None,
    )
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


def test_g4_runtime_service_propagates_bounded_host_failure_evidence(monkeypatch, tmp_path):
    configuration = AgentRuntimeConfiguration.from_environment(_runtime_environment())
    controller = RuntimeSafetyController(configured=True, stop_file=tmp_path / "stop")
    controller.mark_ready()
    executor = RuntimeDispatchExecutor(configuration, controller)
    evidence = {
        "operationId": "unavailable",
        "attemptRef": "unavailable",
        "receiptRef": "unavailable",
        "status": "unavailable",
        "errorCode": "HOST_UNAVAILABLE",
        "codeModePhase": "unavailable",
        "failureClass": "transport_unavailable",
        "socketPhase": "read",
        "socketState": "failed",
    }
    host_server = SimpleNamespace(
        failure_evidence=evidence,
        start=lambda: None,
        close=lambda: None,
    )
    monkeypatch.setattr("plane.agent.runtime.service.PlaneHostServer", lambda **_kwargs: host_server)
    monkeypatch.setattr(
        "plane.agent.runtime.service._hermes_bootstrap_payload",
        lambda *_args, **_kwargs: (b"payload", "run:test", "invocation:test", "digest"),
    )

    def fail_dispatch(**_kwargs):
        raise RuntimeDispatchError("private child details")

    monkeypatch.setattr(executor._transport, "dispatch_payload", fail_dispatch)
    with pytest.raises(RuntimeDispatchError) as raised:
        executor._execute(
            {"runId": "run:test"},
            {"invocationId": "invocation:test", "correlationId": "correlation:test"},
            "digest",
            credentials={},
            credential_lease=None,
            allowance=None,
            host_url="http://plane-api:8091",
            host_token="host-token",
        )

    failure = raised.value.public_failure()
    assert failure["hostOperationFailure"] == evidence
    assert "private child details" not in json.dumps(failure)


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
