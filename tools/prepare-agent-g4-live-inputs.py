#!/usr/bin/env python3
"""Create owner-only live inputs from one exact disposable manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


AUTHORITY_TTL = timedelta(hours=24)
AUTHORITY_BACKDATE = timedelta(minutes=1)


def authority_window(now: datetime | None = None) -> tuple[str, str]:
    """Return a bounded UTC authority window that remains valid at launch."""

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("authority_window_requires_timezone")
    current = current.astimezone(timezone.utc)
    issued = current - AUTHORITY_BACKDATE
    expires = current + AUTHORITY_TTL
    return (
        issued.isoformat().replace("+00:00", "Z"),
        expires.isoformat().replace("+00:00", "Z"),
    )


def _owner_only(path: Path, payload: bytes) -> None:
    path.write_bytes(payload)
    path.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--descriptor", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--candidate", required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    selected_manifest = args.manifest or root / "tools" / "agent-g4-manifest.json"
    if not selected_manifest.is_absolute():
        raise SystemExit("manifest_must_be_absolute")
    manifest_path = selected_manifest.resolve(strict=True)
    if manifest_path != selected_manifest:
        raise SystemExit("manifest_must_not_be_a_symlink")
    durable_manifest = (root / "tools" / "agent-g4-manifest.json").resolve(strict=True)
    if manifest_path != durable_manifest and not manifest_path.is_relative_to(root / "tmp"):
        raise SystemExit("manifest_must_be_checked_in_wrapper_or_owned_disposable")
    sys.path.insert(0, str(root / "tools"))
    from validate_agent_g4_live import (
        EXPECTED_PROVIDER_DESCRIPTOR,
        exact_binding,
        provider_relay_descriptor,
        validate_candidate_binding,
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_candidate_binding(manifest, args.candidate, root)
    descriptor = args.descriptor.read_bytes()
    issued_at, expires_at = authority_window()
    binding = exact_binding(manifest, args.candidate)
    binding.update(
        {
            "commandSha256": hashlib.sha256(b"bash tools/agent-g4-live.sh").hexdigest(),
            "provider": dict(EXPECTED_PROVIDER_DESCRIPTOR),
            "thresholdProfile": "g4-live-approved-v1",
            "thresholds": {
                "permittedSuccessRateMin": 1.0,
                "deniedRejectionRateMin": 1.0,
                "maxLatencyP95Ms": 500,
                "maxErrorRate": 0.0,
            },
            "canaries": {
                "permitted": {"id": "w05-w06-permitted", "expectedStatus": "allowed"},
                "denied": {"id": "w05-w06-denied", "expectedStatus": "denied"},
            },
        }
    )
    authority = {
        "schemaVersion": "plane-agent-g4/live-authority/v1",
        "authorityId": "authority-w05-w06-c-20260816",
        "purpose": "g4-live-evaluation",
        "issuedAt": issued_at,
        "expiresAt": expires_at,
        "expectedCandidate": args.candidate,
        "fallbackAllowed": False,
        "binding": binding,
        "providerRelay": provider_relay_descriptor(),
    }
    config = {
        "schemaVersion": "plane-agent-g4/live-config/v1",
        "authorityId": authority["authorityId"],
        "mode": "live",
        "offline": False,
        "fallbackAllowed": False,
        "expectedCandidate": args.candidate,
        "binding": binding,
        "provider": {**EXPECTED_PROVIDER_DESCRIPTOR, "fallbackUsed": False},
        "providerRelay": provider_relay_descriptor(),
        "thresholdProfile": binding["thresholdProfile"],
        "thresholds": binding["thresholds"],
        "canaries": {key: value["id"] for key, value in binding["canaries"].items()},
        "requiredReadbacks": ["audit", "version"],
    }
    args.run_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    _owner_only(args.run_dir / "authority.json", json.dumps(authority, indent=2, sort_keys=True).encode() + b"\n")
    _owner_only(args.run_dir / "config.json", json.dumps(config, indent=2, sort_keys=True).encode() + b"\n")
    shutil.copyfile(args.descriptor, args.run_dir / "descriptor.json")
    (args.run_dir / "descriptor.json").chmod(0o600)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
