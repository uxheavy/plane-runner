#!/usr/bin/env python3
"""Build and attest the dedicated production Plane Agent runtime image."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


HERMES_COMMIT = "114eabf9d807b659e36d767e4de46ca056297ccb"
HERMES_REMOTE = "github.com/uxheavy/hermes-agent"
DOCKERFILE = Path(__file__).resolve().parents[1] / "deployments/cli/community/agent-runtime/Dockerfile"
PLANE_RUNTIME = Path(__file__).resolve().parents[1] / "apps/api/plane/agent/runtime"


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


def verify_plane() -> str:
    root = DOCKERFILE.parents[4]
    dirty = run("git", "status", "--porcelain", "--untracked-files=all", cwd=root)
    if dirty:
        raise RuntimeError("Plane checkout must be clean before an image is built")
    return run("git", "rev-parse", "HEAD", cwd=root)


def stage_context(checkout: Path, destination: Path) -> None:
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
    shutil.copytree(
        PLANE_RUNTIME,
        destination / "plane_runtime_service",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hermes-checkout", required=True, type=Path)
    parser.add_argument("--tag", default="plane-agent-runtime:hermes-114eabf9-g4-98f4762")
    args = parser.parse_args()
    if shutil.which("docker") is None:
        raise SystemExit("Docker CLI is required")
    verify_hermes(args.hermes_checkout)
    plane_revision = verify_plane()
    with tempfile.TemporaryDirectory(prefix="plane-agent-runtime-build-") as temporary:
        context = Path(temporary)
        stage_context(args.hermes_checkout, context)
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
            str(context),
            capture=False,
        )
    image_id = run("docker", "image", "inspect", args.tag, "--format", "{{.Id}}")
    labels = json.loads(run("docker", "image", "inspect", args.tag, "--format", "{{json .Config.Labels}}"))
    print(
        json.dumps(
            {
                "image": args.tag,
                "imageDigest": image_id,
                "hermesCommit": HERMES_COMMIT,
                "hermesRemote": HERMES_REMOTE,
                "planeRevision": plane_revision,
                "labels": labels,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
