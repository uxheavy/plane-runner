# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import hashlib
import hmac
import json
import logging
import re
import uuid
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode

import requests
from typing import Any, Dict, List, Optional, Union

# Third party imports
from celery import shared_task

# Django imports
from django.conf import settings
from django.db.models import Prefetch
from django.core.mail import EmailMultiAlternatives, get_connection
from django.core.serializers.json import DjangoJSONEncoder
from django.template.loader import render_to_string
from django.core.exceptions import ObjectDoesNotExist

# Module imports
from plane.api.serializers import (
    CycleIssueSerializer,
    CycleSerializer,
    IssueCommentSerializer,
    IssueExpandSerializer,
    ModuleIssueSerializer,
    ModuleSerializer,
    ProjectSerializer,
    UserLiteSerializer,
    IntakeIssueSerializer,
)
from plane.db.models import (
    Cycle,
    CycleIssue,
    Issue,
    IssueComment,
    Module,
    ModuleIssue,
    Project,
    User,
    Webhook,
    WebhookLog,
    IntakeIssue,
    IssueLabel,
    IssueAssignee,
)
from plane.license.utils.instance_value import get_email_configuration
from plane.operation_gateway.role_boundary import audited_gateway_boundary
from plane.utils.email import generate_plain_text_from_html
from plane.utils.exception_logger import log_exception
from plane.utils.url_security import pinned_fetch


SERIALIZER_MAPPER = {
    "project": ProjectSerializer,
    "issue": IssueExpandSerializer,
    "cycle": CycleSerializer,
    "module": ModuleSerializer,
    "cycle_issue": CycleIssueSerializer,
    "module_issue": ModuleIssueSerializer,
    "issue_comment": IssueCommentSerializer,
    "user": UserLiteSerializer,
    "intake_issue": IntakeIssueSerializer,
}

MODEL_MAPPER = {
    "project": Project,
    "issue": Issue,
    "cycle": Cycle,
    "module": Module,
    "cycle_issue": CycleIssue,
    "module_issue": ModuleIssue,
    "issue_comment": IssueComment,
    "user": User,
    "intake_issue": IntakeIssue,
}


logger = logging.getLogger("plane.worker")

WEBHOOK_RESPONSE_BODY_LIMIT = 4096
_REDACTED_RESPONSE_VALUE = "[REDACTED]"
_SENSITIVE_RESPONSE_FIELD_PREFIX = re.compile(
    r"(?i)(?P<prefix>[\"']?[a-z0-9_-]*(?:authorization|cookie|password|secret|token|api[_-]?key)[a-z0-9_-]*[\"']?\s*[:=]\s*)"
)


@dataclass(frozen=True)
class WebhookResponseEvidence:
    """Bounded response evidence retained for the durable webhook audit log."""

    prefix: str = ""
    observed_size: int = 0
    size_known: bool = False
    truncated: bool = False
    prefix_sha256: str | None = None


class WebhookResponseReadError(RuntimeError):
    """A streamed response failed after bounded evidence was collected."""

    def __init__(self, cause: Exception, evidence: WebhookResponseEvidence):
        super().__init__(str(cause))
        self.cause = cause
        self.evidence = evidence


def _decode_bounded_prefix(raw_prefix: bytes) -> str:
    """Decode complete UTF-8 characters without exceeding the byte cap."""

    return raw_prefix.decode("utf-8", errors="ignore")


def _redact_response_prefix(raw_prefix: bytes, *, limit: int = WEBHOOK_RESPONSE_BODY_LIMIT) -> str:
    text = _decode_bounded_prefix(raw_prefix)
    redacted = text
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        parsed = None
    if isinstance(parsed, (dict, list)):
        redacted = json.dumps(_redact_structured_response(parsed), ensure_ascii=False, separators=(",", ":"))
    elif "=" in text and not text.lstrip().startswith(("{", "[")):
        pairs = parse_qsl(text, keep_blank_values=True)
        if pairs:
            redacted = urlencode(
                [
                    (key, _REDACTED_RESPONSE_VALUE if _is_sensitive_response_field(key) else value)
                    for key, value in pairs
                ]
            ).replace("%5BREDACTED%5D", _REDACTED_RESPONSE_VALUE)
    else:
        match = _SENSITIVE_RESPONSE_FIELD_PREFIX.search(text)
        if match:
            # A malformed or byte-truncated body is not safe to parse. Once a
            # sensitive field is found, discard the rest of the prefix so a
            # multi-word or partially quoted secret cannot survive redaction.
            redacted = f"{text[:match.end()]}{_REDACTED_RESPONSE_VALUE}"
    encoded = redacted.encode("utf-8")
    if len(encoded) > limit:
        encoded = encoded[:limit]
        redacted = _decode_bounded_prefix(encoded)
    return redacted


