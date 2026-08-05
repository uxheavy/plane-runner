# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded local process transport for the Plane runtime contract.

The transport is deliberately ignorant of the runtime kernel.  It accepts
canonical JSON strings, starts one explicitly configured child process, and
returns bounded JSON-lines text for the existing Plane ingress validator.
The SQLite ledger is transport recovery state only; it is not a second Plane
run or outcome authority.
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import sqlite3
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .dispatch import RuntimeDispatchError, RuntimeTransport


_LEDGER_TABLE = "plane_runtime_dispatch_ledger"
_DEFAULT_TIMEOUT_SECONDS = 30.0
_DEFAULT_MAX_INPUT_BYTES = 256 * 1024
_DEFAULT_MAX_OUTPUT_BYTES = 512 * 1024
_DEFAULT_MAX_DIAGNOSTICS_BYTES = 64 * 1024
_CANCELLATION_GRACE_SECONDS = 1.0
_READ_CHUNK_BYTES = 16 * 1024
_HERMES_RUNTIME_POLICY_FIELDS = frozenset(
    {
        "model",
        "adapter",
        "isolation",
        "maxEventPayloadBytes",
        "maxArtifactBytes",
        "maxReceiptBytes",
    }
)
_PLANE_ONLY_HERMES_POLICY_FIELDS = frozenset({"maxCodeModeInputBytes", "maxCodeModeOutputBytes", "maxCodeModeCalls"})
_HERMES_G1_CONTRACT_DIGESTS = {
    # Frozen by the exact Hermes 2dd316df69afba586b99acda2f5aeb1529307b63
    # plane_runtime.g1_contract manifest accepted at this process boundary.
    "runSnapshot": "e538fe79ede53e6bb2e307600dbefea507e30b996c002c3dab32d543ca0e36a2",
    "invocationEnvelope": "b7a15d74406f1624cdb7cd95b42edfd1ffee596abe57e4f00ed60e2e23ded995",
    "runtimeEvent": "fcbf67ce71fa90dd9661a8f2a739b8119c59357c8bf01afabf4fe92a13de9425",
    "runtimeExit": "055792eb1bf4931dafe19de456b15037522f0b5e8f6a0d2fedfe0e0d1d1d1c05",
    "runtimeDurableState": "444c944ec8a5054f33c8662470529a1f4565d42ff06138438beceeef7967a0da",
}
_HERMES_DISPATCH_PROTOCOL = "plane.agent-runtime/dispatch-control/v1"
_HERMES_CREDENTIAL_PROTOCOL = "plane.agent-runtime/credential-control/v1"


