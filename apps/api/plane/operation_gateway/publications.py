# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Durable, independently retryable Plane publication intents."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone

from plane.api.serializers import IssueActivitySerializer
from plane.bgtasks.issue_activities_task import issue_activity
from plane.bgtasks.notification_task import run_notifications
from plane.bgtasks.webhook_task import (
    WebhookDeliveryResult,
    deliver_webhook_target,
    get_model_data,
    model_activity,
    webhook_activity,
)
from plane.db.models import IssueActivity, OperationGatewayIdempotency, OperationGatewayPublication, Webhook

from .role_boundary import audited_gateway_boundary


PUBLICATION_LEASE_SECONDS = 300
ACTIVITY_NAMESPACE = uuid.UUID("cbf3b03a-6bc3-4b09-89f1-04f3ffdecd38")
MODEL_ACTIVITY_KIND = "model_activity"


class PublicationDispatchFailure(Exception):
    """A publication could not be completed."""

    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class PublicationClaim:
    publication_id: uuid.UUID
    kind: str


@dataclass(frozen=True)
class PreparedWebhookDelivery:
    target_id: str
    slug: str
    event_data: dict[str, Any]
    activity: dict[str, Any]


@audited_gateway_boundary
def activity_id_for_publication(publication_key: str) -> str:
    """Return the deterministic Activity PK for one gateway activity intent."""

    return str(uuid.uuid5(ACTIVITY_NAMESPACE, publication_key))


@audited_gateway_boundary
def create_publication_intents(
    record: OperationGatewayIdempotency,
    payload: dict[str, Any] | None,
    *,
    preserve_webhook_targets: bool = False,
) -> list[OperationGatewayPublication]:
    """Create durable intent rows, one webhook row per concrete target."""

    if not payload:
        return []

    publications: list[OperationGatewayPublication] = []
    model_payload = payload.get("model_activity")
    if isinstance(model_payload, dict):
        kind = MODEL_ACTIVITY_KIND
        publication, _ = OperationGatewayPublication.objects.get_or_create(
            idempotency=record,
            kind=kind,
            target_id=None,
            defaults={
                "invocation_id": record.invocation_id,
                "publication_key": f"{record.id}:{kind}",
                "payload": model_payload,
            },
        )
        publications.append(publication)
    else:
        for kind in (
            OperationGatewayPublication.Kind.ACTIVITY,
            OperationGatewayPublication.Kind.NOTIFICATION,
        ):
            publication_payload = payload.get(kind)
            if not isinstance(publication_payload, dict):
                raise PublicationDispatchFailure(f"Missing {kind} publication payload", retryable=False)
            publication_key = f"{record.id}:{kind}"
            publication, _ = OperationGatewayPublication.objects.get_or_create(
                idempotency=record,
                kind=kind,
                target_id=None,
                defaults={
                    "invocation_id": record.invocation_id,
                    "publication_key": publication_key,
                    "payload": publication_payload,
                },
            )
            changed = False
            if publication_payload.get("deterministic_activity", True):
                expected_activity_id = activity_id_for_publication(f"{record.id}:activity")
                if publication.payload.get("activity_id") != expected_activity_id:
                    publication.payload["activity_id"] = expected_activity_id
                    changed = True
            if changed:
                publication.save(update_fields=["payload", "updated_at"])
            publications.append(publication)

    webhook_payload = payload.get(OperationGatewayPublication.Kind.WEBHOOK)
    if isinstance(model_payload, dict):
        return publications
    if not isinstance(webhook_payload, dict):
        raise PublicationDispatchFailure("Missing webhook publication payload", retryable=False)
    if webhook_payload.get("skip"):
        return publications

    requested_webhook_id = webhook_payload.get("webhook_id")
    existing_target_ids = set(
        OperationGatewayPublication.objects.filter(
            idempotency=record,
            kind=OperationGatewayPublication.Kind.WEBHOOK,
            target_id__isnull=False,
        ).values_list("target_id", flat=True)
    )
    if preserve_webhook_targets:
        # Reconciliation restores the original target set. A webhook added
        # after the mutation must not receive a historical event, and an
        # inactive target remains a durable failed/unknown intent to resolve.
        targets = Webhook.all_objects.filter(pk__in=existing_target_ids).only("id")
    else:
        targets = Webhook.objects.filter(
            workspace_id=record.workspace_id,
            is_active=True,
            issue=True,
        ).only("id")
    if requested_webhook_id:
        targets = targets.filter(pk=requested_webhook_id)

    for webhook in targets:
        target_payload = {**webhook_payload, "webhook_id": str(webhook.id)}
        publication_key = f"{record.id}:webhook:{webhook.id}"
        publication, _ = OperationGatewayPublication.objects.get_or_create(
            idempotency=record,
            kind=OperationGatewayPublication.Kind.WEBHOOK,
            target_id=webhook.id,
            defaults={
                "invocation_id": record.invocation_id,
                "publication_key": publication_key,
                "payload": target_payload,
            },
        )
        publications.append(publication)

    return publications