def _is_sensitive_response_field(key: Any) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
    return any(marker in normalized for marker in ("authorization", "cookie", "password", "secret", "token", "apikey"))


def _redact_structured_response(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _REDACTED_RESPONSE_VALUE if _is_sensitive_response_field(key) else _redact_structured_response(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_structured_response(item) for item in value]
    return value


def _evidence_from_raw(
    raw_prefix: bytes,
    *,
    observed_size: int,
    size_known: bool,
    truncated: bool,
    limit: int = WEBHOOK_RESPONSE_BODY_LIMIT,
) -> WebhookResponseEvidence:
    return WebhookResponseEvidence(
        prefix=_redact_response_prefix(raw_prefix, limit=limit),
        observed_size=observed_size,
        size_known=size_known,
        truncated=truncated,
        prefix_sha256=hashlib.sha256(raw_prefix).hexdigest(),
    )


@audited_gateway_boundary
def read_bounded_webhook_response(
    response: Any,
    *,
    limit: int = WEBHOOK_RESPONSE_BODY_LIMIT,
) -> WebhookResponseEvidence:
    """Read at most ``limit + 1`` observed bytes without trusting headers.

    The iterator is the only body API used. One extra observed byte
    distinguishes an exact-limit body from a longer body; declared
    ``Content-Length`` is deliberately ignored as untrusted metadata. The
    response is closed on every path.
    """

    if limit <= 0:
        raise ValueError("response limit must be positive")
    raw_prefix = bytearray()
    observed_size = 0
    truncated = False
    natural_end = False
    try:
        iterator = iter(response.iter_content(chunk_size=1))
        while observed_size < limit + 1:
            try:
                chunk = next(iterator)
            except StopIteration:
                natural_end = True
                break
            if not chunk:
                continue
            remaining = limit + 1 - observed_size
            data, has_more = _bounded_chunk_bytes(chunk, remaining)
            if not data and not has_more:
                continue
            observed_size += len(data)
            prefix_remaining = limit - len(raw_prefix)
            if prefix_remaining > 0:
                raw_prefix.extend(data[:prefix_remaining])
            if has_more or observed_size >= limit + 1:
                truncated = True
                break
    except Exception as error:
        evidence = _evidence_from_raw(
            bytes(raw_prefix),
            observed_size=observed_size,
            size_known=False,
            truncated=True,
            limit=limit,
        )
        raise WebhookResponseReadError(error, evidence) from error
    finally:
        try:
            response.close()
        except Exception:
            logger.warning("Failed to close webhook response", exc_info=True)
    return _evidence_from_raw(
        bytes(raw_prefix),
        observed_size=observed_size,
        size_known=natural_end,
        truncated=truncated,
        limit=limit,
    )


def _bounded_chunk_bytes(chunk: Any, limit: int) -> tuple[bytes, bool]:
    """Copy only the bytes needed to determine whether a chunk is too long."""

    if isinstance(chunk, bytes):
        return chunk[:limit], len(chunk) > limit
    if isinstance(chunk, (bytearray, memoryview)):
        return bytes(chunk[:limit]), len(chunk) > limit
    if isinstance(chunk, str):
        encoded = bytearray()
        for character in chunk:
            character_bytes = character.encode("utf-8")
            remaining = limit - len(encoded)
            if remaining <= 0:
                return bytes(encoded), True
            encoded.extend(character_bytes[:remaining])
            if len(character_bytes) > remaining:
                return bytes(encoded), True
        return bytes(encoded), False
    raise TypeError("webhook response chunks must be bytes-like")


@dataclass(frozen=True)
class WebhookDeliveryResult:
    """Durable result of one concrete webhook delivery attempt."""

    state: str
    retryable: bool
    response_status: int | None = None
    response_body: str = ""
    response_body_size: int | None = None
    response_body_size_known: bool = False
    response_body_truncated: bool = False
    response_body_prefix_sha256: str | None = None
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "retryable": self.retryable,
            "response_status": self.response_status,
            "response_body": self.response_body[:WEBHOOK_RESPONSE_BODY_LIMIT],
            "response_body_size": self.response_body_size,
            "response_body_size_known": self.response_body_size_known,
            "response_body_truncated": self.response_body_truncated,
            "response_body_prefix_sha256": self.response_body_prefix_sha256,
            "error": self.error[:255],
        }


