#!/usr/bin/env python3
"""Launch the existing G4 runner from one validated owner-only run directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = ROOT / "tmp" / "persona-wave-v6"
DEFAULT_MANIFEST = ROOT / "tools" / "agent-g4-manifest.json"
RUNNER = ROOT / "tools" / "agent-g4-live.sh"
VALIDATOR = ROOT / "tools" / "validate_agent_g4_live.py"
SCENARIO_VALIDATOR = ROOT / "tools" / "agent_g4_live_scenario.py"
RUNNER_COMMAND = "bash tools/agent-g4-live.sh"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
COMMISSION_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:/-]{0,63}$")


def derive_run_paths(run_dir: Path) -> dict[str, Path]:
    """Derive every owner-controlled live input/output path from one run directory."""

    return {
        "run_dir": run_dir,
        "authority": run_dir / "authority.json",
        "config": run_dir / "config.json",
        "descriptor": run_dir / "descriptor.json",
        "result": run_dir / "result.json",
    }


def _owner_only_directory(path: Path) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ValueError("launch_run_directory_missing") from exc
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
        raise ValueError("launch_run_directory_not_owner_only")


def _owner_only_file(path: Path, reason: str) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ValueError(reason) from exc
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o600:
        raise ValueError(reason)


def _checked_in_manifest(path: Path) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ValueError("launch_manifest_missing") from exc
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o022:
        raise ValueError("launch_checked_in_manifest_not_safe_regular_file")


def load_manifest_provenance(manifest: Path) -> dict[str, object]:
    """Read the exact API/runtime/Hermes pins from one disposable manifest."""

    if manifest == DEFAULT_MANIFEST:
        _checked_in_manifest(manifest)
    else:
        _owner_only_file(manifest, "launch_manifest_not_owner_only_regular_file")
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("launch_manifest_invalid_json") from exc
    pins = payload.get("pins") if isinstance(payload, dict) else None
    api = pins.get("apiArtifact") if isinstance(pins, dict) else None
    if not isinstance(pins, dict) or not isinstance(api, dict):
        raise ValueError("launch_manifest_provenance_missing")
    candidate = api.get("sourceRevision")
    runtime_revision = pins.get("runtimeImageRevision")
    hermes_commit = pins.get("hermesCommit")
    api_digest = api.get("imageDigest")
    api_tag = api.get("imageTag")
    runtime_digest = pins.get("runtimeImageDigest")
    runtime_tag = pins.get("runtimeImageTag")
    if (
        not isinstance(candidate, str)
        or not SHA_RE.fullmatch(candidate)
        or runtime_revision != candidate
        or not isinstance(hermes_commit, str)
        or not SHA_RE.fullmatch(hermes_commit)
        or not isinstance(api_digest, str)
        or not DIGEST_RE.fullmatch(api_digest)
        or not isinstance(runtime_digest, str)
        or not DIGEST_RE.fullmatch(runtime_digest)
        or not isinstance(api_tag, str)
        or not api_tag
        or not isinstance(runtime_tag, str)
        or not runtime_tag
    ):
        raise ValueError("launch_manifest_provenance_mismatch")
    return {
        "candidate": candidate,
        "hermesCommit": hermes_commit,
        "apiArtifact": dict(api),
        "runtimeImage": {
            "imageDigest": runtime_digest,
            "imageTag": runtime_tag,
            "sourceRevision": runtime_revision,
        },
    }


def resolve_manifest(manifest: Path | None) -> Path:
    """Select only the checked-in wrapper manifest unless a disposable path is explicit."""

    selected = DEFAULT_MANIFEST if manifest is None else manifest
    if not selected.is_absolute():
        raise ValueError("launch_manifest_must_be_absolute")
    try:
        resolved = selected.resolve(strict=True)
    except OSError as exc:
        raise ValueError("launch_manifest_missing") from exc
    if resolved != selected:
        raise ValueError("launch_manifest_must_not_be_a_symlink")
    if resolved != DEFAULT_MANIFEST and not resolved.is_relative_to(ROOT / "tmp"):
        raise ValueError("launch_manifest_out_of_scope")
    return resolved


def validate_provider_source(path: Path) -> Path:
    """Validate the trusted provider source without opening or reading it."""

    if not path.is_absolute():
        raise ValueError("launch_provider_source_must_be_absolute")
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ValueError("launch_provider_source_missing") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_size > 64 * 1024
    ):
        raise ValueError("launch_provider_source_not_owner_only_regular_file")
    return path


def validate_run_inputs(run_dir: Path, manifest: Path) -> dict[str, Path]:
    """Reject ambiguous, symlinked, or reusable live destinations before Docker/provider access."""

    if not run_dir.is_absolute() or not manifest.is_absolute():
        raise ValueError("launch_paths_must_be_absolute")
    original_run_dir = run_dir
    original_manifest = manifest
    run_dir = run_dir.resolve(strict=True)
    manifest = manifest.resolve(strict=True)
    if run_dir != original_run_dir or manifest != original_manifest or not run_dir.is_relative_to(RUN_ROOT):
        raise ValueError("launch_run_directory_out_of_scope")
    if manifest != DEFAULT_MANIFEST and not manifest.is_relative_to(ROOT / "tmp"):
        raise ValueError("launch_manifest_out_of_scope")
    _owner_only_directory(run_dir)
    paths = derive_run_paths(run_dir)
    for name in ("authority", "config", "descriptor"):
        _owner_only_file(paths[name], f"launch_{name}_not_owner_only_regular_file")
    if paths["result"].exists() or paths["result"].is_symlink():
        raise ValueError("launch_result_must_be_absent")
    if manifest == DEFAULT_MANIFEST:
        _checked_in_manifest(manifest)
    else:
        _owner_only_file(manifest, "launch_manifest_not_owner_only_regular_file")
    paths["manifest"] = manifest
    return paths


def _validate_config(paths: dict[str, Path], candidate: str) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--authority",
            str(paths["authority"]),
            "--config",
            str(paths["config"]),
            "--manifest",
            str(paths["manifest"]),
            "--candidate",
            candidate,
            "--expected-candidate",
            candidate,
            "--command",
            RUNNER_COMMAND,
            "--config-only",
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError("launch_config_preflight_failed")


def _host_revision() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError("launch_host_revision_unavailable") from exc
    host_revision = result.stdout.strip()
    if not SHA_RE.fullmatch(host_revision):
        raise ValueError("launch_host_revision_invalid")
    return host_revision


def _validate_descriptor(paths: dict[str, Path]) -> str:
    digest = hashlib.sha256(paths["descriptor"].read_bytes()).hexdigest()
    result = subprocess.run(
        [sys.executable, str(SCENARIO_VALIDATOR), "--descriptor", str(paths["descriptor"]), "--sha256", digest],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError("launch_descriptor_preflight_failed")
    return digest


def build_launch_environment(
    paths: dict[str, Path],
    *,
    artifact_revision: str,
    host_revision: str,
    descriptor_digest: str,
    provider_source: Path | None = None,
    commission_id: str | None = None,
) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "PLANE_G4_EXPECTED_CANDIDATE": host_revision,
            "PLANE_G4_ARTIFACT_CANDIDATE": artifact_revision,
            "PLANE_G4_LIVE_AUTHORITY": str(paths["authority"]),
            "PLANE_G4_LIVE_CONFIG": str(paths["config"]),
            "PLANE_G4_LIVE_MANIFEST": str(paths["manifest"]),
            "PLANE_G4_SCENARIO_DESCRIPTOR": str(paths["descriptor"]),
            "PLANE_G4_SCENARIO_SHA256": descriptor_digest,
            "PLANE_G4_LIVE_RESULT_PATH": str(paths["result"]),
            "PLANE_G4_LIVE_COMMAND": RUNNER_COMMAND,
        }
    )
    if provider_source is not None:
        environment["PLANE_G4_PROVIDER_SECRET_SOURCE"] = str(provider_source)
    environment.pop("PLANE_G4_SCENARIO_COMMISSION_ID", None)
    if commission_id is not None:
        if not COMMISSION_ID_RE.fullmatch(commission_id):
            raise ValueError("launch_commission_id_invalid")
        environment["PLANE_G4_SCENARIO_COMMISSION_ID"] = commission_id
    return environment


def launch(
    run_dir: Path,
    manifest: Path | None,
    candidate: str,
    provider_source: Path,
    commission_id: str | None = None,
) -> int:
    if not SHA_RE.fullmatch(candidate):
        raise ValueError("launch_candidate_must_be_full_sha")
    manifest = resolve_manifest(manifest)
    paths = validate_run_inputs(run_dir, manifest)
    _validate_config(paths, candidate)
    descriptor_digest = _validate_descriptor(paths)
    provider_source = validate_provider_source(provider_source)
    host_revision = _host_revision()
    if host_revision != candidate:
        raise ValueError("launch_candidate_is_not_checked_out_wrapper")
    provenance = load_manifest_provenance(manifest)
    artifact_revision = provenance["candidate"]
    assert isinstance(artifact_revision, str)
    environment = build_launch_environment(
        paths,
        artifact_revision=artifact_revision,
        host_revision=host_revision,
        descriptor_digest=descriptor_digest,
        provider_source=provider_source,
        commission_id=commission_id,
    )
    completed = subprocess.run(["bash", str(RUNNER)], cwd=ROOT, env=environment, check=False)
    print(f"event=agent.g4.live-launch status=exited code={completed.returncode} result={paths['result']}")
    return completed.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Checked-in wrapper manifest by default; disposable manifests must be under tmp/",
    )
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--provider-source", required=True, type=Path)
    parser.add_argument("--commission-id")
    args = parser.parse_args(argv)
    try:
        return launch(
            args.run_dir,
            args.manifest,
            args.candidate,
            args.provider_source,
            args.commission_id,
        )
    except ValueError as exc:
        print(f"event=agent.g4.live-launch status=failed reason={exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
