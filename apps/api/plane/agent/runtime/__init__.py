"""Plane Agent runtime exports with lazy imports across process boundaries."""

from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORTS: dict[str, tuple[str, str]] = {
    "RuntimeDispatchError": ("dispatch", "RuntimeDispatchError"),
    "RuntimeIngressError": ("dispatch", "RuntimeIngressError"),
    "RuntimeTransport": ("dispatch", "RuntimeTransport"),
    "dispatch_invocation": ("dispatch", "dispatch_invocation"),
    "ingest_runtime_frame": ("dispatch", "ingest_runtime_frame"),
    "SubprocessRuntimeTransport": ("subprocess", "SubprocessRuntimeTransport"),
    "HostBoundSubprocessRuntimeTransport": ("subprocess", "HostBoundSubprocessRuntimeTransport"),
    "RuntimeProcessPolicy": ("subprocess", "RuntimeProcessPolicy"),
    "RemoteRuntimeTransport": ("remote", "RemoteRuntimeTransport"),
    "RuntimeHostEndpoint": ("remote", "RuntimeHostEndpoint"),
    "RUNTIME_DISPATCH_PROTOCOL": ("remote", "RUNTIME_DISPATCH_PROTOCOL"),
    "DEFAULT_LEASE_SECONDS": ("supervisor", "DEFAULT_LEASE_SECONDS"),
    "RuntimeLeaseBusy": ("supervisor", "RuntimeLeaseBusy"),
    "RuntimeSupervisorError": ("supervisor", "RuntimeSupervisorError"),
    "SupervisorResult": ("supervisor", "SupervisorResult"),
    "request_runtime_cancellation": ("supervisor", "request_runtime_cancellation"),
    "run_runtime_invocation": ("supervisor", "run_runtime_invocation"),
    "terminalize_pre_dispatch_failure": ("supervisor", "terminalize_pre_dispatch_failure"),
    "runtime_invocation_cancelled": ("supervisor", "runtime_invocation_cancelled"),
    "runtime_invocation_cancellation_requested": ("supervisor", "runtime_invocation_cancellation_requested"),
    "HOST_PROTOCOL": ("host_rpc", "HOST_PROTOCOL"),
    "PlaneGatewayHostPort": ("host_rpc", "PlaneGatewayHostPort"),
    "PlaneHostCall": ("host_rpc", "PlaneHostCall"),
    "PlaneHostRPCError": ("host_rpc", "PlaneHostRPCError"),
    "PlaneHostResult": ("host_rpc", "PlaneHostResult"),
    "PlaneHostServer": ("host_rpc", "PlaneHostServer"),
    "PlaneHostHTTPClient": ("host_rpc", "PlaneHostHTTPClient"),
    "PlaneHostHTTPServer": ("host_rpc", "PlaneHostHTTPServer"),
    "build_gateway_host_port": ("host_rpc", "build_gateway_host_port"),
    "AgentRuntimeConfiguration": ("config", "AgentRuntimeConfiguration"),
    "RuntimeConfigurationError": ("config", "RuntimeConfigurationError"),
    "DEFAULT_HEALTH_PATH": ("config", "DEFAULT_HEALTH_PATH"),
    "DEFAULT_DISPATCH_PATH": ("config", "DEFAULT_DISPATCH_PATH"),
    "DEFAULT_LEDGER_PATH": ("config", "DEFAULT_LEDGER_PATH"),
    "DEFAULT_RUNTIME_COMMAND": ("config", "DEFAULT_RUNTIME_COMMAND"),
    "DEFAULT_SAFETY_STOP_FILE": ("config", "DEFAULT_SAFETY_STOP_FILE"),
    "RUNTIME_BOOTSTRAP_MODULE": ("config", "RUNTIME_BOOTSTRAP_MODULE"),
    "RUNTIME_PROTOCOL": ("config", "RUNTIME_PROTOCOL"),
    "validate_runtime_host_url": ("config", "validate_runtime_host_url"),
    "validate_runtime_command": ("config", "validate_runtime_command"),
    "runtime_transport_kind": ("config", "runtime_transport_kind"),
    "CredentialLease": ("credentials", "CredentialLease"),
    "RuntimeCredentialBroker": ("credentials", "RuntimeCredentialBroker"),
    "RuntimeCredentialError": ("credentials", "RuntimeCredentialError"),
    "CommandCredentialResolver": ("credentials", "CommandCredentialResolver"),
    "credential_source_from_configuration": ("credentials", "credential_source_from_configuration"),
    "validate_credential_lease_metadata": ("credentials", "validate_credential_lease_metadata"),
    "PROVIDER_RELAY_PROTOCOL": ("provider_egress", "PROVIDER_RELAY_PROTOCOL"),
    "PROVIDER_RELAY_HOST": ("provider_egress", "PROVIDER_RELAY_HOST"),
    "ProviderRelayAudit": ("provider_egress", "ProviderRelayAudit"),
    "ProviderRelayBinding": ("provider_egress", "ProviderRelayBinding"),
    "ProviderRelayDescriptor": ("provider_egress", "ProviderRelayDescriptor"),
    "ProviderRelayError": ("provider_egress", "ProviderRelayError"),
    "ProviderRelayPolicy": ("provider_egress", "ProviderRelayPolicy"),
    "ProviderRelayServer": ("provider_egress", "ProviderRelayServer"),
    "ProviderRequest": ("provider_egress", "ProviderRequest"),
    "ProviderResponse": ("provider_egress", "ProviderResponse"),
    "RuntimeHealthState": ("health", "RuntimeHealthState"),
    "RuntimeHealthStatus": ("health", "RuntimeHealthStatus"),
    "RuntimeSafetyStopError": ("health", "RuntimeSafetyStopError"),
    "RuntimeSafetyController": ("health", "RuntimeSafetyController"),
    "operator_health_readback": ("health", "operator_health_readback"),
    "request_operator_safety_stop": ("health", "request_operator_safety_stop"),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(f"{__name__}.{module_name}"), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()).union(_EXPORTS))


__all__ = list(_EXPORTS)