@audited_gateway_boundary
def dispatch_publication_once(publication_id: str) -> None:
    """Claim and dispatch one intent without holding a DB transaction over HTTP."""

    claim = _claim_publication(publication_id)
    if claim is None:
        return

    if claim.kind == OperationGatewayPublication.Kind.WEBHOOK:
        _dispatch_external_publication(claim)
        return

    try:
        with transaction.atomic():
            publication = (
                OperationGatewayPublication.objects.select_for_update()
                .select_related("idempotency")
                .get(pk=claim.publication_id)
            )
            if publication.state != OperationGatewayPublication.State.RUNNING:
                return
            if publication.kind == OperationGatewayPublication.Kind.ACTIVITY:
                activity_ids = _dispatch_activity(publication.payload)
                if activity_ids:
                    publication.payload["activity_ids"] = activity_ids[:32]
            elif publication.kind == OperationGatewayPublication.Kind.NOTIFICATION:
                _dispatch_notification(publication)
            elif publication.kind == MODEL_ACTIVITY_KIND:
                _dispatch_model_activity(publication.payload)
            else:
                raise PublicationDispatchFailure("Unknown publication kind", retryable=False)
            publication.state = OperationGatewayPublication.State.SUCCEEDED
            publication.dispatch_started = False
            publication.lease_until = None
            publication.published_at = timezone.now()
            publication.delivery_result = {"state": OperationGatewayPublication.State.SUCCEEDED}
            publication.save(
                update_fields=[
                    "state",
                    "dispatch_started",
                    "lease_until",
                    "published_at",
                    "delivery_result",
                    "payload",
                    "updated_at",
                ]
            )
    except Exception as error:
        _record_dispatch_failure(claim.publication_id, error)
        raise


def _claim_publication(publication_id: str) -> PublicationClaim | None:
    with transaction.atomic():
        publication = OperationGatewayPublication.objects.select_for_update().get(pk=publication_id)
        now = timezone.now()
        if publication.state in (
            OperationGatewayPublication.State.SUCCEEDED,
            OperationGatewayPublication.State.FAILED,
            OperationGatewayPublication.State.OUTCOME_UNKNOWN,
        ):
            return None
        if publication.state == OperationGatewayPublication.State.RUNNING:
            queued = publication.delivery_result == {"state": "queued"}
            if not queued and publication.lease_until is not None and publication.lease_until > now:
                return None
            if not queued and publication.dispatch_started:
                publication.state = OperationGatewayPublication.State.OUTCOME_UNKNOWN
                publication.lease_until = None
                publication.last_error = "Worker lease expired after external delivery began"
                publication.delivery_result = {
                    "state": OperationGatewayPublication.State.OUTCOME_UNKNOWN,
                    "reason": "worker_lease_expired_after_dispatch_started",
                }
                publication.save(update_fields=["state", "lease_until", "last_error", "delivery_result", "updated_at"])
                return None

        publication.state = OperationGatewayPublication.State.RUNNING
        publication.attempts += 1
        publication.dispatch_started = False
        publication.lease_until = now + timedelta(seconds=PUBLICATION_LEASE_SECONDS)
        publication.last_error = ""
        publication.delivery_result = None
        publication.save(
            update_fields=[
                "state",
                "attempts",
                "dispatch_started",
                "lease_until",
                "last_error",
                "delivery_result",
                "updated_at",
            ]
        )
        return PublicationClaim(publication_id=publication.id, kind=publication.kind)


def _dispatch_external_publication(claim: PublicationClaim) -> None:
    started = False
    try:
        publication = OperationGatewayPublication.objects.select_related("idempotency").get(pk=claim.publication_id)
        prepared = _prepare_webhook(publication)
        # Preparation is deterministic local work. Commit the marker only
        # immediately before the adapter can issue the external request.
        _mark_dispatch_started(claim.publication_id)
        started = True
        result = _dispatch_webhook(publication, prepared)
    except Exception as error:
        if started:
            _mark_outcome_unknown(claim.publication_id, str(error))
        else:
            _record_dispatch_failure(claim.publication_id, error)
        raise

    _finalize_external_publication(claim.publication_id, result)


