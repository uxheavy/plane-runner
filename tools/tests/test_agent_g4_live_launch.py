from __future__ import annotations

from pathlib import Path

import pytest

import importlib.util

TOOLS = Path(__file__).parents[1]
_SPEC = importlib.util.spec_from_file_location("agent_g4_live_launch", TOOLS / "agent-g4-live-launch.py")
assert _SPEC is not None and _SPEC.loader is not None
launch = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(launch)


def test_run_paths_are_derived_from_one_directory() -> None:
    paths = launch.derive_run_paths(Path("/tmp/persona-wave-v6/worker"))

    assert paths == {
        "run_dir": Path("/tmp/persona-wave-v6/worker"),
        "authority": Path("/tmp/persona-wave-v6/worker/authority.json"),
        "config": Path("/tmp/persona-wave-v6/worker/config.json"),
        "descriptor": Path("/tmp/persona-wave-v6/worker/descriptor.json"),
        "result": Path("/tmp/persona-wave-v6/worker/result.json"),
    }


def test_validate_run_inputs_rejects_non_owner_only_inputs(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir(mode=0o700)
    for name in ("authority.json", "config.json", "descriptor.json"):
        path = run_dir / name
        path.write_text("{}")
        path.chmod(0o600)
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}")
    manifest.chmod(0o600)

    with pytest.raises(ValueError, match="launch_run_directory_out_of_scope"):
        launch.validate_run_inputs(run_dir, manifest)


def test_validate_run_inputs_rejects_existing_result_under_owned_scope() -> None:
    run_dir = launch.RUN_ROOT / "test-launch-regression"
    run_dir.mkdir(mode=0o700, exist_ok=True)
    try:
        for name in ("authority.json", "config.json", "descriptor.json", "result.json"):
            path = run_dir / name
            path.write_text("{}")
            path.chmod(0o600)
        manifest = launch.RUN_ROOT / "test-launch-manifest.json"
        manifest.write_text("{}")
        manifest.chmod(0o600)
        try:
            with pytest.raises(ValueError, match="launch_result_must_be_absent"):
                launch.validate_run_inputs(run_dir, manifest)
        finally:
            manifest.unlink()
    finally:
        for child in run_dir.iterdir():
            child.unlink()
        run_dir.rmdir()
