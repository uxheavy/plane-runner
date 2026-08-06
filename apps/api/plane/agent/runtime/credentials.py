"""Disposable, invocation-bound runtime credential leases.

The broker keeps only digests and lease metadata.  The credential resolver is
the deployment-owned source of current disposable credentials; raw values are
returned to the already-isolated child only for the active invocation.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any


class RuntimeCredentialError(ValueError):
    """A credential lease is absent, expired, revoked, rotated, or unbound."""


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
    revoked_at: float | None = None


CredentialSource = Callable[[str], Mapping[str, str]] | Mapping[str, Mapping[str, str]]


class RuntimeCredentialBroker:
    """Issue, bind, rotate, resolve, and revoke short-lived credential leases."""

    def __init__(
        self,
        source: CredentialSource,
        *,
        ttl_seconds: float = 300.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if not callable(source) and not isinstance(source, Mapping):
            raise TypeError("credential source must be callable or a mapping")
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, (int, float)):
            raise ValueError("credential lease TTL must be numeric")
        if ttl_seconds <= 0 or ttl_seconds > 3600:
            raise ValueError("credential lease TTL is outside its allowed range")
        self._source = source
        self._ttl_seconds = float(ttl_seconds)
        self._clock = clock or time.time
        self._lock = threading.RLock()
        self._leases: dict[str, CredentialLease] = {}
        self._generations: dict[str, int] = {}

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
            credentials = self._load_current(credential_ref)
            generation = self._generations.get(credential_ref, 0) + 1
            self._generations[credential_ref] = generation
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
            )
            self._leases[lease.lease_id] = lease
            return lease, credentials

    def bind(self, lease_id: str, *, invocation_ref: str) -> CredentialLease:
        self._validate_lease_id(lease_id)
        self._validate_ref(invocation_ref, "invocation_ref")
        with self._lock:
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
            return revoked

    def revoke_invocation(self, invocation_ref: str) -> int:
        self._validate_ref(invocation_ref, "invocation_ref")
        with self._lock:
            now = self._now()
            count = 0
            for lease_id, lease in tuple(self._leases.items()):
                if lease.invocation_ref == invocation_ref and lease.revoked_at is None:
                    self._leases[lease_id] = replace(lease, revoked_at=now)
                    count += 1
            return count

    def rotate(self, credential_ref: str) -> int:
        self._validate_ref(credential_ref, "credential_ref")
        with self._lock:
            generation = self._generations.get(credential_ref, 0) + 1
            self._generations[credential_ref] = generation
            now = self._now()
            for lease_id, lease in tuple(self._leases.items()):
                if lease.credential_ref == credential_ref and lease.revoked_at is None:
                    self._leases[lease_id] = replace(lease, revoked_at=now)
            return generation

    def get_lease(self, lease_id: str) -> CredentialLease:
        self._validate_lease_id(lease_id)
        with self._lock:
            lease = self._leases.get(lease_id)
            if lease is None:
                raise RuntimeCredentialError("credential lease is unknown")
            return lease

    def _active_lease(self, lease_id: str) -> CredentialLease:
        lease = self._leases.get(lease_id)
        if lease is None:
            raise RuntimeCredentialError("credential lease is unknown")
        if lease.revoked_at is not None:
            raise RuntimeCredentialError("credential lease is revoked")
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


__all__ = ["CredentialLease", "RuntimeCredentialBroker", "RuntimeCredentialError"]
