#!/usr/bin/env python3
"""Validate the ordinary and agent-enabled local Compose contracts safely."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping


BASE_SERVICES = {
    "api",
    "beat-worker",
    "migrator",
    "plane-db",
    "plane-minio",
    "plane-mq",
    "plane-redis",
    "proxy",
    "worker",
}
RUNTIME_IMAGE = "uxheavy/plane-agent-runtime:hermes-e573a466-g4-ff8cd9c5"
RUNTIME_STATE_VOLUME = "agent_runtime_credential_state"
RUNTIME_SECRET_FILE = "/run/secrets/plane_agent_runtime"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def mapping(value: object, name: str) -> Mapping[str, object]:
    require(isinstance(value, Mapping), f"{name} must be an object")
    return value


def service(model: Mapping[str, object], name: str) -> Mapping[str, object]:
    services = mapping(model.get("services"), "services")
    require(name in services, f"service {name} is missing")
    return mapping(services[name], f"service {name}")


def environment(service_model: Mapping[str, object], name: str) -> Mapping[str, object]:
    values = service_model.get("environment", {})
    if isinstance(values, list):
        values = {item.split("=", 1)[0]: item.split("=", 1)[1] for item in values if "=" in item}
    return mapping(values, f"{name}.environment")


def list_values(service_model: Mapping[str, object], field: str) -> list[object]:
    values = service_model.get(field, [])
    require(isinstance(values, list), f"{field} must be a list")
    return values


def has_secret(service_model: Mapping[str, object]) -> bool:
    return any(
        isinstance(value, Mapping) and value.get("source") == "plane_agent_runtime"
        for value in list_values(service_model, "secrets")
    )


def has_credential_state_volume(service_model: Mapping[str, object]) -> bool:
    return any(
        isinstance(value, Mapping)
        and value.get("type") == "volume"
        and value.get("source") == RUNTIME_STATE_VOLUME
        and value.get("target") == "/run/plane-agent-credentials"
        for value in list_values(service_model, "volumes")
    )


def assert_common(model: Mapping[str, object], *, agent_enabled: bool) -> None:
    services = mapping(model.get("services"), "services")
    expected = BASE_SERVICES | ({"agent-runtime"} if agent_enabled else set())
    require(set(services) == expected, f"unexpected local service set for agent_enabled={agent_enabled}")

    for name in ("api", "worker", "beat-worker"):
        values = environment(service(model, name), name)
        require(values.get("DJANGO_SETTINGS_MODULE") == "plane.settings.local", f"{name} must select local settings")
        require(values.get("PLANE_AGENT_RUNTIME_ENABLED") == ("1" if agent_enabled else "0"), f"{name} runtime mode is wrong")
        require("PLANE_AGENT_RUNTIME_SECRET" not in values, f"{name} must not receive the runtime secret as an environment value")
        require(values.get("PLANE_AGENT_RUNTIME_SECRET_FILE") == RUNTIME_SECRET_FILE, f"{name} must use the runtime secret file seam")
        require(has_secret(service(model, name)), f"{name} must receive the Compose secret")
        if name in {"api", "worker"}:
            app_networks = mapping(service(model, name).get("networks"), f"{name}.networks")
            require(set(app_networks) == {"dev_env", "agent_runtime_internal"}, f"{name} network boundary is wrong")

    for name in ("api", "worker"):
        require(has_credential_state_volume(service(model, name)), f"{name} must mount credential state")

    migrator_environment = environment(service(model, "migrator"), "migrator")
    require(migrator_environment.get("DJANGO_SETTINGS_MODULE") == "plane.settings.local", "migrator must select local settings")
    require(migrator_environment.get("PLANE_DB_MIGRATION_MODE") == "1", "migrator must use explicit migration mode")
    require(migrator_environment.get("DATABASE_RUNTIME_URL") == "", "migrator must not receive the runtime database URL")

    volumes = mapping(model.get("volumes"), "volumes")
    require(RUNTIME_STATE_VOLUME in volumes, "credential state volume is missing")
    secrets = mapping(model.get("secrets"), "secrets")
    runtime_secret = mapping(secrets.get("plane_agent_runtime"), "plane_agent_runtime")
    require(str(runtime_secret.get("file", "")).endswith("/.plane-agent-runtime.secret"), "runtime secret must come from the generated file seam")

    if not agent_enabled:
        return

    networks = mapping(model.get("networks"), "networks")
    internal = mapping(networks.get("agent_runtime_internal"), "agent_runtime_internal")
    require(internal.get("internal") is True, "runtime network must be internal")

    runtime = service(model, "agent-runtime")
    require(runtime.get("image") == RUNTIME_IMAGE, "agent runtime must reuse the pinned community image")
    require(runtime.get("profiles") == ["agent"], "agent runtime must be opt-in through the agent profile")
    require(runtime.get("entrypoint") == ["python3", "-m", "plane.agent.runtime.service"], "agent runtime must select the runtime service module")
    require(runtime.get("command") == [], "agent runtime must not append arguments to the image bootstrap entrypoint")
    require(runtime.get("read_only") is True, "agent runtime filesystem must be read-only")
    require("env_file" not in runtime, "agent runtime must not inherit the Plane application env file")
    require("ports" not in runtime, "agent runtime must not publish a host port")
    runtime_networks = mapping(runtime.get("networks"), "agent-runtime.networks")
    require(set(runtime_networks) == {"agent_runtime_internal"}, "agent runtime must use the internal network only")
    runtime_values = environment(runtime, "agent-runtime")
    require(runtime_values.get("PLANE_AGENT_RUNTIME_SECRET_FILE") == RUNTIME_SECRET_FILE, "agent runtime must use the mounted secret file")
    require("PLANE_AGENT_RUNTIME_SECRET" not in runtime_values, "agent runtime must not receive a direct secret environment value")
    require(not any(key.startswith(("DATABASE", "AWS_", "POSTGRES_")) for key in runtime_values), "agent runtime must not receive Plane storage credentials")
    require(has_secret(runtime), "agent runtime must receive the mounted runtime secret")
    require("/run/plane-agent-runtime:rw,noexec,nosuid,nodev,size=1m" in list_values(runtime, "tmpfs"), "agent runtime state mount is missing")
    require("api" in mapping(runtime.get("depends_on"), "agent-runtime.depends_on"), "agent runtime must wait for api")
    require("worker" in mapping(runtime.get("depends_on"), "agent-runtime.depends_on"), "agent runtime must wait for worker")
    require("healthcheck" in runtime, "agent runtime readiness healthcheck is missing")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("ordinary", "agent"), required=True)
    args = parser.parse_args()
    try:
        model = json.load(sys.stdin)
        require(isinstance(model, Mapping), "Compose model must be an object")
        assert_common(model, agent_enabled=args.mode == "agent")
    except (AssertionError, json.JSONDecodeError, TypeError) as exc:
        print(f"Local development topology contract mismatch: {exc}", file=sys.stderr)
        return 1
    print(f"Local {args.mode} Compose topology contract is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
