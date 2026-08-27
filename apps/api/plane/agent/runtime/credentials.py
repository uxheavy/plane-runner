# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Disposable, invocation-bound runtime credential leases.

The broker keeps only digests and lease metadata.  The credential resolver is
the deployment-owned source of current disposable credentials; raw values are
returned to the already-isolated child only for the active invocation.
"""

from __future__ import annotations

import hashlib
import base64
import json
import math
import os
import re
import secrets
import subprocess
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contracts import RUNTIME_BUDGET_MAX_SECONDS


RUNTIME_CREDENTIAL_LEASE_GRACE_SECONDS = 1.0
RUNTIME_CREDENTIAL_LEASE_MAX_SECONDS = RUNTIME_BUDGET_MAX_SECONDS + RUNTIME_CREDENTIAL_LEASE_GRACE_SECONDS

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows has no supported production runtime
    fcntl = None


class RuntimeCredentialError(ValueError):
    """A credential lease is absent, expired, revoked, rotated, or unbound."""


def credential_failure_subreason(error: RuntimeCredentialError) -> str:
    """Map credential failures to a finite diagnostic vocabulary.

    Exception text remains local-only.  The transport may expose only this
    bounded category at the Plane diagnostic boundary.
    """

    message = str(error).casefold()
    if "reference is not allowed" in message:
        return "credential_reference_not_allowed"
    if "resolver failed" in message:
        return "credential_resolver_failed"
    if "resolver returned" in message or "resolver must return" in message:
        return "credential_resolver_output_invalid"
    if "requires trusted resolver refresh" in message:
        return "credential_source_requires_refresh"
    if "state is unavailable" in message:
        return "credential_state_unavailable"
    if "state is invalid" in message:
        return "credential_state_invalid"
    if "metadata is invalid" in message:
        return "credential_lease_metadata_invalid"
    if "bound to another" in message or "binding does not match" in message:
        return "credential_lease_binding"
    if "expired" in message:
        return "credential_lease_expired"
    if "revoked" in message:
        return "credential_lease_revoked"
    if "rotated" in message:
        return "credential_lease_rotated"
    if "oversized" in message or "too many values" in message:
        return "credential_source_oversized"
    if "source" in message and (
        "invalid" in message or "not valid" in message or "fields" in message
    ):
        return "credential_source_invalid"
    if "source" in message or "unavailable" in message:
        return "credential_source_unavailable"
    return "runtime_configuration_rejected"


# Compose/Swarm mounts the operator-owned provider secret at this fixed path.
# The packaged resolver never accepts a caller-selected source path.
DEPLOYMENT_CREDENTIAL_SOURCE_PATH = "/run/secrets/plane_agent_provider_credentials"
DEPLOYMENT_CREDENTIAL_ALLOWED_REFS = frozenset({"runtime"})
# The deployment source is deliberately provider-neutral.  The legacy xAI
# spelling remains accepted for existing deployments, while the live
# ChatGPT route may provide the standard OpenAI key spelling or one opaque
# single-line token.  The broker still exposes only the canonical api_key
# value to the trusted runtime parent.
_DEPLOYMENT_CREDENTIAL_KEYS = frozenset({"API_KEY", "OPENAI_API_KEY", "XAI_API_KEY", "api_key"})
# Keep accepting the older shape without host metadata. The current Codex
# document is exact: its API-key placeholder is null and auth mode is chatgpt.
_CODEX_AUTH_DOCUMENT_KEYS = frozenset({"last_refresh", "tokens"})
_CODEX_AUTH_CURRENT_DOCUMENT_KEYS = frozenset(
    {"OPENAI_API_KEY", "auth_mode", "last_refresh", "tokens"}
)
_CODEX_AUTH_DOCUMENT_SHAPES = (_CODEX_AUTH_DOCUMENT_KEYS, _CODEX_AUTH_CURRENT_DOCUMENT_KEYS)
_CODEX_AUTH_TOKEN_KEYS = frozenset({"access_token", "account_id", "id_token", "refresh_token"})
_CODEX_AUTH_MAX_FUTURE_SKEW_SECONDS = 60
_CODEX_ACCESS_TOKEN_MAX_LIFETIME_SECONDS = 14 * 24 * 60 * 60
_CODEX_ACCESS_TOKEN_MIN_REMAINING_SECONDS = 60
_CODEX_ACCESS_TOKEN_PAYLOAD_MAX_BYTES = 8 * 1024
_DEPLOYMENT_CREDENTIAL_MAX_BYTES = 64 * 1024
_DEPLOYMENT_CREDENTIAL_MAX_VALUE_BYTES = 16 * 1024
_DEPLOYMENT_ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _bounded_deployment_secret(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeCredentialError("deployment credential source is unavailable")
    if len(value.encode("utf-8")) > _DEPLOYMENT_CREDENTIAL_MAX_VALUE_BYTES:
        raise RuntimeCredentialError("deployment credential source value is oversized")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise RuntimeCredentialError("deployment credential source value is invalid")
    return value


def _parse_deployment_dotenv(text: str) -> str:
    lines: list[str] = []
    for raw_line in text.splitlines():
        if len(raw_line.encode("utf-8")) > _DEPLOYMENT_CREDENTIAL_MAX_VALUE_BYTES:
            raise RuntimeCredentialError("deployment credential source line is oversized")
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        lines.append(line)
    if len(lines) == 1 and "=" not in lines[0]:
        if any(char.isspace() for char in lines[0]):
            raise RuntimeCredentialError("deployment credential source is not valid dotenv")
        return _bounded_deployment_secret(lines[0])

    found: str | None = None
    for line in lines:
        if "=" not in line:
            raise RuntimeCredentialError("deployment credential source is not valid dotenv")
        key, value = line.split("=", 1)
        key = key.strip()
        if _DEPLOYMENT_ENV_KEY.fullmatch(key) is None:
            raise RuntimeCredentialError("deployment credential source contains an invalid key")
        value = value.strip()
        if value.startswith('"'):
            try:
                parsed = json.loads(value)
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise RuntimeCredentialError("deployment credential source contains an invalid value") from exc
            if not isinstance(parsed, str):
                raise RuntimeCredentialError("deployment credential source contains an invalid value")
            value = parsed
        elif value.startswith("'"):
            if len(value) < 2 or not value.endswith("'"):
                raise RuntimeCredentialError("deployment credential source contains an invalid value")
            value = value[1:-1]
        if key not in _DEPLOYMENT_CREDENTIAL_KEYS:
            continue
        if found is not None:
            raise RuntimeCredentialError("deployment credential source contains a duplicate key")
        found = _bounded_deployment_secret(value)
    if found is None:
        raise RuntimeCredentialError("deployment credential source does not contain the configured provider")
    return found


def _parse_codex_auth_document(value: object) -> str:
    if not isinstance(value, dict) or frozenset(value) not in _CODEX_AUTH_DOCUMENT_SHAPES:
        raise RuntimeCredentialError("deployment credential JSON fields are invalid")
    if "OPENAI_API_KEY" in value and (
        value["OPENAI_API_KEY"] is not None or value.get("auth_mode") != "chatgpt"
    ):
        raise RuntimeCredentialError("deployment credential JSON fields are invalid")
    last_refresh = value["last_refresh"]
    if not isinstance(last_refresh, str) or not last_refresh.strip():
        raise RuntimeCredentialError("deployment credential JSON fields are invalid")
    if len(last_refresh.encode("utf-8")) > _DEPLOYMENT_CREDENTIAL_MAX_VALUE_BYTES:
        raise RuntimeCredentialError("deployment credential source value is oversized")
    if not last_refresh.endswith("Z"):
        raise RuntimeCredentialError("deployment credential JSON fields are invalid")
    try:
        refreshed_at = datetime.fromisoformat(f"{last_refresh[:-1]}+00:00")
    except ValueError as exc:
        raise RuntimeCredentialError("deployment credential JSON fields are invalid") from exc
    if refreshed_at.tzinfo != timezone.utc:
        raise RuntimeCredentialError("deployment credential JSON fields are invalid")
    tokens = value["tokens"]
    if not isinstance(tokens, dict) or set(tokens) != _CODEX_AUTH_TOKEN_KEYS:
        raise RuntimeCredentialError("deployment credential JSON fields are invalid")
    for token_name in _CODEX_AUTH_TOKEN_KEYS:
        _bounded_deployment_secret(tokens[token_name])
    now = time.time()
    if refreshed_at.timestamp() - now > _CODEX_AUTH_MAX_FUTURE_SKEW_SECONDS:
        raise RuntimeCredentialError(
            "deployment credential source requires trusted resolver refresh"
        )
    access_token = _bounded_deployment_secret(tokens["access_token"])
    segments = access_token.split(".")
    if len(segments) != 3 or any(not segment for segment in segments):
        raise RuntimeCredentialError("deployment credential source requires trusted resolver refresh")
    payload_segment = segments[1]
    if len(payload_segment) > (_CODEX_ACCESS_TOKEN_PAYLOAD_MAX_BYTES * 4 // 3) + 4:
        raise RuntimeCredentialError("deployment credential source requires trusted resolver refresh")
    try:
        payload = base64.b64decode(
            payload_segment + "=" * (-len(payload_segment) % 4),
            altchars=b"-_",
            validate=True,
        )
        if len(payload) > _CODEX_ACCESS_TOKEN_PAYLOAD_MAX_BYTES:
            raise ValueError("oversized JWT payload")

        def reject_duplicate_claims(pairs: list[tuple[str, object]]) -> dict[str, object]:
            claims: dict[str, object] = {}
            for key, claim in pairs:
                if key in claims:
                    raise ValueError("duplicate JWT claim")
                claims[key] = claim
            return claims

        claims = json.loads(payload, object_pairs_hook=reject_duplicate_claims)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeCredentialError(
            "deployment credential source requires trusted resolver refresh"
        ) from exc
    if not isinstance(claims, dict):
        raise RuntimeCredentialError("deployment credential source requires trusted resolver refresh")
    issued_at = claims.get("iat")
    expires_at = claims.get("exp")
    if (
        isinstance(issued_at, bool)
        or not isinstance(issued_at, int)
        or isinstance(expires_at, bool)
        or not isinstance(expires_at, int)
        or issued_at > now + _CODEX_AUTH_MAX_FUTURE_SKEW_SECONDS
        or expires_at <= now + _CODEX_ACCESS_TOKEN_MIN_REMAINING_SECONDS
        or expires_at <= issued_at
        or expires_at - issued_at > _CODEX_ACCESS_TOKEN_MAX_LIFETIME_SECONDS
    ):
        raise RuntimeCredentialError("deployment credential source requires trusted resolver refresh")
    # Signature verification remains provider-owned. This trusted-host check
    # only fails fast on malformed or unusable token lifetime metadata.
    return access_token


def _parse_deployment_credential_document(raw: bytes) -> str:
    if len(raw) > _DEPLOYMENT_CREDENTIAL_MAX_BYTES:
        raise RuntimeCredentialError("deployment credential source is oversized")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise RuntimeCredentialError("deployment credential source is not UTF-8") from exc
    stripped = text.lstrip()
    if stripped.startswith("{"):
        def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate key")
                result[key] = value
            return result

        try:
            value = json.loads(stripped, object_pairs_hook=reject_duplicate_keys)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeCredentialError("deployment credential source is not valid JSON") from exc
        if isinstance(value, dict) and frozenset(value) in _CODEX_AUTH_DOCUMENT_SHAPES:
            return _parse_codex_auth_document(value)
        if not isinstance(value, dict) or len(value) != 1:
            raise RuntimeCredentialError("deployment credential JSON fields are invalid")
        credential_key, credential_value = next(iter(value.items()))
        if credential_key not in _DEPLOYMENT_CREDENTIAL_KEYS:
            raise RuntimeCredentialError("deployment credential JSON fields are invalid")
        return _bounded_deployment_secret(credential_value)
    return _parse_deployment_dotenv(text)


def resolve_deployment_credential(credential_ref: str) -> dict[str, str]:
    """Resolve the one approved provider credential for the broker subprocess."""

    if not isinstance(credential_ref, str) or credential_ref not in DEPLOYMENT_CREDENTIAL_ALLOWED_REFS:
        raise RuntimeCredentialError("credential reference is not allowed")
    try:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(DEPLOYMENT_CREDENTIAL_SOURCE_PATH, flags)
    except OSError as exc:
        raise RuntimeCredentialError("deployment credential source is unavailable") from exc
    try:
        with os.fdopen(descriptor, "rb") as source:
            descriptor = -1
            raw = source.read(_DEPLOYMENT_CREDENTIAL_MAX_BYTES + 1)
    except OSError as exc:
        raise RuntimeCredentialError("deployment credential source is unavailable") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return {"api_key": _parse_deployment_credential_document(raw)}


@dataclass(frozen=True)
class CredentialLease:
    """Non-secret lease metadata returned to Plane and never the raw secret."""

    lease_id: str
    agent_ref: str
    credential_ref: str
    invocation_ref: str | None
    generation: int
    issued_at: float
    expires_at: float
    credential_digest: str
    rotation_generation: int = 0
    revoked_at: float | None = None

    def public_metadata(self) -> dict[str, object]:
        """Return only the lease facts the trusted runtime needs to recheck.

        The credential values and their digest are intentionally absent.  The
        digest remains host-side evidence; the runtime only needs identity,
        expiry, revocation, and rotation binding for relay admission.
        """

        return {
            "leaseId": self.lease_id,
            "agentRef": self.agent_ref,
            "credentialRef": self.credential_ref,
            "invocationRef": self.invocation_ref,
            "generation": self.generation,
            "issuedAt": self.issued_at,
            "expiresAt": self.expires_at,
            "rotationGeneration": self.rotation_generation,
        }


CredentialSource = Callable[[str], Mapping[str, str]] | Mapping[str, Mapping[str, str]]


class CommandCredentialResolver:
    """Resolve one credential reference through a deployment-owned executable.

    The executable is the only production source of provider credentials.  Its
    stdout is consumed in the supervisor process and never placed in settings,
    product state, or the runtime container environment.
    """

    def __init__(self, executable: str, *, timeout_seconds: float = 5.0) -> None:
        if not isinstance(executable, str) or not executable.startswith("/") or "\x00" in executable:
            raise RuntimeCredentialError("credential resolver executable is invalid")
        if len(executable.encode("utf-8")) > 512:
            raise RuntimeCredentialError("credential resolver executable is too long")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0:
            raise RuntimeCredentialError("credential resolver timeout is invalid")
        self.executable = executable
        self.timeout_seconds = float(timeout_seconds)

    def __call__(self, credential_ref: str) -> Mapping[str, str]:
        if not isinstance(credential_ref, str) or not credential_ref or "\x00" in credential_ref:
            raise RuntimeCredentialError("credential reference is invalid")
        try:
            result = subprocess.run(
                [self.executable, credential_ref],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env={"PATH": "/usr/bin:/bin"},
                check=True,
                timeout=self.timeout_seconds,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeCredentialError("deployment credential resolver failed") from exc
        if len(result.stdout) > 128 * 1024:
            raise RuntimeCredentialError("deployment credential resolver output is oversized")
        try:
            value = json.loads(result.stdout.decode("utf-8"))
        except (UnicodeDecodeError, TypeError, ValueError) as exc:
            raise RuntimeCredentialError("deployment credential resolver returned invalid JSON") from exc
        if not isinstance(value, dict):
            raise RuntimeCredentialError("deployment credential resolver must return an object")
        return value


def credential_source_from_configuration(configuration: object) -> CredentialSource:
    """Build the host-only resolver from settings or a test-owned source."""

    if isinstance(configuration, str):
        if not configuration.startswith("command:"):
            raise RuntimeCredentialError("credential resolver must use command:/absolute/path")
        executable = configuration.removeprefix("command:")
        if not executable or any(char.isspace() for char in executable):
            raise RuntimeCredentialError("credential resolver executable is invalid")
        return CommandCredentialResolver(executable)
    if callable(configuration) or isinstance(configuration, Mapping):
        return configuration
    raise RuntimeCredentialError("deployment credential resolver is not configured")


class RuntimeCredentialBroker:
    """Issue, bind, rotate, resolve, and revoke short-lived credential leases."""

    def __init__(
        self,
        source: CredentialSource,
        *,
        ttl_seconds: float = 300.0,
        clock: Callable[[], float] | None = None,
        state_file: str | os.PathLike[str] | None = None,
    ) -> None:
        if not callable(source) and not isinstance(source, Mapping):
            raise TypeError("credential source must be callable or a mapping")
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, (int, float)):
            raise ValueError("credential lease TTL must be numeric")
        if ttl_seconds <= 0 or ttl_seconds > RUNTIME_CREDENTIAL_LEASE_MAX_SECONDS:
            raise ValueError("credential lease TTL is outside its allowed range")
        self._source = source
        self._ttl_seconds = float(ttl_seconds)
        self._clock = clock or time.time
        self._lock = threading.RLock()
        self._leases: dict[str, CredentialLease] = {}
        self._generations: dict[str, int] = {}
        self._state_file = Path(state_file) if state_file else None
        if self._state_file is not None and not self._state_file.is_absolute():
            raise RuntimeCredentialError("credential state file must be absolute")

    def issue(
        self,
        *,
        agent_ref: str,
        credential_ref: str,
        invocation_ref: str | None = None,
    ) -> tuple[CredentialLease, dict[str, str]]:
        self._validate_ref(agent_ref, "agent_ref")
        self._validate_ref(credential_ref, "credential_ref")
        if invocation_ref is not None:
            self._validate_ref(invocation_ref, "invocation_ref")
        with self._lock:
            self._refresh_external_state()
            credentials = self._load_current(credential_ref)
            generation = self._generations.get(credential_ref, 0) + 1
            self._generations[credential_ref] = generation
            state = self._read_state()
            rotation_generation = int(state["rotationGeneration"].get(credential_ref, 0))
            now = self._now()
            lease = CredentialLease(
                lease_id=secrets.token_urlsafe(24),
                agent_ref=agent_ref,
                credential_ref=credential_ref,
                invocation_ref=invocation_ref,
                generation=generation,
                issued_at=now,
                expires_at=now + self._ttl_seconds,
                credential_digest=self._digest(credentials),
                rotation_generation=rotation_generation,
            )
            self._leases[lease.lease_id] = lease
            return lease, credentials

    def bind(self, lease_id: str, *, invocation_ref: str) -> CredentialLease:
        self._validate_lease_id(lease_id)
        self._validate_ref(invocation_ref, "invocation_ref")
        with self._lock:
            self._refresh_external_state()
            lease = self._active_lease(lease_id)
            if lease.invocation_ref is not None and lease.invocation_ref != invocation_ref:
                raise RuntimeCredentialError("credential lease is bound to another invocation")
            bound = replace(lease, invocation_ref=invocation_ref)
            self._leases[lease_id] = bound
            return bound

    def resolve(self, lease_id: str, *, agent_ref: str, invocation_ref: str) -> dict[str, str]:
        self._validate_lease_id(lease_id)
        self._validate_ref(agent_ref, "agent_ref")
        self._validate_ref(invocation_ref, "invocation_ref")
        with self._lock:
            self._refresh_external_state()
            lease = self._active_lease(lease_id)
            if lease.agent_ref != agent_ref or lease.invocation_ref != invocation_ref:
                raise RuntimeCredentialError("credential lease binding does not match the invocation")
            credentials = self._load_current(lease.credential_ref)
            if self._digest(credentials) != lease.credential_digest:
                raise RuntimeCredentialError("credential lease was rotated")
            return credentials

    def revoke(self, lease_id: str) -> CredentialLease:
        self._validate_lease_id(lease_id)
        with self._lock:
            lease = self._active_lease(lease_id)
            revoked = replace(lease, revoked_at=self._now())
            self._leases[lease_id] = revoked
            self._persist_state_change(lambda state: state["revokedLeases"].append(lease_id))
            return revoked

    def revoke_lease_id(self, lease_id: str) -> bool:
        """Persist a lease revocation even when the lease lives in another worker."""

        self._validate_lease_id(lease_id)
        with self._lock:
            self._refresh_external_state()
            lease = self._leases.get(lease_id)
            if lease is not None and lease.revoked_at is None:
                self._leases[lease_id] = replace(lease, revoked_at=self._now())
            state = self._read_state()
            already_revoked = (
                (lease is not None and lease.revoked_at is not None)
                or lease_id in state["revokedLeases"]
            )
            if not already_revoked:
                self._persist_state_change(lambda current: current["revokedLeases"].append(lease_id))
            return not already_revoked

    def revoke_invocation(self, invocation_ref: str) -> int:
        self._validate_ref(invocation_ref, "invocation_ref")
        with self._lock:
            self._refresh_external_state()
            now = self._now()
            count = 0
            for lease_id, lease in tuple(self._leases.items()):
                if lease.invocation_ref == invocation_ref and lease.revoked_at is None:
                    self._leases[lease_id] = replace(lease, revoked_at=now)
                    count += 1
            self._persist_state_change(lambda state: state["revokedInvocations"].update({invocation_ref: now}))
            return count

    def rotate(self, credential_ref: str) -> int:
        self._validate_ref(credential_ref, "credential_ref")
        with self._lock:
            self._refresh_external_state()
            generation = self._generations.get(credential_ref, 0) + 1
            self._generations[credential_ref] = generation
            now = self._now()
            state = self._read_state()
            rotation_generation = int(state["rotationGeneration"].get(credential_ref, 0)) + 1
            for lease_id, lease in tuple(self._leases.items()):
                if lease.credential_ref == credential_ref and lease.revoked_at is None:
                    self._leases[lease_id] = replace(lease, revoked_at=now)
            self._persist_state_change(
                lambda current: current["rotationGeneration"].update({credential_ref: rotation_generation})
            )
            return generation

    def _active_lease(self, lease_id: str) -> CredentialLease:
        lease = self._leases.get(lease_id)
        if lease is None:
            raise RuntimeCredentialError("credential lease is unknown")
        if lease.revoked_at is not None:
            raise RuntimeCredentialError("credential lease is revoked")
        state = self._read_state()
        if lease_id in state["revokedLeases"]:
            self._leases[lease_id] = replace(lease, revoked_at=self._now())
            raise RuntimeCredentialError("credential lease is revoked")
        if lease.invocation_ref and lease.invocation_ref in state["revokedInvocations"]:
            self._leases[lease_id] = replace(lease, revoked_at=self._now())
            raise RuntimeCredentialError("credential lease is revoked")
        current_rotation = state["rotationGeneration"].get(lease.credential_ref, 0)
        if isinstance(current_rotation, int) and current_rotation > lease.rotation_generation:
            self._leases[lease_id] = replace(lease, revoked_at=self._now())
            raise RuntimeCredentialError("credential lease was rotated")
        if self._now() >= lease.expires_at:
            raise RuntimeCredentialError("credential lease is expired")
        return lease

    def _load_current(self, credential_ref: str) -> dict[str, str]:
        raw: Any
        if callable(self._source):
            raw = self._source(credential_ref)
        else:
            raw = self._source.get(credential_ref)
        if raw is None or not isinstance(raw, Mapping):
            raise RuntimeCredentialError("credential source is unavailable")
        if len(raw) > 16:
            raise RuntimeCredentialError("credential source contains too many values")
        validated: dict[str, str] = {}
        for key, value in raw.items():
            if (
                not isinstance(key, str)
                or not key
                or len(key.encode("utf-8")) > 128
                or any(ord(char) < 0x20 or ord(char) == 0x7F for char in key)
                or not isinstance(value, str)
                or not value
                or len(value.encode("utf-8")) > 16 * 1024
                or any(ord(char) < 0x20 or ord(char) == 0x7F for char in value)
            ):
                raise RuntimeCredentialError("credential source contains an invalid value")
            validated[key] = value
        return validated

    @staticmethod
    def _digest(credentials: Mapping[str, str]) -> str:
        encoded = json.dumps(dict(credentials), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _now(self) -> float:
        value = float(self._clock())
        if value < 0:
            raise RuntimeCredentialError("credential clock is invalid")
        return value

    @staticmethod
    def _empty_state() -> dict[str, Any]:
        return {"revokedLeases": [], "revokedInvocations": {}, "rotationGeneration": {}}

    def _read_state(self) -> dict[str, Any]:
        if self._state_file is None or not self._state_file.exists():
            return self._empty_state()
        try:
            value = json.loads(self._state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeCredentialError("credential state is unavailable") from exc
        if not isinstance(value, dict):
            raise RuntimeCredentialError("credential state is invalid")
        state = self._empty_state()
        if isinstance(value.get("revokedLeases"), list):
            state["revokedLeases"] = [item for item in value["revokedLeases"] if isinstance(item, str)]
        if isinstance(value.get("revokedInvocations"), dict):
            state["revokedInvocations"] = {
                key: item
                for key, item in value["revokedInvocations"].items()
                if isinstance(key, str) and isinstance(item, (int, float))
            }
        if isinstance(value.get("rotationGeneration"), dict):
            state["rotationGeneration"] = {
                key: item
                for key, item in value["rotationGeneration"].items()
                if isinstance(key, str) and isinstance(item, int) and item >= 0
            }
        return state

    def _refresh_external_state(self) -> None:
        state = self._read_state()
        now = self._now()
        for lease_id, lease in tuple(self._leases.items()):
            if lease.revoked_at is not None:
                continue
            if lease_id in state["revokedLeases"] or (
                lease.invocation_ref and lease.invocation_ref in state["revokedInvocations"]
            ):
                self._leases[lease_id] = replace(lease, revoked_at=now)
            elif state["rotationGeneration"].get(lease.credential_ref, 0) > lease.rotation_generation:
                self._leases[lease_id] = replace(lease, revoked_at=now)

    def _persist_state_change(self, update: Callable[[dict[str, Any]], None]) -> None:
        if self._state_file is None:
            return
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self._state_file.with_name(self._state_file.name + ".lock")
        with lock_path.open("a+", encoding="utf-8") as lock:
            if fcntl is not None:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                state = self._read_state()
                update(state)
                temporary = self._state_file.with_name(f".{self._state_file.name}.{secrets.token_hex(8)}.tmp")
                temporary.write_text(json.dumps(state, sort_keys=True, separators=(",", ":")), encoding="utf-8")
                os.chmod(temporary, 0o600)
                os.replace(temporary, self._state_file)
            except OSError as exc:
                raise RuntimeCredentialError("credential state could not be updated") from exc
            finally:
                if fcntl is not None:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _validate_ref(value: str, name: str) -> None:
        if (
            not isinstance(value, str)
            or not value
            or len(value.encode("utf-8")) > 256
            or any(ord(char) < 0x20 or ord(char) == 0x7F for char in value)
        ):
            raise RuntimeCredentialError(f"{name} is invalid")

    @staticmethod
    def _validate_lease_id(value: str) -> None:
        RuntimeCredentialBroker._validate_ref(value, "lease_id")


def validate_credential_lease_metadata(
    metadata: Mapping[str, object],
    *,
    invocation_ref: str,
    state_file: str | os.PathLike[str] | None,
    clock: Callable[[], float] | None = None,
) -> None:
    """Revalidate a host-issued lease at the trusted runtime boundary.

    The runtime process does not resolve credentials and therefore does not
    create a second broker.  It checks the immutable lease facts plus the
    broker's shared revocation/rotation journal immediately before a provider
    call and while streaming its response.
    """

    required = {
        "leaseId",
        "agentRef",
        "credentialRef",
        "invocationRef",
        "generation",
        "issuedAt",
        "expiresAt",
        "rotationGeneration",
    }
    if not isinstance(metadata, Mapping) or set(metadata) != required:
        raise RuntimeCredentialError("credential lease metadata is invalid")
    for key in ("leaseId", "agentRef", "credentialRef", "invocationRef"):
        value = metadata.get(key)
        if not isinstance(value, str) or not value:
            raise RuntimeCredentialError("credential lease metadata is invalid")
        RuntimeCredentialBroker._validate_ref(value, key)
    if metadata.get("invocationRef") != invocation_ref:
        raise RuntimeCredentialError("credential lease is bound to another invocation")
    for key in ("generation", "rotationGeneration"):
        value = metadata.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise RuntimeCredentialError("credential lease metadata is invalid")
    issued_at = metadata.get("issuedAt")
    expires_at = metadata.get("expiresAt")
    if (
        isinstance(issued_at, bool)
        or not isinstance(issued_at, (int, float))
        or isinstance(expires_at, bool)
        or not isinstance(expires_at, (int, float))
        or expires_at <= issued_at
        or not math.isfinite(float(issued_at))
        or not math.isfinite(float(expires_at))
    ):
        raise RuntimeCredentialError("credential lease metadata is invalid")
    now = float((clock or time.time)())
    if not math.isfinite(now) or now < 0 or now >= expires_at:
        raise RuntimeCredentialError("credential lease is expired")
    if state_file is None:
        return
    path = Path(state_file)
    if not path.is_absolute():
        raise RuntimeCredentialError("credential state file must be absolute")
    if not path.exists():
        return
    try:
        raw_state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeCredentialError("credential state is unavailable") from exc
    if not isinstance(raw_state, dict):
        raise RuntimeCredentialError("credential state is invalid")
    revoked_leases = raw_state.get("revokedLeases", [])
    revoked_invocations = raw_state.get("revokedInvocations", {})
    rotation_generation = raw_state.get("rotationGeneration", {})
    if not isinstance(revoked_leases, list) or not isinstance(revoked_invocations, dict) or not isinstance(
        rotation_generation, dict
    ):
        raise RuntimeCredentialError("credential state is invalid")
    lease_id = metadata["leaseId"]
    credential_ref = metadata["credentialRef"]
    if lease_id in revoked_leases or invocation_ref in revoked_invocations:
        raise RuntimeCredentialError("credential lease is revoked")
    current_rotation = rotation_generation.get(credential_ref, 0)
    if isinstance(current_rotation, bool) or not isinstance(current_rotation, int) or current_rotation < 0:
        raise RuntimeCredentialError("credential state is invalid")
    if current_rotation > metadata["rotationGeneration"]:
        raise RuntimeCredentialError("credential lease was rotated")


__all__ = [
    "CommandCredentialResolver",
    "CredentialLease",
    "RUNTIME_CREDENTIAL_LEASE_GRACE_SECONDS",
    "RUNTIME_CREDENTIAL_LEASE_MAX_SECONDS",
    "RuntimeCredentialBroker",
    "RuntimeCredentialError",
    "credential_failure_subreason",
    "validate_credential_lease_metadata",
    "credential_source_from_configuration",
]
