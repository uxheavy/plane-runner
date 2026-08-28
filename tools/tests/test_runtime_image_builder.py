# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from __future__ import annotations

import importlib.util
import io
import json
import os
import stat
import sys
import tarfile
from pathlib import Path
from unittest import mock

import pytest


TOOLS = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


builder = _load("build_agent_runtime_image", TOOLS / "build-agent-runtime-image.py")
probe = _load("agent_runtime_red_team", TOOLS / "agent-g4-runtime-red-team.py")


def _donor_manifest():
    return {
        "pins": {
            "runtimeImageTag": "plane-agent-runtime:sealed-donor",
            "runtimeImageDigest": "sha256:" + "a" * 64,
            "runtimeImageRevision": "b" * 40,
            "hermesCommit": builder.HERMES_COMMIT,
            "runtimeContract": "plane.agent-runtime/v1",
        }
    }


def _donor_metadata(*, digest=None, labels=None):
    expected = _donor_manifest()["pins"]
    return {
        "imageDigest": digest or expected["runtimeImageDigest"],
        "labels": labels
        or {
            "org.uxheavy.plane.hermes.commit": expected["hermesCommit"],
            "org.uxheavy.plane.hermes.remote": "https://github.com/uxheavy/hermes-agent.git",
            "org.uxheavy.plane.runtime.revision": expected["runtimeImageRevision"],
            "org.uxheavy.plane.runtime.contract": expected["runtimeContract"],
        },
    }


def test_sealed_donor_requires_manifest_digest_and_labels() -> None:
    with mock.patch.object(builder, "image_metadata", return_value=_donor_metadata()):
        binding = builder.verify_donor_image(
            "plane-agent-runtime:sealed-donor", _donor_manifest()
        )
    assert binding["sourceKind"] == "sealed-image"
    assert binding["donorDigest"] == "sha256:" + "a" * 64

    with mock.patch.object(
        builder,
        "image_metadata",
        return_value=_donor_metadata(digest="sha256:" + "d" * 64),
    ), pytest.raises(RuntimeError, match="digest"):
        builder.verify_donor_image("plane-agent-runtime:sealed-donor", _donor_manifest())

    labels = _donor_metadata()["labels"]
    labels["org.uxheavy.plane.hermes.commit"] = "e" * 40
    with mock.patch.object(
        builder, "image_metadata", return_value=_donor_metadata(labels=labels)
    ), pytest.raises(RuntimeError, match="label mismatch"):
        builder.verify_donor_image("plane-agent-runtime:sealed-donor", _donor_manifest())


def test_archive_extraction_rejects_traversal_and_links(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.tar"
    destination = tmp_path / "hermes"
    with tarfile.open(archive_path, "w") as archive:
        entry = tarfile.TarInfo("opt/hermes/../escape.py")
        entry.size = 1
        archive.addfile(entry, io.BytesIO(b"x"))
    with pytest.raises(RuntimeError, match="unsafe archive entry"):
        builder.extract_safe_hermes_archive(archive_path, destination)

    with tarfile.open(archive_path, "w") as archive:
        entry = tarfile.TarInfo("opt/hermes/link")
        entry.type = tarfile.SYMTYPE
        entry.linkname = "/etc/passwd"
        archive.addfile(entry)
    with pytest.raises(RuntimeError, match="unsafe archive entry type"):
        builder.extract_safe_hermes_archive(archive_path, destination)


def test_source_provenance_rejects_mixed_checkout_and_donor_facts() -> None:
    with pytest.raises(RuntimeError, match="mixed"):
        builder.validate_hermes_source_binding(
            builder.HERMES_SOURCE_KIND_GIT,
            "plane-agent-runtime:sealed-donor",
            "sha256:" + "a" * 64,
            "b" * 64,
        )


@pytest.mark.parametrize(
    "origin",
    [
        "https://github.com/uxheavy/hermes-agent.git",
        "ssh://git@github.com/uxheavy/hermes-agent.git",
        "git@github.com:uxheavy/hermes-agent.git",
    ],
)
def test_repository_origin_normalizes_supported_fork_urls(origin: str) -> None:
    assert builder.canonical_hermes_remote(origin) == "github.com/uxheavy/hermes-agent"


def test_only_repository_owned_disposable_checkout_can_rewrite_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkout = builder.ROOT / "tmp" / "disposable-hermes"
    calls: list[tuple[object, ...]] = []

    def fake_run(*args: object, **_kwargs: object) -> str:
        calls.append(args)
        return builder.HERMES_ORIGIN if args[-3:] == ("remote", "get-url", "origin") else ""

    monkeypatch.setattr(Path, "resolve", lambda self, strict=False: checkout)
    monkeypatch.setattr(builder, "run", fake_run)
    assert (
        builder.normalize_disposable_hermes_origin(checkout, "/tmp/source-hermes")
        == builder.HERMES_REMOTE
    )
    assert (
        "git",
        "-C",
        str(checkout),
        "remote",
        "set-url",
        "origin",
        builder.HERMES_ORIGIN,
    ) in calls


def test_external_checkout_origin_is_never_rewritten(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_run(*_args: object, **_kwargs: object) -> str:
        pytest.fail("external checkout origin was mutated")

    monkeypatch.setattr(builder, "run", unexpected_run)
    with pytest.raises(RuntimeError, match="uxheavy fork"):
        builder.normalize_disposable_hermes_origin(
            Path("/Users/example/hermes-agent"), "/tmp/source-hermes"
        )


def test_disposable_manifest_is_owner_only_regular_file(tmp_path: Path) -> None:
    path = tmp_path / "tmp" / "manifest.json"
    original_root = builder.ROOT
    original_manifest = builder.DURABLE_MANIFEST
    builder.ROOT = tmp_path.resolve()
    builder.DURABLE_MANIFEST = builder.ROOT / "durable-manifest.json"
    try:
        builder.write_disposable_manifest(path, {"schemaVersion": "test/v1"})
    finally:
        builder.ROOT = original_root
        builder.DURABLE_MANIFEST = original_manifest

    metadata = path.stat()
    assert stat.S_ISREG(metadata.st_mode)
    assert metadata.st_uid == os.getuid()
    assert stat.S_IMODE(metadata.st_mode) == 0o600
    assert json.loads(path.read_text(encoding="utf-8")) == {"schemaVersion": "test/v1"}


def test_pinned_agent_identity_rejects_shadowing() -> None:
    valid = {
        "module": "run_agent",
        "path": probe.PINNED_HERMES_RUN_AGENT_PATH,
        "sha256": probe.PINNED_HERMES_RUN_AGENT_SHA256,
        "class": "AIAgent",
        "classModule": "run_agent",
        "shadowPresent": False,
    }
    probe.validate_pinned_hermes_identity(valid)

    for field, value in (
        ("path", "/tmp/shadowed.py"),
        ("sha256", "0" * 64),
        ("class", "ShadowAgent"),
        ("classModule", "shadowed"),
        ("shadowPresent", True),
    ):
        candidate = dict(valid)
        candidate[field] = value
        with pytest.raises(probe.ProbeFailure, match="tamper_guard_failed"):
            probe.validate_pinned_hermes_identity(candidate)
