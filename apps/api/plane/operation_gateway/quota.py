"""Transactional quota reservations for the shared Operation Gateway."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.db import IntegrityError, connection, transaction
from django.db.models import BooleanField, Case, CharField, Exists, OuterRef, Value, When
from django.db.models.functions import Cast
from django.utils import timezone

from plane.db.models import OperationGatewayIdempotency, OperationGatewayQuotaBucket

from .limits import (
    MAX_QUOTA_IDENTITY_LENGTH,
    QUOTA_CLEANUP_BATCH_SIZE,
    QUOTA_LIMITS,
    QUOTA_RETENTION,
    QUOTA_WINDOW,
    QuotaScope,
)


class GatewayQuotaExceeded(Exception):
    """The shared gateway quota was exhausted before product dispatch."""

    def __init__(self, scope: QuotaScope):
        super().__init__(scope)
        self.scope = scope


@dataclass(frozen=True)
class QuotaIdentity:
    """Stable, non-secret quota subjects derived at the gateway boundary."""

    workspace_id: str
    agent_key: str
    invocation_key: str


@dataclass(frozen=True)
class QuotaReservation:
    bucket_start: datetime
    agent_key: str
    invocation_key: str


def build_quota_identity(
    *,
    workspace_id: Any,
    caller_id: str,
    agent_ref: Any,
    invocation_ref: Any,
) -> QuotaIdentity:
    """Hash caller-controlled runtime references before using them as keys."""

    agent_value = _validated_identity(agent_ref, f"user:{caller_id}")
    invocation_value = _validated_identity(invocation_ref, f"caller:{caller_id}")
    return QuotaIdentity(
        workspace_id=str(workspace_id),
        agent_key=_stable_key(agent_value),
        invocation_key=_stable_key(invocation_value),
    )


def reserve_gateway_quota(identity: QuotaIdentity, *, now: datetime | None = None) -> QuotaReservation:
    """Lock all three quota buckets and reserve one request atomically.

    The caller must already be inside ``transaction.atomic()``.  Buckets are
    locked in a fixed scope order, so concurrent requests cannot oversubscribe
    a workspace, Agent, or runtime invocation.
    """

    if not connection.in_atomic_block:
        raise RuntimeError("Gateway quota reservations require an atomic transaction")
    bucket_start = _bucket_start(now or timezone.now())
    # Keep partial increments out of the caller's transaction if a later
    # scope rejects the reservation and the caller intentionally handles the
    # bounded exception to write a denial audit.
    with transaction.atomic():
        subjects = (
            ("workspace", identity.workspace_id),
            ("agent", identity.agent_key),
            ("invocation", identity.invocation_key),
        )
        limits = {limit.scope: limit for limit in QUOTA_LIMITS}
        for scope, subject_key in subjects:
            bucket = _locked_bucket(
                workspace_id=identity.workspace_id,
                scope=scope,
                subject_key=subject_key,
                bucket_start=bucket_start,
            )
            limit = limits[scope]
            if bucket.request_count >= limit.max_requests or bucket.active_count >= limit.max_active:
                raise GatewayQuotaExceeded(scope)
            bucket.request_count += 1
            bucket.active_count += 1
            bucket.save(update_fields=["request_count", "active_count", "updated_at"])
        return QuotaReservation(bucket_start, identity.agent_key, identity.invocation_key)


def release_gateway_quota(record: OperationGatewayIdempotency) -> None:
    """Release a terminal invocation's active reservations exactly once."""

    if not record.quota_reserved or record.quota_bucket_start is None or record.workspace_id is None:
        return
    if not connection.in_atomic_block:
        raise RuntimeError("Gateway quota releases require an atomic transaction")
    subjects = (
        ("workspace", str(record.workspace_id)),
        ("agent", record.quota_agent_key),
        ("invocation", record.quota_invocation_key),
    )
    for scope, subject_key in subjects:
        bucket = (
            OperationGatewayQuotaBucket.objects.select_for_update()
            .filter(
                workspace_id=record.workspace_id,
                scope=scope,
                subject_key=subject_key,
                bucket_start=record.quota_bucket_start,
            )
            .first()
        )
        if bucket is not None and bucket.active_count:
            bucket.active_count -= 1
            bucket.save(update_fields=["active_count", "updated_at"])
    record.quota_reserved = False
    record.save(update_fields=["quota_reserved", "updated_at"])


