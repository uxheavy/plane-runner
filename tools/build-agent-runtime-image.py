#!/usr/bin/env python3
"""Build and attest the dedicated production Plane Agent runtime image."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import stat
import subprocess
import tarfile
import tempfile
import uuid
from pathlib import Path
from pathlib import PurePosixPath


HERMES_REMOTE = "github.com/uxheavy/hermes-agent"
HERMES_ORIGIN = f"https://{HERMES_REMOTE}.git"
RUNTIME_CONTRACT = "plane.agent-runtime/v1"
HERMES_SOURCE_KIND_GIT = "git-checkout"
HERMES_SOURCE_KIND_SEALED_IMAGE = "sealed-image"
HERMES_DONOR_ROOT = PurePosixPath("opt/hermes")
HERMES_DONOR_ROOT_PARTS = HERMES_DONOR_ROOT.parts
HERMES_REQUIRED_FILES = (
    PurePosixPath("run_agent.py"),
    PurePosixPath("plane_runtime/g1_runtime_image/dotenv"),
)
DOCKERFILE = Path(__file__).resolve().parents[1] / "deployments/cli/community/agent-runtime/Dockerfile"
ROOT = DOCKERFILE.parents[4]
DURABLE_MANIFEST = ROOT / "tools/agent-g4-manifest.json"
HERMES_COMMIT = str(json.loads(DURABLE_MANIFEST.read_text(encoding="utf-8"))["pins"]["hermesCommit"])
PLANE_RUNTIME_SOURCE_DIR = "apps/api/plane/agent/runtime"
PLANE_CODE_MODE_CONTRACT_FILES = (
    "apps/api/plane/agent/code_mode/__init__.py",
    "apps/api/plane/agent/code_mode/contracts.py",
)


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


def canonical_hermes_remote(value: str) -> str:
    """Normalize supported uxheavy GitHub URL forms to one provenance value."""

    normalized = value.strip().removesuffix(".git")
    accepted = {
        f"https://{HERMES_REMOTE}",
        f"ssh://git@{HERMES_REMOTE}",
        "git@github.com:uxheavy/hermes-agent",
    }
    if normalized not in accepted:
        raise RuntimeError("Hermes origin must point to the uxheavy fork")
    return HERMES_REMOTE


def normalize_disposable_hermes_origin(checkout: Path, origin: str) -> str:
    """Normalize only repository-owned disposable clones; never mutate source checkouts."""

    try:
        return canonical_hermes_remote(origin)
    except RuntimeError as exc:
        try:
            resolved = checkout.resolve(strict=True)
        except OSError:
            raise exc
        if not resolved.is_relative_to(ROOT / "tmp"):
            raise exc
        run("git", "-C", str(resolved), "remote", "set-url", "origin", HERMES_ORIGIN)
        return canonical_hermes_remote(run("git", "-C", str(resolved), "remote", "get-url", "origin"))


def verify_hermes(checkout: Path, revision: str) -> None:
    actual = run("git", "-C", str(checkout), "rev-parse", "HEAD")
    if actual != revision:
        raise RuntimeError(f"Hermes checkout SHA is {actual}, expected {revision}")
    dirty = run("git", "-C", str(checkout), "status", "--porcelain", "--untracked-files=all")
    if dirty:
        raise RuntimeError("Hermes checkout must be clean before an image is built")
    origin = run("git", "-C", str(checkout), "remote", "get-url", "origin")
    normalize_disposable_hermes_origin(checkout, origin)


def pinned_build_defaults(manifest: dict[str, object], plane_revision: str) -> tuple[str, str]:
    """Derive exact Hermes and runtime-tag defaults from the selected manifest."""

    pins = manifest.get("pins")
    if not isinstance(pins, dict):
        raise RuntimeError("durable manifest pins are missing")
    hermes_revision = str(pins.get("hermesCommit", ""))
    runtime_revision = str(pins.get("runtimeImageRevision", ""))
    runtime_tag = str(pins.get("runtimeImageTag", ""))
    if len(hermes_revision) != 40 or any(character not in "0123456789abcdef" for character in hermes_revision):
        raise RuntimeError("durable Hermes commit is not a full lowercase Git SHA")
    if runtime_revision != plane_revision or not runtime_tag:
        raise RuntimeError("--tag is required when Plane revision is not the manifest-pinned runtime source")
    return hermes_revision, runtime_tag


def _hash(value: str, label: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise RuntimeError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _image_digest(value: str, label: str) -> str:
    if not value.startswith("sha256:"):
        raise RuntimeError(f"{label} must be a sha256 image digest")
    _hash(value.removeprefix("sha256:"), label)
    return value


def _require_disposable_revision(value: str | None, option: str) -> str:
    if value is None:
        raise SystemExit(f"{option} is required with --manifest-out")
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        raise SystemExit(f"{option} must be a full lowercase Git SHA")
    return value


def _safe_mode(mode: int, label: str) -> None:
    if mode & 0o022:
        raise RuntimeError(f"{label} has group/world writable metadata")
    if mode & 0o7000:
        raise RuntimeError(f"{label} has unexpected special permission metadata")


def _safe_archive_parts(name: str) -> tuple[str, ...]:
    if not name or "\x00" in name or name.startswith("/") or "\\" in name:
        raise RuntimeError(f"unsafe archive entry: {name!r}")
    parts = tuple(part for part in PurePosixPath(name).parts if part not in ("", "."))
    if not parts or ".." in parts:
        raise RuntimeError(f"unsafe archive entry: {name!r}")
    return parts


def hermes_file_hashes(root: Path) -> dict[str, str]:
    """Inventory regular Hermes files while rejecting unsafe source metadata."""

    if root.is_symlink() or not root.is_dir():
        raise RuntimeError("Hermes source directory is missing or is not a directory")
    _safe_mode(root.stat().st_mode, str(root))
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*"), key=lambda value: value.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise RuntimeError(f"Hermes source contains a symlink: {relative}")
        if stat.S_ISDIR(metadata.st_mode):
            _safe_mode(metadata.st_mode, relative)
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError(f"Hermes source contains a non-regular file: {relative}")
        _safe_mode(metadata.st_mode, relative)
        files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not files:
        raise RuntimeError("Hermes source directory contains no regular files")
    return files


def hermes_tree_digest(file_hashes: dict[str, str]) -> str:
    return runtime_source_digest(file_hashes)


def validate_hermes_source_binding(
    source_kind: str,
    donor_image: str,
    donor_digest: str,
    tree_digest: str,
) -> None:
    """Reject a source label set that mixes checkout and sealed-image facts."""

    if source_kind not in {HERMES_SOURCE_KIND_GIT, HERMES_SOURCE_KIND_SEALED_IMAGE}:
        raise RuntimeError(f"unsupported Hermes source kind: {source_kind}")
    _hash(tree_digest, "Hermes tree digest")
    if source_kind == HERMES_SOURCE_KIND_SEALED_IMAGE:
        if not donor_image:
            raise RuntimeError("sealed-image Hermes source requires a donor image")
        _image_digest(donor_digest, "Hermes donor digest")
        return
    if donor_image or donor_digest:
        raise RuntimeError("mixed Hermes source: git-checkout cannot carry sealed-image donor metadata")


def load_manifest(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("selected durable manifest must be a regular file")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("selected durable manifest must be an object")
    return value


def verify_donor_image(image: str, manifest: dict[str, object]) -> dict[str, str]:
    """Attest the sealed donor image without executing it or claiming Git proof."""

    pins = manifest.get("pins")
    if not isinstance(pins, dict):
        raise RuntimeError("durable manifest pins are missing")
    expected_image = str(pins.get("runtimeImageTag", ""))
    if image != expected_image:
        raise RuntimeError("Hermes donor image does not match the durable manifest tag")
    expected_digest = _image_digest(str(pins.get("runtimeImageDigest", "")), "durable runtime image digest")
    expected_commit = str(pins.get("hermesCommit", ""))
    if len(expected_commit) != 40 or any(character not in "0123456789abcdef" for character in expected_commit):
        raise RuntimeError("durable Hermes commit is not a Git SHA-shaped attestation")
    expected_revision = str(pins.get("runtimeImageRevision", ""))
    if len(expected_revision) != 40 or any(character not in "0123456789abcdef" for character in expected_revision):
        raise RuntimeError("durable runtime revision is not a Git SHA-shaped attestation")
    expected_contract = str(pins.get("runtimeContract", ""))
    if expected_contract != RUNTIME_CONTRACT:
        raise RuntimeError("durable runtime contract is not the Plane runtime contract")

    metadata = image_metadata(image)
    labels = metadata["labels"]
    assert isinstance(labels, dict)
    actual_digest = str(metadata["imageDigest"])
    expected_labels = {
        "org.uxheavy.plane.hermes.commit": expected_commit,
        "org.uxheavy.plane.hermes.remote": HERMES_ORIGIN,
        "org.uxheavy.plane.runtime.revision": expected_revision,
        "org.uxheavy.plane.runtime.contract": expected_contract,
    }
    if actual_digest != expected_digest:
        raise RuntimeError("Hermes donor image digest does not match the durable manifest")
    for label, expected in expected_labels.items():
        if str(labels.get(label, "")) != expected:
            raise RuntimeError(f"Hermes donor image label mismatch: {label}")
    return {
        "sourceKind": HERMES_SOURCE_KIND_SEALED_IMAGE,
        "hermesCommit": expected_commit,
        "hermesRemote": HERMES_REMOTE,
        "runtimeRevision": expected_revision,
        "contract": expected_contract,
        "donorImage": image,
        "donorDigest": actual_digest,
    }


def extract_safe_hermes_archive(archive: Path, destination: Path) -> dict[str, str]:
    """Extract only a validated /opt/hermes tree from an untrusted image tar."""

    if destination.is_symlink() or destination.exists() and not destination.is_dir():
        raise RuntimeError("Hermes extraction destination is not a directory")
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    members: list[tuple[tarfile.TarInfo, tuple[str, ...]]] = []
    seen: set[tuple[str, ...]] = set()
    with tarfile.open(archive, mode="r:") as stream:
        for member in stream:
            parts = _safe_archive_parts(member.name)
            is_hermes_member = parts[: len(HERMES_DONOR_ROOT_PARTS)] == HERMES_DONOR_ROOT_PARTS
            if not is_hermes_member:
                continue
            if parts in seen:
                raise RuntimeError(f"duplicate archive entry: {member.name!r}")
            seen.add(parts)
            if (
                member.issym()
                or member.islnk()
                or member.isdev()
                or member.isfifo()
            ):
                raise RuntimeError(f"unsafe archive entry type: {member.name!r}")
            if not member.isdir() and not member.isreg():
                raise RuntimeError(f"unsupported archive entry type: {member.name!r}")
            _safe_mode(member.mode, member.name)
            if member.isdir() and member.size != 0:
                raise RuntimeError(f"directory archive entry has unexpected data: {member.name!r}")
            members.append((member, parts))

        hermes_members = [
            (member, parts)
            for member, parts in members
            if parts[: len(HERMES_DONOR_ROOT_PARTS)] == HERMES_DONOR_ROOT_PARTS
        ]
        if not any(parts == HERMES_DONOR_ROOT_PARTS and member.isdir() for member, parts in hermes_members):
            raise RuntimeError("donor image is missing /opt/hermes")
        for member, parts in sorted(hermes_members, key=lambda pair: (len(pair[1]), pair[1])):
            relative_parts = parts[len(HERMES_DONOR_ROOT_PARTS) :]
            if not relative_parts:
                continue
            target = destination.joinpath(*relative_parts)
            if member.isdir():
                target.mkdir(mode=member.mode & 0o777, parents=True, exist_ok=True)
                _safe_mode(target.stat().st_mode, str(target))
                continue
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if target.exists() or target.is_symlink():
                raise RuntimeError(f"archive extraction collision: {target}")
            source = stream.extractfile(member)
            if source is None:
                raise RuntimeError(f"archive regular file has no payload: {member.name!r}")
            with target.open("xb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(member.mode & 0o777)

    files = hermes_file_hashes(destination)
    for required in HERMES_REQUIRED_FILES:
        required_path = destination.joinpath(*required.parts)
        expected_directory = required.as_posix().endswith("/dotenv")
        if (not required_path.exists()) or (expected_directory and not required_path.is_dir()) or (
            not expected_directory and not required_path.is_file()
        ):
            raise RuntimeError(f"donor Hermes source is missing required path: {required.as_posix()}")
    return files


def extract_donor_hermes(
    image: str,
    destination: Path,
    manifest: dict[str, object],
) -> dict[str, object]:
    """Create-only/export a donor image and return its sealed source attestation."""

    binding = verify_donor_image(image, manifest)
    container = f"plane-ut013-donor-{uuid.uuid4().hex[:12]}"
    archive = destination.parent / "hermes-donor.tar"
    created = False
    try:
        run("docker", "create", "--name", container, image)
        created = True
        with archive.open("wb") as output:
            result = subprocess.run(
                ["docker", "export", container],
                stdout=output,
                stderr=subprocess.PIPE,
                check=False,
            )
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip().splitlines()
            raise RuntimeError(f"docker export failed: {(detail[-1] if detail else 'no output')[:240]}")
        files = extract_safe_hermes_archive(archive, destination)
    finally:
        if archive.exists():
            archive.unlink()
        if created:
            subprocess.run(["docker", "rm", container], capture_output=True, text=True, check=False)
    binding.update(
        {
            "sourceKind": HERMES_SOURCE_KIND_SEALED_IMAGE,
            "treeDigest": hermes_tree_digest(files),
            "files": files,
        }
    )
    return binding


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
        PLANE_RUNTIME_SOURCE_DIR,
        *PLANE_CODE_MODE_CONTRACT_FILES,
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


def stage_plane_runtime(destination: Path, plane_revision: str) -> None:
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
                PLANE_RUNTIME_SOURCE_DIR,
                *PLANE_CODE_MODE_CONTRACT_FILES,
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
        str(extracted / PLANE_RUNTIME_SOURCE_DIR),
        str(destination / "plane_runtime_service"),
    )
    code_mode_destination = destination / "plane_code_mode_contracts"
    code_mode_destination.mkdir(mode=0o700)
    code_mode_source = extracted / "apps/api/plane/agent/code_mode"
    for relative in ("__init__.py", "contracts.py"):
        shutil.move(str(code_mode_source / relative), str(code_mode_destination / relative))


def stage_git_hermes(checkout: Path, destination: Path, revision: str) -> dict[str, str]:
    hermes = destination / "hermes"
    hermes.mkdir()
    archive_path = destination / "hermes.tar"
    with archive_path.open("wb") as archive:
        subprocess.run(
            ["git", "-C", str(checkout), "archive", "--format=tar", revision],
            stdout=archive,
            stderr=subprocess.PIPE,
            check=True,
        )
    run("tar", "-xf", str(archive_path), "-C", str(hermes))
    archive_path.unlink()
    return hermes_file_hashes(hermes)


def stage_context(
    checkout: Path,
    destination: Path,
    plane_revision: str,
    hermes_revision: str,
) -> dict[str, object]:
    hermes_files = stage_git_hermes(checkout, destination, hermes_revision)
    stage_plane_runtime(destination, plane_revision)
    return {
        "sourceKind": HERMES_SOURCE_KIND_GIT,
        "donorImage": "",
        "donorDigest": "",
        "treeDigest": hermes_tree_digest(hermes_files),
        "files": hermes_files,
    }


def _stage_donor_source(
    image: str,
    destination: Path,
    plane_revision: str,
    manifest: dict[str, object],
) -> dict[str, object]:
    hermes = destination / "hermes"
    donor_source = extract_donor_hermes(image, hermes, manifest)
    stage_plane_runtime(destination, plane_revision)
    files = hermes_file_hashes(hermes)
    if files != donor_source["files"]:
        raise RuntimeError("sealed Hermes donor source changed before Docker staging")
    return donor_source


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
    hermes_files: dict[str, str] | None = None,
    hermes_source_kind: str = HERMES_SOURCE_KIND_GIT,
    hermes_donor_image: str = "",
    hermes_donor_digest: str = "",
    hermes_tree_digest: str = "",
) -> dict[str, str]:
    hermes_files = hermes_files or {}
    validate_hermes_source_binding(
        hermes_source_kind,
        hermes_donor_image,
        hermes_donor_digest,
        hermes_tree_digest,
    )
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
        "hermesSourceKind": str(labels.get("org.uxheavy.plane.hermes.source.kind", "")),
        "hermesDonorImage": str(labels.get("org.uxheavy.plane.hermes.donor.image", "")),
        "hermesDonorDigest": str(labels.get("org.uxheavy.plane.hermes.donor.digest", "")),
        "hermesTreeDigest": str(labels.get("org.uxheavy.plane.hermes.tree.sha256", "")),
    }
    if expected["runtimeRevision"] != plane_revision:
        raise RuntimeError("runtime image Plane revision does not match the selected Plane candidate")
    if expected["hermesCommit"] != hermes_commit or expected["hermesRemote"] != f"https://{hermes_remote}.git":
        raise RuntimeError("runtime image Hermes provenance does not match the pinned checkout")
    if expected["contract"] != contract or expected["runtimeSourceDigest"] != expected_source_digest:
        raise RuntimeError("runtime image contract or source digest label is not exact")
    if (
        expected["hermesSourceKind"] != hermes_source_kind
        or expected["hermesDonorImage"] != hermes_donor_image
        or expected["hermesDonorDigest"] != hermes_donor_digest
        or expected["hermesTreeDigest"] != hermes_tree_digest
    ):
        raise RuntimeError("runtime image Hermes source provenance is mixed or not exact")

    probe = (
        "import hashlib,json,pathlib,stat\n"
        "def inventory(root,prefix,exclude_bytecode=False):\n"
        "  actual={}\n"
        "  for p in sorted(root.rglob('*')):\n"
        "    metadata=p.lstat()\n"
        "    if stat.S_ISLNK(metadata.st_mode) or (not stat.S_ISREG(metadata.st_mode) and not stat.S_ISDIR(metadata.st_mode)):\n"
        "      raise SystemExit('unsafe runtime source metadata')\n"
        "    if metadata.st_mode & 0o022 or metadata.st_mode & 0o7000:\n"
        "      raise SystemExit('writable runtime source metadata')\n"
        "    if stat.S_ISREG(metadata.st_mode) and (not exclude_bytecode or (p.suffix not in ('.pyc','.pyo') and '__pycache__' not in p.parts)):\n"
        "      actual[prefix+p.relative_to(root).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()\n"
        "  return actual\n"
        "def digest(files):\n"
        "  return hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest()\n"
        "hermes=inventory(pathlib.Path('/opt/hermes'),'')\n"
        "plane={}\n"
        "plane.update(inventory(pathlib.Path('/opt/plane/agent/runtime'),'apps/api/plane/agent/runtime/',True))\n"
        "plane.update(inventory(pathlib.Path('/opt/plane/agent/code_mode'),'apps/api/plane/agent/code_mode/',True))\n"
        "print(json.dumps({'hermesTreeDigest':digest(hermes),'planeTreeDigest':digest(plane),'hermesFileCount':len(hermes),'planeFileCount':len(plane)},sort_keys=True,separators=(',',':')))"
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
    )
    try:
        actual_files = json.loads(actual_raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("runtime image source parity probe did not return JSON") from exc
    expected_tree = {
        "hermesTreeDigest": hermes_tree_digest,
        "planeTreeDigest": expected_source_digest,
        "hermesFileCount": len(hermes_files),
        "planeFileCount": len(expected_files),
    }
    if actual_files != expected_tree:
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
    mcp_revision: str,
    sdk_revision: str,
    hermes_source: dict[str, object] | None = None,
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
    pins["mcpGitlink"] = mcp_revision
    pins["sdkGitlink"] = sdk_revision
    pins["apiArtifact"] = api
    disposable_binding: dict[str, object] = {
        "mode": "exact-api-runtime-candidate",
        "candidateCommit": plane_revision,
        "apiSourceRevision": plane_revision,
        "runtimeRevision": plane_revision,
        "hermesCommit": hermes_commit,
        "hermesRemote": hermes_remote,
        "runtimeSourceDigest": runtime["runtimeSourceDigest"],
        "runtimeFiles": runtime_files,
    }
    if hermes_source is not None:
        source_kind = str(hermes_source.get("sourceKind", ""))
        donor_image = str(hermes_source.get("donorImage", ""))
        donor_digest = str(hermes_source.get("donorDigest", ""))
        tree_digest = str(hermes_source.get("treeDigest", ""))
        validate_hermes_source_binding(source_kind, donor_image, donor_digest, tree_digest)
        disposable_binding.update(
            {
                "hermesSourceKind": source_kind,
                "hermesDonorImage": donor_image,
                "hermesDonorDigest": donor_digest,
                "hermesTreeDigest": tree_digest,
            }
        )
    manifest["disposableBinding"] = disposable_binding
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
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        descriptor = os.open(
            resolved,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
        )
    except OSError as exc:
        raise RuntimeError("disposable manifest output must be an owner-only regular file") from exc
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=False) as output:
            output.write(payload)
            output.flush()
            os.fsync(descriptor)
    finally:
        os.close(descriptor)
    metadata = resolved.stat(follow_symlinks=False)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise RuntimeError("disposable manifest output must be an owner-only regular file")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    hermes_input = parser.add_mutually_exclusive_group(required=True)
    hermes_input.add_argument("--hermes-checkout", type=Path)
    hermes_input.add_argument(
        "--hermes-donor-image",
        help="Use the exact sealed Hermes filesystem from the manifest-bound runtime image",
    )
    parser.add_argument("--tag", help="Runtime image tag; defaults only for the exact manifest-pinned source")
    parser.add_argument("--plane-revision", help="Build an exact clean Git revision instead of HEAD")
    parser.add_argument(
        "--hermes-revision",
        help="Exact clean Hermes Git revision to stage (defaults to the selected manifest pin)",
    )
    parser.add_argument("--api-image", help="Current candidate API image required for disposable manifest output")
    parser.add_argument("--manifest-out", type=Path, help="Write a disposable manifest under repository tmp/")
    parser.add_argument("--mcp-revision", help="Exact MCP Git revision required with --manifest-out")
    parser.add_argument("--sdk-revision", help="Exact SDK Git revision required with --manifest-out")
    parser.add_argument("--manifest", type=Path, default=DURABLE_MANIFEST, help="Durable donor attestation manifest")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    mcp_revision = None
    sdk_revision = None
    if args.manifest_out is not None:
        mcp_revision = _require_disposable_revision(args.mcp_revision, "--mcp-revision")
        sdk_revision = _require_disposable_revision(args.sdk_revision, "--sdk-revision")
    donor_manifest = load_manifest(args.manifest)
    requested_plane_revision = run("git", "rev-parse", args.plane_revision or "HEAD", cwd=ROOT)
    pins = donor_manifest.get("pins")
    if not isinstance(pins, dict):
        raise SystemExit("durable manifest pins are missing")
    pinned_hermes_revision = str(pins.get("hermesCommit", ""))
    if len(pinned_hermes_revision) != 40 or any(
        character not in "0123456789abcdef" for character in pinned_hermes_revision
    ):
        raise SystemExit("durable Hermes commit is not a full lowercase Git SHA")
    if args.tag is None:
        _, selected_tag = pinned_build_defaults(donor_manifest, requested_plane_revision)
    else:
        selected_tag = str(args.tag)
    hermes_revision = str(args.hermes_revision or pinned_hermes_revision)
    if len(hermes_revision) != 40 or any(character not in "0123456789abcdef" for character in hermes_revision):
        raise SystemExit("--hermes-revision must be a full lowercase Git SHA")
    if args.hermes_donor_image and hermes_revision != pinned_hermes_revision:
        raise SystemExit("--hermes-revision cannot override a sealed donor image")
    if shutil.which("docker") is None:
        raise SystemExit("Docker CLI is required")
    if args.hermes_checkout is not None:
        verify_hermes(args.hermes_checkout, hermes_revision)
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
        if args.hermes_donor_image:
            hermes_source = _stage_donor_source(
                args.hermes_donor_image,
                context,
                plane_revision,
                donor_manifest,
            )
        else:
            assert args.hermes_checkout is not None
            hermes_source = stage_context(
                args.hermes_checkout,
                context,
                plane_revision,
                hermes_revision,
            )
        hermes_commit = str(
            hermes_source.get("hermesCommit", hermes_revision)
        )
        hermes_remote = str(hermes_source.get("hermesRemote", HERMES_REMOTE))
        hermes_source_kind = str(hermes_source["sourceKind"])
        hermes_donor_image = str(hermes_source.get("donorImage", ""))
        hermes_donor_digest = str(hermes_source.get("donorDigest", ""))
        hermes_tree_digest = str(hermes_source["treeDigest"])
        hermes_files = hermes_source["files"]
        if not isinstance(hermes_files, dict):
            raise RuntimeError("Hermes source inventory is invalid")
        validate_hermes_source_binding(
            hermes_source_kind,
            hermes_donor_image,
            hermes_donor_digest,
            hermes_tree_digest,
        )
        run(
            "docker",
            "build",
            "--file",
            str(DOCKERFILE),
            "--tag",
            selected_tag,
            "--build-arg",
            f"HERMES_COMMIT={hermes_commit}",
            "--build-arg",
            f"HERMES_SOURCE_KIND={hermes_source_kind}",
            "--build-arg",
            f"HERMES_DONOR_IMAGE={hermes_donor_image}",
            "--build-arg",
            f"HERMES_DONOR_DIGEST={hermes_donor_digest}",
            "--build-arg",
            f"HERMES_TREE_SHA256={hermes_tree_digest}",
            "--build-arg",
            f"PLANE_REVISION={plane_revision}",
            "--build-arg",
            f"PLANE_RUNTIME_SOURCE_SHA256={source_digest}",
            str(context),
            capture=False,
        )
    runtime = verify_runtime_image(
        selected_tag,
        plane_revision,
        hermes_commit,
        hermes_remote,
        RUNTIME_CONTRACT,
        runtime_files,
        source_digest,
        hermes_files,
        hermes_source_kind,
        hermes_donor_image,
        hermes_donor_digest,
        hermes_tree_digest,
    )
    if api is not None:
        assert args.manifest_out is not None
        manifest = disposable_manifest(
            plane_revision,
            plane_parent,
            hermes_commit,
            hermes_remote,
            runtime,
            api,
            runtime_files,
            mcp_revision,
            sdk_revision,
            hermes_source,
        )
        write_disposable_manifest(args.manifest_out, manifest)
    print(
        json.dumps(
            {
                "image": selected_tag,
                "imageDigest": runtime["imageDigest"],
                "hermesCommit": hermes_commit,
                "hermesRemote": hermes_remote,
                "hermesSourceKind": hermes_source_kind,
                "hermesDonorImage": hermes_donor_image,
                "hermesDonorDigest": hermes_donor_digest,
                "hermesTreeDigest": hermes_tree_digest,
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
