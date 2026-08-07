from __future__ import annotations

import time
from subprocess import CompletedProcess

import pytest

from plane.agent.runtime import provenance


def _git_result(command: list[str], stdout: str) -> CompletedProcess[str]:
    return CompletedProcess(command, 0, stdout, "")


def test_checkout_provenance_preflight_tolerates_slow_read_only_status_and_runs_once(monkeypatch):
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if command[-2:] == ["rev-parse", "HEAD"]:
            return _git_result(command, "expected-sha\n")
        if command[-3:] == ["status", "--porcelain", "--untracked-files=all"]:
            time.sleep(0.01)
            return _git_result(command, "")
        if command[-2:] == ["remote", "-v"]:
            return _git_result(command, "origin https://github.com/uxheavy/hermes-agent.git (fetch)\n")
        raise AssertionError(command)

    monkeypatch.setattr(provenance.subprocess, "run", fake_run)
    provenance.verify_runtime_checkout_provenance.cache_clear()

    provenance.verify_runtime_checkout_provenance("/hermes", "expected-sha")
    provenance.verify_runtime_checkout_provenance("/hermes", "expected-sha")

    assert len(calls) == 3
    status_kwargs = calls[1][1]
    assert "timeout" not in status_kwargs


@pytest.mark.parametrize(
    ("actual_sha", "dirty", "remotes", "message"),
    (
        ("different-sha", "", "github.com/uxheavy/hermes-agent", "does not match"),
        ("expected-sha", " M tracked.py\n", "github.com/uxheavy/hermes-agent", "must be clean"),
        ("expected-sha", "", "github.com/other/hermes-agent", "must use the uxheavy fork"),
    ),
)
def test_checkout_provenance_rejects_mismatch_or_dirty_checkout(
    monkeypatch, actual_sha, dirty, remotes, message
):
    def fake_run(command, **kwargs):
        if command[-2:] == ["rev-parse", "HEAD"]:
            return _git_result(command, actual_sha + "\n")
        if command[-3:] == ["status", "--porcelain", "--untracked-files=all"]:
            return _git_result(command, dirty)
        if command[-2:] == ["remote", "-v"]:
            return _git_result(command, remotes + "\n")
        raise AssertionError(command)

    monkeypatch.setattr(provenance.subprocess, "run", fake_run)
    provenance.verify_runtime_checkout_provenance.cache_clear()

    with pytest.raises(provenance.RuntimeProvenanceError, match=message):
        provenance.verify_runtime_checkout_provenance("/hermes", "expected-sha")


def test_checkout_provenance_fails_closed_when_git_preflight_fails(monkeypatch):
    def fail_run(*_args, **_kwargs):
        raise OSError("read-only checkout unavailable")

    monkeypatch.setattr(provenance.subprocess, "run", fail_run)
    provenance.verify_runtime_checkout_provenance.cache_clear()

    with pytest.raises(provenance.RuntimeProvenanceError, match="could not be verified"):
        provenance.verify_runtime_checkout_provenance("/hermes", "expected-sha")


def test_first_remote_dispatch_does_not_scan_a_slow_checkout(monkeypatch):
    calls: list[tuple[object, dict[str, object]]] = []

    def slow_status(*args, **kwargs):
        calls.append((args, kwargs))
        time.sleep(5.1)
        raise AssertionError("remote runtime dispatch reached the checkout status scan")

    monkeypatch.setattr(provenance.subprocess, "run", slow_status)

    with pytest.raises(provenance.RuntimeProvenanceError, match="must not be paired"):
        provenance.preflight_runtime_provenance(
            "/hermes",
            "expected-sha",
            remote_runtime=True,
        )

    assert calls == []
