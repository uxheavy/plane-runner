"""Authorization, idempotency, bounded execution, and audit for gateway calls."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder
from django.db import DatabaseError, IntegrityError, transaction
from django.utils import timezone

from plane.api.views.issue import IssueDetailAPIEndpoint
from plane.api.serializers import IssueSerializer
from plane.api.serializers.user import UserLiteSerializer
from plane.app.permissions import ProjectEntityPermission
from plane.db.models import (
    Issue,
    OperationGatewayAudit,
    OperationGatewayIdempotency,
    OperationGatewayPublication,
    Workspace,
)

from .catalog import OperationDescriptor, get_operation
from .contracts import (
    GatewayError,
    GatewayEnvelope,
    GatewayFailureEnvelope,
    GatewaySuccessEnvelope,
    MAX_INPUT_BYTES,
    MAX_RESPONSE_BYTES,
    MAX_RESULT_BYTES,
    SCHEMA_VERSION,
    AttachmentListInputSerializer,
    AttachmentReadInputSerializer,
    AttachmentUploadFromUrlInputSerializer,
    EmptyOperationInputSerializer,
    WorkItemReadInputSerializer,
    WorkItemRenameInputSerializer,
    canonical_json,
)
from .publications import (
    activity_id_for_publication,
    create_publication_intents,
    dispatch_publication_once,
    schedule_publications_on_commit,
)
from .role_boundary import audited_gateway_boundary
from .mcp.attachments import AttachmentFailure, WorkItemAttachmentService, _assert_issue_permission
from .work_items import WorkItemRenameFailure, WorkItemRenameOutcome, WorkItemRenameService

READ_RESULT_FIELDS = ("id", "name", "sequence_id", "priority", "state", "project", "workspace")

ERROR_MESSAGES = {
    "AUTHENTICATION_REQUIRED": "Authentication is required for this operation.",
    "AUTHORIZATION_UNAVAILABLE": "Authorization could not be evaluated.",
    "ATTACHMENT_CONTENT_UNSUPPORTED": "This attachment content type cannot be read.",
    "ATTACHMENT_NOT_FOUND": "The attachment could not be found.",
    "ATTACHMENT_TOO_LARGE": "The attachment exceeds the size limit.",
    "EXTERNAL_SOURCE_REJECTED": "The external attachment source was rejected.",
    "IDEMPOTENCY_CONFLICT": "The idempotency key was already used for another request.",
    "INTERNAL_ERROR": "The operation could not be completed.",
    "NOT_AUTHORIZED": "Operation is not authorized for this caller.",
    "OPERATION_REJECTED": "The operation could not be completed.",
    "OPERATION_UNAVAILABLE": "The operation could not be completed.",
    "OUTCOME_UNKNOWN": "The operation outcome cannot be safely determined.",
    "PLANE_CONFLICT": "Plane rejected the operation.",
    "PLANE_VALIDATION_ERROR": "Plane rejected the operation.",
    "REQUEST_TOO_LARGE": "The operation request exceeds its size limit.",
    "RESULT_TOO_LARGE": "The operation result exceeded its limit.",
    "THROTTLED": "Too many operation requests.",
    "UNKNOWN_OPERATION": "Operation is not available.",
    "UPSTREAM_FAILURE": "The operation could not be completed.",
    "VALIDATION_ERROR": "Operation request is invalid.",
}


class GatewayFailure(Exception):
    """A bounded failure that is safe to expose through the gateway contract."""

    def __init__(self, code: str, http_status: int, retryable: bool, ambiguous: bool = False):
        super().__init__(code)
        self.code = code
        self.http_status = http_status
        self.retryable = retryable
        self.ambiguous = ambiguous


class RetryRunningAttempt(Exception):
    """The first-use row is fresh; let its owner finish before replaying."""


@dataclass(frozen=True)
class AttemptDecision:
    workspace: Workspace
    record: OperationGatewayIdempotency | None
    response: tuple[GatewayEnvelope, int] | None = None


class GatewayServiceRequest:
    """Minimal request adapter required by the existing read and permission code."""

    def __init__(self, request: Any, *, method: str, data: dict[str, Any] | None = None):
        self.user = request.user
        self.method = method
        self.data = data or {}
        self.GET = {"fields": ",".join(READ_RESULT_FIELDS)} if method == "GET" else {}
        self.META = request.META


class OperationGateway:
    """One deep application boundary for the initial gateway vertical slice."""

    @audited_gateway_boundary
    def execute(self, request: Any, envelope: dict[str, Any]) -> tuple[GatewayEnvelope, int]:
        caller_id = str(request.user.id)
        operation_id = envelope["operation_id"]
        workspace_slug = envelope["workspace_slug"]
        descriptor = get_operation(operation_id)
        if descriptor is None:
            return self._record_unkeyed_failure(
                operation_id=operation_id,
                workspace_slug=workspace_slug,
                idempotency_key=envelope["idempotency_key"],
                correlation_id=envelope["correlation_id"],
                caller_id=caller_id,
                workspace_id=self._workspace_id(workspace_slug),
                request_digest=self._digest_for_raw(envelope),
                failure=GatewayFailure("UNKNOWN_OPERATION", 404, False),
            )

        parsed_input, input_failure = self._parse_operation_input(descriptor, envelope["input"])
        if input_failure is not None:
            return self._record_unkeyed_failure(
                operation_id=descriptor.operation_id,
                workspace_slug=workspace_slug,
                idempotency_key=envelope["idempotency_key"],
                correlation_id=envelope["correlation_id"],
                caller_id=caller_id,
                workspace_id=self._workspace_id(workspace_slug),
                request_digest=self._digest_for_raw(envelope),
                failure=input_failure,
            )

        workspace = Workspace.objects.filter(slug=workspace_slug).first()
        if workspace is None:
            return self._record_unkeyed_failure(
                operation_id=descriptor.operation_id,
                workspace_slug=workspace_slug,
                idempotency_key=envelope["idempotency_key"],
                correlation_id=envelope["correlation_id"],
                caller_id=caller_id,
                workspace_id=None,
                request_digest=self._digest_for_raw(envelope),
                failure=GatewayFailure("OPERATION_REJECTED", 400, False),
            )

        request_digest = self._request_digest(
            workspace_id=workspace.id,
            caller_id=caller_id,
            descriptor=descriptor,
            idempotency_key=envelope["idempotency_key"],
            parsed_input=parsed_input,
        )
        decision = self._begin_attempt(
            workspace=workspace,
            descriptor=descriptor,
            idempotency_key=envelope["idempotency_key"],
            correlation_id=envelope["correlation_id"],
            caller_id=caller_id,
            request_digest=request_digest,
            parsed_input=parsed_input,
        )
        if decision.response is not None:
            return decision.response
        return self._run_attempt(
            request=request,
            workspace=workspace,
            descriptor=descriptor,
            record=decision.record,
            parsed_input=parsed_input,
            request_digest=request_digest,
            caller_id=caller_id,
        )

    def unauthenticated_response(self, raw_data: Any, *, code: str = "AUTHENTICATION_REQUIRED", status_code: int = 401):
        data = raw_data if isinstance(raw_data, dict) else {}
        return self._direct_failure_envelope(
            operation_id=self._wire_text(data.get("operation_id"), "unknown", 128),
            workspace_slug=self._wire_text(data.get("workspace_slug"), "unknown", 255),
            caller_id="anonymous",
            request_id=uuid.uuid4(),
            idempotency_key=self._wire_text(data.get("idempotency_key"), "unbound", 128),
            correlation_id=self._wire_text(data.get("correlation_id"), str(uuid.uuid4()), 128),
            audit_receipt=None,
            error=GatewayFailure(code, status_code, False),
            replayed=False,
            status_code=status_code,
        )

    @audited_gateway_boundary
    def record_invalid_request(
        self,
        request: Any,
        raw_data: Any,
        *,
        code: str = "VALIDATION_ERROR",
        status_code: int | None = None,
    ):
        """Persist an authenticated malformed attempt before returning its bounded error."""

        data = raw_data if isinstance(raw_data, dict) else {}
        operation_id = self._wire_text(data.get("operation_id"), "unknown", 128)
        workspace_slug = self._wire_text(data.get("workspace_slug"), "unknown", 255)
        idempotency_key = self._wire_text(data.get("idempotency_key"), "unbound", 128)
        correlation_id = self._wire_text(data.get("correlation_id"), str(uuid.uuid4()), 128)
        workspace_id = self._workspace_id(workspace_slug)
        return self._record_unkeyed_failure(
            operation_id=operation_id,
            workspace_slug=workspace_slug,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            caller_id=str(request.user.id),
            workspace_id=workspace_id,
            request_digest=self._digest_for_raw(raw_data),
            failure=GatewayFailure(code, status_code or (413 if code == "REQUEST_TOO_LARGE" else 400), False),
        )

    @audited_gateway_boundary
    def reconcile(self, idempotency_id: uuid.UUID) -> tuple[GatewayEnvelope, int]:
        """Restore and dispatch every publication before resolving the operation."""

        with transaction.atomic():
            record = OperationGatewayIdempotency.objects.select_for_update().get(pk=idempotency_id)
            descriptor = get_operation(record.operation_id)
            if descriptor is None:
                return self._direct_unknown(record)
            if descriptor.operation_id != "work_item.rename" or not record.workspace_id or record.result is None:
                return self._reconcile_unknown_locked(record, descriptor)
            input_data = record.request_input or {}
            issue = Issue.objects.filter(
                workspace_id=record.workspace_id,
                project_id=input_data.get("project_id"),
                pk=input_data.get("issue_id"),
            ).first()
            if issue is None or issue.name != input_data.get("name"):
                return self._reconcile_unknown_locked(record, descriptor)
            self._restore_publications(record, issue)
            publications = list(record.publications.all())

        for publication in publications:
            try:
                dispatch_publication_once(str(publication.id))
            except Exception:
                # The intent remains durable and independently retryable.
                continue

        with transaction.atomic():
            record = OperationGatewayIdempotency.objects.select_for_update().get(pk=idempotency_id)
            descriptor = get_operation(record.operation_id)
            publications = list(record.publications.all())
            if not publications or any(
                publication.state != OperationGatewayPublication.State.SUCCEEDED for publication in publications
            ):
                return self._reconcile_unknown_locked(record, descriptor)
            audit_id = record.audit_receipt
            if record.state != OperationGatewayIdempotency.State.SUCCEEDED:
                audit = self._write_audit(
                    phase=OperationGatewayAudit.Phase.OUTCOME,
                    outcome=OperationGatewayAudit.Outcome.SUCCESS,
                    descriptor=descriptor,
                    record=record,
                    result=record.result,
                    error=None,
                )
                record.state = OperationGatewayIdempotency.State.SUCCEEDED
                record.retryable = False
                record.error = None
                record.audit_receipt = audit.id
                record.save(update_fields=["state", "retryable", "error", "audit_receipt", "updated_at"])
                audit_id = audit.id
            return self._success_envelope(
                record,
                descriptor,
                record.workspace_slug,
                str(record.caller_id),
                audit_id,
                record.result,
                True,
            ), 200

    def _begin_attempt(
        self,
        *,
        workspace: Workspace,
        descriptor: OperationDescriptor,
        idempotency_key: str,
        correlation_id: str,
        caller_id: str,
        request_digest: str,
        parsed_input: dict[str, Any],
    ) -> AttemptDecision:
        deadline = time.monotonic() + 30
        while True:
            try:
                return self._begin_attempt_once(
                    workspace=workspace,
                    descriptor=descriptor,
                    idempotency_key=idempotency_key,
                    correlation_id=correlation_id,
                    caller_id=caller_id,
                    request_digest=request_digest,
                    parsed_input=parsed_input,
                )
            except RetryRunningAttempt:
                if time.monotonic() >= deadline:
                    return self._begin_attempt_once(
                        workspace=workspace,
                        descriptor=descriptor,
                        idempotency_key=idempotency_key,
                        correlation_id=correlation_id,
                        caller_id=caller_id,
                        request_digest=request_digest,
                        parsed_input=parsed_input,
                        allow_running_unknown=True,
                    )
                time.sleep(0.01)

    def _restore_publications(self, record: OperationGatewayIdempotency, issue: Issue) -> None:
        """Rebuild missing post-commit intents from the durable terminal receipt."""

        input_data = record.request_input or {}
        current_instance = json.dumps(IssueSerializer(issue).data, cls=DjangoJSONEncoder)
        requested_data = json.dumps({"name": input_data.get("name")}, cls=DjangoJSONEncoder)
        payload = {
            "activity": {
                "type": "issue.activity.updated",
                "requested_data": requested_data,
                "actor_id": str(record.caller_id),
                "issue_id": str(issue.id),
                "project_id": str(issue.project_id),
                "current_instance": current_instance,
                "epoch": record.updated_at.timestamp(),
                "activity_id": activity_id_for_publication(f"{record.id}:activity"),
                "origin": None,
                "expected": True,
            },
            "notification": {
                "type": "issue.activity.updated",
                "issue_id": str(issue.id),
                "project_id": str(issue.project_id),
                "actor_id": str(record.caller_id),
                "subscriber": True,
                "requested_data": requested_data,
                "current_instance": current_instance,
                "activity_id": activity_id_for_publication(f"{record.id}:activity"),
            },
            "webhook": {
                "model_name": "issue",
                "model_id": str(issue.id),
                "requested_data": {"name": input_data.get("name")},
                "current_instance": current_instance,
                "actor_id": str(record.caller_id),
                "slug": record.workspace_slug,
                "origin": None,
            },
        }
        create_publication_intents(record, payload, preserve_webhook_targets=True)

    def _begin_attempt_once(
        self,
        *,
        workspace: Workspace,
        descriptor: OperationDescriptor,
        idempotency_key: str,
        correlation_id: str,
        caller_id: str,
        request_digest: str,
        parsed_input: dict[str, Any],
        allow_running_unknown: bool = False,
    ) -> AttemptDecision:
        with transaction.atomic():
            query = OperationGatewayIdempotency.objects.select_for_update()
            try:
                record = query.get(
                    workspace_id=workspace.id,
                    caller_id=caller_id,
                    operation_id=descriptor.operation_id,
                    idempotency_key=idempotency_key,
                )
                created = False
            except OperationGatewayIdempotency.DoesNotExist:
                try:
                    with transaction.atomic():
                        record = OperationGatewayIdempotency.objects.create(
                            request_id=uuid.uuid4(),
                            invocation_id=uuid.uuid4(),
                            operation_id=descriptor.operation_id,
                            workspace_id=workspace.id,
                            workspace_slug=workspace.slug,
                            caller_id=caller_id,
                            idempotency_key=idempotency_key,
                            correlation_id=correlation_id,
                            request_digest=request_digest,
                            state=OperationGatewayIdempotency.State.RUNNING,
                            request_input=parsed_input,
                        )
                    created = True
                except IntegrityError:
                    record = query.get(
                        workspace_id=workspace.id,
                        caller_id=caller_id,
                        operation_id=descriptor.operation_id,
                        idempotency_key=idempotency_key,
                    )
                    created = False

            if created:
                self._write_audit(
                    phase=OperationGatewayAudit.Phase.INTENT,
                    outcome=OperationGatewayAudit.Outcome.INTENT,
                    descriptor=descriptor,
                    record=record,
                    result=None,
                    error=None,
                )
                return AttemptDecision(workspace=workspace, record=record)

            if record.request_digest != request_digest:
                conflict_request_id = uuid.uuid4()
                audit = self._write_invocation_pair(
                    record=record,
                    correlation_id=correlation_id,
                    request_digest=request_digest,
                    invocation_id=uuid.uuid4(),
                    request_id=conflict_request_id,
                    outcome=OperationGatewayAudit.Outcome.DENIED,
                    error=GatewayFailure("IDEMPOTENCY_CONFLICT", 409, False),
                )
                return AttemptDecision(
                    workspace=workspace,
                    record=None,
                    response=self._direct_failure_envelope(
                        operation_id=descriptor.operation_id,
                        workspace_slug=workspace.slug,
                        caller_id=caller_id,
                        request_id=conflict_request_id,
                        idempotency_key=idempotency_key,
                        correlation_id=correlation_id,
                        audit_receipt=audit.id,
                        error=GatewayFailure("IDEMPOTENCY_CONFLICT", 409, False),
                        replayed=False,
                        status_code=409,
                    ),
                )

            if record.state in (
                OperationGatewayIdempotency.State.RUNNING,
                OperationGatewayIdempotency.State.PENDING,
            ):
                if (
                    record.state == OperationGatewayIdempotency.State.RUNNING
                    and not allow_running_unknown
                    and record.updated_at > timezone.now() - timedelta(seconds=30)
                ):
                    raise RetryRunningAttempt
                audit = self._write_invocation_pair(
                    record=record,
                    correlation_id=correlation_id,
                    request_digest=request_digest,
                    invocation_id=uuid.uuid4(),
                    request_id=uuid.uuid4(),
                    outcome=OperationGatewayAudit.Outcome.OUTCOME_UNKNOWN,
                    error=GatewayFailure("OUTCOME_UNKNOWN", 409, False),
                )
                error = self._error("OUTCOME_UNKNOWN", False)
                return AttemptDecision(
                    workspace=workspace,
                    record=None,
                    response=(
                        self._failure_envelope(
                            record,
                            descriptor,
                            workspace.slug,
                            caller_id,
                            audit.id,
                            error,
                            True,
                            request_id=audit.request_id,
                            correlation_id=audit.correlation_id,
                        ),
                        409,
                    ),
                )

            if record.state == OperationGatewayIdempotency.State.FAILED_PRECOMMIT and record.retryable:
                record.request_id = uuid.uuid4()
                record.invocation_id = uuid.uuid4()
                record.correlation_id = correlation_id
                record.request_digest = request_digest
                record.request_input = parsed_input
                record.state = OperationGatewayIdempotency.State.RUNNING
                record.result = None
                record.error = None
                record.audit_receipt = None
                record.retryable = False
                record.save(
                    update_fields=[
                        "request_id",
                        "invocation_id",
                        "correlation_id",
                        "request_digest",
                        "request_input",
                        "state",
                        "result",
                        "error",
                        "audit_receipt",
                        "retryable",
                        "updated_at",
                    ]
                )
                self._write_audit(
                    phase=OperationGatewayAudit.Phase.INTENT,
                    outcome=OperationGatewayAudit.Outcome.INTENT,
                    descriptor=descriptor,
                    record=record,
                    result=None,
                    error=None,
                )
                return AttemptDecision(workspace=workspace, record=record)

            replay_audit = self._write_invocation_pair(
                record=record,
                correlation_id=correlation_id,
                request_digest=request_digest,
                invocation_id=uuid.uuid4(),
                request_id=uuid.uuid4(),
                outcome=OperationGatewayAudit.Outcome.REPLAY,
                result=record.result,
                error=self._failure_from_record(record),
            )
            return AttemptDecision(
                workspace=workspace,
                record=None,
                response=self._replay_terminal(record, descriptor, workspace.slug, caller_id, replay_audit),
            )

    def _run_attempt(
        self,
        *,
        request: Any,
        workspace: Workspace,
        descriptor: OperationDescriptor,
        record: OperationGatewayIdempotency | None,
        parsed_input: dict[str, Any],
        request_digest: str,
        caller_id: str,
    ) -> tuple[GatewayEnvelope, int]:
        if record is None:
            raise RuntimeError("Gateway execution requires an idempotency record")
        try:
            with transaction.atomic():
                record = OperationGatewayIdempotency.objects.select_for_update().get(pk=record.id)
                if record.state not in (
                    OperationGatewayIdempotency.State.RUNNING,
                    OperationGatewayIdempotency.State.PENDING,
                ):
                    error = self._error("OUTCOME_UNKNOWN", False)
                    return self._failure_envelope(
                        record,
                        descriptor,
                        workspace.slug,
                        caller_id,
                        record.audit_receipt,
                        error,
                        True,
                    ), 409
                authorization_failure = self._authorize(request, descriptor, parsed_input, workspace.slug)
                if authorization_failure is not None:
                    raise authorization_failure

                status_code, raw_result, publication_payload = self._dispatch(
                    request=request,
                    workspace=workspace,
                    descriptor=descriptor,
                    parsed_input=parsed_input,
                )
                if status_code >= 400:
                    raise GatewayFailure(
                        "PLANE_CONFLICT" if status_code == 409 else "PLANE_VALIDATION_ERROR",
                        409 if status_code == 409 else 400,
                        False,
                    )
                result = self._bound_result(
                    descriptor,
                    raw_result,
                    max_bytes=min(descriptor.max_result_bytes, MAX_RESULT_BYTES),
                )
                return (
                    self._finish_success(
                        record,
                        descriptor,
                        workspace.slug,
                        caller_id,
                        result,
                        publication_payload=publication_payload,
                    ),
                    200,
                )
        except GatewayFailure as failure:
            return self._persist_failure(record, descriptor, workspace.slug, caller_id, request_digest, failure)
        except AttachmentFailure as failure:
            return self._persist_failure(
                record,
                descriptor,
                workspace.slug,
                caller_id,
                request_digest,
                GatewayFailure(failure.code, failure.http_status, failure.retryable),
            )
        except Issue.DoesNotExist:
            return self._persist_failure(
                record,
                descriptor,
                workspace.slug,
                caller_id,
                request_digest,
                GatewayFailure("OPERATION_REJECTED", 400, False),
            )
        except DatabaseError:
            return self._persist_failure(
                record,
                descriptor,
                workspace.slug,
                caller_id,
                request_digest,
                GatewayFailure("UPSTREAM_FAILURE", 503, True, ambiguous=descriptor.kind == "mutation"),
            )
        except Exception:
            return self._persist_failure(
                record,
                descriptor,
                workspace.slug,
                caller_id,
                request_digest,
                GatewayFailure("UPSTREAM_FAILURE", 503, True),
            )

    def _parse_operation_input(
        self, descriptor: OperationDescriptor, value: dict[str, Any]
    ) -> tuple[dict[str, Any], GatewayFailure | None]:
        serializer_class = {
            "work_item.read": WorkItemReadInputSerializer,
            "work_item.rename": WorkItemRenameInputSerializer,
            "user.me": EmptyOperationInputSerializer,
            "work_item_attachment.list": AttachmentListInputSerializer,
            "work_item_attachment.download_url": AttachmentReadInputSerializer,
            "work_item_attachment.upload_from_url": AttachmentUploadFromUrlInputSerializer,
            "work_item_attachment.delete": AttachmentReadInputSerializer,
            "work_item_attachment.read": AttachmentReadInputSerializer,
        }.get(descriptor.operation_id)
        if serializer_class is None:
            return {}, GatewayFailure("UNKNOWN_OPERATION", 404, False)
        serializer = serializer_class(data=value)
        if not serializer.is_valid():
            return {}, GatewayFailure("VALIDATION_ERROR", 400, False)
        # Keep the canonical parsed contract JSON-safe for durable reconciliation.
        return json.loads(canonical_json(serializer.validated_data)), None

    def _authorize(
        self,
        request: Any,
        descriptor: OperationDescriptor,
        parsed_input: dict[str, Any],
        workspace_slug: str,
    ) -> GatewayFailure | None:
        if descriptor.operation_id == "user.me":
            return None
        if descriptor.operation_id.startswith("work_item_attachment."):
            try:
                _assert_issue_permission(
                    request,
                    Workspace.objects.get(slug=workspace_slug),
                    str(parsed_input["project_id"]),
                    str(parsed_input["issue_id"]),
                    mutation=descriptor.kind == "mutation",
                )
            except AttachmentFailure as failure:
                return GatewayFailure(failure.code, failure.http_status, failure.retryable)
            return None
        service_request = GatewayServiceRequest(
            request,
            method="GET" if descriptor.kind == "read" else "PATCH",
        )
        view = IssueDetailAPIEndpoint()
        view.request = service_request
        view.kwargs = {"slug": workspace_slug, "project_id": str(parsed_input["project_id"])}
        try:
            allowed = ProjectEntityPermission().has_permission(service_request, view)
        except Exception:
            return GatewayFailure("AUTHORIZATION_UNAVAILABLE", 503, True)
        if not allowed:
            return GatewayFailure("NOT_AUTHORIZED", 403, False)
        return None

    def _dispatch(
        self,
        *,
        request: Any,
        workspace: Workspace,
        descriptor: OperationDescriptor,
        parsed_input: dict[str, Any],
    ) -> tuple[int, dict[str, Any], dict[str, Any] | None]:
        if descriptor.operation_id == "user.me":
            return 200, UserLiteSerializer(request.user).data, None

        if descriptor.operation_id.startswith("work_item_attachment."):
            service = WorkItemAttachmentService()
            project_id = str(parsed_input["project_id"])
            issue_id = str(parsed_input["issue_id"])
            attachment_id = str(parsed_input.get("attachment_id", ""))
            if descriptor.operation_id == "work_item_attachment.list":
                result = service.list(
                    request=request,
                    workspace=workspace,
                    project_id=project_id,
                    issue_id=issue_id,
                )
            elif descriptor.operation_id == "work_item_attachment.download_url":
                result = service.download_url(
                    request=request,
                    workspace=workspace,
                    project_id=project_id,
                    issue_id=issue_id,
                    attachment_id=attachment_id,
                )
            elif descriptor.operation_id == "work_item_attachment.upload_from_url":
                result = service.upload_from_url(
                    request=request,
                    workspace=workspace,
                    project_id=project_id,
                    issue_id=issue_id,
                    url=parsed_input["url"],
                    name=parsed_input.get("name"),
                )
            elif descriptor.operation_id == "work_item_attachment.delete":
                result = service.delete(
                    request=request,
                    workspace=workspace,
                    project_id=project_id,
                    issue_id=issue_id,
                    attachment_id=attachment_id,
                )
            else:
                result = service.authorize_read(
                    request=request,
                    workspace=workspace,
                    project_id=project_id,
                    issue_id=issue_id,
                    attachment_id=attachment_id,
                )
            return 200, result, None

        project_id = str(parsed_input["project_id"])
        issue_id = str(parsed_input["issue_id"])
        if descriptor.operation_id == "work_item.read":
            service_request = GatewayServiceRequest(request, method="GET")
            view = IssueDetailAPIEndpoint()
            view.request = service_request
            view.kwargs = {"slug": workspace.slug, "project_id": project_id}
            response = view.get(service_request, slug=workspace.slug, project_id=project_id, pk=issue_id)
            return response.status_code, response.data, None

        try:
            outcome = WorkItemRenameService().rename(
                request=request,
                workspace=workspace,
                project_id=project_id,
                issue_id=issue_id,
                name=parsed_input["name"],
            )
        except WorkItemRenameFailure as failure:
            raise GatewayFailure(failure.code, failure.http_status, failure.retryable) from None
        if not isinstance(outcome, WorkItemRenameOutcome):
            raise GatewayFailure("UPSTREAM_FAILURE", 503, True)
        return 200, outcome.result, outcome.publication_payload

    def _bound_result(
        self,
        descriptor: OperationDescriptor,
        raw_result: dict[str, Any],
        *,
        max_bytes: int,
    ) -> dict[str, Any]:
        if descriptor.result_key == "work_item":
            bounded = {field: raw_result.get(field) for field in READ_RESULT_FIELDS if field in raw_result}
        else:
            bounded = json.loads(canonical_json(raw_result))
        result = json.loads(canonical_json({descriptor.result_key: bounded}))
        if len(canonical_json(result).encode("utf-8")) > max_bytes:
            raise GatewayFailure("RESULT_TOO_LARGE", 409, False)
        return result

    def _finish_success(
        self,
        record: OperationGatewayIdempotency,
        descriptor: OperationDescriptor,
        workspace_slug: str,
        caller_id: str,
        result: dict[str, Any],
        publication_payload: dict[str, Any] | None = None,
    ) -> GatewaySuccessEnvelope:
        create_publication_intents(record, publication_payload)
        audit = self._write_audit(
            phase=OperationGatewayAudit.Phase.OUTCOME,
            outcome=OperationGatewayAudit.Outcome.SUCCESS,
            descriptor=descriptor,
            record=record,
            result=result,
            error=None,
        )
        record.state = OperationGatewayIdempotency.State.SUCCEEDED
        record.result = result
        record.error = None
        record.retryable = False
        record.audit_receipt = audit.id
        record.save(update_fields=["state", "result", "error", "retryable", "audit_receipt", "updated_at"])
        if publication_payload:
            schedule_publications_on_commit(record)
        return self._success_envelope(record, descriptor, workspace_slug, caller_id, audit.id, result, False)

    def _persist_failure(
        self,
        record: OperationGatewayIdempotency,
        descriptor: OperationDescriptor,
        workspace_slug: str,
        caller_id: str,
        request_digest: str,
        failure: GatewayFailure,
    ) -> tuple[GatewayFailureEnvelope, int]:
        with transaction.atomic():
            locked = OperationGatewayIdempotency.objects.select_for_update().get(pk=record.id)
            if locked.invocation_id != record.invocation_id or locked.state not in (
                OperationGatewayIdempotency.State.RUNNING,
                OperationGatewayIdempotency.State.PENDING,
            ):
                error = self._error("OUTCOME_UNKNOWN", False)
                return self._failure_envelope(
                    locked,
                    descriptor,
                    workspace_slug,
                    caller_id,
                    locked.audit_receipt,
                    error,
                    True,
                ), 409
            return self._finish_failure(
                locked,
                descriptor,
                workspace_slug,
                caller_id,
                request_digest,
                failure,
            )

    def _finish_failure(
        self,
        record: OperationGatewayIdempotency,
        descriptor: OperationDescriptor,
        workspace_slug: str,
        caller_id: str,
        request_digest: str,
        failure: GatewayFailure,
    ) -> tuple[GatewayFailureEnvelope, int]:
        outcome_unknown = failure.ambiguous
        is_denied = failure.code == "NOT_AUTHORIZED"
        state = (
            OperationGatewayIdempotency.State.DENIED
            if is_denied
            else OperationGatewayIdempotency.State.OUTCOME_UNKNOWN
            if outcome_unknown
            else OperationGatewayIdempotency.State.FAILED_PRECOMMIT
        )
        error = self._error(
            "OUTCOME_UNKNOWN" if outcome_unknown else failure.code,
            failure.retryable and not outcome_unknown,
        )
        audit = self._write_audit(
            phase=OperationGatewayAudit.Phase.OUTCOME,
            outcome=(
                OperationGatewayAudit.Outcome.DENIED
                if is_denied
                else OperationGatewayAudit.Outcome.OUTCOME_UNKNOWN
                if outcome_unknown
                else OperationGatewayAudit.Outcome.FAILURE
            ),
            descriptor=descriptor,
            record=record,
            result=None,
            error=error,
        )
        record.state = state
        record.result = None if not outcome_unknown else record.result
        record.error = error
        record.retryable = failure.retryable and not outcome_unknown
        record.audit_receipt = audit.id
        record.save(update_fields=["state", "result", "error", "retryable", "audit_receipt", "updated_at"])
        return self._failure_envelope(record, descriptor, workspace_slug, caller_id, audit.id, error, False), (
            409 if outcome_unknown else failure.http_status
        )

    def _mark_outcome_unknown(
        self,
        record: OperationGatewayIdempotency,
        descriptor: OperationDescriptor,
        workspace_slug: str,
        caller_id: str,
        request_digest: str,
    ) -> tuple[GatewayFailureEnvelope, int]:
        with transaction.atomic():
            locked = OperationGatewayIdempotency.objects.select_for_update().get(pk=record.id)
            error = self._error("OUTCOME_UNKNOWN", False)
            if locked.state == OperationGatewayIdempotency.State.OUTCOME_UNKNOWN:
                audit = self._write_invocation_pair(
                    record=locked,
                    correlation_id=locked.correlation_id,
                    request_digest=request_digest,
                    invocation_id=uuid.uuid4(),
                    request_id=uuid.uuid4(),
                    outcome=OperationGatewayAudit.Outcome.OUTCOME_UNKNOWN,
                    result=locked.result,
                    error=GatewayFailure("OUTCOME_UNKNOWN", 409, False),
                )
                return self._failure_envelope(
                    locked,
                    descriptor,
                    workspace_slug,
                    caller_id,
                    audit.id,
                    error,
                    True,
                    request_id=audit.request_id,
                    correlation_id=audit.correlation_id,
                ), 409
            audit = self._write_audit(
                phase=OperationGatewayAudit.Phase.OUTCOME,
                outcome=OperationGatewayAudit.Outcome.OUTCOME_UNKNOWN,
                descriptor=descriptor,
                record=locked,
                result=locked.result,
                error=error,
            )
            locked.state = OperationGatewayIdempotency.State.OUTCOME_UNKNOWN
            locked.error = error
            locked.retryable = False
            locked.audit_receipt = audit.id
            locked.save(update_fields=["state", "error", "retryable", "audit_receipt", "updated_at"])
            return self._failure_envelope(locked, descriptor, workspace_slug, caller_id, audit.id, error, False), 409

    def _reconcile_unknown_locked(
        self,
        record: OperationGatewayIdempotency,
        descriptor: OperationDescriptor,
    ) -> tuple[GatewayFailureEnvelope, int]:
        error = self._error("OUTCOME_UNKNOWN", False)
        invocation_id = uuid.uuid4()
        audit = self._write_invocation_pair(
            record=record,
            correlation_id=record.correlation_id,
            request_digest=record.request_digest,
            invocation_id=invocation_id,
            request_id=uuid.uuid4(),
            outcome=OperationGatewayAudit.Outcome.OUTCOME_UNKNOWN,
            result=record.result,
            error=error,
        )
        if record.state in (
            OperationGatewayIdempotency.State.RUNNING,
            OperationGatewayIdempotency.State.PENDING,
        ):
            record.state = OperationGatewayIdempotency.State.OUTCOME_UNKNOWN
            record.error = error
            record.retryable = False
            record.audit_receipt = audit.id
            record.save(update_fields=["state", "error", "retryable", "audit_receipt", "updated_at"])
        return self._failure_envelope(
            record,
            descriptor,
            record.workspace_slug,
            str(record.caller_id),
            audit.id,
            error,
            True,
            request_id=audit.request_id,
            correlation_id=audit.correlation_id,
        ), 409

    def _write_audit(
        self,
        *,
        phase: str,
        outcome: str,
        descriptor: OperationDescriptor,
        record: OperationGatewayIdempotency,
        result: dict[str, Any] | None,
        error: GatewayError | None,
    ) -> OperationGatewayAudit:
        return OperationGatewayAudit.objects.create(
            invocation_id=record.invocation_id,
            phase=phase,
            outcome=outcome,
            request_id=record.request_id,
            operation_id=descriptor.operation_id,
            workspace_id=record.workspace_id,
            workspace_slug=record.workspace_slug,
            caller_id=record.caller_id,
            idempotency_key=record.idempotency_key,
            correlation_id=record.correlation_id,
            request_digest=record.request_digest,
            result=result,
            error_code=error["code"] if error else None,
        )

    def _write_invocation_pair(
        self,
        *,
        record: OperationGatewayIdempotency,
        correlation_id: str,
        request_digest: str,
        invocation_id: uuid.UUID,
        request_id: uuid.UUID,
        outcome: str,
        result: dict[str, Any] | None = None,
        error: GatewayError | GatewayFailure | None = None,
    ) -> OperationGatewayAudit:
        error_value = self._error(error.code, error.retryable) if isinstance(error, GatewayFailure) else error
        fields = {
            "invocation_id": invocation_id,
            "request_id": request_id,
            "operation_id": record.operation_id,
            "workspace_id": record.workspace_id,
            "workspace_slug": record.workspace_slug,
            "caller_id": record.caller_id,
            "idempotency_key": record.idempotency_key,
            "correlation_id": correlation_id,
            "request_digest": request_digest,
        }
        OperationGatewayAudit.objects.create(
            **fields,
            phase=OperationGatewayAudit.Phase.INTENT,
            outcome=OperationGatewayAudit.Outcome.INTENT,
        )
        return OperationGatewayAudit.objects.create(
            **fields,
            phase=OperationGatewayAudit.Phase.OUTCOME,
            outcome=outcome,
            result=result,
            error_code=error_value["code"] if error_value else None,
        )

    def _record_unkeyed_failure(
        self,
        *,
        operation_id: str,
        workspace_slug: str,
        idempotency_key: str,
        correlation_id: str,
        caller_id: str,
        workspace_id: uuid.UUID | None,
        request_digest: str,
        failure: GatewayFailure,
    ) -> tuple[GatewayFailureEnvelope, int]:
        request_id = uuid.uuid4()
        invocation_id = uuid.uuid4()
        fields = {
            "invocation_id": invocation_id,
            "request_id": request_id,
            "operation_id": self._wire_text(operation_id, "unknown", 128),
            "workspace_id": workspace_id,
            "workspace_slug": self._wire_text(workspace_slug, "unknown", 255),
            "caller_id": uuid.UUID(caller_id),
            "idempotency_key": self._wire_text(idempotency_key, "unbound", 128),
            "correlation_id": self._wire_text(correlation_id, str(uuid.uuid4()), 128),
            "request_digest": request_digest,
        }
        with transaction.atomic():
            OperationGatewayAudit.objects.create(
                **fields,
                phase=OperationGatewayAudit.Phase.INTENT,
                outcome=OperationGatewayAudit.Outcome.INTENT,
            )
        error = self._error(failure.code, failure.retryable)
        with transaction.atomic():
            outcome_audit = OperationGatewayAudit.objects.create(
                **fields,
                phase=OperationGatewayAudit.Phase.OUTCOME,
                outcome=(
                    OperationGatewayAudit.Outcome.DENIED
                    if failure.code == "NOT_AUTHORIZED"
                    else OperationGatewayAudit.Outcome.FAILURE
                ),
                error_code=error["code"],
            )
        return self._direct_failure_envelope(
            operation_id=fields["operation_id"],
            workspace_slug=fields["workspace_slug"],
            caller_id=caller_id,
            request_id=request_id,
            idempotency_key=fields["idempotency_key"],
            correlation_id=fields["correlation_id"],
            audit_receipt=outcome_audit.id,
            error=failure,
            replayed=False,
            status_code=failure.http_status,
        )

    def _replay_terminal(
        self,
        record: OperationGatewayIdempotency,
        descriptor: OperationDescriptor,
        workspace_slug: str,
        caller_id: str,
        replay_audit: OperationGatewayAudit,
    ) -> tuple[GatewayEnvelope, int]:
        if record.state == OperationGatewayIdempotency.State.SUCCEEDED and record.result is not None:
            return self._success_envelope(
                record,
                descriptor,
                workspace_slug,
                caller_id,
                replay_audit.id,
                record.result,
                True,
                request_id=replay_audit.request_id,
                correlation_id=replay_audit.correlation_id,
            ), 200
        failure = self._failure_from_record(record) or GatewayFailure("UPSTREAM_FAILURE", 503, False)
        status_code = (
            403 if record.state == OperationGatewayIdempotency.State.DENIED else self._status_for_code(failure.code)
        )
        return self._failure_envelope(
            record,
            descriptor,
            workspace_slug,
            caller_id,
            replay_audit.id,
            self._error(failure.code, record.retryable),
            True,
            request_id=replay_audit.request_id,
            correlation_id=replay_audit.correlation_id,
        ), status_code

    def _direct_unknown(self, record: OperationGatewayIdempotency) -> tuple[GatewayFailureEnvelope, int]:
        audit = self._write_invocation_pair(
            record=record,
            correlation_id=record.correlation_id,
            request_digest=record.request_digest,
            invocation_id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            outcome=OperationGatewayAudit.Outcome.OUTCOME_UNKNOWN,
            result=record.result,
            error=GatewayFailure("OUTCOME_UNKNOWN", 409, False),
        )
        return self._direct_failure_envelope(
            operation_id=record.operation_id,
            workspace_slug=record.workspace_slug,
            caller_id=str(record.caller_id),
            request_id=audit.request_id,
            idempotency_key=record.idempotency_key,
            correlation_id=audit.correlation_id,
            audit_receipt=audit.id,
            error=GatewayFailure("OUTCOME_UNKNOWN", 409, False),
            replayed=True,
            status_code=409,
        )

    def _failure_from_record(self, record: OperationGatewayIdempotency) -> GatewayFailure | None:
        if not isinstance(record.error, dict):
            return None
        code = record.error.get("code")
        if not isinstance(code, str) or code not in ERROR_MESSAGES:
            return GatewayFailure("UPSTREAM_FAILURE", 503, False)
        return GatewayFailure(code, self._status_for_code(code), bool(record.retryable))

    def _success_envelope(
        self,
        record: OperationGatewayIdempotency,
        descriptor: OperationDescriptor,
        workspace_slug: str,
        caller_id: str,
        audit_receipt: uuid.UUID | None,
        result: dict[str, Any],
        replayed: bool,
        *,
        request_id: uuid.UUID | None = None,
        correlation_id: str | None = None,
    ) -> GatewaySuccessEnvelope:
        envelope = self._envelope_base(
            descriptor.operation_id,
            workspace_slug,
            caller_id,
            request_id or record.request_id,
            record.idempotency_key,
            correlation_id or record.correlation_id,
            str(audit_receipt) if audit_receipt else None,
            replayed,
            record.workspace_id,
        )
        envelope.update({"ok": True, "result": result})
        return self._bounded_response(envelope)

    def _failure_envelope(
        self,
        record: OperationGatewayIdempotency,
        descriptor: OperationDescriptor,
        workspace_slug: str,
        caller_id: str,
        audit_receipt: uuid.UUID | None,
        error: GatewayError,
        replayed: bool,
        *,
        request_id: uuid.UUID | None = None,
        correlation_id: str | None = None,
    ) -> GatewayFailureEnvelope:
        envelope = self._envelope_base(
            descriptor.operation_id,
            workspace_slug,
            caller_id,
            request_id or record.request_id,
            record.idempotency_key,
            correlation_id or record.correlation_id,
            str(audit_receipt) if audit_receipt else None,
            replayed,
            None,
        )
        envelope.update({"ok": False, "error": self._error(error["code"], error["retryable"])})
        return self._bounded_response(envelope)

    def _direct_failure_envelope(
        self,
        *,
        operation_id: str,
        workspace_slug: str,
        caller_id: str,
        request_id: uuid.UUID,
        idempotency_key: str,
        correlation_id: str,
        audit_receipt: uuid.UUID | None,
        error: GatewayFailure,
        replayed: bool,
        status_code: int,
    ) -> tuple[GatewayFailureEnvelope, int]:
        envelope = self._envelope_base(
            operation_id,
            workspace_slug,
            caller_id,
            request_id,
            idempotency_key,
            correlation_id,
            str(audit_receipt) if audit_receipt else None,
            replayed,
            None,
        )
        envelope.update({"ok": False, "error": self._error(error.code, error.retryable)})
        return self._bounded_response(envelope), status_code

    def _envelope_base(
        self,
        operation_id: str,
        workspace_slug: str,
        caller_id: str,
        request_id: uuid.UUID,
        idempotency_key: str,
        correlation_id: str,
        audit_receipt: str | None,
        replayed: bool,
        workspace_id: uuid.UUID | None,
    ) -> dict[str, Any]:
        workspace: dict[str, str] = {"slug": self._wire_text(workspace_slug, "unknown", 255)}
        if workspace_id is not None:
            workspace["id"] = str(workspace_id)
        return {
            "schema_version": SCHEMA_VERSION,
            "operation_id": self._wire_text(operation_id, "unknown", 128),
            "request_id": str(request_id),
            "caller": {"type": "user", "id": self._wire_text(caller_id, "unknown", 64)},
            "workspace": workspace,
            "idempotency": {
                "key": self._wire_text(idempotency_key, "unbound", 128),
                "replayed": replayed,
            },
            "correlation_id": self._wire_text(correlation_id, str(uuid.uuid4()), 128),
            "audit_receipt": audit_receipt,
        }

    def _bounded_response(self, envelope: dict[str, Any]):
        if len(canonical_json(envelope).encode("utf-8")) <= MAX_RESPONSE_BYTES:
            return envelope
        bounded = dict(envelope)
        bounded["result"] = {"work_item": {}} if envelope.get("operation_id", "").startswith("work_item.") else {}
        bounded["error"] = self._error("RESULT_TOO_LARGE", False)
        bounded["ok"] = False
        return bounded

    @staticmethod
    def _error(code: str, retryable: bool) -> GatewayError:
        safe_code = code if code in ERROR_MESSAGES else "INTERNAL_ERROR"
        return {"code": safe_code, "message": ERROR_MESSAGES[safe_code], "retryable": retryable}

    @staticmethod
    def _status_for_code(code: str) -> int:
        return {
            "ATTACHMENT_CONTENT_UNSUPPORTED": 400,
            "ATTACHMENT_NOT_FOUND": 404,
            "ATTACHMENT_TOO_LARGE": 400,
            "EXTERNAL_SOURCE_REJECTED": 400,
            "NOT_AUTHORIZED": 403,
            "AUTHORIZATION_UNAVAILABLE": 503,
            "IDEMPOTENCY_CONFLICT": 409,
            "OUTCOME_UNKNOWN": 409,
            "RESULT_TOO_LARGE": 409,
            "UNKNOWN_OPERATION": 404,
            "UPSTREAM_FAILURE": 503,
        }.get(code, 400)

    @staticmethod
    def _workspace_id(workspace_slug: str) -> uuid.UUID | None:
        if not isinstance(workspace_slug, str):
            return None
        workspace = Workspace.objects.filter(slug=workspace_slug).only("id").first()
        return workspace.id if workspace else None

    @staticmethod
    def _request_digest(
        *,
        workspace_id: uuid.UUID,
        caller_id: str,
        descriptor: OperationDescriptor,
        idempotency_key: str,
        parsed_input: dict[str, Any],
    ) -> str:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "workspace_id": str(workspace_id),
            "caller_id": caller_id,
            "operation_id": descriptor.operation_id,
            "idempotency_key": idempotency_key,
            "input": parsed_input,
        }
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()

    @staticmethod
    def _digest_for_raw(value: Any) -> str:
        try:
            encoded = canonical_json(value)
        except (TypeError, ValueError):
            encoded = str(value)[:MAX_INPUT_BYTES]
        return hashlib.sha256(encoded.encode("utf-8")[:MAX_INPUT_BYTES]).hexdigest()

    @staticmethod
    def _wire_text(value: Any, fallback: str, max_length: int) -> str:
        if not isinstance(value, str) or not value.strip():
            return fallback
        return value.strip()[:max_length]
