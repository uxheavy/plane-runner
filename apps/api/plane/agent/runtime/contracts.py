"""Dependency-free runtime transport contracts shared by both processes."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol


RUNTIME_TRANSPORT_PRE_DISPATCH_FAILURE = "runtime_transport_pre_dispatch_failure"
RUNTIME_CONFIGURATION_PRE_DISPATCH_FAILURE = "runtime_configuration_pre_dispatch_failure"
RUNTIME_PROCESS_FAILED = "runtime_process_failed"
RUNTIME_PROCESS_TIMEOUT = "runtime_process_timeout"
RUNTIME_PROCESS_CANCELLED = "runtime_process_cancelled"
RUNTIME_PROCESS_OUTPUT_INVALID = "runtime_process_output_invalid"
RUNTIME_SUPERVISOR_PRE_DISPATCH_FAILURE = "runtime_supervisor_pre_dispatch_failure"

_FAILURE_CODES = frozenset(
    {
        RUNTIME_TRANSPORT_PRE_DISPATCH_FAILURE,
        RUNTIME_CONFIGURATION_PRE_DISPATCH_FAILURE,
        RUNTIME_PROCESS_FAILED,
        RUNTIME_PROCESS_TIMEOUT,
        RUNTIME_PROCESS_CANCELLED,
        RUNTIME_PROCESS_OUTPUT_INVALID,
        RUNTIME_SUPERVISOR_PRE_DISPATCH_FAILURE,
    }
)
_FAILURE_PHASES = frozenset(
    {"runtime_transport", "runtime_configuration", "runtime_process", "launcher", "runtime_supervisor"}
)
_FAILURE_DETAILS = frozenset(
    {
        "dispatch_rejected",
        "process_start_failed",
        "process_exit",
        "bootstrap_argv_rejected",
        "process_timeout",
        "process_cancelled",
        "process_output_invalid",
        "unclassified_exception",
    }
)
_UNCLASSIFIED_FAILURE_DETAIL = "unclassified_exception"


class RuntimeDispatchError(ValueError):
    """Raised when a serialized runtime dispatch cannot be completed safely."""

    def __init__(
        self,
        message: str,
        *,
        failure_code: str | None = None,
        failure_phase: str | None = None,
        failure_detail: str | None = None,
    ) -> None:
        super().__init__(message)
        classification_is_valid = (
            isinstance(failure_code, str)
            and failure_code in _FAILURE_CODES
            and isinstance(failure_phase, str)
            and failure_phase in _FAILURE_PHASES
            and isinstance(failure_detail, str)
            and failure_detail in _FAILURE_DETAILS
            and failure_detail != _UNCLASSIFIED_FAILURE_DETAIL
        )
        self.has_allowlisted_failure = classification_is_valid
        self.failure_code = (
            failure_code
            if classification_is_valid
            else RUNTIME_TRANSPORT_PRE_DISPATCH_FAILURE
        )
        self.failure_phase = (
            failure_phase
            if classification_is_valid
            else "runtime_transport"
        )
        self.failure_detail = (
            failure_detail
            if classification_is_valid
            else _UNCLASSIFIED_FAILURE_DETAIL
        )

    def public_failure(self) -> dict[str, str]:
        """Return only a bounded cross-process classification, never exception text."""

        return {
            "failureCode": self.failure_code,
            "failurePhase": self.failure_phase,
            "failureDetail": self.failure_detail,
        }


class RuntimeTransport(Protocol):
    """Logical transport to the separate runtime service."""

    def dispatch(self, snapshot_json: str, envelope_json: str) -> Iterable[str]:
        """Send canonical JSON and return serialized untrusted frames."""


__all__ = [
    "RUNTIME_CONFIGURATION_PRE_DISPATCH_FAILURE",
    "RUNTIME_PROCESS_CANCELLED",
    "RUNTIME_PROCESS_FAILED",
    "RUNTIME_PROCESS_OUTPUT_INVALID",
    "RUNTIME_PROCESS_TIMEOUT",
    "RUNTIME_SUPERVISOR_PRE_DISPATCH_FAILURE",
    "RUNTIME_TRANSPORT_PRE_DISPATCH_FAILURE",
    "RuntimeDispatchError",
    "RuntimeTransport",
]
