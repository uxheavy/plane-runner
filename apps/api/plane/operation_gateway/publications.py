"""Durable publication intents and their existing Plane task adapters."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone

from plane.api.serializers import IssueActivitySerializer
from plane.bgtasks.issue_activities_task import issue_activity
from plane.bgtasks.notification_task import notifications
from plane.bgtasks.webhook_task import model_activity
from plane.db.models import IssueActivity, OperationGatewayIdempotency, OperationGatewayPublication, Webhook


PUBLICATION_LEASE_SECONDS = 300


class PublicationDispatchFailure(Exception):
    """A publication could not be completed and should remain retryable."""


def create_publication_intents(
    record: OperationGatewayIdempotency,
    payload: dict[str, Any] | None,
) -> list[OperationGatewayPublication]:
    """Create all required intents in the mutation/receipt transaction."""

    if not payload:
        return []

    publications: list[OperationGatewayPublication] = []
    for kind in (
        OperationGatewayPublication.Kind.ACTIVITY,
        OperationGatewayPublication.Kind.NOTIFICATION,
        OperationGatewayPublication.Kind.WEBHOOK,
    ):
        publication_payload = payload.get(kind)
        if not isinstance(publication_payload, dict):
            raise PublicationDispatchFailure(f"Missing {kind} publication payload")
        publication, _ = OperationGatewayPublication.objects.get_or_create(
            idempotency=record,
            kind=kind,
            defaults={
                "invocation_id": record.invocation_id,
                "publication_key": f"{record.id}:{kind}",
                "payload": publication_payload,
            },
        )
        publications.append(publication)

    return publications


def dispatch_publication_once(publication_id: str) -> None:
    """Run one intent atomically; database effects and the state transition commit together."""

    with transaction.atomic():
        publication = (
            OperationGatewayPublication.objects.select_for_update()
            .select_related("idempotency")
            .get(pk=publication_id)
        )
        now = timezone.now()
        if publication.state == OperationGatewayPublication.State.SUCCEEDED:
            return
        if (
            publication.state == OperationGatewayPublication.State.RUNNING
            and publication.lease_until is not None
            and publication.lease_until > now
        ):
            return

        publication.state = OperationGatewayPublication.State.RUNNING
        publication.attempts += 1
        publication.lease_until = now + timedelta(seconds=PUBLICATION_LEASE_SECONDS)
        publication.last_error = ""
        publication.save(update_fields=["state", "attempts", "lease_until", "last_error", "updated_at"])

        if publication.kind == OperationGatewayPublication.Kind.ACTIVITY:
            _dispatch_activity(publication.payload)
        elif publication.kind == OperationGatewayPublication.Kind.NOTIFICATION:
            _dispatch_notification(publication)
        elif publication.kind == OperationGatewayPublication.Kind.WEBHOOK:
            _dispatch_webhook(publication.payload)
        else:
            raise PublicationDispatchFailure("Unknown publication kind")

        publication.state = OperationGatewayPublication.State.SUCCEEDED
        publication.lease_until = None
        publication.published_at = timezone.now()
        publication.save(update_fields=["state", "lease_until", "published_at", "updated_at"])


def _dispatch_activity(payload: dict[str, Any]) -> None:
    if not payload.get("expected", True):
        return
    if _activity_exists(payload):
        return
    issue_activity.run(
        type=payload["type"],
        requested_data=payload["requested_data"],
        actor_id=payload["actor_id"],
        issue_id=payload["issue_id"],
        project_id=payload["project_id"],
        current_instance=payload["current_instance"],
        epoch=payload["epoch"],
        notification=False,
        origin=payload.get("origin"),
    )
    if not _activity_exists(payload):
        raise PublicationDispatchFailure("Activity task completed without an activity row")


def _dispatch_notification(publication: OperationGatewayPublication) -> None:
    activity_publication = OperationGatewayPublication.objects.get(
        idempotency_id=publication.idempotency_id,
        kind=OperationGatewayPublication.Kind.ACTIVITY,
    )
    if activity_publication.state != OperationGatewayPublication.State.SUCCEEDED:
        dispatch_publication_once(str(activity_publication.id))
        activity_publication.refresh_from_db(fields=["state"])
    if activity_publication.state != OperationGatewayPublication.State.SUCCEEDED:
        raise PublicationDispatchFailure("Activity publication is not resolved")

    payload = publication.payload
    activity_rows = IssueActivity.objects.filter(
        issue_id=payload["issue_id"],
        actor_id=payload["actor_id"],
        field="name",
        old_value=_old_name(payload),
        new_value=_new_name(payload),
        epoch=payload.get("epoch"),
    ).order_by("created_at", "id")
    issue_activities_created = json.dumps(
        IssueActivitySerializer(activity_rows, many=True).data,
        cls=DjangoJSONEncoder,
    )
    notifications.run(
        type=payload["type"],
        issue_id=payload["issue_id"],
        project_id=payload["project_id"],
        actor_id=payload["actor_id"],
        subscriber=payload.get("subscriber", True),
        issue_activities_created=issue_activities_created,
        requested_data=payload["requested_data"],
        current_instance=payload["current_instance"],
    )


def _dispatch_webhook(payload: dict[str, Any]) -> None:
    if not Webhook.objects.filter(
        workspace__slug=payload["slug"],
        is_active=True,
        issue=True,
    ).exists():
        return
    model_activity.run(
        model_name=payload["model_name"],
        model_id=payload["model_id"],
        requested_data=payload["requested_data"],
        current_instance=payload["current_instance"],
        actor_id=payload["actor_id"],
        slug=payload["slug"],
        origin=payload.get("origin"),
    )


def _activity_exists(payload: dict[str, Any]) -> bool:
    if not payload.get("expected", True):
        return True
    return IssueActivity.objects.filter(
        issue_id=payload["issue_id"],
        actor_id=payload["actor_id"],
        field="name",
        old_value=_old_name(payload),
        new_value=_new_name(payload),
        epoch=payload.get("epoch"),
    ).exists()


def _old_name(payload: dict[str, Any]) -> str | None:
    current_instance = json.loads(payload["current_instance"])
    return current_instance.get("name")


def _new_name(payload: dict[str, Any]) -> str | None:
    requested_data = json.loads(payload["requested_data"])
    return requested_data.get("name")


def schedule_publications(publications: list[OperationGatewayPublication]) -> None:
    """Best-effort post-commit dispatch; durable rows are the recovery source."""

    from .tasks import dispatch_publication

    for publication in publications:
        dispatch_publication.delay(str(publication.id))


def schedule_publications_on_commit(record: OperationGatewayIdempotency) -> None:
    publications = list(record.publications.all())
    transaction.on_commit(
        lambda: schedule_publications(publications),
        robust=True,
    )
