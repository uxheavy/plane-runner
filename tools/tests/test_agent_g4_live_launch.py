from __future__ import annotations

import importlib.util
import json
import stat
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

TOOLS = Path(__file__).parents[1]
ROOT = TOOLS.parent
CURRENT_MANIFEST = json.loads((TOOLS / "agent-g4-manifest.json").read_text(encoding="utf-8"))
CURRENT_API_SOURCE = CURRENT_MANIFEST["pins"]["apiArtifact"]["sourceRevision"]
CURRENT_RUNTIME_SOURCE = CURRENT_MANIFEST["pins"]["runtimeImageRevision"]
V64_WRAPPER = "01a67e40b73801438638ea56d09105c318b1f444"
_SPEC = importlib.util.spec_from_file_location("agent_g4_live_launch", TOOLS / "agent-g4-live-launch.py")
assert _SPEC is not None and _SPEC.loader is not None
launch = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(launch)
_INPUTS_SPEC = importlib.util.spec_from_file_location(
    "prepare_agent_g4_live_inputs", TOOLS / "prepare-agent-g4-live-inputs.py"
)
assert _INPUTS_SPEC is not None and _INPUTS_SPEC.loader is not None
launch_inputs = importlib.util.module_from_spec(_INPUTS_SPEC)
_INPUTS_SPEC.loader.exec_module(launch_inputs)


def test_prepare_authority_window_tracks_current_utc_date() -> None:
    first = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)
    later = first + timedelta(days=365)

    first_issued, first_expires = launch_inputs.authority_window(first)
    later_issued, later_expires = launch_inputs.authority_window(later)

    assert first_issued == "2026-08-18T11:59:00Z"
    assert first_expires == "2026-08-19T12:00:00Z"
    assert later_issued == "2027-08-18T11:59:00Z"
    assert later_expires == "2027-08-19T12:00:00Z"


def test_prepare_authority_window_requires_timezone() -> None:
    with pytest.raises(ValueError, match="authority_window_requires_timezone"):
        launch_inputs.authority_window(datetime(2026, 8, 18, 12, 0))


def test_prepare_defaults_to_manifest_for_exact_checked_in_wrapper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = TOOLS.parent
    descriptor = tmp_path / "descriptor.json"
    descriptor.write_text("{}", encoding="utf-8")
    run_dir = tmp_path / "prepared"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prepare-agent-g4-live-inputs.py",
            "--root",
            str(root),
            "--descriptor",
            str(descriptor),
            "--run-dir",
            str(run_dir),
            "--candidate",
            V64_WRAPPER,
        ],
    )

    assert launch_inputs.main() == 0
    authority = json.loads((run_dir / "authority.json").read_text(encoding="utf-8"))
    assert authority["expectedCandidate"] == V64_WRAPPER
    for name in ("authority.json", "config.json", "descriptor.json"):
        metadata = (run_dir / name).stat()
        assert metadata.st_uid == launch_inputs.os.getuid()
        assert launch_inputs.stat.S_ISREG(metadata.st_mode)
        assert launch_inputs.stat.S_IMODE(metadata.st_mode) == 0o600


def test_prepare_rejects_source_when_wrapper_is_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = TOOLS.parent
    descriptor = tmp_path / "descriptor.json"
    descriptor.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prepare-agent-g4-live-inputs.py",
            "--root",
            str(root),
            "--descriptor",
            str(descriptor),
            "--run-dir",
            str(tmp_path / "rejected"),
            "--candidate",
            CURRENT_RUNTIME_SOURCE,
        ],
    )

    with pytest.raises(ValueError, match="candidate_is_not_exact_single_child"):
        launch_inputs.main()


def test_run_paths_are_derived_from_one_directory() -> None:
    paths = launch.derive_run_paths(Path("/tmp/persona-wave-v6/worker"))

    assert paths == {
        "run_dir": Path("/tmp/persona-wave-v6/worker"),
        "authority": Path("/tmp/persona-wave-v6/worker/authority.json"),
        "config": Path("/tmp/persona-wave-v6/worker/config.json"),
        "descriptor": Path("/tmp/persona-wave-v6/worker/descriptor.json"),
        "result": Path("/tmp/persona-wave-v6/worker/result.json"),
    }


