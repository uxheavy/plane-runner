"""Dependency-free runtime transport contracts shared by both processes."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol


class RuntimeDispatchError(ValueError):
    """Raised when a serialized runtime dispatch cannot be completed safely."""


class RuntimeTransport(Protocol):
    """Logical transport to the separate runtime service."""

    def dispatch(self, snapshot_json: str, envelope_json: str) -> Iterable[str]:
        """Send canonical JSON and return serialized untrusted frames."""


__all__ = ["RuntimeDispatchError", "RuntimeTransport"]
