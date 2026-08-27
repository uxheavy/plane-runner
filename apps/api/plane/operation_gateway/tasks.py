# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Celery workers for durable Operation Gateway publications."""

from __future__ import annotations

from celery import shared_task
from django.db.models import Q
from django.utils import timezone

from plane.db.models import OperationGatewayPublication

from .publications import dispatch_publication_once
from .role_boundary import audited_gateway_boundary


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
    """Requeue each missing/failed/expired intent independently."""

    now = timezone.now()
    publication_ids = list(
        OperationGatewayPublication.objects.filter(
            Q(
                state__in=(
                    OperationGatewayPublication.State.PENDING,
                    OperationGatewayPublication.State.RETRYABLE,
                )
            )
            | Q(state=OperationGatewayPublication.State.RUNNING, lease_until__lt=now)
            | Q(state=OperationGatewayPublication.State.RUNNING, lease_until__isnull=True)
        ).values_list("id", flat=True)
    )
    for publication_id in publication_ids:
        dispatch_publication.delay(str(publication_id))
    return len(publication_ids)
