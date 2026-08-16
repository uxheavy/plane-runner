"""Plane-owned, credential-free Code Mode host seam.

Exports are lazy so the dependency-free child launcher can import from this
package without loading Django models or the Plane host implementation.
"""

from importlib import import_module
from typing import Any


_EXPORTS: dict[str, tuple[str, str]] = {
    "CODE_MODE_EXECUTION_OPERATION": ("contracts", "CODE_MODE_EXECUTION_OPERATION"),
    "CODE_MODE_SCHEMA_VERSION": ("contracts", "CODE_MODE_SCHEMA_VERSION"),
    "CodeModeBindingError": ("host", "CodeModeBindingError"),
    "CodeModeBudget": ("contracts", "CodeModeBudget"),
    "CodeModeExecutionRequest": ("contracts", "CodeModeExecutionRequest"),
    "CodeModeHostRPC": ("host", "CodeModeHostRPC"),
    "CodeModeIsolateError": ("isolate", "CodeModeIsolateError"),
    "CodeModeIsolateRunner": ("isolate", "CodeModeIsolateRunner"),
    "HostBinding": ("contracts", "HostBinding"),
    "SandboxPolicy": ("contracts", "SandboxPolicy"),
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


__all__ = [
    "CODE_MODE_EXECUTION_OPERATION",
    "CODE_MODE_SCHEMA_VERSION",
    "CodeModeBindingError",
    "CodeModeBudget",
    "CodeModeExecutionRequest",
    "CodeModeHostRPC",
    "CodeModeIsolateError",
    "CodeModeIsolateRunner",
    "HostBinding",
    "SandboxPolicy",
]
