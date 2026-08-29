# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only

"""Plane-owned serialized runtime dispatch and evidence ingress."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from django.db import IntegrityError, OperationalError, transaction

from plane.agent.lifecycle.runtime_contract import (
    RuntimeContractError,
    canonical_json,
    content_digest,
    validate_invocation_envelope,
    validate_run_snapshot,
    validate_runtime_event,
    validate_runtime_exit,
)
from plane.agent.lifecycle import lock_invocation_path
from plane.db.models import RunTerminalEvent, RuntimeEventIngress, RuntimeExitEvidence, RuntimeInvocation

from .contracts import RuntimeDispatchError, RuntimeTransport


class RuntimeIngressError(ValueError):
    """Raised when an untrusted runtime frame cannot become Plane evidence."""


def _contract_error(exc: RuntimeContractError, context: str) -> RuntimeIngressError:
    return RuntimeIngressError(f"{context}: {exc}")


def _decode_frame(serialized_frame: str) -> dict[str, Any]:
    if not isinstance(serialized_frame, str):
        raise RuntimeIngressError("runtime frame must be serialized JSON text")
    try:
        frame = json.loads(serialized_frame)
    except (TypeError, ValueError) as exc:
        raise RuntimeIngressError("runtime frame is not valid JSON") from exc
    if not isinstance(frame, dict):
        raise RuntimeIngressError("runtime frame must be a JSON object")
    return frame


def _dispatch_binding(snapshot: dict[str, Any], envelope: dict[str, Any], invocation: RuntimeInvocation) -> None:
    expected = {
        "workspaceRef": snapshot["workspaceRef"],
        "actorRef": snapshot["actorRef"],
        "runId": snapshot["runId"],
        "invocationId": envelope["invocationId"],
        "runSnapshotDigest": snapshot["contentDigest"],
    }
    if any(envelope[key] != value for key, value in expected.items()):
        raise RuntimeDispatchError("invocation envelope is not bound to the stored run snapshot")
    if envelope["invocationId"] != invocation.invocation_id:
        raise RuntimeDispatchError("invocation envelope is not bound to the stored invocation")
    if (
        invocation.run.snapshot_content_digest != snapshot["contentDigest"]
        or invocation.idempotency_key != envelope["idempotencyKey"]
    ):
        raise RuntimeDispatchError("runtime invocation does not match its immutable Plane contract")
    if invocation.run_id != invocation.run.id or invocation.run.actor_id != invocation.run.profile_version.actor_id:
        raise RuntimeDispatchError("runtime invocation has an invalid Plane actor binding")


def dispatch_invocation(invocation: RuntimeInvocation, transport: RuntimeTransport) -> tuple[str, ...]:
    """Dispatch one stored invocation across the serialized runtime seam."""

    stored = RuntimeInvocation.objects.select_related("run", "run__profile_version").get(pk=invocation.pk)
    try:
        snapshot = validate_run_snapshot(stored.run.snapshot)
        envelope = validate_invocation_envelope(stored.envelope)
    except RuntimeContractError as exc:
        raise RuntimeDispatchError(f"stored runtime contract is invalid: {exc}") from exc
    _dispatch_binding(snapshot, envelope, stored)
    snapshot_json = canonical_json(snapshot)
    envelope_json = canonical_json(envelope)
    try:
        raw_frames = transport.dispatch(snapshot_json, envelope_json)
        if isinstance(raw_frames, str):
            raise RuntimeDispatchError("runtime transport returned one frame instead of a frame iterable")
        frames = tuple(raw_frames)
    except Exception as exc:
        if isinstance(exc, OperationalError):
            raise
        if isinstance(exc, RuntimeDispatchError):
            raise
        raise RuntimeDispatchError("runtime transport dispatch failed") from exc
    if any(not isinstance(frame, str) for frame in frames):
        raise RuntimeDispatchError("runtime transport returned a non-serialized frame")
    return frames


def _binding_error(frame: dict[str, Any], invocation: RuntimeInvocation) -> RuntimeIngressError | None:
    snapshot = invocation.run.snapshot
    envelope = invocation.envelope
    expected = {
        "workspaceRef": snapshot["workspaceRef"],
        "actorRef": snapshot["actorRef"],
        "runId": snapshot["runId"],
        "invocationId": envelope["invocationId"],
        "correlationId": envelope["correlationId"],
        "causationRef": envelope["causationRef"],
    }
    for field, value in expected.items():
        if frame.get(field) != value:
            return RuntimeIngressError(f"runtime frame {field} is not bound to the invocation")
    if frame.get("authority") == "runtime_evidence_only" and frame.get("idempotencyKey") != envelope["idempotencyKey"]:
        return RuntimeIngressError("runtime exit idempotencyKey is not bound to the invocation")
    return None


def _existing_event_replay(event: dict[str, Any], invocation: RuntimeInvocation) -> RuntimeEventIngress | None:
    fingerprint = content_digest(event)
    by_event_id = RuntimeEventIngress.all_objects.filter(event_id=event["eventId"]).first()
    by_key = RuntimeEventIngress.all_objects.filter(idempotency_key=event["idempotencyKey"]).first()
    exit_by_key = RuntimeExitEvidence.all_objects.filter(idempotency_key=event["idempotencyKey"]).first()
    candidates = [candidate for candidate in (by_event_id, by_key) if candidate is not None]
    if not candidates and exit_by_key is None:
        return None
    if (
        len(candidates) == 2
        and candidates[0].pk == candidates[1].pk
        and candidates[0].invocation_id == invocation.pk
        and candidates[0].fingerprint == fingerprint
        and exit_by_key is None
    ):
        return candidates[0]
    raise RuntimeIngressError("runtime event idempotency or event id is already bound to different evidence")


def _existing_exit_replay(exit_frame: dict[str, Any], invocation: RuntimeInvocation) -> RuntimeExitEvidence | None:
    fingerprint = content_digest(exit_frame)
    existing = RuntimeExitEvidence.all_objects.filter(invocation=invocation).first()
    by_key = RuntimeExitEvidence.all_objects.filter(idempotency_key=exit_frame["idempotencyKey"]).first()
    event_by_key = RuntimeEventIngress.all_objects.filter(idempotency_key=exit_frame["idempotencyKey"]).first()
    candidates = [candidate for candidate in (existing, by_key) if candidate is not None]
    if not candidates and event_by_key is None:
        return None
    if (
        len(candidates) == 2
        and candidates[0].pk == candidates[1].pk
        and candidates[0].invocation_id == invocation.pk
        and candidates[0].fingerprint == fingerprint
        and event_by_key is None
    ):
        return candidates[0]
    raise RuntimeIngressError("runtime exit idempotency or invocation is already bound to different evidence")


def _ingest_event(event: dict[str, Any], invocation: RuntimeInvocation) -> RuntimeEventIngress:
    replay = _existing_event_replay(event, invocation)
    if replay is not None:
        return replay
    terminal = RunTerminalEvent.objects.filter(invocation=invocation, visible=True).first()
    if RuntimeExitEvidence.all_objects.filter(invocation=invocation).exists():
        raise RuntimeIngressError("runtime events are illegal after an exit")
    latest = RuntimeEventIngress.all_objects.filter(invocation=invocation).order_by("-sequence").first()
    expected_sequence = 0 if latest is None else latest.sequence + 1
    if event["sequence"] != expected_sequence:
        raise RuntimeIngressError("runtime event sequence is out of order or gapped")
    body = event["body"]
    raw_payload = deepcopy(event)
    if terminal is not None:
        raw_payload["planeIngress"] = {
            "disposition": "late_after_terminal",
            "authoritative": False,
            "terminalProductEventRef": terminal.product_event_ref,
        }
    try:
        with transaction.atomic():
            return RuntimeEventIngress.objects.create(
                workspace=invocation.workspace,
                project=invocation.project,
                invocation=invocation,
                run=invocation.run,
                actor=invocation.run.actor,
                snapshot_content_digest=invocation.run.snapshot_content_digest,
                event_id=event["eventId"],
                idempotency_key=event["idempotencyKey"],
                correlation_id=event["correlationId"],
                causation_ref=event["causationRef"],
                sequence=event["sequence"],
                fingerprint=content_digest(event),
                kind=body["kind"],
                observed_at=event["observedAt"],
                raw_payload=raw_payload,
            )
    except IntegrityError as exc:
        raise RuntimeIngressError("runtime event could not be persisted without an identity collision") from exc


def _ingest_exit(exit_frame: dict[str, Any], invocation: RuntimeInvocation) -> RuntimeExitEvidence:
    replay = _existing_exit_replay(exit_frame, invocation)
    if replay is not None:
        return replay
    latest = RuntimeEventIngress.all_objects.filter(invocation=invocation).order_by("-sequence").first()
    last_sequence = 0 if latest is None else latest.sequence
    if exit_frame["finalSequence"] != last_sequence:
        raise RuntimeIngressError("runtime exit finalSequence does not match accepted event sequence")
    try:
        with transaction.atomic():
            return RuntimeExitEvidence.objects.create(
                workspace=invocation.workspace,
                project=invocation.project,
                invocation=invocation,
                run=invocation.run,
                actor=invocation.run.actor,
                snapshot_content_digest=invocation.run.snapshot_content_digest,
                idempotency_key=exit_frame["idempotencyKey"],
                correlation_id=exit_frame["correlationId"],
                causation_ref=exit_frame["causationRef"],
                final_sequence=exit_frame["finalSequence"],
                fingerprint=content_digest(exit_frame),
                kind=exit_frame["kind"],
                raw_payload=deepcopy(exit_frame),
            )
    except IntegrityError as exc:
        raise RuntimeIngressError("runtime exit could not be persisted without an identity collision") from exc


@transaction.atomic
def ingest_runtime_frame(
    invocation: RuntimeInvocation, serialized_frame: str
) -> RuntimeEventIngress | RuntimeExitEvidence:
    """Validate, bind, sequence, and persist one serialized runtime frame."""

    _assignment, run, stored = lock_invocation_path(invocation.pk)
    stored.run = run
    frame = _decode_frame(serialized_frame)
    if "trust" in frame:
        try:
            validated = validate_runtime_event(frame)
        except RuntimeContractError as exc:
            raise _contract_error(exc, "runtime event rejected") from exc
        record_type = "event"
    elif "authority" in frame:
        try:
            validated = validate_runtime_exit(frame)
        except RuntimeContractError as exc:
            raise _contract_error(exc, "runtime exit rejected") from exc
        record_type = "exit"
    else:
        raise RuntimeIngressError("runtime frame is neither RuntimeEvent nor RuntimeExit")
    binding_error = _binding_error(validated, stored)
    if binding_error is not None:
        raise binding_error
    if record_type == "event":
        return _ingest_event(validated, stored)
    return _ingest_exit(validated, stored)
