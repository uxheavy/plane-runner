"""Fail-closed configuration for the separate Plane Agent runtime service.

This module deliberately has no Django dependency.  The runtime health process
and Plane settings both use the same parser, so a production process cannot
silently turn a malformed URL or missing secret into a disabled integration.
"""

from __future__ import annotations

import json
import os
import shlex
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit

from .contracts import RUNTIME_BUDGET_MAX_SECONDS
from .provider_egress import GPT56_MODEL_RE, ProviderRelayPolicy, provider_wire


RUNTIME_PROTOCOL = "plane.agent-runtime/v1"
RUNTIME_BOOTSTRAP_MODULE = "plane_runtime.g1_runtime_image.bootstrap"
DEFAULT_RUNTIME_COMMAND = (
    "python3",
    "-m",
    RUNTIME_BOOTSTRAP_MODULE,
    "--once",
    "--g1-production",
)
DEFAULT_HEALTH_PATH = "/health/ready"
DEFAULT_DISPATCH_PATH = "/v1/runtime/dispatch"
DEFAULT_SAFETY_STOP_FILE = "/run/plane-agent-runtime/safety-stop"
DEFAULT_LEDGER_PATH = "/run/plane-agent-runtime/dispatch-ledger.sqlite"

_PLACEHOLDER_SECRETS = frozenset(
    {
        "change-this-key-on-deployment",
        "change-this-runtime-password",
        "change-this-migration-password",
        "secret-key",
        "runtime-secret",
        "runtime-credential",
        "password",
    }
)
_SENSITIVE_ENV_MARKERS = (
    "API_KEY",
    "APITOKEN",
    "AUTH",
    "CREDENTIAL",
    "DATABASE",
    "PASSWORD",
    "PG",
    "SECRET",
    "TOKEN",
)


class RuntimeConfigurationError(ValueError):
    """A runtime configuration value is absent, invalid, or unsafe."""


def runtime_transport_kind(runtime_url: object, shared_secret: object) -> str:
    """Select the only transport allowed by the configured runtime boundary.

    A configured remote endpoint without its authentication secret must never
    silently downgrade to the host-bound subprocess transport. The same
    invariant applies in the opposite direction: a secret without an
    endpoint is not a usable remote configuration.
    """

    if not isinstance(runtime_url, str) or not isinstance(shared_secret, str):
        raise RuntimeConfigurationError("runtime URL and shared secret must be strings")
    if bool(runtime_url) != bool(shared_secret):
        raise RuntimeConfigurationError("remote runtime URL and shared secret must be configured together")
    return "remote" if runtime_url else "local"


_APPROVED_PYTHON_EXECUTABLES = frozenset(
    {
        "python3",
        "/usr/bin/python3",
        "/usr/local/bin/python3",
        sys.executable,
    }
)
_RUNTIME_BOOTSTRAP_FLAGS = ("--once", "--g1-production")


def validate_runtime_command(command: Sequence[str]) -> tuple[str, ...]:
    """Validate the exact production bootstrap argv shape.

    Substring matching would allow ``python -c`` comments or lookalike
    filenames to replace the pinned bootstrap. Only the approved Python
    executable, ``-m``, the exact module, and the frozen bootstrap flags are
    accepted here.
    """

    if isinstance(command, (str, bytes)) or not isinstance(command, Sequence):
        raise RuntimeConfigurationError("PLANE_AGENT_RUNTIME_COMMAND must be an argv sequence")
    values = tuple(command)
    if len(values) != 5 or any(not isinstance(part, str) or not part or "\x00" in part for part in values):
        raise RuntimeConfigurationError("PLANE_AGENT_RUNTIME_COMMAND has an invalid argv shape")
    if values[0] not in _APPROVED_PYTHON_EXECUTABLES:
        raise RuntimeConfigurationError("PLANE_AGENT_RUNTIME_COMMAND executable is not approved")
    if values[1:] != ("-m", RUNTIME_BOOTSTRAP_MODULE, *_RUNTIME_BOOTSTRAP_FLAGS):
        raise RuntimeConfigurationError("PLANE_AGENT_RUNTIME_COMMAND must use the exact pinned bootstrap argv")
    return values


