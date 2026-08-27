# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


TOOLS = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("build_agent_api_image", TOOLS / "build-agent-api-image.py")
assert SPEC is not None and SPEC.loader is not None
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def test_source_hashes_are_committed_and_complete() -> None:
    candidate = builder.candidate_head()
    hashes = builder.source_hashes(candidate)

    assert set(hashes) == set(builder.SOURCE_FILES)
    assert all(len(value) == 64 for value in hashes.values())


def test_stale_runtime_contract_binding_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package_directory = tmp_path / "package"
    api_directory = tmp_path / "api"
    for directory in (package_directory, api_directory):
        directory.mkdir()
        for source in builder.RUNTIME_CONTRACT_DIRECTORIES[0].glob("*.json"):
            (directory / source.name).write_bytes(source.read_bytes())
    manifest = package_directory / "manifest.json"
    value = manifest.read_text(encoding="utf-8")
    value = value.replace(json.loads(value)["schemas"]["run-snapshot"]["sha256"], "0" * 64)
    manifest.write_text(value, encoding="utf-8")
    monkeypatch.setattr(builder, "RUNTIME_CONTRACT_DIRECTORIES", (package_directory, api_directory))

    with pytest.raises(RuntimeError, match="schema digest mismatch"):
        builder.verify_runtime_contract_artifacts()


def test_dirty_checkout_is_rejected_before_candidate_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(builder, "_run", lambda *args, **kwargs: " M apps/api/manage.py")

    with pytest.raises(RuntimeError, match="checkout must be clean"):
        builder.verify_clean_candidate()


def test_candidate_must_equal_full_head(monkeypatch: pytest.MonkeyPatch) -> None:
    head = "a" * 40
    calls = iter(("", head))
    monkeypatch.setattr(builder, "_run", lambda *args, **kwargs: next(calls))

    with pytest.raises(RuntimeError, match="candidate must equal full HEAD"):
        builder.verify_clean_candidate("b" * 40)


def test_docker_command_uses_dockerfile_argument_contract() -> None:
    candidate = "a" * 40
    hashes = {name: hashlib.sha256(name.encode()).hexdigest() for name in builder.SOURCE_FILES}
    command = builder.docker_build_command(candidate, hashes, tag="plane-agent-api:g4-test")

    assert command[:4] == ["docker", "build", "--network", "none"]
    assert "-f" in command
    assert "apps/api/Dockerfile.g4" in command
    for name, digest in hashes.items():
        assert f"{name}={digest}" in command
    assert f"PLANE_TYPESCRIPT_VERSION={builder.TYPESCRIPT_VERSION}" in command
    assert command[-1] == "apps/api"


def test_dockerfile_contract_is_checked_without_docker() -> None:
    builder.verify_dockerfile_contract()


def test_base_image_compiler_contract_is_pinned() -> None:
    assert builder.TYPESCRIPT_VERSION == "5.4.5"


def test_prepared_base_binding_comes_from_rollback_truth() -> None:
    tag, digest = builder.default_base_image_binding()

    assert tag == builder.DEFAULT_BASE_IMAGE
    assert digest == "sha256:7812ed213b9cfcbe50580ded7b5e78a30d317e37dd66c1082c5dff97a9e98031"


def test_prepared_base_tag_drift_is_rejected_before_compiler_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_run(*args, **_kwargs):
        calls.append(args)
        return "sha256:" + "0" * 64

    monkeypatch.setattr(builder, "_run", fake_run)

    with pytest.raises(RuntimeError, match="tag does not resolve"):
        builder.verify_base_image(builder.DEFAULT_BASE_IMAGE)
    assert len(calls) == 1


def test_custom_base_requires_an_explicit_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(builder, "_run", lambda *_args, **_kwargs: pytest.fail("Docker probe reached"))

    with pytest.raises(ValueError, match="--base-image-digest is required"):
        builder.verify_base_image("plane-api:custom")


def test_default_image_tag_comes_from_current_manifest() -> None:
    manifest = __import__("json").loads(builder.MANIFEST.read_text(encoding="utf-8"))
    artifact = manifest["pins"]["apiArtifact"]

    assert builder.image_tag(artifact["sourceRevision"]) == artifact["imageTag"]


def test_unpinned_candidate_requires_an_explicit_tag() -> None:
    with pytest.raises(ValueError, match="--tag is required"):
        builder.image_tag("a" * 40)


def test_resolver_probe_is_network_none_and_emits_shape_only(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_run(*args, **_kwargs):
        calls.append(args)
        return '{"exitCode":0,"keys":["api_key"],"valueShape":"nonempty-string"}'

    monkeypatch.setattr(builder, "_run", fake_run)

    builder.verify_resolver_image("plane-agent-api:g4-test")

    command = calls[0]
    assert command[:4] == ("docker", "run", "--rm", "--network")
    assert "none" in command
    assert "--read-only" in command
    assert any("target=/run/secrets/plane_agent_provider_credentials" in item for item in command)
    assert "synthetic-access-token" not in " ".join(command)
