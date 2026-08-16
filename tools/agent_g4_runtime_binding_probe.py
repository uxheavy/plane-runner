"""Probe the API-side runtime secret binding without dispatching an invocation."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import stat
import sys
import types
from pathlib import Path
from typing import NoReturn
from urllib.parse import urlsplit


SCRIPT_FILE = globals().get("__file__", "<stdin>")
if SCRIPT_FILE != "<stdin>":
    api_root = Path(SCRIPT_FILE).resolve().parents[1] / "apps" / "api"
else:
    api_root = Path.cwd()
if str(api_root) not in sys.path:
    sys.path.insert(0, str(api_root))

# The provider-free host regression imports only the dependency-free runtime
# seam. Avoid Plane's package bootstrap there so it does not need unrelated
# Celery/Django service dependencies. The exact API-container probe keeps the
# real Plane package and loads production Django settings below.
if SCRIPT_FILE != "<stdin>":
    plane_package = types.ModuleType("plane")
    plane_package.__path__ = [str(api_root / "plane")]
    agent_package = types.ModuleType("plane.agent")
    agent_package.__path__ = [str(api_root / "plane" / "agent")]
    runtime_package = types.ModuleType("plane.agent.runtime")
    runtime_package.__path__ = [str(api_root / "plane" / "agent" / "runtime")]
    sys.modules.update(
        {
            "plane": plane_package,
            "plane.agent": agent_package,
            "plane.agent.runtime": runtime_package,
        }
    )

from plane.agent.runtime.config import runtime_settings_from_environment, runtime_transport_kind  # noqa: E402

try:
    from plane.agent.runtime.remote import RemoteRuntimeTransport  # noqa: E402
except TypeError:
    # The macOS system Python used by the provider-free host checks is 3.9,
    # while the API image runs the repository's supported Python. The remote
    # transport itself is dependency-free; stub only its unused credential
    # annotations so this check can still construct the exact transport class.
    if SCRIPT_FILE == "<stdin>" or sys.version_info >= (3, 10):
        raise
    sys.modules.pop("plane.agent.runtime.remote", None)
    sys.modules.pop("plane.agent.runtime.credentials", None)
    credentials_stub = types.ModuleType("plane.agent.runtime.credentials")
    credentials_stub.RuntimeCredentialBroker = object
    credentials_stub.RuntimeCredentialError = ValueError
    credentials_stub.credential_failure_subreason = lambda error: "runtime_configuration_rejected"
    sys.modules["plane.agent.runtime.credentials"] = credentials_stub
    from plane.agent.runtime.remote import RemoteRuntimeTransport  # noqa: E402


def _fail(message: str) -> "NoReturn":
    raise SystemExit(f"runtime binding probe failed: {message}")


def main() -> None:
    secret_path_value = os.environ.get("PLANE_AGENT_RUNTIME_SECRET_FILE", "")
    if not secret_path_value:
        _fail("secret file path is not configured")
    secret_path = Path(secret_path_value)
    metadata = os.stat(secret_path, follow_symlinks=False)
    if not stat.S_ISREG(metadata.st_mode):
        _fail("secret target is not a regular file")
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        _fail("secret target mode is not 0600")
    if metadata.st_uid not in {0, os.geteuid()}:
        _fail("secret target is not owned by root or the probe process")

    secret_bytes = secret_path.read_bytes()
    secret_digest = hashlib.sha256(secret_bytes).hexdigest()
    if len(secret_digest) != 64:
        _fail("secret digest could not be classified")

    settings = runtime_settings_from_environment(os.environ)
    runtime_url = settings["PLANE_AGENT_RUNTIME_URL"]
    shared_secret = settings["PLANE_AGENT_RUNTIME_SHARED_SECRET"]
    dispatch_path = settings["PLANE_AGENT_RUNTIME_DISPATCH_PATH"]
    timeout_seconds = settings["PLANE_AGENT_RUNTIME_TIMEOUT_SECONDS"]
    max_request_bytes = settings["PLANE_AGENT_RUNTIME_MAX_REQUEST_BYTES"]
    max_response_bytes = settings["PLANE_AGENT_RUNTIME_MAX_RESPONSE_BYTES"]
    if not all(isinstance(value, str) for value in (runtime_url, shared_secret, dispatch_path)):
        _fail("runtime settings did not materialize as strings")
    if not isinstance(timeout_seconds, (int, float)) or not isinstance(max_request_bytes, int):
        _fail("runtime settings did not materialize with bounded transport values")
    if not isinstance(max_response_bytes, int):
        _fail("runtime response bound did not materialize as an integer")

    settings_source = "parser"
    if SCRIPT_FILE == "<stdin>":
        if os.environ.get("DJANGO_SETTINGS_MODULE") != "plane.settings.production":
            _fail("API container did not select production Django settings")
        import django

        django.setup()
        from django.conf import settings as django_settings

        django_runtime_url = django_settings.PLANE_AGENT_RUNTIME_URL
        django_shared_secret = django_settings.PLANE_AGENT_RUNTIME_SHARED_SECRET
        django_dispatch_path = django_settings.PLANE_AGENT_RUNTIME_DISPATCH_PATH
        if (django_runtime_url, django_shared_secret, django_dispatch_path) != (
            runtime_url,
            shared_secret,
            dispatch_path,
        ):
            _fail("Django settings did not preserve the staged runtime boundary")
        runtime_url = django_runtime_url
        shared_secret = django_shared_secret
        dispatch_path = django_dispatch_path
        settings_source = "django"

    parsed_url = urlsplit(runtime_url)
    if not parsed_url.hostname:
        _fail("runtime URL has no host")
    try:
        socket.getaddrinfo(parsed_url.hostname, parsed_url.port or 80, type=socket.SOCK_STREAM)
    except OSError:
        _fail(f"runtime host is not resolvable: {parsed_url.hostname}")

    transport_kind = runtime_transport_kind(runtime_url, shared_secret)
    if transport_kind != "remote":
        _fail(f"runtime transport kind was {transport_kind}")
    transport = RemoteRuntimeTransport(
        runtime_url=runtime_url,
        shared_secret=shared_secret,
        dispatch_path=dispatch_path,
        timeout_seconds=timeout_seconds,
        max_request_bytes=max_request_bytes,
        max_response_bytes=max_response_bytes,
    )
    if type(transport).__name__ != "RemoteRuntimeTransport":
        _fail("runtime transport class was not RemoteRuntimeTransport")

    print(
        json.dumps(
            {
                "runtimeHost": parsed_url.hostname,
                "secretBytes": len(secret_bytes),
                "secretHashClass": "sha256-not-emitted",
                "secretMode": "0600",
                "secretOwnerGid": metadata.st_gid,
                "secretOwnerUid": metadata.st_uid,
                "secretPath": str(secret_path),
                "settingsSource": settings_source,
                "transportClass": type(transport).__name__,
                "transportKind": transport_kind,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
