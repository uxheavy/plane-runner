#!/usr/bin/env python3
"""Build one candidate-bound Plane Agent API artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "apps/api/Dockerfile.g4"
DEFAULT_BASE_IMAGE = "plane-g3-external-client-api-tests:prepared"
CONTRACT = "plane.operation/v1"
ARTIFACT = "plane-agent-api-g4"
TYPESCRIPT_VERSION = "5.4.5"
SOURCE_FILES = {
    "PLANE_API_MANAGE_SHA256": "apps/api/manage.py",
    "PLANE_API_READBACK_SHA256": "apps/api/plane/agent/readback.py",
    "PLANE_API_ADMIN_SHA256": "apps/api/plane/api/views/agent_admin.py",
    "PLANE_API_CORRUPTION_TEST_SHA256": "apps/api/plane/tests/contract/api/test_agent_admin.py",
    "PLANE_API_PROVIDER_CONFIG_SHA256": "apps/api/plane/agent/runtime/config.py",
}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def _run(*args: str, capture: bool = True) -> str:
    result = subprocess.run(
        list(args),
        cwd=ROOT,
        check=False,
        capture_output=capture,
        text=capture,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines() if capture else []
        raise RuntimeError(f"{' '.join(args)} failed: {(detail[-1] if detail else 'no output')[:240]}")
    return result.stdout.strip() if capture else ""


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _git_sha(value: str, name: str) -> str:
    if not SHA_RE.fullmatch(value):
        raise ValueError(f"{name} must be a full lowercase Git SHA")
    return value


def _regular_source(path: Path, relative: str) -> None:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError(f"API source is not a regular file: {relative}")
    if metadata.st_mode & 0o022 or metadata.st_mode & 0o7000:
        raise RuntimeError(f"API source has unsafe permissions: {relative}")


def candidate_head() -> str:
    return _git_sha(_run("git", "rev-parse", "HEAD"), "HEAD")


def verify_clean_candidate(candidate: str | None = None) -> str:
    """Resolve full HEAD and reject any source that is not that exact checkout."""

    dirty = _run("git", "status", "--porcelain", "--untracked-files=all")
    if dirty:
        raise RuntimeError("Plane checkout must be clean before an API image is built")
    head = candidate_head()
    if candidate is not None and _git_sha(candidate, "--candidate") != head:
        raise RuntimeError(f"candidate must equal full HEAD {head}")
    return head


def source_hashes(candidate: str) -> dict[str, str]:
    """Hash the exact committed source and prove the build context matches it."""

    _git_sha(candidate, "candidate")
    result: dict[str, str] = {}
    for argument, relative in SOURCE_FILES.items():
        path = ROOT / relative
        _regular_source(path, relative)
        committed = subprocess.run(
            ["git", "show", f"{candidate}:{relative}"],
            cwd=ROOT,
            check=False,
            capture_output=True,
        )
        if committed.returncode != 0:
            raise RuntimeError(f"API source is unavailable at {candidate}: {relative}")
        expected = _sha256(committed.stdout)
        actual = _sha256(path.read_bytes())
        if actual != expected:
            raise RuntimeError(f"API source does not match candidate HEAD: {relative}")
        result[argument] = expected
    return result


def verify_dockerfile_contract() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")
    required = [
        "ARG PLANE_API_SOURCE_REVISION",
        "ARG PLANE_API_IMAGE_TAG",
        "ARG PLANE_API_CONTRACT=plane.operation/v1",
        f"ARG PLANE_TYPESCRIPT_VERSION={TYPESCRIPT_VERSION}",
        *[f"ARG {name}" for name in SOURCE_FILES],
        'org.uxheavy.plane.api.artifact="plane-agent-api-g4"',
        'org.uxheavy.plane.api.code-mode.typescript.version="${PLANE_TYPESCRIPT_VERSION}"',
    ]
    missing = [item for item in required if item not in text]
    if missing:
        raise RuntimeError(f"Dockerfile.g4 API contract is missing: {','.join(missing)}")


def image_tag(candidate: str) -> str:
    return f"plane-agent-api:g4-v6-{candidate[:8]}"


def docker_build_command(
    candidate: str,
    hashes: dict[str, str],
    *,
    base_image: str = DEFAULT_BASE_IMAGE,
    tag: str | None = None,
) -> list[str]:
    _git_sha(candidate, "candidate")
    if not base_image:
        raise ValueError("API base image is required")
    selected_tag = tag or image_tag(candidate)
    if set(hashes) != set(SOURCE_FILES) or any(not HASH_RE.fullmatch(value) for value in hashes.values()):
        raise ValueError("API source hashes are incomplete or invalid")
    return [
        "docker",
        "build",
        "--network",
        "none",
        "-f",
        str(DOCKERFILE.relative_to(ROOT)),
        "--tag",
        selected_tag,
        "--build-arg",
        f"BASE_API_IMAGE={base_image}",
        "--build-arg",
        f"PLANE_TYPESCRIPT_VERSION={TYPESCRIPT_VERSION}",
        "--build-arg",
        f"PLANE_API_SOURCE_REVISION={candidate}",
        "--build-arg",
        f"PLANE_API_IMAGE_TAG={selected_tag}",
        *sum((["--build-arg", f"{name}={hashes[name]}"] for name in SOURCE_FILES), []),
        str(DOCKERFILE.parent.relative_to(ROOT)),
    ]


def verify_base_image(base_image: str) -> None:
    """Reject a prepared base that does not carry the pinned Code Mode compiler."""

    probe = (
        "const actual = require('/usr/share/node_modules/typescript/lib/typescript.js').version; "
        f"if (actual !== {TYPESCRIPT_VERSION!r}) process.exit(1)"
    )
    try:
        _run(
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--entrypoint",
            "node",
            base_image,
            "-e",
            probe,
        )
    except RuntimeError as exc:
        raise RuntimeError(
            f"API base image does not contain TypeScript {TYPESCRIPT_VERSION}"
        ) from exc


def image_metadata(tag: str) -> dict[str, object]:
    image_id = _run("docker", "image", "inspect", tag, "--format", "{{.Id}}")
    labels_raw = _run("docker", "image", "inspect", tag, "--format", "{{json .Config.Labels}}")
    labels = json.loads(labels_raw)
    if not isinstance(labels, dict):
        raise RuntimeError("API image labels are missing")
    return {"imageTag": tag, "imageDigest": image_id, "labels": labels}


def build_api_image(
    *,
    candidate: str | None = None,
    base_image: str = DEFAULT_BASE_IMAGE,
    tag: str | None = None,
) -> dict[str, str]:
    verify_dockerfile_contract()
    resolved = verify_clean_candidate(candidate)
    hashes = source_hashes(resolved)
    verify_base_image(base_image)
    selected_tag = tag or image_tag(resolved)
    _run(*docker_build_command(resolved, hashes, base_image=base_image, tag=selected_tag), capture=False)
    metadata = image_metadata(selected_tag)
    labels = metadata["labels"]
    assert isinstance(labels, dict)
    expected_labels = {
        "org.uxheavy.plane.api.artifact": ARTIFACT,
        "org.uxheavy.plane.api.contract": CONTRACT,
        "org.uxheavy.plane.api.source.revision": resolved,
        "org.uxheavy.plane.api.image.tag": selected_tag,
        "org.uxheavy.plane.api.source.manage.sha256": hashes["PLANE_API_MANAGE_SHA256"],
        "org.uxheavy.plane.api.source.readback.sha256": hashes["PLANE_API_READBACK_SHA256"],
        "org.uxheavy.plane.api.source.agent-admin.sha256": hashes["PLANE_API_ADMIN_SHA256"],
        "org.uxheavy.plane.api.source.corruption-test.sha256": hashes["PLANE_API_CORRUPTION_TEST_SHA256"],
        "org.uxheavy.plane.api.source.provider-config.sha256": hashes["PLANE_API_PROVIDER_CONFIG_SHA256"],
    }
    for label, expected in expected_labels.items():
        if str(labels.get(label, "")) != expected:
            raise RuntimeError(f"API image label mismatch: {label}")
    return {"imageTag": selected_tag, "imageDigest": str(metadata["imageDigest"]), "sourceRevision": resolved, "contract": CONTRACT}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate")
    parser.add_argument("--base-image", default=DEFAULT_BASE_IMAGE)
    parser.add_argument("--tag")
    args = parser.parse_args(argv)
    print(json.dumps(build_api_image(candidate=args.candidate, base_image=args.base_image, tag=args.tag), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