def _mark_dispatch_started(publication_id: uuid.UUID) -> None:
    with transaction.atomic():
        publication = OperationGatewayPublication.objects.select_for_update().get(pk=publication_id)
        if publication.state != OperationGatewayPublication.State.RUNNING:
            raise PublicationDispatchFailure("Publication is no longer running", retryable=False)
        publication.dispatch_started = True
        publication.save(update_fields=["dispatch_started", "updated_at"])


def _finalize_external_publication(publication_id: uuid.UUID, result: WebhookDeliveryResult) -> None:
    with transaction.atomic():
        publication = OperationGatewayPublication.objects.select_for_update().get(pk=publication_id)
        if publication.state != OperationGatewayPublication.State.RUNNING:
            return
        publication.state = result.state
        publication.dispatch_started = True
        publication.lease_until = None
        publication.published_at = (
            timezone.now() if result.state == OperationGatewayPublication.State.SUCCEEDED else None
        )
        publication.last_error = result.error[:255] if result.error else ""
        publication.delivery_result = result.as_dict()
        publication.save(
            update_fields=[
                "state",
                "dispatch_started",
                "lease_until",
                "published_at",
                "last_error",
                "delivery_result",
                "updated_at",
            ]
        )


def _record_dispatch_failure(publication_id: uuid.UUID, error: Exception) -> None:
    retryable = getattr(error, "retryable", True)
    state = OperationGatewayPublication.State.RETRYABLE if retryable else OperationGatewayPublication.State.FAILED
    with transaction.atomic():
        publication = OperationGatewayPublication.objects.select_for_update().get(pk=publication_id)
        if publication.state not in (
            OperationGatewayPublication.State.SUCCEEDED,
            OperationGatewayPublication.State.OUTCOME_UNKNOWN,
        ):
            publication.state = state
            publication.dispatch_started = False
            publication.lease_until = None
            publication.last_error = str(error)[:255]
            publication.delivery_result = {"state": state, "error": str(error)[:255]}
            publication.save(
                update_fields=[
                    "state",
                    "dispatch_started",
                    "lease_until",
                    "last_error",
                    "delivery_result",
                    "updated_at",
                ]
            )


def _mark_outcome_unknown(publication_id: uuid.UUID, reason: str) -> None:
    with transaction.atomic():
        publication = OperationGatewayPublication.objects.select_for_update().get(pk=publication_id)
        if publication.state in (
            OperationGatewayPublication.State.SUCCEEDED,
            OperationGatewayPublication.State.OUTCOME_UNKNOWN,
        ):
            return
        publication.state = OperationGatewayPublication.State.OUTCOME_UNKNOWN
        publication.lease_until = None
        publication.dispatch_started = True
        publication.last_error = reason[:255]
        publication.delivery_result = {
            "state": OperationGatewayPublication.State.OUTCOME_UNKNOWN,
            "reason": reason[:255],
        }
        publication.save(
            update_fields=["state", "lease_until", "dispatch_started", "last_error", "delivery_result", "updated_at"]
        )


def _dispatch_activity(payload: dict[str, Any]) -> list[str]:
    if not payload.get("expected", True):
        return []
    activity_id = payload.get("activity_id")
    if (
        activity_id
        and IssueActivity.objects.filter(
            pk=activity_id,
            issue_id=payload["issue_id"],
            actor_id=payload["actor_id"],
        ).exists()
    ):
        return [str(activity_id)]
    created_ids = issue_activity.run(
        type=payload["type"],
        requested_data=payload["requested_data"],
        actor_id=payload["actor_id"],
        issue_id=payload["issue_id"],
        project_id=payload["project_id"],
        current_instance=payload["current_instance"],
        epoch=payload.get("epoch"),
        notification=False,
        origin=payload.get("origin"),
        activity_id=activity_id,
        raise_on_error=True,
    )
    if activity_id:
        if not IssueActivity.objects.filter(
            pk=activity_id,
            issue_id=payload["issue_id"],
            actor_id=payload["actor_id"],
        ).exists():
            raise PublicationDispatchFailure("Activity task completed without its durable activity row")
    if not created_ids:
        raise PublicationDispatchFailure("Activity task completed without an activity row")
    return created_ids


def _dispatch_model_activity(payload: dict[str, Any]) -> None:
    if payload.get("deleted"):
        webhook_activity.run(
            event=payload["model_name"],
            verb="deleted",
            field=None,
            old_value=None,
            new_value=None,
            actor_id=payload["actor_id"],
            slug=payload["slug"],
            current_site=payload.get("origin"),
            event_id=payload["model_id"],
            old_identifier=None,
            new_identifier=None,
        )
        return
    model_activity.run(
        model_name=payload["model_name"],
        model_id=payload["model_id"],
        requested_data=payload.get("requested_data") or {},
        current_instance=payload.get("current_instance"),
        actor_id=payload["actor_id"],
        slug=payload["slug"],
        origin=payload.get("origin"),
    )


