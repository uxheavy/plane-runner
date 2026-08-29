# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Celery workers for durable Operation Gateway publications."""

from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from plane.db.models import OperationGatewayPublication

from .publications import PUBLICATION_LEASE_SECONDS, dispatch_publication_once
from .quota import cleanup_gateway_quota
from .role_boundary import audited_gateway_boundary


PUBLICATION_RECONCILE_BATCH_SIZE = 500
QUEUED_DELIVERY_RESULT = {"state": "queued"}


@shared_task(bind=True, max_retries=5)
@audited_gateway_boundary
def dispatch_publication(self, publication_id: str) -> None:
    try:
        dispatch_publication_once(publication_id)
    except Exception as error:
        publication = OperationGatewayPublication.objects.get(pk=publication_id)
        if publication.state == OperationGatewayPublication.State.RETRYABLE:
            raise self.retry(exc=error, countdown=min(60 * (self.request.retries + 1), 900)) from error
        # FAILED and OUTCOME_UNKNOWN are durable terminal decisions. In
        # particular, an external delivery that may have reached its target
        # must never be replayed by Celery's generic exception path.
        raise


@shared_task
@audited_gateway_boundary
def reconcile_publications() -> int:
    """Claim and requeue one bounded page of missing or expired intents."""

    now = timezone.now()
    with transaction.atomic():
        publications = list(
            OperationGatewayPublication.objects.select_for_update(skip_locked=True)
            .filter(
                Q(
                    state__in=(
                        OperationGatewayPublication.State.PENDING,
                        OperationGatewayPublication.State.RETRYABLE,
                    )
                )
                | Q(state=OperationGatewayPublication.State.RUNNING, lease_until__lt=now)
                | Q(state=OperationGatewayPublication.State.RUNNING, lease_until__isnull=True)
            )
            .order_by("created_at", "id")[:PUBLICATION_RECONCILE_BATCH_SIZE]
        )
        for publication in publications:
            if publication.state in (
                OperationGatewayPublication.State.PENDING,
                OperationGatewayPublication.State.RETRYABLE,
            ):
                publication.state = OperationGatewayPublication.State.RUNNING
                publication.dispatch_started = False
                publication.lease_until = now + timedelta(seconds=PUBLICATION_LEASE_SECONDS)
                publication.delivery_result = QUEUED_DELIVERY_RESULT
                publication.save(
                    update_fields=["state", "dispatch_started", "lease_until", "delivery_result", "updated_at"]
                )
        publication_ids = [str(publication.id) for publication in publications]
        transaction.on_commit(
            lambda: [dispatch_publication.delay(publication_id) for publication_id in publication_ids],
            robust=True,
        )
    return len(publication_ids)


@shared_task
@audited_gateway_boundary
def cleanup_gateway_quotas() -> int:
    return cleanup_gateway_quota()
