# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Fail-closed provenance checks for developer/build checkout launches.

Production runtime services are selected by an immutable image attestation and
do not expose a source checkout to Plane. The direct checkout adapter remains
useful for developer and image-build paths, where its expensive full-tree
cleanliness proof is performed once per supervisor process.
"""

from __future__ import annotations

import subprocess
from functools import lru_cache


HERMES_REMOTE = "github.com/uxheavy/hermes-agent"


class RuntimeProvenanceError(RuntimeError):
    """The configured runtime checkout cannot be trusted for execution."""


def preflight_runtime_provenance(
    checkout: str | None,
    expected_sha: str | None,
    *,
    remote_runtime: bool,
) -> None:
    """Select immutable production attestation or the direct dev/build proof.

    A source checkout is never inspected on the remote runtime dispatch path.
    Production services are trusted through their immutable image/deployment
    attestation; checkout verification is reserved for direct developer and
    image-build launches.
    """

    if bool(checkout) != bool(expected_sha):
        raise RuntimeProvenanceError("Hermes runtime checkout and SHA must be configured together")
    if not checkout:
        return
    if remote_runtime:
        raise RuntimeProvenanceError("remote immutable runtime must not be paired with a source checkout")
    verify_runtime_checkout_provenance(checkout, expected_sha or "")


def _git_output(checkout: str, *arguments: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", checkout, *arguments],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeProvenanceError("Hermes runtime checkout provenance could not be verified") from exc


@lru_cache(maxsize=16)
def verify_runtime_checkout_provenance(checkout: str, expected_sha: str) -> None:
    """Prove one direct Hermes checkout is pinned, clean, and from our fork.

    The successful result is cached by checkout and expected SHA for the life
    of this supervisor process. A failed proof is never cached, so a caller
    cannot turn a transient or changed checkout into an accepted one.
    """

    actual_sha = _git_output(checkout, "rev-parse", "HEAD").strip()
    if actual_sha != expected_sha:
        raise RuntimeProvenanceError("Hermes runtime checkout does not match the configured SHA")

    dirty = _git_output(checkout, "status", "--porcelain", "--untracked-files=all").strip()
    if dirty:
        raise RuntimeProvenanceError("Hermes runtime checkout must be clean")

    remotes = _git_output(checkout, "remote", "-v")
    if HERMES_REMOTE not in remotes:
        raise RuntimeProvenanceError("Hermes runtime checkout must use the uxheavy fork")


__all__ = [
    "HERMES_REMOTE",
    "RuntimeProvenanceError",
    "preflight_runtime_provenance",
    "verify_runtime_checkout_provenance",
]