def _canonical_object(raw: str, name: str) -> dict[str, Any]:
    if not isinstance(raw, str):
        raise RuntimeDispatchError(f"{name} must be serialized JSON text")
    try:
        value = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeDispatchError(f"{name} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeDispatchError(f"{name} must be a JSON object")
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if canonical != raw:
        raise RuntimeDispatchError(f"{name} must be canonical JSON")
    return value


def _request_payload(snapshot_json: str, envelope_json: str) -> tuple[bytes, str, str, str]:
    snapshot = _canonical_object(snapshot_json, "runtime snapshot")
    envelope = _canonical_object(envelope_json, "runtime invocation")
    run_id = snapshot.get("runId")
    invocation_id = envelope.get("invocationId")
    if not isinstance(run_id, str) or not run_id:
        raise RuntimeDispatchError("runtime snapshot has no runId")
    if not isinstance(invocation_id, str) or not invocation_id:
        raise RuntimeDispatchError("runtime invocation has no invocationId")
    if envelope.get("runId") != run_id:
        raise RuntimeDispatchError("runtime invocation is not bound to the runtime snapshot")
    request = (
        json.dumps(
            {"invocation": envelope, "run": snapshot},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )
    digest = hashlib.sha256(
        b"plane.agent-runtime/subprocess-request/v1\n"
        + snapshot_json.encode("utf-8")
        + b"\n"
        + envelope_json.encode("utf-8")
    ).hexdigest()
    return request, run_id, invocation_id, digest


def _hermes_request_payload(snapshot_json: str, envelope_json: str) -> tuple[bytes, str, str, str]:
    """Project Plane's richer immutable snapshot onto exact Hermes G1 wire fields.

    Plane retains Code Mode limits in its authoritative snapshot. Hermes 2dd's
    strict G1 contract intentionally does not accept those Plane-owned policy
    fields, so the child receives a deterministic projection and a matching
    invocation digest. The persisted Plane snapshot and invocation are never
    modified; host callbacks remain bound to their original durable records.
    """

    snapshot = _canonical_object(snapshot_json, "runtime snapshot")
    envelope = _canonical_object(envelope_json, "runtime invocation")
    policy = snapshot.get("runtimePolicy")
    if policy is None:
        return _request_payload(snapshot_json, envelope_json)
    if not isinstance(policy, dict):
        raise RuntimeDispatchError("runtime snapshot has no runtime policy")
    extras = set(policy).difference(_HERMES_RUNTIME_POLICY_FIELDS)
    if extras != _PLANE_ONLY_HERMES_POLICY_FIELDS:
        if extras:
            raise RuntimeDispatchError("runtime snapshot has unprojectable Hermes policy fields")
        return _request_payload(snapshot_json, envelope_json)
    projected = dict(snapshot)
    projected_policy = {key: policy[key] for key in _HERMES_RUNTIME_POLICY_FIELDS}
    projected["runtimePolicy"] = projected_policy
    projected["contractDigests"] = dict(_HERMES_G1_CONTRACT_DIGESTS)
    projected.pop("contentDigest", None)
    projected["contentDigest"] = (
        "snapshot:"
        + hashlib.sha256(
            json.dumps(projected, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
    )
    projected_envelope = dict(envelope)
    projected_envelope["runSnapshotDigest"] = projected["contentDigest"]
    return _request_payload(
        json.dumps(projected, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        json.dumps(projected_envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
    )


def _hermes_bootstrap_payload(
    snapshot_json: str,
    envelope_json: str,
    *,
    model_call_allowance: int | None = None,
    credentials: Mapping[str, str] | None = None,
) -> tuple[bytes, str, str, str]:
    """Frame the exact private bootstrap handoff for the marked Hermes child."""

    request, run_id, invocation_id, _request_digest = _hermes_request_payload(snapshot_json, envelope_json)
    envelope = _canonical_object(envelope_json, "runtime invocation")
    if model_call_allowance is None:
        remaining = envelope.get("remainingBudget", {})
        allowance = remaining.get("outputTokens", 0) if isinstance(remaining, dict) else 0
        model_call_allowance = min(4096, max(0, int(allowance)))
    if (
        isinstance(model_call_allowance, bool)
        or not isinstance(model_call_allowance, int)
        or not 0 <= model_call_allowance <= 4096
    ):
        raise RuntimeDispatchError("model-call allowance is outside the bootstrap bound")
    credential_values = dict(credentials or {})
    if len(credential_values) > 16 or any(
        not isinstance(key, str)
        or not isinstance(value, str)
        or not key
        or not value
        or any(ord(char) < 0x20 or ord(char) == 0x7F for char in key + value)
        or len(key.encode("utf-8")) > 128
        or len(value.encode("utf-8")) > 16 * 1024
        for key, value in credential_values.items()
    ):
        raise RuntimeDispatchError("credential control is invalid")
    controls = b"".join(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
        for value in (
            {"modelCallAllowance": model_call_allowance, "protocol": _HERMES_DISPATCH_PROTOCOL},
            {"credentials": credential_values, "protocol": _HERMES_CREDENTIAL_PROTOCOL},
        )
    )
    payload = controls + request
    if len(payload) > _DEFAULT_MAX_INPUT_BYTES:
        raise RuntimeDispatchError("runtime bootstrap request exceeds the process input bound")
    digest = hashlib.sha256(b"plane.agent-runtime/hermes-bootstrap/v1\n" + payload).hexdigest()
    return payload, run_id, invocation_id, digest


def _encode_frames(frames: Sequence[str]) -> str:
    if any(not isinstance(frame, str) for frame in frames):
        raise RuntimeDispatchError("runtime process returned a non-text frame")
    return json.dumps(list(frames), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode_frames(raw: str) -> tuple[str, ...]:
    try:
        frames = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeDispatchError("runtime dispatch ledger contains invalid frames") from exc
    if not isinstance(frames, list) or any(not isinstance(frame, str) for frame in frames):
        raise RuntimeDispatchError("runtime dispatch ledger contains invalid frames")
    return tuple(frames)


class _DispatchLedger:
    """Small durable claim/commit ledger for one invocation identity."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        if not path:
            raise ValueError("ledger_path is required")
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=5.0)
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {_LEDGER_TABLE} (
                    invocation_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    request_digest TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (state IN ('running', 'completed', 'outcome_unknown')),
                    frames_json TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )

    def claim(self, *, run_id: str, invocation_id: str, request_digest: str) -> tuple[str, ...] | None:
        now = time.time()
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    f"SELECT run_id, request_digest, state, frames_json FROM {_LEDGER_TABLE} WHERE invocation_id = ?",
                    (invocation_id,),
                ).fetchone()
                if row is not None:
                    stored_run_id, stored_digest, state, frames_json = row
                    if stored_run_id != run_id or stored_digest != request_digest:
                        raise RuntimeDispatchError("changed runtime replay is denied")
                    if state == "completed":
                        if not isinstance(frames_json, str):
                            raise RuntimeDispatchError("runtime dispatch ledger completion is missing frames")
                        return _decode_frames(frames_json)
                    if state in {"running", "outcome_unknown"}:
                        raise RuntimeDispatchError(
                            "runtime outcome is unknown; reconciliation is required before replay"
                        )
                    raise RuntimeDispatchError("runtime dispatch ledger contains an invalid state")
                connection.execute(
                    f"""
                    INSERT INTO {_LEDGER_TABLE}
                        (invocation_id, run_id, request_digest, state, frames_json, created_at, updated_at)
                    VALUES (?, ?, ?, 'running', NULL, ?, ?)
                    """,
                    (invocation_id, run_id, request_digest, now, now),
                )
                return None
        except RuntimeDispatchError:
            raise
        except sqlite3.Error as exc:
            raise RuntimeDispatchError("runtime dispatch ledger is unavailable") from exc

    def complete(self, *, invocation_id: str, frames: Sequence[str]) -> None:
        now = time.time()
        encoded = _encode_frames(frames)
        try:
            with self._connect() as connection:
                updated = connection.execute(
                    f"""
                    UPDATE {_LEDGER_TABLE}
                    SET state = 'completed', frames_json = ?, updated_at = ?
                    WHERE invocation_id = ? AND state = 'running'
                    """,
                    (encoded, now, invocation_id),
                ).rowcount
                if updated != 1:
                    raise RuntimeDispatchError("runtime dispatch ledger claim is no longer active")
        except RuntimeDispatchError:
            raise
        except sqlite3.Error as exc:
            raise RuntimeDispatchError("runtime dispatch ledger could not commit completion") from exc

    def mark_unknown(self, *, invocation_id: str) -> None:
        now = time.time()
        try:
            with self._connect() as connection:
                updated = connection.execute(
                    f"""
                    UPDATE {_LEDGER_TABLE}
                    SET state = 'outcome_unknown', updated_at = ?
                    WHERE invocation_id = ? AND state = 'running'
                    """,
                    (now, invocation_id),
                ).rowcount
                if updated != 1:
                    raise RuntimeDispatchError("runtime dispatch ledger claim is no longer active")
        except RuntimeDispatchError:
            raise
        except sqlite3.Error as exc:
            raise RuntimeDispatchError("runtime dispatch ledger could not record unknown outcome") from exc


class SubprocessRuntimeTransport(RuntimeTransport):
    """Run one replaceable runtime service process behind the Plane port.

    ``command`` and ``environment`` are trusted deployment configuration. The
    child receives only the immutable snapshot and invocation JSON; no ambient
    process environment is inherited and no shell is used.
    """

    def __init__(
        self,
        *,
        command: Sequence[str],
        ledger_path: str | os.PathLike[str],
        cwd: str | os.PathLike[str] | None = None,
        environment: Mapping[str, str] | None = None,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        max_input_bytes: int = _DEFAULT_MAX_INPUT_BYTES,
        max_output_bytes: int = _DEFAULT_MAX_OUTPUT_BYTES,
        max_diagnostics_bytes: int = _DEFAULT_MAX_DIAGNOSTICS_BYTES,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> None:
        if not command or any(not isinstance(part, str) or not part or "\x00" in part for part in command):
            raise ValueError("command must contain non-empty strings without NUL bytes")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        for name, value in (
            ("max_input_bytes", max_input_bytes),
            ("max_output_bytes", max_output_bytes),
            ("max_diagnostics_bytes", max_diagnostics_bytes),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        self._command = tuple(command)
        self._ledger = _DispatchLedger(ledger_path)
        self._cwd = os.fspath(cwd) if cwd is not None else None
        self._environment = dict(environment or {})
        self._timeout_seconds = float(timeout_seconds)
        self._max_input_bytes = max_input_bytes
        self._max_output_bytes = max_output_bytes
        self._max_diagnostics_bytes = max_diagnostics_bytes
        self._cancellation_callback = is_cancelled
        self._is_cancelled = is_cancelled or (lambda: False)

    @staticmethod
    def _terminate(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (AttributeError, OSError):
            try:
                process.kill()
            except OSError:
                pass

    @staticmethod
    def _request_cancellation(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGUSR1)
        except (AttributeError, OSError):
            try:
                process.send_signal(signal.SIGUSR1)
            except OSError:
                pass

    @staticmethod
    def _read_bounded(stream: Any, target: bytearray, limit: int, overflow: threading.Event) -> None:
        try:
            while True:
                chunk = stream.read(_READ_CHUNK_BYTES)
                if not chunk:
                    return
                if len(target) + len(chunk) > limit:
                    overflow.set()
                    return
                target.extend(chunk)
        except (OSError, ValueError):
            overflow.set()

    def _run_process(self, payload: bytes, *, command: Sequence[str] | None = None) -> tuple[str, ...]:
        process_command = tuple(command or self._command)
        try:
            process = subprocess.Popen(
                process_command,
                cwd=self._cwd,
                env=self._environment,
                shell=False,
                start_new_session=True,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except (OSError, ValueError) as exc:
            raise RuntimeDispatchError("runtime process could not be started") from exc

        stdout = bytearray()
        stderr = bytearray()
        overflow = threading.Event()
        write_error = threading.Event()

        def write_input() -> None:
            try:
                assert process.stdin is not None
                process.stdin.write(payload)
                process.stdin.flush()
                process.stdin.close()
            except (BrokenPipeError, OSError, ValueError):
                write_error.set()

        threads = [
            threading.Thread(
                target=self._read_bounded,
                args=(process.stdout, stdout, self._max_output_bytes, overflow),
                daemon=True,
            ),
            threading.Thread(
                target=self._read_bounded,
                args=(process.stderr, stderr, self._max_diagnostics_bytes, overflow),
                daemon=True,
            ),
            threading.Thread(target=write_input, daemon=True),
        ]
        for thread in threads:
            thread.start()

        deadline = time.monotonic() + self._timeout_seconds
        timed_out = False
        cancellation_requested = False
        forced_cancellation = False
        cancellation_deadline = 0.0
        while process.poll() is None:
            if overflow.is_set():
                self._terminate(process)
                break
            try:
                cancelled = bool(self._is_cancelled())
            except Exception as exc:
                self._terminate(process)
                raise RuntimeDispatchError("runtime cancellation state is unavailable") from exc
            if cancelled:
                if not cancellation_requested:
                    cancellation_requested = True
                    cancellation_deadline = time.monotonic() + _CANCELLATION_GRACE_SECONDS
                    self._request_cancellation(process)
                remaining = cancellation_deadline - time.monotonic()
                if remaining <= 0:
                    forced_cancellation = True
                    self._terminate(process)
                    break
                time.sleep(min(0.01, remaining))
                continue
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                self._terminate(process)
                break
            time.sleep(min(0.01, remaining))
        self._terminate(process)
        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            self._terminate(process)
            process.wait(timeout=1.0)
        for thread in threads:
            thread.join(timeout=0.25)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass

        if forced_cancellation:
            raise RuntimeDispatchError("runtime invocation was cancelled")
        if timed_out or overflow.is_set() or write_error.is_set() or process.returncode != 0:
            raise RuntimeDispatchError("runtime process did not produce a durable terminal result")
        if not stdout or not stdout.endswith(b"\n"):
            raise RuntimeDispatchError("runtime process output is not newline-delimited")
        try:
            lines = stdout[:-1].split(b"\n")
            frames = tuple(line.decode("utf-8") for line in lines if line)
        except UnicodeDecodeError as exc:
            raise RuntimeDispatchError("runtime process output is not UTF-8") from exc
        if not frames or len(frames) != len(lines):
            raise RuntimeDispatchError("runtime process output contains an empty frame")
        return frames

    def dispatch(self, snapshot_json: str, envelope_json: str) -> tuple[str, ...]:
        payload, run_id, invocation_id, request_digest = _request_payload(snapshot_json, envelope_json)
        if len(payload) > self._max_input_bytes:
            raise RuntimeDispatchError("runtime request exceeds the process input bound")
        if self._is_cancelled():
            raise RuntimeDispatchError("runtime invocation was cancelled")
        replay = self._ledger.claim(run_id=run_id, invocation_id=invocation_id, request_digest=request_digest)
        if replay is not None:
            return replay
        try:
            frames = self._run_process(payload)
        except Exception:
            try:
                self._ledger.mark_unknown(invocation_id=invocation_id)
            except RuntimeDispatchError as ledger_error:
                raise ledger_error
            raise
        try:
            self._ledger.complete(invocation_id=invocation_id, frames=frames)
        except Exception:
            try:
                self._ledger.mark_unknown(invocation_id=invocation_id)
            except RuntimeDispatchError as ledger_error:
                raise ledger_error
            raise
        return frames


class HostBoundSubprocessRuntimeTransport(SubprocessRuntimeTransport):
    """Run Hermes with one trusted Plane host socket for the invocation."""

    def __init__(
        self,
        *,
        gateway: Any,
        host_timeout_seconds: float = 5.0,
        bootstrap_command: bool | None = None,
        model_call_allowance: int | Callable[[Any], int] | None = None,
        credential_control: Callable[[Any], Mapping[str, str]] | None = None,
        **kwargs: Any,
    ) -> None:
        if gateway is None:
            raise ValueError("gateway is required")
        if host_timeout_seconds <= 0:
            raise ValueError("host_timeout_seconds must be positive")
        super().__init__(**kwargs)
        self._gateway = gateway
        self._host_timeout_seconds = float(host_timeout_seconds)
        command = tuple(self._command)
        self._bootstrap_command = (
            any("plane_runtime.g1_runtime_image.bootstrap" in part for part in command)
            if bootstrap_command is None
            else bool(bootstrap_command)
        )
        self._model_call_allowance = model_call_allowance
        self._credential_control = credential_control

    def dispatch(self, snapshot_json: str, envelope_json: str) -> tuple[str, ...]:
        payload, run_id, invocation_id, request_digest = _hermes_request_payload(snapshot_json, envelope_json)
        if len(payload) > self._max_input_bytes:
            raise RuntimeDispatchError("runtime request exceeds the process input bound")

        from plane.agent.runtime.host_rpc import PlaneHostServer, build_gateway_host_port
        from plane.db.models import RuntimeInvocation

        temp_dir: str | None = None
        server: PlaneHostServer | None = None
        ledger_claimed = False
        try:
            try:
                invocation = RuntimeInvocation.objects.get(invocation_id=invocation_id)
            except RuntimeInvocation.DoesNotExist as exc:
                raise RuntimeDispatchError("runtime invocation is unavailable for host binding") from exc
            if self._cancellation_callback is None and hasattr(invocation, "pk"):
                from .supervisor import runtime_invocation_cancelled

                invocation_ref = invocation.pk
                self._is_cancelled = lambda: runtime_invocation_cancelled(invocation_ref)
            if self._is_cancelled():
                raise RuntimeDispatchError("runtime invocation was cancelled")
            if self._credential_control is not None:
                credentials = self._credential_control(invocation)
            else:
                credentials = {}
            allowance = (
                self._model_call_allowance(invocation)
                if callable(self._model_call_allowance)
                else self._model_call_allowance
            )
            if self._bootstrap_command:
                payload, run_id, invocation_id, request_digest = _hermes_bootstrap_payload(
                    snapshot_json,
                    envelope_json,
                    model_call_allowance=allowance,
                    credentials=credentials,
                )
            if len(payload) > self._max_input_bytes:
                raise RuntimeDispatchError("runtime bootstrap request exceeds the process input bound")
            replay = self._ledger.claim(run_id=run_id, invocation_id=invocation_id, request_digest=request_digest)
            if replay is not None:
                return replay
            ledger_claimed = True
            host_kwargs = {"invocation": invocation, "gateway": self._gateway}
            if self._cancellation_callback is not None:
                host_kwargs["is_cancelled"] = self._cancellation_callback
            host_port = build_gateway_host_port(**host_kwargs)
            temp_dir = tempfile.mkdtemp(prefix="plane-host-")
            socket_path = Path(temp_dir) / "host.sock"
            if len(os.fsencode(str(socket_path))) >= 104:
                raise RuntimeDispatchError("host socket path exceeds the local Unix socket bound")
            server = PlaneHostServer(
                socket_path=socket_path,
                invoke=host_port.invoke,
                timeout_seconds=self._host_timeout_seconds,
            )
            server.start()
            command = (*self._command, "--plane-host-socket", str(socket_path))
            frames = self._run_process(payload, command=command)
        except Exception:
            if ledger_claimed:
                try:
                    self._ledger.mark_unknown(invocation_id=invocation_id)
                except RuntimeDispatchError as ledger_error:
                    raise ledger_error
            raise
        finally:
            if server is not None:
                server.close()
            if temp_dir is not None:
                try:
                    os.rmdir(temp_dir)
                except OSError:
                    pass
        try:
            self._ledger.complete(invocation_id=invocation_id, frames=frames)
        except Exception:
            try:
                self._ledger.mark_unknown(invocation_id=invocation_id)
            except RuntimeDispatchError as ledger_error:
                raise ledger_error
            raise
        return frames


__all__ = ["HostBoundSubprocessRuntimeTransport", "SubprocessRuntimeTransport", "_hermes_bootstrap_payload"]
