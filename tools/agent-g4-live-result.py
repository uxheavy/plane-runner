#!/usr/bin/env python3
"""Persist one bounded JSON receipt from the disposable G4 live runner."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import stat
import sys
from pathlib import Path


MAX_EVIDENCE_BYTES = 16 * 1024
MAX_RESULT_BYTES = 20 * 1024
EMPTY_STDERR_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
EVIDENCE_SCHEMAS = {
    "plane-agent-g4/live-evidence/v1",
    "plane-agent-g4/live-failure/v1",
}
RUNNER_FAILURE_SCHEMA = "plane-agent-g4/live-runner-failure/v1"
FAILURE_PHASES = {
    "capacity-lease",
    "initialization",
    "credential-staging",
    "credential-bind-preflight",
    "credential-state-volume",
    "compose",
    "audit-bootstrap",
    "migrate",
    "runtime-start",
    "runtime-health",
    "api-invocation",
}
ERROR_CLASSES = {
    "CommandError",
    "ConnectionError",
    "FileNotFoundError",
    "ImportError",
    "ImproperlyConfigured",
    "ModuleNotFoundError",
    "OperationalError",
    "PermissionError",
    "RuntimeError",
    "TimeoutError",
    "unavailable",
    "unspecified",
}
DOCKER_REASON_CATEGORIES = {
    "docker_mount_target_read_only",
    "docker_mount_invalid",
    "docker_mount_source_unavailable",
    "docker_mount_permission_denied",
    "docker_network_configuration_invalid",
    "docker_image_unavailable",
    "docker_container_start_failed",
    "docker_precontainer_failure",
}
SENSITIVE_FIELD_RE = re.compile(
    rb"(?i)(?:password|passwd|secret|token|api[_-]?key|authorization|credential)\s*[\"']?\s*[:=]"
)
STDERR_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MODULE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")
SETUP_ERROR_STAGES = {
    "shared-setup",
    "assignment",
    "preconditions",
    "lineage",
    "schedule",
    "schedule-fire",
    "run",
    "invocation",
}
SETUP_ERROR_CLASSES = {
    "AgentDomainError",
    "AgentScheduleError",
    "AttributeError",
    "ConnectionError",
    "IntegrityError",
    "KeyError",
    "LookupError",
    "OperationalError",
    "RuntimeError",
    "TimeoutError",
    "TypeError",
    "ValueError",
    "ValidationError",
    "unknown",
}
SETUP_ERROR_COUNTERS = {
    "actors",
    "profiles",
    "assignments",
    "lineageAssignments",
    "schedules",
    "scheduleFires",
}


class ResultPersistenceError(ValueError):
    """A finite, non-sensitive result persistence failure."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _read_schema_controlled_evidence(path: Path, *, required: bool) -> bytes:
    try:
        file_descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    except FileNotFoundError:
        if required:
            raise ResultPersistenceError("evidence_unavailable") from None
        return b""
    except OSError:
        raise ResultPersistenceError("evidence_unavailable") from None

    try:
        metadata = os.fstat(file_descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_EVIDENCE_BYTES:
            raise ResultPersistenceError("evidence_invalid")
        payload = b""
        while len(payload) <= MAX_EVIDENCE_BYTES:
            chunk = os.read(file_descriptor, MAX_EVIDENCE_BYTES - len(payload) + 1)
            if not chunk:
                break
            payload += chunk
        if len(payload) > MAX_EVIDENCE_BYTES:
            raise ResultPersistenceError("evidence_oversized")
    except ResultPersistenceError:
        raise
    except OSError:
        raise ResultPersistenceError("evidence_unavailable") from None
    finally:
        os.close(file_descriptor)

    if not payload:
        if required:
            raise ResultPersistenceError("evidence_unavailable")
        return b""
    if SENSITIVE_FIELD_RE.search(payload):
        raise ResultPersistenceError("evidence_sensitive_field")
    try:
        parsed = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ResultPersistenceError("evidence_invalid") from None
    if not isinstance(parsed, dict) or parsed.get("schemaVersion") not in EVIDENCE_SCHEMAS:
        raise ResultPersistenceError("evidence_schema_invalid")
    return payload


def _bounded_failure_line(
    *,
    phase: str,
    error_class: str,
    exit_code: int,
    reason_category: str,
    stderr_sha256: str = EMPTY_STDERR_SHA256,
    missing_module: str = "",
) -> bytes:
    if phase not in FAILURE_PHASES:
        raise ResultPersistenceError("failure_phase_invalid")
    if error_class not in ERROR_CLASSES:
        raise ResultPersistenceError("error_class_invalid")
    if isinstance(exit_code, bool) or not isinstance(exit_code, int) or not 1 <= exit_code <= 255:
        raise ResultPersistenceError("exit_code_invalid")
    if (exit_code == 125 or phase == "compose") and reason_category not in DOCKER_REASON_CATEGORIES:
        raise ResultPersistenceError("docker_reason_category_invalid")
    if exit_code != 125 and phase != "compose" and reason_category != "unavailable":
        raise ResultPersistenceError("reason_category_invalid")
    if not isinstance(stderr_sha256, str) or not STDERR_SHA256_RE.fullmatch(stderr_sha256):
        raise ResultPersistenceError("stderr_sha256_invalid")
    if missing_module and (error_class != "ModuleNotFoundError" or not MODULE_NAME_RE.fullmatch(missing_module)):
        raise ResultPersistenceError("missing_module_invalid")
    module_detail = f" missing_module={missing_module}" if missing_module else ""
    return (
        f"event=agent.g4.live-runner.failure phase={phase} error_class={error_class} "
        f"exit_code={exit_code} reason_category={reason_category} stderr_sha256={stderr_sha256}{module_detail}\n"
    ).encode("ascii")


def _validated_setup_error(value: str | None) -> dict | None:
    if value in (None, ""):
        return None
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        raise ResultPersistenceError("setup_error_invalid") from None
    if not isinstance(parsed, dict) or set(parsed) != {"id", "stage", "errorClass", "counters"}:
        raise ResultPersistenceError("setup_error_invalid")
    identifier = parsed["id"]
    if (
        not isinstance(identifier, str)
        or not 1 <= len(identifier.encode("utf-8")) <= 128
        or not re.fullmatch(r"setup:[a-z-]+:[A-Za-z]+Error|setup:[a-z-]+:unknown", identifier)
    ):
        raise ResultPersistenceError("setup_error_invalid")
    if parsed["stage"] not in SETUP_ERROR_STAGES or parsed["errorClass"] not in SETUP_ERROR_CLASSES:
        raise ResultPersistenceError("setup_error_invalid")
    counters = parsed["counters"]
    if not isinstance(counters, dict) or set(counters) != SETUP_ERROR_COUNTERS:
        raise ResultPersistenceError("setup_error_invalid")
    if any(isinstance(item, bool) or not isinstance(item, int) or not 0 <= item <= 256 for item in counters.values()):
        raise ResultPersistenceError("setup_error_invalid")
    return {
        "id": identifier,
        "stage": parsed["stage"],
        "errorClass": parsed["errorClass"],
        "counters": {key: counters[key] for key in sorted(counters)},
    }


def _runner_failure_receipt(
    *,
    phase: str,
    error_class: str,
    exit_code: int,
    reason_category: str,
    stderr_sha256: str = EMPTY_STDERR_SHA256,
    missing_module: str = "",
    setup_error: str | None = None,
) -> bytes:
    _bounded_failure_line(
        phase=phase,
        error_class=error_class,
        exit_code=exit_code,
        reason_category=reason_category,
        stderr_sha256=stderr_sha256,
        missing_module=missing_module,
    )
    receipt = {
            "schemaVersion": RUNNER_FAILURE_SCHEMA,
            "status": "failed",
            "phase": phase,
            "errorClass": error_class,
            "exitCode": exit_code,
            "reasonCategory": reason_category,
            "stderrSha256": stderr_sha256,
    }
    if missing_module:
        receipt["missingModule"] = missing_module
    bounded_setup_error = _validated_setup_error(setup_error)
    if bounded_setup_error is not None:
        receipt["setupError"] = bounded_setup_error
    return json.dumps(receipt, separators=(",", ":")).encode("ascii")


def _validate_destination_parent(destination: Path) -> Path:
    if not destination.is_absolute() or any(
        ord(character) < 0x20 or ord(character) == 0x7F for character in str(destination)
    ):
        raise ResultPersistenceError("result_path_invalid")
    parent = Path(os.path.abspath(destination.parent))
    try:
        resolved_parent = parent.resolve(strict=True)
    except (OSError, RuntimeError):
        raise ResultPersistenceError("result_parent_unavailable") from None
    try:
        metadata = os.stat(resolved_parent, follow_symlinks=False)
    except OSError:
        raise ResultPersistenceError("result_parent_unavailable") from None
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise ResultPersistenceError("result_parent_not_owner_only")
    return resolved_parent


def _ensure_fresh_destination(destination: Path) -> None:
    try:
        metadata = os.lstat(destination)
    except FileNotFoundError:
        return
    except OSError:
        raise ResultPersistenceError("result_path_unavailable") from None
    if stat.S_ISLNK(metadata.st_mode):
        raise ResultPersistenceError("result_path_symlink")
    raise ResultPersistenceError("result_path_collision")


def _write_atomically(destination: Path, payload: bytes, parent: Path) -> None:
    temporary = parent / f".{destination.name}.tmp-{os.getpid()}-{secrets.token_hex(8)}"
    file_descriptor = None
    try:
        file_descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
        )
        os.fchmod(file_descriptor, 0o600)
        view = memoryview(payload)
        while view:
            written = os.write(file_descriptor, view)
            if written <= 0:
                raise OSError("result write made no progress")
            view = view[written:]
        os.fsync(file_descriptor)
    except ResultPersistenceError:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    except OSError:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise ResultPersistenceError("result_write_failed") from None
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)

    try:
        _ensure_fresh_destination(destination)
        os.link(temporary, destination, follow_symlinks=False)
        os.unlink(temporary)
        directory_descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except FileExistsError:
        raise ResultPersistenceError("result_path_collision") from None
    except OSError:
        raise ResultPersistenceError("result_publish_failed") from None
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass

    try:
        metadata = os.lstat(destination)
    except OSError:
        raise ResultPersistenceError("result_publish_failed") from None
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise ResultPersistenceError("result_permissions_invalid")