@audited_gateway_boundary
def get_issue_prefetches():
    return [
        Prefetch("label_issue", queryset=IssueLabel.objects.select_related("label")),
        Prefetch("issue_assignee", queryset=IssueAssignee.objects.select_related("assignee")),
    ]


@audited_gateway_boundary
def save_webhook_log(
    webhook: Webhook,
    request_method: str,
    request_headers: str,
    request_body: str,
    response_status: str,
    response_headers: str,
    response_body: str | bytes,
    retry_count: int,
    event_type: str,
    delivery_key: str | None = None,
    delivery_state: str | None = None,
    delivery_result: dict[str, Any] | None = None,
    response_body_size: int | None = None,
    response_body_size_known: bool = False,
    response_body_truncated: bool = False,
    response_body_prefix_sha256: str | None = None,
    raise_on_error: bool = False,
) -> None:
    raw_response_body = response_body if isinstance(response_body, bytes) else str(response_body).encode("utf-8")
    response_body_size_known = bool(response_body_size_known and response_body_size is not None)
    bounded_response_body = _redact_response_prefix(raw_response_body[:WEBHOOK_RESPONSE_BODY_LIMIT])
    log_data = {
        "workspace_id": str(webhook.workspace_id),
        "webhook": str(webhook.id),
        "event_type": str(event_type),
        "request_method": str(request_method),
        "request_headers": str(request_headers),
        "request_body": str(request_body),
        "response_status": str(response_status),
        "response_headers": str(response_headers),
        "response_body": bounded_response_body,
        "response_body_size": response_body_size,
        "response_body_size_known": response_body_size_known,
        "response_body_truncated": response_body_truncated,
        # The legacy column name remains for schema compatibility; its value
        # is explicitly a digest of the retained response prefix.
        "response_body_sha256": response_body_prefix_sha256,
        "retry_count": retry_count,
        "delivery_key": delivery_key,
        "delivery_state": delivery_state,
        "delivery_result": delivery_result,
    }

    try:
        if delivery_key:
            log, created = WebhookLog.all_objects.get_or_create(delivery_key=delivery_key, defaults=log_data)
            if not created:
                WebhookLog.all_objects.filter(pk=log.pk).update(
                    **{key: value for key, value in log_data.items() if key != "delivery_key"},
                )
        else:
            WebhookLog.objects.create(**log_data)
        logger.info("Webhook log saved successfully to database")
    except Exception as e:
        log_exception(e, warning=True)
        logger.error(f"Failed to save webhook log: {e}")
        if raise_on_error:
            raise


