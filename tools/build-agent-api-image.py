#!/usr/bin/env python3
# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Build one candidate-bound Plane Agent API artifact."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import stat
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "apps/api/Dockerfile.g4"
MANIFEST = ROOT / "tools/agent-g4-manifest.json"
ROLLBACK_PINS = ROOT / "apps/api/plane/tests/fixtures/agent_g4_rollback_pins.json"
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
    "PLANE_API_CREDENTIALS_SHA256": "apps/api/plane/agent/runtime/credentials.py",
    "PLANE_API_CREDENTIAL_RESOLVER_SHA256": "apps/api/bin/plane-agent-runtime-credential-resolver",
}
RUNTIME_CONTRACT_DIRECTORY = ROOT / "apps/api/plane/agent/lifecycle/contract_artifacts/v1"
RUNTIME_CONTRACT_SCHEMA_NAMES = (
    "run-snapshot",
    "invocation-envelope",
    "runtime-event",
    "runtime-exit",
    "runtime-durable-state",
)
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
    verify_runtime_contract_artifacts()
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


def verify_runtime_contract_artifacts() -> None:
    """Reject runtime-contract manifest entries that do not match their bytes."""

    directory = RUNTIME_CONTRACT_DIRECTORY
    manifest_path = directory / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"runtime contract manifest is unavailable or invalid: {manifest_path}") from exc
    schemas = manifest.get("schemas") if isinstance(manifest, dict) else None
    if not isinstance(schemas, dict) or set(schemas) != set(RUNTIME_CONTRACT_SCHEMA_NAMES):
        raise RuntimeError(f"runtime contract manifest schema set is invalid: {manifest_path}")
    for name in RUNTIME_CONTRACT_SCHEMA_NAMES:
        entry = schemas.get(name)
        schema_path = directory / f"{name}.schema.json"
        if not isinstance(entry, dict) or entry.get("filename") != schema_path.name:
            raise RuntimeError(f"runtime contract manifest entry is invalid: {schema_path}")
        try:
            actual_digest = _sha256(schema_path.read_bytes())
        except OSError as exc:
            raise RuntimeError(f"runtime contract schema is unavailable: {schema_path}") from exc
        if entry.get("sha256") != actual_digest:
            raise RuntimeError(f"runtime contract schema digest mismatch: {schema_path}")


def verify_dockerfile_contract() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")
    required = [
        "ARG PLANE_API_SOURCE_REVISION",
        "ARG PLANE_API_IMAGE_TAG",
        "ARG PLANE_API_CONTRACT=plane.operation/v1",
        f"ARG PLANE_TYPESCRIPT_VERSION={TYPESCRIPT_VERSION}",
        "RUN rm -rf /workspace/apps/api",
        *[f"ARG {name}" for name in SOURCE_FILES],
        'org.uxheavy.plane.api.artifact="plane-agent-api-g4"',
        'org.uxheavy.plane.api.code-mode.typescript.version="${PLANE_TYPESCRIPT_VERSION}"',
    ]
    missing = [item for item in required if item not in text]
    if missing:
        raise RuntimeError(f"Dockerfile.g4 API contract is missing: {','.join(missing)}")


def image_tag(candidate: str) -> str:
    """Use the checked-in candidate tag, never a version-shaped stale default."""

    _git_sha(candidate, "candidate")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    artifact = manifest.get("pins", {}).get("apiArtifact", {})
    if artifact.get("sourceRevision") != candidate or not artifact.get("imageTag"):
        raise ValueError("--tag is required when candidate is not the manifest-pinned API source")
    return str(artifact["imageTag"])


def default_base_image_binding() -> tuple[str, str]:
    """Read the immutable prepared-base tag and digest from rollback truth."""

    fixture = json.loads(ROLLBACK_PINS.read_text(encoding="utf-8"))
    artifact = fixture.get("previous", {}).get("apiArtifact", {})
    tag = artifact.get("imageTag")
    digest = artifact.get("imageDigest")
    if tag != DEFAULT_BASE_IMAGE or not isinstance(digest, str) or not digest.startswith("sha256:"):
        raise RuntimeError("prepared API base binding is missing or drifted")
    if not HASH_RE.fullmatch(digest.removeprefix("sha256:")):
        raise RuntimeError("prepared API base digest is invalid")
    return tag, digest


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


