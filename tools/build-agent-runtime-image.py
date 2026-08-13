#!/usr/bin/env python3
"""Build and attest the dedicated production Plane Agent runtime image."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


HERMES_COMMIT = "d2e655101f263329359e7d0de9d0b856202a3e4b"
HERMES_REMOTE = "github.com/uxheavy/hermes-agent"
RUNTIME_CONTRACT = "plane.agent-runtime/v1"
DOCKERFILE = Path(__file__).resolve().parents[1] / "deployments/cli/community/agent-runtime/Dockerfile"
ROOT = DOCKERFILE.parents[4]
DURABLE_MANIFEST = ROOT / "tools/agent-g4-manifest.json"


def run(*args: str, cwd: Path | None = None, capture: bool = True) -> str:
    result = subprocess.run(
        list(args),
        cwd=cwd,
        check=False,
        capture_output=capture,
        text=capture,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        raise RuntimeError(f"{' '.join(args)} failed: {(detail[-1] if detail else 'no output')[:240]}")
    return result.stdout.strip() if capture else ""


def verify_hermes(checkout: Path) -> None:
    actual = run("git", "-C", str(checkout), "rev-parse", "HEAD")
    if actual != HERMES_COMMIT:
        raise RuntimeError(f"Hermes checkout SHA is {actual}, expected {HERMES_COMMIT}")
    dirty = run("git", "-C", str(checkout), "status", "--porcelain", "--untracked-files=all")
    if dirty:
        raise RuntimeError("Hermes checkout must be clean before an image is built")
    remotes = run("git", "-C", str(checkout), "remote", "-v")
    if HERMES_REMOTE not in remotes:
        raise RuntimeError("Hermes checkout must have the uxheavy fork configured as a remote")


def verify_plane(revision: str | None = None) -> tuple[str, str]:
    dirty = run("git", "status", "--porcelain", "--untracked-files=all", cwd=ROOT)
    if dirty:
        raise RuntimeError("Plane checkout must be clean before an image is built")
    candidate = run("git", "rev-parse", revision or "HEAD", cwd=ROOT)
    parent = run("git", "rev-parse", f"{candidate}^", cwd=ROOT)
    return candidate, parent


def _git_bytes(revision: str, relative: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{revision}:{relative}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Plane source file is unavailable at {revision}: {relative}")
    return result.stdout


def runtime_file_hashes(revision: str) -> dict[str, str]:
    paths = run(
        "git",
        "ls-tree",
        "-r",
        "--name-only",
        revision,
        "apps/api/plane/agent/runtime",
        cwd=ROOT,
    ).splitlines()
    if not paths:
        raise RuntimeError(f"Plane runtime package is empty at {revision}")
    return {
        relative: hashlib.sha256(_git_bytes(revision, relative)).hexdigest()
        for relative in paths
        if not relative.endswith((".pyc", ".pyo")) and "/__pycache__/" not in relative
    }


def runtime_source_digest(file_hashes: dict[str, str]) -> str:
    encoded = json.dumps(file_hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def stage_context(checkout: Path, destination: Path, plane_revision: str) -> None:
    hermes = destination / "hermes"
    hermes.mkdir()
    archive_path = destination / "hermes.tar"
    with archive_path.open("wb") as archive:
        subprocess.run(
            ["git", "-C", str(checkout), "archive", "--format=tar", HERMES_COMMIT],
            stdout=archive,
            stderr=subprocess.PIPE,
            check=True,
        )
    run("tar", "-xf", str(archive_path), "-C", str(hermes))
    archive_path.unlink()
    plane_archive = destination / "plane-runtime.tar"
    with plane_archive.open("wb") as archive:
        subprocess.run(
            [
                "git",
                "-C",
                str(ROOT),
                "archive",
                "--format=tar",
                plane_revision,
                "apps/api/plane/agent/runtime",
            ],
            stdout=archive,
            stderr=subprocess.PIPE,
            check=True,
        )
    extracted = destination / "plane-source"
    extracted.mkdir()
    run("tar", "-xf", str(plane_archive), "-C", str(extracted))
    plane_archive.unlink()
    shutil.move(
        str(extracted / "apps/api/plane/agent/runtime"),
        str(destination / "plane_runtime_service"),
    )


def image_metadata(image: str) -> dict[str, object]:
    image_id = run("docker", "image", "inspect", image, "--format", "{{.Id}}")
    labels_raw = run("docker", "image", "inspect", image, "--format", "{{json .Config.Labels}}")
    try:
        labels = json.loads(labels_raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Docker image labels are not JSON for {image}") from exc
    if not isinstance(labels, dict):
        raise RuntimeError(f"Docker image labels are missing for {image}")
    return {"imageDigest": image_id, "labels": labels}


def api_artifact(image: str, plane_revision: str) -> dict[str, str]:
    metadata = image_metadata(image)
    labels = metadata["labels"]
    assert isinstance(labels, dict)
    actual = {
        "imageTag": image,
        "imageDigest": str(metadata["imageDigest"]),
        "sourceRevision": str(labels.get("org.uxheavy.plane.api.source.revision", "")),
        "contract": str(labels.get("org.uxheavy.plane.api.contract", "")),
    }
    if actual["sourceRevision"] != plane_revision:
        raise RuntimeError("API image source revision does not match the selected Plane candidate")
    if actual["contract"] != "plane.operation/v1" or labels.get("org.uxheavy.plane.api.artifact") != "plane-agent-api-g4":
        raise RuntimeError("API image is not the bound Plane Agent API artifact")
    return actual


def verify_runtime_image(
    image: str,
    plane_revision: str,
    hermes_commit: str,
    hermes_remote: str,
    contract: str,
    expected_files: dict[str, str],
    expected_source_digest: str,
) -> dict[str, str]:
    metadata = image_metadata(image)
    labels = metadata["labels"]
    assert isinstance(labels, dict)
    expected = {
        "imageTag": image,
        "imageDigest": str(metadata["imageDigest"]),
        "runtimeRevision": str(labels.get("org.uxheavy.plane.runtime.revision", "")),
        "hermesCommit": str(labels.get("org.uxheavy.plane.hermes.commit", "")),
        "hermesRemote": str(labels.get("org.uxheavy.plane.hermes.remote", "")),
        "contract": str(labels.get("org.uxheavy.plane.runtime.contract", "")),
        "runtimeSourceDigest": str(labels.get("org.uxheavy.plane.runtime.source.sha256", "")),
    }
    if expected["runtimeRevision"] != plane_revision:
        raise RuntimeError("runtime image Plane revision does not match the selected Plane candidate")
    if expected["hermesCommit"] != hermes_commit or expected["hermesRemote"] != f"https://{hermes_remote}.git":
        raise RuntimeError("runtime image Hermes provenance does not match the pinned checkout")
    if expected["contract"] != contract or expected["runtimeSourceDigest"] != expected_source_digest:
        raise RuntimeError("runtime image contract or source digest label is not exact")

    probe = (
        "import hashlib,json,pathlib; "
        "root=pathlib.Path('/opt/plane/agent/runtime'); "
        "actual={('apps/api/plane/agent/runtime/'+p.relative_to(root).as_posix()):hashlib.sha256(p.read_bytes()).hexdigest() "
        "for p in root.rglob('*') if p.is_file() and p.suffix not in ('.pyc','.pyo') and '__pycache__' not in p.parts}; "
        "print(json.dumps(actual,sort_keys=True,separators=(',',':')))"
    )
    actual_raw = run(
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--read-only",
        "--entrypoint",
        "python3",
        image,
        "-c",
        probe,
        json.dumps(expected_files, sort_keys=True, separators=(",", ":")),
    )
    try:
        actual_files = json.loads(actual_raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("runtime image source parity probe did not return JSON") from exc
    if actual_files != expected_files:
        raise RuntimeError("runtime image source file hashes do not match the selected Plane candidate")
    return expected


def disposable_manifest(
    plane_revision: str,
    plane_parent: str,
    hermes_commit: str,
    hermes_remote: str,
    runtime: dict[str, str],
    api: dict[str, str],
    runtime_files: dict[str, str],
) -> dict[str, object]:
    manifest = json.loads(DURABLE_MANIFEST.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise RuntimeError("durable G4 manifest must be an object")
    manifest = copy.deepcopy(manifest)
    candidate_binding = manifest["candidateBinding"]
    assert isinstance(candidate_binding, dict)
    candidate_binding.update(
        {
            "mode": "disposable-exact-candidate",
            "parentCommit": plane_parent,
            "candidateCommitSource": "builder-exact-git-revision",
        }
    )
    pins = manifest["pins"]
    assert isinstance(pins, dict)
    pins["runtimeImageTag"] = runtime["imageTag"]
    pins["runtimeImageDigest"] = runtime["imageDigest"]
    pins["runtimeImageRevision"] = plane_revision
    pins["runtimeContract"] = RUNTIME_CONTRACT
    pins["hermesCommit"] = hermes_commit
    pins["apiArtifact"] = api
    manifest["disposableBinding"] = {
        "mode": "exact-api-runtime-candidate",
        "candidateCommit": plane_revision,
        "apiSourceRevision": plane_revision,
        "runtimeRevision": plane_revision,
        "hermesCommit": hermes_commit,
        "hermesRemote": hermes_remote,
        "runtimeSourceDigest": runtime["runtimeSourceDigest"],
        "runtimeFiles": runtime_files,
    }
    return manifest


def write_disposable_manifest(path: Path, manifest: dict[str, object]) -> None:
    if path.is_symlink():
        raise RuntimeError("disposable manifest output must be a regular file")
    resolved = path.resolve()
    disposable_root = ROOT / "tmp"
    if resolved == DURABLE_MANIFEST.resolve() or not resolved.is_relative_to(disposable_root):
        raise RuntimeError("disposable manifest must be under the repository-owned tmp directory")
    resolved.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if resolved.is_symlink() or (resolved.exists() and not resolved.is_file()):
        raise RuntimeError("disposable manifest output must be a regular file")
    resolved.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    resolved.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hermes-checkout", required=True, type=Path)
    parser.add_argument("--tag", default="plane-agent-runtime:hermes-d2e65510-g4-codex-fix")
    parser.add_argument("--plane-revision", help="Build an exact clean Git revision instead of HEAD")
    parser.add_argument("--api-image", help="Current candidate API image required for disposable manifest output")
    parser.add_argument("--manifest-out", type=Path, help="Write a disposable manifest under repository tmp/")
    args = parser.parse_args()
    if shutil.which("docker") is None:
        raise SystemExit("Docker CLI is required")
    verify_hermes(args.hermes_checkout)
    plane_revision, plane_parent = verify_plane(args.plane_revision)
    runtime_files = runtime_file_hashes(plane_revision)
    source_digest = runtime_source_digest(runtime_files)
    api = None
    if args.manifest_out is not None:
        if not args.api_image:
            raise SystemExit("--api-image is required with --manifest-out")
        api = api_artifact(args.api_image, plane_revision)
    with tempfile.TemporaryDirectory(prefix="plane-agent-runtime-build-") as temporary:
        context = Path(temporary)
        stage_context(args.hermes_checkout, context, plane_revision)
        run(
            "docker",
            "build",
            "--file",
            str(DOCKERFILE),
            "--tag",
            args.tag,
            "--build-arg",
            f"HERMES_COMMIT={HERMES_COMMIT}",
            "--build-arg",
            f"PLANE_REVISION={plane_revision}",
            "--build-arg",
            f"PLANE_RUNTIME_SOURCE_SHA256={source_digest}",
            str(context),
            capture=False,
        )
    runtime = verify_runtime_image(
        args.tag,
        plane_revision,
        HERMES_COMMIT,
        HERMES_REMOTE,
        RUNTIME_CONTRACT,
        runtime_files,
        source_digest,
    )
    if api is not None:
        assert args.manifest_out is not None
        manifest = disposable_manifest(
            plane_revision,
            plane_parent,
            HERMES_COMMIT,
            HERMES_REMOTE,
            runtime,
            api,
            runtime_files,
        )
        write_disposable_manifest(args.manifest_out, manifest)
    print(
        json.dumps(
            {
                "image": args.tag,
                "imageDigest": runtime["imageDigest"],
                "hermesCommit": HERMES_COMMIT,
                "hermesRemote": HERMES_REMOTE,
                "planeRevision": plane_revision,
                "runtimeSourceDigest": source_digest,
                "runtimeFiles": runtime_files,
                "runtime": runtime,
                "manifest": str(args.manifest_out.resolve()) if args.manifest_out is not None else None,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