@audited_gateway_boundary
def deliver_webhook_target(
    *,
    webhook_id: str,
    slug: str,
    event: str,
    event_data: Optional[Dict[str, Any]],
    action: str,
    current_site: str | None,
    activity: Optional[Dict[str, Any]],
    delivery_key: str,
) -> WebhookDeliveryResult:
    """Send one target with a stable key and record its durable result.

    A transport exception is deliberately ``outcome_unknown``. The receiver
    may have observed the request even when the worker did not receive a
    response, so callers must not blindly replay this key.
    """

    try:
        webhook = Webhook.objects.get(id=webhook_id, workspace__slug=slug)
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Autopilot",
            "X-Plane-Delivery": delivery_key,
            "Idempotency-Key": delivery_key,
            "X-Plane-Event": event,
        }
        event_data = json.loads(json.dumps(event_data, cls=DjangoJSONEncoder)) if event_data is not None else None
        activity = json.loads(json.dumps(activity, cls=DjangoJSONEncoder)) if activity is not None else None
        payload = {
            "event": event,
            "action": action,
            "webhook_id": str(webhook.id),
            "workspace_id": str(webhook.workspace_id),
            "workspace_slug": slug,
            "data": event_data,
            "activity": activity,
        }
        if webhook.secret_key:
            signature = hmac.new(
                webhook.secret_key.encode("utf-8"),
                json.dumps(payload).encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            headers["X-Plane-Signature"] = signature
    except ObjectDoesNotExist as error:
        result = WebhookDeliveryResult("failed", False, error=str(error))
        return result
    except Exception as error:
        result = WebhookDeliveryResult("failed", False, error=str(error))
        # No request was attempted, so this is a deterministic pre-send
        # failure. There may be no live Webhook row to attach to.
        webhook = Webhook.objects.filter(pk=webhook_id).first()
        if webhook is not None:
            save_webhook_log(
                webhook=webhook,
                request_method="POST",
                request_headers={},
                request_body={},
                response_status="400",
                response_headers="",
                response_body=str(error),
                retry_count=0,
                event_type=event,
                delivery_key=delivery_key,
                delivery_state=result.state,
                delivery_result=result.as_dict(),
                raise_on_error=True,
            )
        return result

    response = None
    try:
        response = pinned_fetch(
            "POST",
            webhook.url,
            allowed_ips=settings.WEBHOOK_ALLOWED_IPS,
            allowed_hosts=settings.WEBHOOK_ALLOWED_HOSTS,
            headers=headers,
            json=payload,
            timeout=30,
            stream=True,
        )
    except ValueError as error:
        result = WebhookDeliveryResult("failed", False, error=f"Webhook URL rejected: {error}")
        save_webhook_log(
            webhook=webhook,
            request_method="POST",
            request_headers=headers,
            request_body=payload,
            response_status="400",
            response_headers="",
            response_body=result.error,
            retry_count=0,
            event_type=event,
            delivery_key=delivery_key,
            delivery_state=result.state,
            delivery_result=result.as_dict(),
            raise_on_error=True,
        )
        return result
    except requests.RequestException as error:
        result = WebhookDeliveryResult("outcome_unknown", False, error=str(error))
        save_webhook_log(
            webhook=webhook,
            request_method="POST",
            request_headers=headers,
            request_body=payload,
            response_status="unknown",
            response_headers="",
            response_body=str(error),
            retry_count=0,
            event_type=event,
            delivery_key=delivery_key,
            delivery_state=result.state,
            delivery_result=result.as_dict(),
            raise_on_error=True,
        )
        return result

    try:
        evidence = read_bounded_webhook_response(response)
        if 200 <= response.status_code < 300:
            state, retryable = "succeeded", False
        else:
            # A response proves the request reached the receiver. Its
            # application may have performed partial work before returning an
            # error, so the gateway must not blindly replay a non-2xx response.
            state, retryable = "failed", False
        result = WebhookDeliveryResult(
            state,
            retryable,
            response_status=response.status_code,
            response_body=evidence.prefix,
            response_body_size=evidence.observed_size,
            response_body_size_known=evidence.size_known,
            response_body_truncated=evidence.truncated,
            response_body_prefix_sha256=evidence.prefix_sha256,
            error="" if state == "succeeded" else f"Webhook returned HTTP {response.status_code}",
        )
        save_webhook_log(
            webhook=webhook,
            request_method="POST",
            request_headers=headers,
            request_body=payload,
            response_status=response.status_code,
            response_headers=response.headers,
            response_body=evidence.prefix,
            response_body_size=evidence.observed_size,
            response_body_size_known=evidence.size_known,
            response_body_truncated=evidence.truncated,
            response_body_prefix_sha256=evidence.prefix_sha256,
            retry_count=0,
            event_type=event,
            delivery_key=delivery_key,
            delivery_state=result.state,
            delivery_result=result.as_dict(),
            raise_on_error=True,
        )
        return result
    except WebhookResponseReadError as stream_error:
        evidence = stream_error.evidence
        result = WebhookDeliveryResult(
            "outcome_unknown",
            False,
            response_status=getattr(response, "status_code", None),
            response_body=evidence.prefix,
            response_body_size=evidence.observed_size,
            response_body_size_known=evidence.size_known,
            response_body_truncated=evidence.truncated,
            response_body_prefix_sha256=evidence.prefix_sha256,
            error=str(stream_error.cause),
        )
        save_webhook_log(
            webhook=webhook,
            request_method="POST",
            request_headers=headers,
            request_body=payload,
            response_status=getattr(response, "status_code", "unknown"),
            response_headers=getattr(response, "headers", ""),
            response_body=evidence.prefix,
            response_body_size=evidence.observed_size,
            response_body_size_known=evidence.size_known,
            response_body_truncated=evidence.truncated,
            response_body_prefix_sha256=evidence.prefix_sha256,
            retry_count=0,
            event_type=event,
            delivery_key=delivery_key,
            delivery_state=result.state,
            delivery_result=result.as_dict(),
            raise_on_error=True,
        )
        return result
    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                logger.warning("Failed to close webhook response", exc_info=True)


@audited_gateway_boundary
def get_model_data(event: str, event_id: Union[str, List[str]], many: bool = False) -> Dict[str, Any]:
    """
    Retrieve and serialize model data based on the event type.

    Args:
        event (str): The type of event/model to retrieve data for
        event_id (Union[str, List[str]]): The ID or list of IDs of the model instance(s)
        many (bool): Whether to retrieve multiple instances

    Returns:
        Dict[str, Any]: Serialized model data

    Raises:
        ValueError: If serializer is not found for the event
        ObjectDoesNotExist: If model instance is not found
    """
    model = MODEL_MAPPER.get(event)
    if model is None:
        raise ValueError(f"Model not found for event: {event}")

    try:
        if many:
            queryset = model.objects.filter(pk__in=event_id)
        else:
            queryset = model.objects.get(pk=event_id)

        serializer = SERIALIZER_MAPPER.get(event)

        if serializer is None:
            raise ValueError(f"Serializer not found for event: {event}")

        issue_prefetches = get_issue_prefetches()
        if event == "issue":
            if many:
                queryset = queryset.prefetch_related(*issue_prefetches)
            else:
                issue_id = queryset.id
                queryset = model.objects.filter(pk=issue_id).prefetch_related(*issue_prefetches).first()

            return serializer(queryset, many=many, context={"expand": ["labels", "assignees"]}).data
        else:
            return serializer(queryset, many=many).data
    except ObjectDoesNotExist:
        raise ObjectDoesNotExist(f"No {event} found with id: {event_id}")


@shared_task
@audited_gateway_boundary
def send_webhook_deactivation_email(webhook_id: str, receiver_id: str, current_site: str, reason: str) -> None:
    """
    Send an email notification when a webhook is deactivated.

    Args:
        webhook_id (str): ID of the deactivated webhook
        receiver_id (str): ID of the user to receive the notification
        current_site (str): Current site URL
        reason (str): Reason for webhook deactivation
    """
    try:
        (
            EMAIL_HOST,
            EMAIL_HOST_USER,
            EMAIL_HOST_PASSWORD,
            EMAIL_PORT,
            EMAIL_USE_TLS,
            EMAIL_USE_SSL,
            EMAIL_FROM,
        ) = get_email_configuration()

        receiver = User.objects.get(pk=receiver_id)
        webhook = Webhook.objects.get(pk=webhook_id)

        # Get the webhook payload
        subject = "Webhook Deactivated"
        message = f"Webhook {webhook.url} has been deactivated due to failed requests."

        # Send the mail
        context = {
            "email": receiver.email,
            "message": message,
            "webhook_url": f"{current_site}/{str(webhook.workspace.slug)}/settings/webhooks/{str(webhook.id)}",
        }
        html_content = render_to_string("emails/notifications/webhook-deactivate.html", context)
        text_content = generate_plain_text_from_html(html_content)

        # Set the email connection
        connection = get_connection(
            host=EMAIL_HOST,
            port=int(EMAIL_PORT),
            username=EMAIL_HOST_USER,
            password=EMAIL_HOST_PASSWORD,
            use_tls=EMAIL_USE_TLS == "1",
            use_ssl=EMAIL_USE_SSL == "1",
        )

        # Create the email message
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=EMAIL_FROM,
            to=[receiver.email],
            connection=connection,
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send()
        logger.info("Email sent successfully.")
    except Exception as e:
        log_exception(e, warning=True)
        logger.error(f"Failed to send email: {e}")


@shared_task(
    bind=True,
    autoretry_for=(requests.RequestException,),
    retry_backoff=600,
    max_retries=5,
    retry_jitter=True,
)
@audited_gateway_boundary
def webhook_send_task(
    self,
    webhook_id: str,
    slug: str,
    event: str,
    event_data: Optional[Dict[str, Any]],
    action: str,
    current_site: str,
    activity: Optional[Dict[str, Any]],
) -> None:
    """
    Send webhook notifications to configured endpoints.

    Args:
        webhook (str): Webhook ID
        slug (str): Workspace slug
        event (str): Event type
        event_data (Optional[Dict[str, Any]]): Event data to be sent
        action (str): HTTP method/action
        current_site (str): Current site URL
        activity (Optional[Dict[str, Any]]): Activity data
    """
    try:
        webhook = Webhook.objects.get(id=webhook_id, workspace__slug=slug)

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Autopilot",
            "X-Plane-Delivery": str(uuid.uuid4()),
            "X-Plane-Event": event,
        }

        # # Your secret key
        event_data = json.loads(json.dumps(event_data, cls=DjangoJSONEncoder)) if event_data is not None else None

        activity = json.loads(json.dumps(activity, cls=DjangoJSONEncoder)) if activity is not None else None

        action = {
            "POST": "create",
            "PATCH": "update",
            "PUT": "update",
            "DELETE": "delete",
        }.get(action, action)

        payload = {
            "event": event,
            "action": action,
            "webhook_id": str(webhook.id),
            "workspace_id": str(webhook.workspace_id),
            "workspace_slug": slug,
            "data": event_data,
            "activity": activity,
        }

        # Use HMAC for generating signature
        if webhook.secret_key:
            hmac_signature = hmac.new(
                webhook.secret_key.encode("utf-8"),
                json.dumps(payload).encode("utf-8"),
                hashlib.sha256,
            )
            signature = hmac_signature.hexdigest()
            headers["X-Plane-Signature"] = signature
    except Exception as e:
        log_exception(e)
        logger.error(f"Failed to send webhook: {e}")
        return

    response = None
    try:
        # Resolve + validate the webhook URL and pin the connection to the
        # validated IP. Pinning closes the DNS-rebinding TOCTOU (validating the
        # name then letting requests re-resolve it lets an attacker swap in an
        # internal IP between the two lookups). Redirects are never followed, so
        # a 3xx Location cannot bounce the request to an internal address
        # (GHSA-mq87-52pf-hm3h / cluster C).
        response = pinned_fetch(
            "POST",
            webhook.url,
            allowed_ips=settings.WEBHOOK_ALLOWED_IPS,
            allowed_hosts=settings.WEBHOOK_ALLOWED_HOSTS,
            headers=headers,
            json=payload,
            timeout=30,
            stream=True,
        )
        evidence = read_bounded_webhook_response(response)

        # Log the webhook request
        save_webhook_log(
            webhook=webhook,
            request_method=action,
            request_headers=headers,
            request_body=payload,
            response_status=response.status_code,
            response_headers=response.headers,
            response_body=evidence.prefix,
            response_body_size=evidence.observed_size,
            response_body_size_known=evidence.size_known,
            response_body_truncated=evidence.truncated,
            response_body_prefix_sha256=evidence.prefix_sha256,
            retry_count=self.request.retries,
            event_type=event,
        )
        logger.info(f"Webhook {webhook.id} sent successfully")
    except WebhookResponseReadError as e:
        evidence = e.evidence
        save_webhook_log(
            webhook=webhook,
            request_method=action,
            request_headers=headers,
            request_body=payload,
            response_status=getattr(response, "status_code", "unknown"),
            response_headers=getattr(response, "headers", ""),
            response_body=evidence.prefix,
            response_body_size=evidence.observed_size,
            response_body_size_known=evidence.size_known,
            response_body_truncated=evidence.truncated,
            response_body_prefix_sha256=evidence.prefix_sha256,
            retry_count=self.request.retries,
            event_type=event,
        )
        logger.error(f"Webhook {webhook.id} response stream failed: {e}")
        return
    except requests.RequestException as e:
        # Log the failed webhook request
        save_webhook_log(
            webhook=webhook,
            request_method=action,
            request_headers=headers,
            request_body=payload,
            response_status=500,
            response_headers="",
            response_body=str(e),
            retry_count=self.request.retries,
            event_type=event,
        )
        logger.error(f"Webhook {webhook.id} failed with error: {e}")
        # Retry logic
        if self.request.retries >= self.max_retries:
            Webhook.objects.filter(pk=webhook.id).update(is_active=False)
            if webhook:
                # send email for the deactivation of the webhook
                send_webhook_deactivation_email.delay(
                    webhook_id=webhook.id,
                    receiver_id=webhook.created_by_id,
                    reason=str(e),
                    current_site=current_site,
                )
            return
        raise requests.RequestException()

    except ValueError as e:
        # SSRF validation failure (blocked/internal target or unresolvable host).
        # Not retryable — record it so the failure is visible to the admin, but
        # do not raise (no Celery retry) and do not auto-deactivate (the cause
        # may be transient DNS).
        save_webhook_log(
            webhook=webhook,
            request_method=action,
            request_headers=headers,
            request_body=payload,
            response_status=400,
            response_headers="",
            response_body=f"Webhook URL rejected: {e}",
            retry_count=self.request.retries,
            event_type=event,
        )
        logger.warning(f"Webhook {webhook.id} URL rejected: {e}")
        return

    except Exception as e:
        log_exception(e)
        return
    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                logger.warning("Failed to close webhook response", exc_info=True)


