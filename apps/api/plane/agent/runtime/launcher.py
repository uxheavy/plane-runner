# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Single-threaded child launcher for the production runtime boundary.

The HTTP runtime service starts this module without ``preexec_fn``.  The
launcher applies child-only limits and the kernel policy, then performs the
one permitted exec transition into the pinned Hermes bootstrap.
"""

from __future__ import annotations

import argparse
import os
import resource
import sys

from plane.agent.runtime.config import validate_runtime_command
from plane.agent.runtime.subprocess import _install_linux_kernel_policy


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--cpu-seconds", type=int, required=True)
    parser.add_argument("--memory-bytes", type=int, required=True)
    parser.add_argument("--pids-limit", type=int, required=True)
    return parser


def _bounded_positive(value: int, maximum: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0 or value > maximum:
        raise ValueError(f"{name} is outside its allowed range")
    return value


def _validate_target(command: list[str]) -> tuple[str, ...]:
    if any(
        not isinstance(part, str)
        or not part
        or "\x00" in part
        or any(ord(char) < 0x20 or ord(char) == 0x7F for char in part)
        for part in command
    ):
        raise ValueError("runtime bootstrap argv is invalid")
    if len(command) not in {5, 7, 9}:
        raise ValueError("runtime bootstrap argv is invalid")
    base = command[:5]
    suffix = command[5:]
    if len(suffix) not in {0, 2, 4}:
        raise ValueError("runtime bootstrap argv is invalid")

    def socket_pair(pair: tuple[str, str], name: str) -> str:
        flag, socket_path = pair
        expected_flag = {
            "host": "--plane-host-socket",
            "provider": "--provider-relay-socket",
        }[name]
        if flag != expected_flag:
            raise ValueError("runtime bootstrap argv is invalid")
        if (
            not os.path.isabs(socket_path)
            or len(os.fsencode(socket_path)) > 512
            or any(ord(char) < 0x20 or ord(char) == 0x7F for char in socket_path)
        ):
            raise ValueError(f"runtime {name} socket path is invalid")
        return socket_path

    if len(suffix) == 2:
        socket_pair((suffix[0], suffix[1]), "host")
    elif len(suffix) == 4:
        host_path = socket_pair((suffix[0], suffix[1]), "host")
        provider_path = socket_pair((suffix[2], suffix[3]), "provider")
        if host_path == provider_path:
            raise ValueError("runtime socket paths must be distinct")
    return validate_runtime_command(base) + tuple(suffix)


def main(argv: list[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    try:
        separator = values.index("--")
        options = _parser().parse_args(values[:separator])
        command = values[separator + 1 :]
        command = list(_validate_target(command))
        cpu_seconds = _bounded_positive(options.cpu_seconds, 3600, "cpu-seconds")
        memory_bytes = _bounded_positive(options.memory_bytes, 2 * 1024 * 1024 * 1024, "memory-bytes")
        pids_limit = _bounded_positive(options.pids_limit, 4096, "pids-limit")
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
        resource.setrlimit(resource.RLIMIT_NPROC, (pids_limit, pids_limit))
        _install_linux_kernel_policy()
        child_environment = dict(os.environ)
        # The service deliberately provides no ambient PATH. This fixed,
        # image-local lookup path keeps the one exec transition deterministic.
        child_environment.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
        os.execvpe(command[0], command, child_environment)
    except (IndexError, OSError, ValueError, argparse.ArgumentError):
        # The parent records the bounded dispatch failure; no target argv or
        # environment values are echoed into diagnostics.
        sys.stderr.write("event=agent.runtime.launcher status=failed reason=policy_installation\n")
        return 78
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
