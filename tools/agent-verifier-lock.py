#!/usr/bin/env python3
# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Hold one process-lifetime advisory lock while a verifier runs."""

from __future__ import annotations

import fcntl
import os
import sys
from pathlib import Path


def check_inherited_fd(argv: list[str]) -> int:
    if len(argv) != 4 or argv[1] != "--check-fd":
        return 2
    try:
        fd = int(argv[2])
    except ValueError:
        return 1
    lock_path = Path(argv[3])
    try:
        fd_stat = os.fstat(fd)
        path_stat = lock_path.stat()
        if (fd_stat.st_dev, fd_stat.st_ino) != (path_stat.st_dev, path_stat.st_ino):
            return 1
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, ValueError, BlockingIOError):
        return 1
    return 0


def main(argv: list[str]) -> int:
    if len(argv) > 1 and argv[1] == "--check-fd":
        return check_inherited_fd(argv)
    if len(argv) < 3 or argv[1] == "--" or argv[2] != "--":
        print(
            "event=agent.verifier.lock status=failed "
            "expected=lock_path_--_command actual=invalid_arguments "
            "suggestion=invoke_the_verifier_lock_wrapper_correctly",
            file=sys.stderr,
        )
        return 2

    lock_path = Path(argv[1])
    command = argv[3:]
    if not command:
        print(
            "event=agent.verifier.lock status=failed expected=command actual=missing "
            "suggestion=provide_the_verifier_command",
            file=sys.stderr,
        )
        return 2

    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = lock_path.open("a+", encoding="utf-8")
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(
            "event=agent.verifier.lock status=failed expected=one_active_g3_or_g4_verifier "
            "actual=lock_held_by_another_process "
            "suggestion=wait_for_the_active_verifier_to_finish",
            file=sys.stderr,
        )
        return 2
    except OSError as exc:
        print(
            "event=agent.verifier.lock status=failed expected=advisory_lock_available "
            f"actual={type(exc).__name__} suggestion=inspect_the_shared_verifier_lock_path",
            file=sys.stderr,
        )
        return 2

    # Python marks opened descriptors close-on-exec. Make the lock survive the
    # exec so the verifier process lifetime, not a helper PID, owns exclusion.
    os.set_inheritable(lock_file.fileno(), True)
    environment = dict(os.environ)
    environment.pop("PLANE_AGENT_VERIFIER_LOCK_HELD", None)
    environment["PLANE_AGENT_VERIFIER_LOCK_FD"] = str(lock_file.fileno())
    os.execvpe(command[0], command, environment)
    return 127


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