@shared_task
@audited_gateway_boundary
def webhook_activity(
    event: str,
    verb: str,
    field: Optional[str],
    old_value: Any,
    new_value: Any,
    actor_id: str | uuid.UUID,
    slug: str,
    current_site: str,
    event_id: str | uuid.UUID,
    old_identifier: Optional[str],
    new_identifier: Optional[str],
) -> None:
    """
    Process and send webhook notifications for various activities in the system.

    This task filters relevant webhooks based on the event type and sends notifications
    to all active webhooks for the workspace.

    Args:
        event (str): Type of event (project, issue, module, cycle, issue_comment)
        verb (str): Action performed (created, updated, deleted)
        field (Optional[str]): Name of the field that was changed
        old_value (Any): Previous value of the field
        new_value (Any): New value of the field
        actor_id (str | uuid.UUID): ID of the user who performed the action
        slug (str): Workspace slug
        current_site (str): Current site URL
        event_id (str | uuid.UUID): ID of the event object
        old_identifier (Optional[str]): Previous identifier if any
        new_identifier (Optional[str]): New identifier if any

    Returns:
        None

    Note:
        The function silently returns on ObjectDoesNotExist exceptions to handle
        race conditions where objects might have been deleted.
    """
    try:
        webhooks = Webhook.objects.filter(workspace__slug=slug, is_active=True)

        if event == "project":
            webhooks = webhooks.filter(project=True)

        if event == "issue":
            webhooks = webhooks.filter(issue=True)

        if event == "module" or event == "module_issue":
            webhooks = webhooks.filter(module=True)

        if event == "cycle" or event == "cycle_issue":
            webhooks = webhooks.filter(cycle=True)

        if event == "issue_comment":
            webhooks = webhooks.filter(issue_comment=True)

        for webhook in webhooks:
            webhook_send_task.delay(
                webhook_id=webhook.id,
                slug=slug,
                event=event,
                event_data=({"id": event_id} if verb == "deleted" else get_model_data(event=event, event_id=event_id)),
                action=verb,
                current_site=current_site,
                activity={
                    "field": field,
                    "new_value": new_value,
                    "old_value": old_value,
                    "actor": get_model_data(event="user", event_id=actor_id),
                    "old_identifier": old_identifier,
                    "new_identifier": new_identifier,
                },
            )
        return
    except Exception as e:
        # Return if a does not exist error occurs
        if isinstance(e, ObjectDoesNotExist):
            return
        if settings.DEBUG:
            print(e)
        log_exception(e)
        return


@shared_task
@audited_gateway_boundary
def model_activity(model_name, model_id, requested_data, current_instance, actor_id, slug, origin=None):
    """Function takes in two json and computes differences between keys of both the json"""
    if current_instance is None:
        webhook_activity.delay(
            event=model_name,
            verb="created",
            field=None,
            old_value=None,
            new_value=None,
            actor_id=actor_id,
            slug=slug,
            current_site=origin,
            event_id=model_id,
            old_identifier=None,
            new_identifier=None,
        )
        return

    # Load the current instance
    current_instance = json.loads(current_instance) if current_instance is not None else None

    # Loop through all keys in requested data and check the current value and requested value
    for key in requested_data:
        # Check if key is present in current instance or not
        if key in current_instance:
            current_value = current_instance.get(key, None)
            requested_value = requested_data.get(key, None)
            if current_value != requested_value:
                webhook_activity.delay(
                    event=model_name,
                    verb="updated",
                    field=key,
                    old_value=current_value,
                    new_value=requested_value,
                    actor_id=actor_id,
                    slug=slug,
                    current_site=origin,
                    event_id=model_id,
                    old_identifier=None,
                    new_identifier=None,
                )

    return