def _bounded_text(value: object, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise RuntimeConfigurationError(f"{name} must be a non-empty string")
    if len(value.encode("utf-8")) > maximum:
        raise RuntimeConfigurationError(f"{name} exceeds its size bound")
    if any(ord(char) < 0x20 and char not in "\t" for char in value):
        raise RuntimeConfigurationError(f"{name} contains control characters")
    return value


def _positive_int(environment: Mapping[str, str], name: str, default: int, maximum: int) -> int:
    raw = environment.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeConfigurationError(f"{name} must be a positive integer") from exc
    if value <= 0 or value > maximum:
        raise RuntimeConfigurationError(f"{name} is outside its allowed range")
    return value


def _positive_float(environment: Mapping[str, str], name: str, default: float, maximum: float) -> float:
    raw = environment.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeConfigurationError(f"{name} must be a positive number") from exc
    if value <= 0 or value > maximum:
        raise RuntimeConfigurationError(f"{name} is outside its allowed range")
    return value


def _reject_placeholder(value: str, name: str) -> str:
    if value.strip().casefold() in _PLACEHOLDER_SECRETS:
        raise RuntimeConfigurationError(f"{name} is a placeholder and cannot be used")
    return value


def _read_secret(environment: Mapping[str, str]) -> str:
    direct = environment.get("PLANE_AGENT_RUNTIME_SECRET")
    secret_file = environment.get("PLANE_AGENT_RUNTIME_SECRET_FILE")
    if direct and secret_file:
        raise RuntimeConfigurationError(
            "PLANE_AGENT_RUNTIME_SECRET and PLANE_AGENT_RUNTIME_SECRET_FILE are mutually exclusive"
        )
    if secret_file:
        path = Path(_bounded_text(secret_file, "PLANE_AGENT_RUNTIME_SECRET_FILE", 512))
        if not path.is_absolute():
            raise RuntimeConfigurationError("PLANE_AGENT_RUNTIME_SECRET_FILE must be absolute")
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise RuntimeConfigurationError("PLANE_AGENT_RUNTIME_SECRET_FILE cannot be read") from exc
        if len(raw) > 4096:
            raise RuntimeConfigurationError("PLANE_AGENT_RUNTIME_SECRET_FILE exceeds its size bound")
        try:
            value = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RuntimeConfigurationError("PLANE_AGENT_RUNTIME_SECRET_FILE is not UTF-8") from exc
        if not value or value != value.strip() or "\n" in value or "\r" in value:
            raise RuntimeConfigurationError("PLANE_AGENT_RUNTIME_SECRET_FILE must contain one secret line")
    else:
        value = direct or ""
    value = _bounded_text(value, "PLANE_AGENT_RUNTIME_SECRET", 4096)
    if len(value.encode("utf-8")) < 32:
        raise RuntimeConfigurationError("PLANE_AGENT_RUNTIME_SECRET must contain at least 32 UTF-8 bytes")
    return _reject_placeholder(value, "PLANE_AGENT_RUNTIME_SECRET")


def _parse_object(raw: str, name: str) -> dict[str, object]:
    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate object key")
            result[key] = item
        return result

    try:
        value = json.loads(
            raw,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=lambda constant: (_ for _ in ()).throw(ValueError(constant)),
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeConfigurationError(f"{name} must be a JSON object") from exc
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise RuntimeConfigurationError(f"{name} must be a JSON object")
    return value


def _validate_child_environment(environment: Mapping[str, object]) -> dict[str, str]:
    validated: dict[str, str] = {}
    for key, value in environment.items():
        _bounded_text(key, "runtime child environment key", 128)
        if any(marker in key.upper().replace("-", "_") for marker in _SENSITIVE_ENV_MARKERS):
            raise RuntimeConfigurationError("runtime child environment contains a credential-shaped key")
        if not isinstance(value, str) or "\x00" in value:
            raise RuntimeConfigurationError("runtime child environment values must be NUL-free strings")
        if len(value.encode("utf-8")) > 4096:
            raise RuntimeConfigurationError("runtime child environment value exceeds its size bound")
        validated[key] = value
    if len(validated) > 32:
        raise RuntimeConfigurationError("runtime child environment contains too many entries")
    return validated


def _validate_credential_resolver(value: object) -> str:
    if value in (None, ""):
        return ""
    raw = _bounded_text(value, "PLANE_AGENT_RUNTIME_CREDENTIAL_RESOLVER", 512)
    if not raw.startswith("command:"):
        raise RuntimeConfigurationError(
            "PLANE_AGENT_RUNTIME_CREDENTIAL_RESOLVER must use command:/absolute/path"
        )
    executable = raw.removeprefix("command:")
    if not executable.startswith("/") or any(char.isspace() for char in executable):
        raise RuntimeConfigurationError("PLANE_AGENT_RUNTIME_CREDENTIAL_RESOLVER executable is invalid")
    return raw


def _provider_policy_from_environment(
    source: Mapping[str, str], *, max_request_bytes: int, max_response_bytes: int
) -> ProviderRelayPolicy | None:
    """Parse the trusted-parent provider route; never parse provider secrets."""

    provider = source.get("PLANE_AGENT_RUNTIME_PROVIDER", "")
    companion_keys = (
        "PLANE_AGENT_RUNTIME_PROVIDER_HOST",
        "PLANE_AGENT_RUNTIME_PROVIDER_PATH",
        "PLANE_AGENT_RUNTIME_PROVIDER_MODELS",
        "PLANE_AGENT_RUNTIME_PROVIDER_CREDENTIAL_NAME",
    )
    if not provider:
        if any(source.get(key) for key in companion_keys):
            raise RuntimeConfigurationError("provider egress route is incomplete")
        return None
    provider = _bounded_text(provider, "PLANE_AGENT_RUNTIME_PROVIDER", 64)
    wire = provider_wire(provider)
    host = _bounded_text(
        source.get("PLANE_AGENT_RUNTIME_PROVIDER_HOST", wire.host if wire is not None else None),
        "provider egress host",
        255,
    )
    if any(char in host for char in ("/", "?", "#", "@", ":")) or any(char.isspace() for char in host):
        raise RuntimeConfigurationError("provider egress host must be one pinned hostname")
    path = _bounded_text(
        source.get(
            "PLANE_AGENT_RUNTIME_PROVIDER_PATH",
            wire.path if wire is not None else "/v1/chat/completions",
        ),
        "provider egress path",
        1024,
    )
    raw_models = _bounded_text(
        source.get("PLANE_AGENT_RUNTIME_PROVIDER_MODELS", ""),
        "provider egress models",
        4096,
    )
    models = tuple(item.strip() for item in raw_models.split(",") if item.strip())
    if not models:
        raise RuntimeConfigurationError("provider egress model allowlist is empty")
    if provider == "openai-codex" and any(not GPT56_MODEL_RE.fullmatch(model) for model in models):
        raise RuntimeConfigurationError("Plane Agent provider models must remain within the GPT-5.6 family")
    credential_name = _bounded_text(
        source.get(
            "PLANE_AGENT_RUNTIME_PROVIDER_CREDENTIAL_NAME",
            wire.credential_name if wire is not None else "api_key",
        ),
        "provider egress credential name",
        128,
    )
    try:
        return ProviderRelayPolicy(
            provider=provider,
            host=host,
            path=path,
            models=models,
            credential_name=credential_name,
            timeout_seconds=_positive_float(source, "PLANE_AGENT_RUNTIME_PROVIDER_TIMEOUT_SECONDS", 30.0, 300.0),
            max_request_bytes=_positive_int(
                source,
                "PLANE_AGENT_RUNTIME_PROVIDER_MAX_REQUEST_BYTES",
                1024 * 1024,
                2 * 1024 * 1024,
            ),
            max_response_bytes=max_response_bytes,
            max_chunk_bytes=_positive_int(
                source, "PLANE_AGENT_RUNTIME_PROVIDER_MAX_CHUNK_BYTES", 64 * 1024, 2 * 1024 * 1024
            ),
            max_calls=_positive_int(source, "PLANE_AGENT_RUNTIME_PROVIDER_MAX_CALLS", 16, 256),
            max_concurrent_requests=_positive_int(
                source, "PLANE_AGENT_RUNTIME_PROVIDER_MAX_CONCURRENT_REQUESTS", 2, 32
            ),
        )
    except ValueError as exc:
        raise RuntimeConfigurationError("provider egress route is invalid") from exc


def _validate_runtime_url(value: object) -> str:
    raw = _bounded_text(value, "PLANE_AGENT_RUNTIME_URL", 2048)
    if raw != raw.strip() or any(char.isspace() for char in raw):
        raise RuntimeConfigurationError("PLANE_AGENT_RUNTIME_URL contains whitespace")
    try:
        parsed = urlsplit(raw)
        if parsed.port == 0:
            raise RuntimeConfigurationError("PLANE_AGENT_RUNTIME_URL must not use port zero")
    except ValueError as exc:
        raise RuntimeConfigurationError("PLANE_AGENT_RUNTIME_URL has an invalid port") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise RuntimeConfigurationError("PLANE_AGENT_RUNTIME_URL must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise RuntimeConfigurationError("PLANE_AGENT_RUNTIME_URL must not contain credentials")
    if parsed.query or parsed.fragment:
        raise RuntimeConfigurationError("PLANE_AGENT_RUNTIME_URL must not contain a query or fragment")
    return raw.rstrip("/")


def validate_runtime_host_url(value: object) -> str:
    """Validate the internal Plane host callback URL without importing Django."""

    raw = _bounded_text(value, "PLANE_AGENT_RUNTIME_HOST_URL", 2048).rstrip("/")
    parsed = urlsplit(raw)
    if parsed.scheme != "http" or not parsed.hostname:
        raise RuntimeConfigurationError("PLANE_AGENT_RUNTIME_HOST_URL must be an internal HTTP URL")
    if parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
        raise RuntimeConfigurationError("PLANE_AGENT_RUNTIME_HOST_URL must not contain credentials or query data")
    try:
        if parsed.port is not None and not 0 < parsed.port <= 65535:
            raise RuntimeConfigurationError("PLANE_AGENT_RUNTIME_HOST_URL port is invalid")
    except ValueError as exc:
        raise RuntimeConfigurationError("PLANE_AGENT_RUNTIME_HOST_URL port is invalid") from exc
    return raw


def _validate_health_path(value: object) -> str:
    path = _bounded_text(value, "PLANE_AGENT_RUNTIME_HEALTH_PATH", 128)
    if not path.startswith("/") or "?" in path or "#" in path:
        raise RuntimeConfigurationError("PLANE_AGENT_RUNTIME_HEALTH_PATH must be an absolute path")
    return path


@dataclass(frozen=True)
class AgentRuntimeConfiguration:
    """Validated runtime settings shared by Plane and the runtime service."""

    url: str
    shared_secret: str
    health_path: str
    dispatch_path: str
    safety_stop_file: str
    ledger_path: str
    command: tuple[str, ...]
    child_environment: Mapping[str, str]
    credential_resolver: str
    timeout_seconds: float
    max_request_bytes: int
    max_response_bytes: int
    max_concurrent_invocations: int
    cpu_seconds: int
    memory_bytes: int
    pids_limit: int
    network_policy: str
    filesystem_policy: str
    process_policy: str
    credential_state_file: str
    provider_policy: ProviderRelayPolicy | None

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> "AgentRuntimeConfiguration":
        source = os.environ if environment is None else environment
        url = _validate_runtime_url(source.get("PLANE_AGENT_RUNTIME_URL"))
        shared_secret = _read_secret(source)
        health_path = _validate_health_path(source.get("PLANE_AGENT_RUNTIME_HEALTH_PATH", DEFAULT_HEALTH_PATH))
        dispatch_path = _validate_health_path(source.get("PLANE_AGENT_RUNTIME_DISPATCH_PATH", DEFAULT_DISPATCH_PATH))
        safety_stop_file = _bounded_text(
            source.get("PLANE_AGENT_RUNTIME_SAFETY_STOP_FILE", DEFAULT_SAFETY_STOP_FILE),
            "PLANE_AGENT_RUNTIME_SAFETY_STOP_FILE",
            512,
        )
        if not Path(safety_stop_file).is_absolute():
            raise RuntimeConfigurationError("PLANE_AGENT_RUNTIME_SAFETY_STOP_FILE must be absolute")
        ledger_path = _bounded_text(
            source.get("PLANE_AGENT_RUNTIME_LEDGER_PATH", DEFAULT_LEDGER_PATH),
            "PLANE_AGENT_RUNTIME_LEDGER_PATH",
            512,
        )
        if not Path(ledger_path).is_absolute():
            raise RuntimeConfigurationError("PLANE_AGENT_RUNTIME_LEDGER_PATH must be absolute")
        raw_command = source.get("PLANE_AGENT_RUNTIME_COMMAND")
        if raw_command:
            try:
                command = tuple(shlex.split(raw_command))
            except ValueError as exc:
                raise RuntimeConfigurationError("PLANE_AGENT_RUNTIME_COMMAND is malformed") from exc
        else:
            command = DEFAULT_RUNTIME_COMMAND
        command = validate_runtime_command(command)
        child_environment = _validate_child_environment(
            _parse_object(
                source.get("PLANE_AGENT_RUNTIME_ENVIRONMENT_JSON", "{}"),
                "PLANE_AGENT_RUNTIME_ENVIRONMENT_JSON",
            )
        )
        if source.get("PLANE_AGENT_RUNTIME_CREDENTIALS_JSON"):
            raise RuntimeConfigurationError(
                "PLANE_AGENT_RUNTIME_CREDENTIALS_JSON is not accepted; use the host credential resolver"
            )
        network_policy = source.get("PLANE_AGENT_RUNTIME_NETWORK_POLICY", "none")
        if network_policy != "none":
            raise RuntimeConfigurationError("runtime network policy must be none")
        credential_state_file = _bounded_text(
            source.get("PLANE_AGENT_RUNTIME_CREDENTIAL_STATE_FILE", "/run/plane-agent-credentials/revocations.json"),
            "PLANE_AGENT_RUNTIME_CREDENTIAL_STATE_FILE",
            512,
        )
        if not Path(credential_state_file).is_absolute():
            raise RuntimeConfigurationError("PLANE_AGENT_RUNTIME_CREDENTIAL_STATE_FILE must be absolute")
        max_request_bytes = _positive_int(source, "PLANE_AGENT_RUNTIME_MAX_REQUEST_BYTES", 256 * 1024, 2 * 1024 * 1024)
        max_response_bytes = _positive_int(
            source, "PLANE_AGENT_RUNTIME_MAX_RESPONSE_BYTES", 512 * 1024, 2 * 1024 * 1024
        )
        provider_policy = _provider_policy_from_environment(
            source, max_request_bytes=max_request_bytes, max_response_bytes=max_response_bytes
        )
        return cls(
            url=url,
            shared_secret=shared_secret,
            health_path=health_path,
            dispatch_path=dispatch_path,
            safety_stop_file=safety_stop_file,
            ledger_path=ledger_path,
            command=command,
            child_environment=child_environment,
            credential_resolver=_validate_credential_resolver(
                source.get("PLANE_AGENT_RUNTIME_CREDENTIAL_RESOLVER", "")
            ),
            timeout_seconds=_positive_float(
                source, "PLANE_AGENT_RUNTIME_TIMEOUT_SECONDS", 300.0, RUNTIME_BUDGET_MAX_SECONDS
            ),
            max_request_bytes=max_request_bytes,
            max_response_bytes=max_response_bytes,
            max_concurrent_invocations=_positive_int(source, "PLANE_AGENT_RUNTIME_MAX_CONCURRENT_INVOCATIONS", 1, 32),
            cpu_seconds=_positive_int(source, "PLANE_AGENT_RUNTIME_CPU_SECONDS", 300, RUNTIME_BUDGET_MAX_SECONDS),
            memory_bytes=_positive_int(
                source,
                "PLANE_AGENT_RUNTIME_MEMORY_BYTES",
                512 * 1024 * 1024,
                2 * 1024 * 1024 * 1024,
            ),
            pids_limit=_positive_int(source, "PLANE_AGENT_RUNTIME_PIDS_LIMIT", 128, 4096),
            network_policy="none",
            filesystem_policy="runtime-workdir-readonly",
            process_policy="single-invocation-child",
            credential_state_file=credential_state_file,
            provider_policy=provider_policy,
        )


@dataclass(frozen=True)
class ValidatedAgentRuntimeBoundary:
    """Validated runtime configuration plus the Plane host callback endpoint."""

    configuration: AgentRuntimeConfiguration
    host_url: str
    host_bind: str
    host_port: int


def validate_agent_runtime_boundary(environment: Mapping[str, str]) -> ValidatedAgentRuntimeBoundary:
    """Validate the complete shared runtime boundary without importing Django."""

    configuration = AgentRuntimeConfiguration.from_environment(environment)
    host_url = validate_runtime_host_url(environment.get("PLANE_AGENT_RUNTIME_HOST_URL"))
    host_bind = environment.get("PLANE_AGENT_RUNTIME_HOST_BIND", "0.0.0.0")
    if not host_bind or "\x00" in host_bind or len(host_bind) > 255:
        raise RuntimeConfigurationError("PLANE_AGENT_RUNTIME_HOST_BIND is invalid")
    try:
        host_port = int(environment.get("PLANE_AGENT_RUNTIME_HOST_PORT", "8091"))
    except (TypeError, ValueError) as exc:
        raise RuntimeConfigurationError("PLANE_AGENT_RUNTIME_HOST_PORT is invalid") from exc
    if not 1 <= host_port <= 65535:
        raise RuntimeConfigurationError("PLANE_AGENT_RUNTIME_HOST_PORT is outside its allowed range")
    return ValidatedAgentRuntimeBoundary(
        configuration=configuration,
        host_url=host_url,
        host_bind=host_bind,
        host_port=host_port,
    )


def runtime_settings_from_environment(environment: Mapping[str, str]) -> dict[str, object]:
    """Return the non-Django-specific settings shared by local and production Plane."""

    boundary = validate_agent_runtime_boundary(environment)
    configuration = boundary.configuration
    return {
        "PLANE_AGENT_RUNTIME_URL": configuration.url,
        "PLANE_AGENT_RUNTIME_SHARED_SECRET": configuration.shared_secret,
        "PLANE_AGENT_RUNTIME_HOST_URL": boundary.host_url,
        "PLANE_AGENT_RUNTIME_HOST_BIND": boundary.host_bind,
        "PLANE_AGENT_RUNTIME_HOST_PORT": boundary.host_port,
        "PLANE_AGENT_RUNTIME_DISPATCH_PATH": configuration.dispatch_path,
        "PLANE_AGENT_RUNTIME_LEDGER_PATH": configuration.ledger_path,
        "PLANE_AGENT_RUNTIME_SECRET_FILE": environment.get("PLANE_AGENT_RUNTIME_SECRET_FILE", ""),
        "PLANE_AGENT_RUNTIME_COMMAND": configuration.command,
        "PLANE_AGENT_RUNTIME_ENVIRONMENT": dict(configuration.child_environment),
        "PLANE_AGENT_RUNTIME_CREDENTIAL_RESOLVER": configuration.credential_resolver,
        "PLANE_AGENT_RUNTIME_CREDENTIAL_STATE_FILE": environment.get(
            "PLANE_AGENT_RUNTIME_CREDENTIAL_STATE_FILE", "/run/plane-agent-credentials/revocations.json"
        ),
        "PLANE_AGENT_RUNTIME_PROVIDER": (
            configuration.provider_policy.provider if configuration.provider_policy is not None else ""
        ),
        "PLANE_AGENT_RUNTIME_TIMEOUT_SECONDS": configuration.timeout_seconds,
        "PLANE_AGENT_RUNTIME_MAX_REQUEST_BYTES": configuration.max_request_bytes,
        "PLANE_AGENT_RUNTIME_MAX_RESPONSE_BYTES": configuration.max_response_bytes,
        "PLANE_AGENT_RUNTIME_MAX_CONCURRENT_INVOCATIONS": configuration.max_concurrent_invocations,
        "PLANE_AGENT_RUNTIME_CPU_SECONDS": configuration.cpu_seconds,
        "PLANE_AGENT_RUNTIME_MEMORY_BYTES": configuration.memory_bytes,
        "PLANE_AGENT_RUNTIME_PIDS_LIMIT": configuration.pids_limit,
        "PLANE_AGENT_RUNTIME_NETWORK_POLICY": configuration.network_policy,
        "PLANE_AGENT_RUNTIME_FILESYSTEM_POLICY": configuration.filesystem_policy,
        "PLANE_AGENT_RUNTIME_PROCESS_POLICY": configuration.process_policy,
    }


__all__ = [
    "AgentRuntimeConfiguration",
    "DEFAULT_HEALTH_PATH",
    "DEFAULT_DISPATCH_PATH",
    "DEFAULT_LEDGER_PATH",
    "DEFAULT_RUNTIME_COMMAND",
    "DEFAULT_SAFETY_STOP_FILE",
    "RUNTIME_BOOTSTRAP_MODULE",
    "RUNTIME_PROTOCOL",
    "RuntimeConfigurationError",
    "ValidatedAgentRuntimeBoundary",
    "runtime_settings_from_environment",
    "validate_agent_runtime_boundary",
    "validate_runtime_command",
]
