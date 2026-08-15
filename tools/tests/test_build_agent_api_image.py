from __future__ import annotations

import hashlib
import importlib.util
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
    command = builder.docker_build_command(candidate, hashes)

    assert command[:4] == ["docker", "build", "--network", "none"]
    assert "-f" in command
    assert "apps/api/Dockerfile.g4" in command
    for name, digest in hashes.items():
        assert f"{name}={digest}" in command
    assert command[-1] == "apps/api"


def test_dockerfile_contract_is_checked_without_docker() -> None:
    builder.verify_dockerfile_contract()