def _dispatch_notification(publication: OperationGatewayPublication) -> None:
    if publication.payload.get("skip"):
        return
    activity_publication = OperationGatewayPublication.objects.get(
        idempotency_id=publication.idempotency_id,
        kind=OperationGatewayPublication.Kind.ACTIVITY,
        target_id__isnull=True,
    )
    if activity_publication.state != OperationGatewayPublication.State.SUCCEEDED:
        dispatch_publication_once(str(activity_publication.id))
        activity_publication.refresh_from_db(fields=["state", "payload"])
    if activity_publication.state != OperationGatewayPublication.State.SUCCEEDED:
        raise PublicationDispatchFailure("Activity publication is not resolved")

    payload = publication.payload
    activity_ids = payload.get("activity_ids") or activity_publication.payload.get("activity_ids")
    activity_id = payload.get("activity_id") or activity_publication.payload.get("activity_id")
    if activity_ids:
        activity_queryset = IssueActivity.objects.filter(
            pk__in=activity_ids,
            issue_id=payload["issue_id"],
            actor_id=payload["actor_id"],
        )
        activities = list(activity_queryset)
    elif activity_id:
        activities = list(
            IssueActivity.objects.filter(
                pk=activity_id,
                issue_id=payload["issue_id"],
                actor_id=payload["actor_id"],
                field="name",
            )
        )
    else:
        raise PublicationDispatchFailure("Notification intent has no activity identity", retryable=False)
    if not activities:
        raise PublicationDispatchFailure("Notification activity is missing", retryable=False)
    activity_data = json.dumps(
        IssueActivitySerializer(activities, many=True).data,
        cls=DjangoJSONEncoder,
    )
    try:
        run_notifications(
            type=payload["type"],
            issue_id=payload["issue_id"],
            project_id=payload["project_id"],
            actor_id=payload["actor_id"],
            subscriber=payload.get("subscriber", True),
            issue_activities_created=activity_data,
            requested_data=payload["requested_data"],
            current_instance=payload["current_instance"],
            idempotency_key=publication.publication_key,
            activity_id=str(activities[0].id),
        )
    except Exception as error:
        raise PublicationDispatchFailure(str(error)) from error


def _prepare_webhook(publication: OperationGatewayPublication) -> PreparedWebhookDelivery:
    payload = publication.payload
    target_id = payload.get("webhook_id") or publication.target_id
    if not target_id:
        raise PublicationDispatchFailure("Webhook publication has no concrete target", retryable=False)
    try:
        current_instance = json.loads(payload["current_instance"])
        requested_data = payload["requested_data"]
        if not isinstance(requested_data, dict):
            raise ValueError("Webhook requested data is not an object")
        event_data = get_model_data("issue", payload["model_id"])
        actor = get_model_data("user", payload["actor_id"])
    except ObjectDoesNotExist as error:
        raise PublicationDispatchFailure(str(error), retryable=False) from error
    except (KeyError, TypeError, ValueError) as error:
        raise PublicationDispatchFailure(str(error), retryable=False) from error
    return PreparedWebhookDelivery(
        target_id=str(target_id),
        slug=payload["slug"],
        event_data=event_data,
        activity={
            "field": "name",
            "new_value": requested_data.get("name"),
            "old_value": current_instance.get("name"),
            "actor": actor,
            "old_identifier": None,
            "new_identifier": None,
        },
    )


def _dispatch_webhook(
    publication: OperationGatewayPublication,
    prepared: PreparedWebhookDelivery,
) -> WebhookDeliveryResult:
    return deliver_webhook_target(
        webhook_id=prepared.target_id,
        slug=prepared.slug,
        event="issue",
        event_data=prepared.event_data,
        action="updated",
        current_site=publication.payload.get("origin"),
        activity=prepared.activity,
        delivery_key=publication.publication_key,
    )


@audited_gateway_boundary
def schedule_publications(publications: list[OperationGatewayPublication]) -> None:
    """Best-effort post-commit dispatch; durable rows are the recovery source."""

    from .tasks import dispatch_publication

    for publication in publications:
        dispatch_publication.delay(str(publication.id))


@audited_gateway_boundary
def schedule_publications_on_commit(record: OperationGatewayIdempotency) -> None:
    publications = list(record.publications.all())
    transaction.on_commit(
        lambda: schedule_publications(publications),
        robust=True,
    )