def test_stage_manifest_copies_into_owner_only_run_scope(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir(mode=0o700)
    source = tmp_path / "manifest.json"
    source.write_bytes(b'{"pins":{}}')
    source.chmod(0o600)

    staged = launch.stage_owner_only_manifest(run_dir, source)

    assert staged == run_dir / "manifest.json"
    assert staged.read_bytes() == source.read_bytes()
    assert stat.S_IMODE(staged.stat().st_mode) == 0o600


def test_stage_manifest_rejects_reused_destination(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir(mode=0o700)
    (run_dir / "manifest.json").write_bytes(b"caller-owned")
    source = tmp_path / "manifest-source.json"
    source.write_bytes(b"manifest")
    source.chmod(0o600)

    with pytest.raises(ValueError, match="launch_manifest_staging_collision"):
        launch.stage_owner_only_manifest(run_dir, source)


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


def test_runner_binds_lifecycle_candidate_to_host_wrapper() -> None:
    runner = (TOOLS / "agent-g4-live.sh").read_text(encoding="utf-8")

    assert 'G4_CANDIDATE="${G4_EXPECTED_HOST_CANDIDATE}"' in runner
    assert 'G4_CANDIDATE="${PLANE_G4_ARTIFACT_CANDIDATE:-${G4_EXPECTED_HOST_CANDIDATE}}"' not in runner


def test_launch_defaults_to_checked_in_wrapper_manifest() -> None:
    assert launch.resolve_manifest(None) == launch.DEFAULT_MANIFEST
    launch._checked_in_manifest(launch.DEFAULT_MANIFEST)
    provenance = launch.load_manifest_provenance(launch.DEFAULT_MANIFEST)
    assert provenance["candidate"] == CURRENT_API_SOURCE
    assert provenance["runtimeImage"]["sourceRevision"] == CURRENT_RUNTIME_SOURCE


def test_launch_rejects_similarly_named_manifest_outside_owned_tmp(tmp_path: Path) -> None:
    stale = tmp_path / "agent-g4-manifest.json"
    stale.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="launch_manifest_out_of_scope"):
        launch.resolve_manifest(stale)


def test_config_preflight_uses_repository_python_and_one_wrapper_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str] = []

    def fake_run(command, **_kwargs):
        captured.extend(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(launch.subprocess, "run", fake_run)
    paths = {
        "authority": Path("/tmp/authority.json"),
        "config": Path("/tmp/config.json"),
        "manifest": launch.DEFAULT_MANIFEST,
    }

    launch._validate_config(paths, "a" * 40)

    assert captured[0] == sys.executable
    assert captured.count("--candidate") == 1


def test_launch_inputs_accept_checked_in_default_manifest() -> None:
    launch.RUN_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    run_dir = launch.RUN_ROOT / "test-launch-default-manifest-regression"
    run_dir.mkdir(mode=0o700, exist_ok=False)
    try:
        for name in ("authority.json", "config.json", "descriptor.json"):
            path = run_dir / name
            path.write_text("{}", encoding="utf-8")
            path.chmod(0o600)
        paths = launch.validate_run_inputs(run_dir, launch.DEFAULT_MANIFEST)
        assert paths["manifest"] == launch.DEFAULT_MANIFEST
    finally:
        for child in run_dir.iterdir():
            child.unlink()
        run_dir.rmdir()


def test_provider_source_is_handed_off_without_reading_payload(tmp_path: Path) -> None:
    provider_source = tmp_path / "provider-source"
    provider_source.write_bytes(b"must-not-be-read")
    provider_source.chmod(0o600)
    paths = launch.derive_run_paths(Path("/tmp/persona-wave-v6/worker"))
    paths["manifest"] = Path("/tmp/persona-wave-v6/manifest.json")

    assert launch.validate_provider_source(provider_source) == provider_source
    environment = launch.build_launch_environment(
        paths,
        artifact_revision="a" * 40,
        host_revision="b" * 40,
        descriptor_digest="c" * 64,
        provider_source=provider_source,
    )
    assert environment["PLANE_G4_PROVIDER_SECRET_SOURCE"] == str(provider_source)


def test_provider_source_rejects_non_owner_only_metadata(tmp_path: Path) -> None:
    provider_source = tmp_path / "provider-source"
    provider_source.write_bytes(b"opaque")
    provider_source.chmod(0o644)

    with pytest.raises(ValueError, match="launch_provider_source_not_owner_only_regular_file"):
        launch.validate_provider_source(provider_source)


def test_launch_uses_wrapper_for_host_and_manifest_source_for_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wrapper = "b" * 40
    source = "a" * 40
    provider_source = tmp_path / "provider-source"
    provider_source.write_bytes(b"opaque")
    provider_source.chmod(0o600)
    paths = launch.derive_run_paths(tmp_path / "run")
    paths["manifest"] = launch.DEFAULT_MANIFEST
    captured: dict[str, object] = {}

    monkeypatch.setattr(launch, "resolve_manifest", lambda _manifest: launch.DEFAULT_MANIFEST)
    monkeypatch.setattr(launch, "validate_run_inputs", lambda _run_dir, _manifest: paths)
    monkeypatch.setattr(launch, "stage_owner_only_manifest", lambda _run_dir, _manifest: paths["manifest"])
    monkeypatch.setattr(launch, "_validate_config", lambda _paths, _candidate: None)
    monkeypatch.setattr(launch, "_validate_descriptor", lambda _paths: "c" * 64)
    monkeypatch.setattr(launch, "_host_revision", lambda: wrapper)
    monkeypatch.setattr(launch, "load_manifest_provenance", lambda _manifest: {"candidate": source})

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["environment"] = kwargs["env"]
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(launch.subprocess, "run", fake_run)

    assert launch.launch(tmp_path / "run", None, wrapper, provider_source) == 0
    environment = captured["environment"]
    assert isinstance(environment, dict)
    assert environment["PLANE_G4_EXPECTED_CANDIDATE"] == wrapper
    assert environment["PLANE_G4_ARTIFACT_CANDIDATE"] == source
    assert environment["PLANE_G4_PROVIDER_SECRET_SOURCE"] == str(provider_source)


def test_exact_dry_invocation_binds_provider_source_and_fresh_result_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir(mode=0o700)
    provider_source = tmp_path / "provider-source"
    provider_source.write_bytes(b"opaque-provider-source")
    provider_source.chmod(0o600)
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}")
    manifest.chmod(0o600)
    captured: dict[str, object] = {}

    def fake_launch(run_path, manifest_path, candidate, source_path, commission_id=None):
        paths = launch.derive_run_paths(run_path)
        captured.update(
            {
                "manifest": manifest_path,
                "candidate": candidate,
                "provider_source": source_path,
                "result": paths["result"],
            }
        )
        assert not paths["result"].exists()
        return 0

    monkeypatch.setattr(launch, "launch", fake_launch)

    assert launch.main(
        [
            "--run-dir",
            str(run_dir),
            "--manifest",
            str(manifest),
            "--candidate",
            "a" * 40,
            "--provider-source",
            str(provider_source),
        ]
    ) == 0

    assert captured == {
        "manifest": manifest.resolve(),
        "candidate": "a" * 40,
        "provider_source": provider_source,
        "result": run_dir / "result.json",
    }
    assert not (run_dir / "result.json").exists()


def test_launch_binds_one_validated_commission() -> None:
    paths = launch.derive_run_paths(Path("/tmp/persona-wave-v6/worker"))
    paths["manifest"] = Path("/tmp/persona-wave-v6/manifest.json")

    environment = launch.build_launch_environment(
        paths,
        artifact_revision="a" * 40,
        host_revision="b" * 40,
        descriptor_digest="c" * 64,
        commission_id="context-governance",
    )

    assert environment["PLANE_G4_SCENARIO_COMMISSION_ID"] == "context-governance"

    with pytest.raises(ValueError, match="launch_commission_id_invalid"):
        launch.build_launch_environment(
            paths,
            artifact_revision="a" * 40,
            host_revision="b" * 40,
            descriptor_digest="c" * 64,
            commission_id="../other-commission",
        )


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


def test_manifest_provenance_preserves_split_source_revisions(tmp_path: Path) -> None:
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

    provenance = launch.load_manifest_provenance(manifest)

    assert provenance["candidate"] == "b" * 40
    assert provenance["runtimeImage"]["sourceRevision"] == "e" * 40
