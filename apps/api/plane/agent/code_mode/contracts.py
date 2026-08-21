"""Credential-free Code Mode host contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from typing import Literal


CODE_MODE_SCHEMA_VERSION = "plane.code-mode/v1"
CODE_MODE_EXECUTION_OPERATION = "plane.code-mode.execute@1"
MAX_CODE_MODE_SOURCE_BYTES = 4 * 1024
MAX_CODE_MODE_INLINE_RESULT_BYTES = 2 * 1024
MAX_CODE_MODE_OBSERVATIONS = 32
MAX_CODE_MODE_OBSERVATION_BYTES = 512
MAX_CODE_MODE_OBSERVATIONS_BYTES = 4 * 1024


class CodeModeExecutionError(ValueError):
    """A bounded, public validation error for the execution capsule."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CodeModeExecutionRequest:
    """The versioned capsule accepted by the trusted Plane host callback."""

    source: str
    input_data: dict[str, Any]
    schema_version: str = CODE_MODE_SCHEMA_VERSION
    entrypoint: str = "default"

    def __post_init__(self) -> None:
        if not isinstance(self.source, str) or not self.source.strip():
            raise CodeModeExecutionError("VALIDATION_ERROR", "Code Mode source must be non-empty TypeScript")
        if len(self.source.encode("utf-8")) > MAX_CODE_MODE_SOURCE_BYTES:
            raise CodeModeExecutionError("SOURCE_TOO_LARGE", "Code Mode source exceeds its size bound")
        if self.schema_version != CODE_MODE_SCHEMA_VERSION:
            raise CodeModeExecutionError("VALIDATION_ERROR", "Code Mode schema version is unsupported")
        if self.entrypoint != "default":
            raise CodeModeExecutionError("VALIDATION_ERROR", "Code Mode entrypoint is unsupported")
        if not isinstance(self.input_data, dict) or any(not isinstance(key, str) for key in self.input_data):
            raise CodeModeExecutionError("VALIDATION_ERROR", "Code Mode input must be an object")
        try:
            encoded_input = json.dumps(
                self.input_data,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise CodeModeExecutionError("VALIDATION_ERROR", "Code Mode input must be JSON-compatible") from exc
        if len(encoded_input) > MAX_CODE_MODE_SOURCE_BYTES:
            raise CodeModeExecutionError("VALIDATION_ERROR", "Code Mode input exceeds its size bound")

    @classmethod
    def from_wire(cls, value: Any) -> "CodeModeExecutionRequest":
        if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
            raise CodeModeExecutionError("VALIDATION_ERROR", "Code Mode execution capsule must be an object")
        allowed = {"schemaVersion", "entrypoint", "source", "input"}
        unknown = sorted(set(value).difference(allowed))
        if unknown:
            raise CodeModeExecutionError("VALIDATION_ERROR", "Code Mode execution capsule has unknown fields")
        required = {"schemaVersion", "entrypoint", "source", "input"}
        if not required.issubset(value):
            raise CodeModeExecutionError("VALIDATION_ERROR", "Code Mode execution capsule is missing required fields")
        return cls(
            source=value["source"],
            input_data=value["input"],
            schema_version=value["schemaVersion"],
            entrypoint=value["entrypoint"],
        )


@dataclass(frozen=True)
class HostBinding:
    """Trusted host state; this object is never serialized into generated code."""

    actor_ref: str
    principal_ref: str
    workspace_slug: str
    run_ref: str
    invocation_ref: str
    catalog_digest: str
    assignment_target_ref: str = ""


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