def cleanup_gateway_quota(
    *,
    now: datetime | None = None,
    retention=QUOTA_RETENTION,
    batch_size: int = QUOTA_CLEANUP_BATCH_SIZE,
) -> int:
    """Delete only inactive, expired quota buckets in a bounded batch.

    The active/current checks are evaluated in the delete transaction's
    snapshot and the idempotency guard prevents cleanup from deleting a
    bucket still referenced by an in-flight reservation.  Repeated calls are
    safe and converge because the same deterministic cutoff is used.
    """

    if not isinstance(retention, timedelta) or retention <= timedelta(0):
        raise ValueError("Quota retention must be a positive duration")
    if not isinstance(batch_size, int) or isinstance(batch_size, bool) or not 1 <= batch_size <= 5_000:
        raise ValueError("Quota cleanup batch size must be between 1 and 5000")
    effective_now = now or timezone.now()
    current_bucket = _bucket_start(effective_now)
    cutoff = _bucket_start(effective_now - retention)
    active_reservation = OperationGatewayIdempotency.objects.filter(
        workspace_id=OuterRef("workspace_id"),
        quota_bucket_start=OuterRef("bucket_start"),
        quota_reserved=True,
    )
    active_workspace_reservation = active_reservation.annotate(
        workspace_key=Cast("workspace_id", output_field=CharField())
    ).filter(workspace_key=OuterRef("subject_key"))
    active_agent_reservation = active_reservation.filter(quota_agent_key=OuterRef("subject_key"))
    active_invocation_reservation = active_reservation.filter(quota_invocation_key=OuterRef("subject_key"))
    with transaction.atomic():
        candidate_ids = list(
            OperationGatewayQuotaBucket.objects.select_for_update()
            .filter(bucket_start__lt=cutoff, active_count=0)
            .exclude(bucket_start=current_bucket)
            .annotate(
                has_active_reservation=Case(
                    When(scope="workspace", then=Exists(active_workspace_reservation)),
                    When(scope="agent", then=Exists(active_agent_reservation)),
                    When(scope="invocation", then=Exists(active_invocation_reservation)),
                    default=Value(False),
                    output_field=BooleanField(),
                )
            )
            .filter(has_active_reservation=False)
            .order_by("bucket_start", "id")
            .values_list("id", flat=True)[:batch_size]
        )
        if not candidate_ids:
            return 0
        deleted, _ = OperationGatewayQuotaBucket.objects.filter(id__in=candidate_ids).delete()
        return deleted


def _locked_bucket(*, workspace_id: str, scope: QuotaScope, subject_key: str, bucket_start: datetime):
    query = OperationGatewayQuotaBucket.objects.select_for_update()
    try:
        return query.get(
            workspace_id=workspace_id,
            scope=scope,
            subject_key=subject_key,
            bucket_start=bucket_start,
        )
    except OperationGatewayQuotaBucket.DoesNotExist:
        try:
            with transaction.atomic():
                OperationGatewayQuotaBucket.objects.create(
                    workspace_id=workspace_id,
                    scope=scope,
                    subject_key=subject_key,
                    bucket_start=bucket_start,
                )
        except IntegrityError:
            # The unique bucket key is the race arbiter.  The nested savepoint
            # keeps the surrounding gateway transaction usable after the loser
            # observes the concurrent insert.
            pass
        return query.get(
            workspace_id=workspace_id,
            scope=scope,
            subject_key=subject_key,
            bucket_start=bucket_start,
        )


def _bucket_start(value: datetime) -> datetime:
    if timezone.is_naive(value):
        raise ValueError("Quota timestamps must be timezone-aware")
    seconds = int(QUOTA_WINDOW.total_seconds())
    epoch = int(value.timestamp())
    return datetime.fromtimestamp(epoch - (epoch % seconds), tz=value.tzinfo)


def _stable_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _validated_identity(value: Any, fallback: str) -> str:
    candidate = value if isinstance(value, str) and value.strip() else fallback
    if len(candidate) > MAX_QUOTA_IDENTITY_LENGTH:
        raise ValueError(f"Quota identity exceeds {MAX_QUOTA_IDENTITY_LENGTH} characters")
    return candidate