def verify_base_image(base_image: str, expected_digest: str | None = None) -> None:
    """Reject a prepared base that does not carry the pinned Code Mode compiler."""

    pinned_tag, pinned_digest = default_base_image_binding()
    if expected_digest is None:
        if base_image != pinned_tag:
            raise ValueError("--base-image-digest is required for a non-default API base image")
        expected_digest = pinned_digest
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", expected_digest):
        raise ValueError("API base image digest must be an exact sha256 digest")
    actual_digest = _run("docker", "image", "inspect", base_image, "--format", "{{.Id}}")
    if actual_digest != expected_digest:
        raise RuntimeError("API base image tag does not resolve to the expected prepared digest")
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


def verify_resolver_image(tag: str) -> None:
    """Exercise the packaged resolver network-none without exposing its token."""

    (ROOT / "tmp").mkdir(mode=0o700, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="agent-api-resolver-", dir=ROOT / "tmp") as directory:
        source = Path(directory) / "auth.json"
        now = int(datetime.now(timezone.utc).timestamp())
        encode = lambda value: base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")
        synthetic_access_token = ".".join(
            (
                encode(b'{"alg":"none"}'),
                encode(json.dumps({"iat": now, "exp": now + 3600}, separators=(",", ":")).encode()),
                "synthetic-signature",
            )
        )
        source.write_text(
            json.dumps(
                {
                    "OPENAI_API_KEY": None,
                    "auth_mode": "chatgpt",
                    "last_refresh": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "tokens": {
                        "access_token": synthetic_access_token,
                        "account_id": "synthetic-account-id",
                        "id_token": "synthetic-id-token",
                        "refresh_token": "synthetic-refresh-token",
                    },
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        source.chmod(0o600)
        probe = (
            "import json,subprocess,sys;"
            "r=subprocess.run(['/usr/local/bin/plane-agent-runtime-credential-resolver','runtime'],capture_output=True,text=True);"
            "p=json.loads(r.stdout) if r.returncode==0 else {};"
            "ok=r.returncode==0 and set(p)=={'api_key'} and isinstance(p['api_key'],str) and bool(p['api_key']);"
            "print(json.dumps({'exitCode':r.returncode,'keys':sorted(p),'valueShape':'nonempty-string' if ok else 'invalid'},sort_keys=True,separators=(',',':')));"
            "sys.exit(0 if ok else 1)"
        )
        result = json.loads(
            _run(
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--mount",
                f"type=bind,source={source},target=/run/secrets/plane_agent_provider_credentials,readonly",
                "--entrypoint",
                "python3",
                tag,
                "-c",
                probe,
            )
        )
    if result != {"exitCode": 0, "keys": ["api_key"], "valueShape": "nonempty-string"}:
        raise RuntimeError("API image credential resolver probe returned an invalid shape")


def build_api_image(
    *,
    candidate: str | None = None,
    base_image: str = DEFAULT_BASE_IMAGE,
    base_image_digest: str | None = None,
    tag: str | None = None,
) -> dict[str, str]:
    verify_dockerfile_contract()
    resolved = verify_clean_candidate(candidate)
    hashes = source_hashes(resolved)
    verify_base_image(base_image, base_image_digest)
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
        "org.uxheavy.plane.api.source.credentials.sha256": hashes["PLANE_API_CREDENTIALS_SHA256"],
        "org.uxheavy.plane.api.source.credential-resolver.sha256": hashes[
            "PLANE_API_CREDENTIAL_RESOLVER_SHA256"
        ],
    }
    for label, expected in expected_labels.items():
        if str(labels.get(label, "")) != expected:
            raise RuntimeError(f"API image label mismatch: {label}")
    verify_resolver_image(selected_tag)
    return {"imageTag": selected_tag, "imageDigest": str(metadata["imageDigest"]), "sourceRevision": resolved, "contract": CONTRACT}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate")
    parser.add_argument("--base-image", default=DEFAULT_BASE_IMAGE)
    parser.add_argument("--base-image-digest")
    parser.add_argument("--tag")
    args = parser.parse_args(argv)
    print(
        json.dumps(
            build_api_image(
                candidate=args.candidate,
                base_image=args.base_image,
                base_image_digest=args.base_image_digest,
                tag=args.tag,
            ),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
