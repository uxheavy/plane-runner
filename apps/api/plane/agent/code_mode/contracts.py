"""Credential-free Code Mode host contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


CODE_MODE_SCHEMA_VERSION = "plane.code-mode/v1"


@dataclass(frozen=True)
class HostBinding:
    """Trusted host state; this object is never serialized into generated code."""

    actor_ref: str
    principal_ref: str
    workspace_slug: str
    run_ref: str
    invocation_ref: str
    catalog_digest: str


@dataclass
class CodeModeBudget:
    """Remaining cumulative run budget allocated to one Code Mode invocation."""

    input_bytes: int
    output_bytes: int
    duration_ms: int
    calls: int
    spill_bytes: int = 64 * 1024
    input_tokens: int = 0
    output_tokens: int = 0

    def __post_init__(self) -> None:
        values = (
            self.input_bytes,
            self.output_bytes,
            self.duration_ms,
            self.calls,
            self.spill_bytes,
            self.input_tokens,
            self.output_tokens,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in values):
            raise ValueError("Code Mode budgets must be non-negative integers")


@dataclass(frozen=True)
class SandboxPolicy:
    """The only capabilities the existing restricted child isolate may receive."""

    network: Literal["none"] = "none"
    filesystem: Literal["none"] = "none"
    process: Literal["none"] = "none"
    max_spill_bytes: int = 64 * 1024
    cpu_seconds: int = 60
    memory_bytes: int = 1024 * 1024 * 1024
    pids_limit: int = 64

    def __post_init__(self) -> None:
        if self.network != "none" or self.filesystem != "none" or self.process != "none":
            raise ValueError("Code Mode sandbox capabilities are not permitted")
        if (
            isinstance(self.max_spill_bytes, bool)
            or not isinstance(self.max_spill_bytes, int)
            or self.max_spill_bytes < 0
        ):
            raise ValueError("Code Mode spill bound is invalid")
        for name, value, maximum in (
            ("cpu_seconds", self.cpu_seconds, 3600),
            ("memory_bytes", self.memory_bytes, 2 * 1024 * 1024 * 1024),
            ("pids_limit", self.pids_limit, 4096),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0 or value > maximum:
                raise ValueError(f"Code Mode {name} bound is invalid")


CallbackKind = Literal["search", "describe", "operation", "spill"]