def persist_result(
    destination: Path,
    evidence: Path,
    *,
    status: int,
    phase: str = "api-invocation",
    error_class: str = "unavailable",
    reason_category: str = "unavailable",
    stderr_sha256: str = EMPTY_STDERR_SHA256,
    missing_module: str = "",
    setup_error: str | None = None,
) -> bytes:
    """Publish exactly one schema-controlled JSON receipt."""

    if isinstance(status, bool) or not isinstance(status, int) or not 0 <= status <= 255:
        raise ResultPersistenceError("exit_code_invalid")
    evidence_payload = _read_schema_controlled_evidence(evidence, required=status == 0)
    if status != 0:
        _bounded_failure_line(
            phase=phase,
            error_class=error_class,
            exit_code=status,
            reason_category=reason_category,
            stderr_sha256=stderr_sha256,
            missing_module=missing_module,
        )
    if evidence_payload:
        payload = evidence_payload
    elif status != 0:
        payload = _runner_failure_receipt(
            phase=phase,
            error_class=error_class,
            exit_code=status,
            reason_category=reason_category,
            stderr_sha256=stderr_sha256,
            missing_module=missing_module,
            setup_error=setup_error,
        )
    else:
        raise ResultPersistenceError("evidence_unavailable")
    if not payload or len(payload) > MAX_RESULT_BYTES:
        raise ResultPersistenceError("result_size_invalid")
    parent = _validate_destination_parent(destination)
    destination = parent / destination.name
    _ensure_fresh_destination(destination)
    _write_atomically(destination, payload, parent)
    return payload


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--status", type=int, required=True)
    parser.add_argument("--phase", default="api-invocation")
    parser.add_argument("--error-class", default="unavailable")
    parser.add_argument("--reason-category", default="unavailable")
    parser.add_argument("--stderr-sha256", default=EMPTY_STDERR_SHA256)
    parser.add_argument("--missing-module", default="")
    parser.add_argument("--setup-error", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        payload = persist_result(
            args.destination,
            args.evidence,
            status=args.status,
            phase=args.phase,
            error_class=args.error_class,
            reason_category=args.reason_category,
            stderr_sha256=args.stderr_sha256,
            missing_module=args.missing_module,
            setup_error=args.setup_error,
        )
    except ResultPersistenceError as exc:
        print(f"event=agent.g4.live-runner.result status=failed reason={exc.reason}", file=sys.stderr)
        return 2
    if args.status != 0:
        sys.stderr.buffer.write(
            _bounded_failure_line(
                phase=args.phase,
                error_class=args.error_class,
                exit_code=args.status,
                reason_category=args.reason_category,
                stderr_sha256=args.stderr_sha256,
                missing_module=args.missing_module,
            )
        )
    sys.stdout.buffer.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
