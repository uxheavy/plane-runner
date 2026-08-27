#!/usr/bin/env python3
"""Retain bounded post-run cleanup proof for validated G4 live receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from validate_agent_g4_live import ContractError, validate_files


SCHEMA = "plane-agent-g4/live-cleanup-attestation/v1"
_SHA256 = 64
_RUN_ARTIFACTS = frozenset({"authority.json", "config.json", "descriptor.json", "result.json"})
_ROLES = frozenset({"worker", "delegator"})
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_CLEANUP_FIELDS = frozenset(
    {
        "containersRemaining",
        "networksRemaining",
        "volumesRemaining",
        "leasePresent",
        "staleLabeledVolumesRemoved",
    }
)


class AttestationError(ValueError):
    """A bounded, non-sensitive cleanup-attestation failure."""


@dataclass(frozen=True)
class ReceiptInput:
    role: str
    authority: Path
    config: Path
    evidence: Path


def _regular_owner_only(path: Path, reason: str) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise AttestationError(reason) from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise AttestationError(reason)


def _manifest_regular(path: Path) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise AttestationError("manifest_unreadable") from exc
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o022:
        raise AttestationError("manifest_not_safe_regular_file")


def _check_run_artifacts(receipt: ReceiptInput) -> None:
    directory = receipt.evidence.parent
    try:
        entries = list(os.scandir(directory))
    except OSError as exc:
        raise AttestationError("run_directory_unreadable") from exc
    names = {entry.name for entry in entries}
    if names != _RUN_ARTIFACTS:
        raise AttestationError("run_directory_artifacts_invalid")
    for entry in entries:
        _regular_owner_only(Path(entry.path), "run_directory_artifact_invalid")


def _receipt_hash(path: Path) -> str:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise AttestationError("receipt_unreadable") from exc
    digest = hashlib.sha256(payload).hexdigest()
    if len(digest) != _SHA256:
        raise AttestationError("receipt_hash_invalid")
    return digest


def build_attestation(
    *,
    manifest: Path,
    candidate: str,
    expected_candidate: str,
    command: str,
    receipts: Sequence[ReceiptInput],
    cleanup: dict[str, Any],
) -> dict[str, Any]:
    if not _GIT_SHA.fullmatch(candidate) or candidate != expected_candidate:
        raise AttestationError("candidate_binding_invalid")
    if set(cleanup) != _CLEANUP_FIELDS:
        raise AttestationError("cleanup_observation_invalid")
    if any(
        type(cleanup[field]) is not int or not 0 <= cleanup[field] <= 256
        for field in ("containersRemaining", "networksRemaining", "volumesRemaining", "staleLabeledVolumesRemoved")
    ) or type(cleanup["leasePresent"]) is not bool:
        raise AttestationError("cleanup_observation_invalid")
    if len(receipts) != len(_ROLES) or {item.role for item in receipts} != _ROLES:
        raise AttestationError("receipt_roles_invalid")
    _manifest_regular(manifest)
    result_rows = []
    for receipt in receipts:
        if receipt.evidence.name != "result.json":
            raise AttestationError("receipt_name_invalid")
        for path in (receipt.authority, receipt.config, receipt.evidence):
            _regular_owner_only(path, "receipt_input_invalid")
        _check_run_artifacts(receipt)
        try:
            result = validate_files(
                receipt.authority,
                receipt.config,
                manifest,
                receipt.evidence,
                candidate,
                expected_candidate,
                command,
            )
        except (ContractError, OSError, UnicodeError) as exc:
            raise AttestationError("receipt_validation_failed") from exc
        if result["collected"] != result["passed"] or result["passed"] != 1:
            raise AttestationError("receipt_not_single_passed")
        result_rows.append(
            {
                "role": receipt.role,
                "schemaVersion": "plane-agent-g4/live-evidence/v1",
                "status": "passed",
                "sha256": _receipt_hash(receipt.evidence),
            }
        )
    result_rows.sort(key=lambda row: row["role"])
    return {
        "schemaVersion": SCHEMA,
        "status": "passed",
        "candidateCommit": candidate,
        "receipts": result_rows,
        "cleanup": {
            "scope": "plane-g4-current-run-and-labeled-resources",
            "status": "passed",
            "runDirectoriesChecked": len(result_rows),
            "unexpectedArtifacts": 0,
            "rawFieldsEmitted": False,
            **cleanup,
        },
    }


def _receipt_arg(value: str) -> ReceiptInput:
    parts = value.split(":", 3)
    if len(parts) != 4:
        raise AttestationError("receipt_argument_invalid")
    role, authority, config, evidence = parts
    return ReceiptInput(role, Path(authority), Path(config), Path(evidence))


def _write_output(path: Path, value: dict[str, Any]) -> None:
    parent = path.parent
    try:
        parent_metadata = parent.stat()
    except OSError as exc:
        raise AttestationError("output_parent_unreadable") from exc
    if (
        not stat.S_ISDIR(parent_metadata.st_mode)
        or parent_metadata.st_uid != os.getuid()
        or stat.S_IMODE(parent_metadata.st_mode) & 0o022
        or path.exists()
        or path.is_symlink()
    ):
        raise AttestationError("output_path_invalid")
    file_descriptor = -1
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
        file_descriptor = os.open(path, flags, 0o600)
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as stream:
            file_descriptor = -1
            json.dump(value, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except (OSError, UnicodeError, TypeError) as exc:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        raise AttestationError("output_write_failed") from exc
    _regular_owner_only(path, "output_permissions_invalid")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--expected-candidate", required=True)
    parser.add_argument("--command", required=True)
    parser.add_argument(
        "--receipt",
        action="append",
        required=True,
        metavar="ROLE:AUTHORITY:CONFIG:RESULT",
    )
    for name in ("containers-remaining", "networks-remaining", "volumes-remaining", "stale-labeled-volumes-removed"):
        parser.add_argument(f"--{name}", type=int, required=True)
    parser.add_argument("--lease-present", choices=("true", "false"), required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        attestation = build_attestation(
            manifest=args.manifest,
            candidate=args.candidate,
            expected_candidate=args.expected_candidate,
            command=args.command,
            receipts=[_receipt_arg(value) for value in args.receipt],
            cleanup={
                "containersRemaining": args.containers_remaining,
                "networksRemaining": args.networks_remaining,
                "volumesRemaining": args.volumes_remaining,
                "leasePresent": args.lease_present == "true",
                "staleLabeledVolumesRemoved": args.stale_labeled_volumes_removed,
            },
        )
        if args.output is not None:
            _write_output(args.output, attestation)
    except AttestationError:
        print("event=agent.g4.live-cleanup-attestation status=failed reason=attestation_invalid", file=sys.stderr)
        return 1
    print(json.dumps(attestation, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
