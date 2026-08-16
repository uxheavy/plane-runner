from __future__ import annotations

import json
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


def test_launch_binds_host_wrapper_and_artifact_revisions_separately() -> None:
    paths = launch.derive_run_paths(Path("/tmp/persona-wave-v6/worker"))
    paths["manifest"] = Path("/tmp/persona-wave-v6/manifest.json")

    environment = launch.build_launch_environment(
        paths,
        artifact_revision="a" * 40,
        host_revision="b" * 40,
        descriptor_digest="c" * 64,
    )

    assert environment["PLANE_G4_EXPECTED_CANDIDATE"] == "b" * 40
    assert environment["PLANE_G4_ARTIFACT_CANDIDATE"] == "a" * 40


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
    launch.RUN_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
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


def test_manifest_provenance_derives_current_api_runtime_and_hermes_pins(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "pins": {
                    "apiArtifact": {
                        "imageDigest": "sha256:" + "a" * 64,
                        "imageTag": "plane-agent-api:test",
                        "sourceRevision": "b" * 40,
                    },
                    "hermesCommit": "c" * 40,
                    "runtimeImageDigest": "sha256:" + "d" * 64,
                    "runtimeImageRevision": "b" * 40,
                    "runtimeImageTag": "plane-agent-runtime:test",
                }
            }
        )
    )
    manifest.chmod(0o600)

    assert launch.load_manifest_provenance(manifest) == {
        "candidate": "b" * 40,
        "hermesCommit": "c" * 40,
        "apiArtifact": {
            "imageDigest": "sha256:" + "a" * 64,
            "imageTag": "plane-agent-api:test",
            "sourceRevision": "b" * 40,
        },
        "runtimeImage": {
            "imageDigest": "sha256:" + "d" * 64,
            "imageTag": "plane-agent-runtime:test",
            "sourceRevision": "b" * 40,
        },
    }


def test_manifest_provenance_rejects_mixed_source_revisions(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "pins": {
                    "apiArtifact": {
                        "imageDigest": "sha256:" + "a" * 64,
                        "imageTag": "plane-agent-api:test",
                        "sourceRevision": "b" * 40,
                    },
                    "hermesCommit": "c" * 40,
                    "runtimeImageDigest": "sha256:" + "d" * 64,
                    "runtimeImageRevision": "e" * 40,
                    "runtimeImageTag": "plane-agent-runtime:test",
                }
            }
        )
    )
    manifest.chmod(0o600)

    with pytest.raises(ValueError, match="launch_manifest_provenance_mismatch"):
        launch.load_manifest_provenance(manifest)
