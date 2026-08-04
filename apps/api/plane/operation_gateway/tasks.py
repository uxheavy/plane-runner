"""Celery workers for durable Operation Gateway publications."""

from __future__ import annotations

from celery import shared_task
from django.db.models import Q
from django.utils import timezone

from plane.db.models import OperationGatewayPublication

from .publications import dispatch_publication_once


@shared_task(bind=True, max_retries=5)
def dispatch_publication(self, publication_id: str) -> None:
    try:
        dispatch_publication_once(publication_id)
    except Exception as error:
        OperationGatewayPublication.objects.filter(pk=publication_id).update(
            state=OperationGatewayPublication.State.FAILED,
            lease_until=None,
            last_error=str(error)[:255],
            updated_at=timezone.now(),
        )
        raise self.retry(exc=error, countdown=min(60 * (self.request.retries + 1), 900)) from error


@shared_task
def reconcile_publications() -> int:
    """Requeue each missing/failed/expired intent independently."""

    now = timezone.now()
    publication_ids = OperationGatewayPublication.objects.filter(
        state__in=(
            OperationGatewayPublication.State.PENDING,
            OperationGatewayPublication.State.FAILED,
        )
    ).values_list("id", flat=True)
    publication_ids = list(publication_ids) + list(
        OperationGatewayPublication.objects.filter(
            state=OperationGatewayPublication.State.RUNNING,
        )
        .filter(Q(lease_until__lt=now) | Q(lease_until__isnull=True))
        .values_list("id", flat=True)
    )
    for publication_id in publication_ids:
        dispatch_publication.delay(str(publication_id))
    return len(publication_ids)
