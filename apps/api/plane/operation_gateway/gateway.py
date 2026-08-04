"""Authorization, idempotency, bounded execution, and audit for gateway calls."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from django.db import transaction

from plane.api.views.issue import IssueDetailAPIEndpoint
from plane.app.permissions import ProjectEntityPermission
from plane.db.models import Issue, OperationGatewayAudit, OperationGatewayIdempotency, Workspace

from .catalog import OperationDescriptor, get_operation
from .contracts import (
    GatewayError,
    GatewayEnvelope,
    GatewayFailureEnvelope,
    GatewaySuccessEnvelope,
    MAX_RESULT_BYTES,
    SCHEMA_VERSION,
    WorkItemReadInputSerializer,
    WorkItemRenameInputSerializer,
    canonical_json,
)

READ_RESULT_FIELDS = ("id", "name", "sequence_id", "priority", "state", "project", "workspace")


class GatewayFailure(Exception):
    def __init__(self, code: str, message: str, http_status: int, retryable: bool, ambiguous: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.retryable = retryable
        self.ambiguous = ambiguous


class GatewayServiceRequest:
    """Minimal request adapter required by the existing issue API service."""

    def __init__(self, request: Any, *, method: str, data: dict[str, Any] | None = None):
        self.user = request.user
        self.method = method
        self.data = data or {}
        self.GET = {"fields": ",".join(READ_RESULT_FIELDS)} if method == "GET" else {}
        self.META = request.META


class OperationGateway:
    """One deep application boundary for the initial gateway vertical slice."""

    def execute(self, request: Any, envelope: dict[str, Any]) -> tuple[GatewayEnvelope, int]:
        descriptor = get_operation(envelope["operation_id"])
        caller_id = str(request.user.id)
        if descriptor is None:
            return self._failure_without_receipt(
                operation_id=envelope["operation_id"],
                workspace_slug=envelope["workspace_slug"],
                idempotency_key=envelope["idempotency_key"],
                correlation_id=envelope["correlation_id"],
                caller_id=caller_id,
                failure=GatewayFailure("UNKNOWN_OPERATION", "Operation is not available.", 404, False),
            )

        parsed_input, input_failure = self._parse_operation_input(descriptor, envelope["input"])
        if input_failure is not None:
            return self._failure_without_receipt(
                operation_id=descriptor.operation_id,
                workspace_slug=envelope["workspace_slug"],
                idempotency_key=envelope["idempotency_key"],
                correlation_id=envelope["correlation_id"],
                caller_id=caller_id,
                failure=input_failure,
            )

        request_digest = self._request_digest(descriptor, envelope["workspace_slug"], parsed_input)
        return self._execute_idempotent(
            request=request,
            descriptor=descriptor,
            workspace_slug=envelope["workspace_slug"],
            idempotency_key=envelope["idempotency_key"],
            correlation_id=envelope["correlation_id"],
            caller_id=caller_id,
            request_digest=request_digest,
            parsed_input=parsed_input,
        )

    def _execute_idempotent(
        self,
        *,
        request: Any,
        descriptor: OperationDescriptor,
        workspace_slug: str,
        idempotency_key: str,
        correlation_id: str,
        caller_id: str,
        request_digest: str,
        parsed_input: dict[str, Any],
    ) -> tuple[GatewayEnvelope, int]:
        with transaction.atomic():
            record, created = OperationGatewayIdempotency.objects.select_for_update().get_or_create(
                workspace_slug=workspace_slug,
                caller_id=caller_id,
                idempotency_key=idempotency_key,
                defaults={
                    "request_id": uuid.uuid4(),
                    "operation_id": descriptor.operation_id,
                    "request_digest": request_digest,
                    "correlation_id": correlation_id,
                    "state": OperationGatewayIdempotency.State.PENDING,
                },
            )

            if not created and record.request_digest != request_digest:
                return self._finish_conflict(
                    descriptor=descriptor,
                    workspace_slug=workspace_slug,
                    idempotency_key=idempotency_key,
                    correlation_id=correlation_id,
                    caller_id=caller_id,
                    request_digest=request_digest,
                )

            if not created:
                replay = self._replay_terminal(record, descriptor, workspace_slug, caller_id)
                if replay is not None:
                    return replay

                if record.state == OperationGatewayIdempotency.State.PENDING:
                    return self._finish_outcome_unknown(record, descriptor, workspace_slug, caller_id)

                # A known pre-commit failure may retry under the same key.
                record.request_id = uuid.uuid4()
                record.correlation_id = correlation_id
                record.state = OperationGatewayIdempotency.State.PENDING
                record.result = None
                record.error = None
                record.audit_receipt = None
                record.save(
                    update_fields=[
                        "request_id",
                        "correlation_id",
                        "state",
                        "result",
                        "error",
                        "audit_receipt",
                        "updated_at",
                    ]
                )

            self._write_audit(
                phase=OperationGatewayAudit.Phase.INTENT,
                outcome=OperationGatewayAudit.Outcome.INTENT,
                descriptor=descriptor,
                record=record,
                workspace_slug=workspace_slug,
                caller_id=caller_id,
                request_digest=request_digest,
            )

            authorization_failure = self._authorize(request, descriptor, parsed_input, workspace_slug)
            if authorization_failure is not None:
                return self._finish_failure(
                    record=record,
                    descriptor=descriptor,
                    workspace_slug=workspace_slug,
                    caller_id=caller_id,
                    request_digest=request_digest,
                    failure=authorization_failure,
                )

            try:
                with transaction.atomic():
                    status_code, raw_result = self._dispatch(
                        request=request,
                        descriptor=descriptor,
                        workspace_slug=workspace_slug,
                        parsed_input=parsed_input,
                    )
                    if status_code >= 400:
                        failure = GatewayFailure(
                            "PLANE_CONFLICT" if status_code == 409 else "PLANE_VALIDATION_ERROR",
                            "Plane rejected the operation.",
                            409 if status_code == 409 else 400,
                            False,
                        )
                        return self._finish_failure(
                            record=record,
                            descriptor=descriptor,
                            workspace_slug=workspace_slug,
                            caller_id=caller_id,
                            request_digest=request_digest,
                            failure=failure,
                        )
                    result = self._bound_result(
                        raw_result,
                        max_bytes=min(descriptor.max_result_bytes, MAX_RESULT_BYTES),
                        ambiguous=descriptor.kind == "mutation",
                    )
            except Issue.DoesNotExist:
                return self._finish_failure(
                    record=record,
                    descriptor=descriptor,
                    workspace_slug=workspace_slug,
                    caller_id=caller_id,
                    request_digest=request_digest,
                    failure=GatewayFailure("NOT_FOUND", "The requested Plane object was not found.", 404, False),
                )
            except GatewayFailure as failure:
                return self._finish_failure(
                    record=record,
                    descriptor=descriptor,
                    workspace_slug=workspace_slug,
                    caller_id=caller_id,
                    request_digest=request_digest,
                    failure=failure,
                )
            except Exception:
                # A mutation may have crossed a side-effect boundary before an
                # adapter exception. It is never blindly replayed.
                return self._finish_failure(
                    record=record,
                    descriptor=descriptor,
                    workspace_slug=workspace_slug,
                    caller_id=caller_id,
                    request_digest=request_digest,
                    failure=GatewayFailure(
                        "UPSTREAM_FAILURE",
                        "The operation outcome cannot be safely determined."
                        if descriptor.kind == "mutation"
                        else "Plane could not complete the operation.",
                        409 if descriptor.kind == "mutation" else 500,
                        False,
                        ambiguous=descriptor.kind == "mutation",
                    ),
                )

            return self._finish_success(
                record=record,
                descriptor=descriptor,
                workspace_slug=workspace_slug,
                caller_id=caller_id,
                request_digest=request_digest,
                result=result,
            )

    def _parse_operation_input(
        self, descriptor: OperationDescriptor, value: dict[str, Any]
    ) -> tuple[dict[str, Any], GatewayFailure | None]:
        if descriptor.operation_id == "work_item.read":
            serializer_class = WorkItemReadInputSerializer
        else:
            serializer_class = WorkItemRenameInputSerializer
        serializer = serializer_class(data=value)
        if not serializer.is_valid():
            return {}, GatewayFailure("VALIDATION_ERROR", "Operation input is invalid.", 400, False)
        return serializer.validated_data, None

    def _authorize(
        self, request: Any, descriptor: OperationDescriptor, parsed_input: dict[str, Any], workspace_slug: str
    ) -> GatewayFailure | None:
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
            return GatewayFailure("AUTHORIZATION_UNAVAILABLE", "Authorization could not be evaluated.", 503, True)
        if not allowed:
            return GatewayFailure("NOT_AUTHORIZED", "Operation is not authorized for this caller.", 403, False)
        return None

    def _dispatch(
        self,
        *,
        request: Any,
        descriptor: OperationDescriptor,
        workspace_slug: str,
        parsed_input: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        project_id = str(parsed_input["project_id"])
        issue_id = str(parsed_input["issue_id"])
        if descriptor.operation_id == "work_item.read":
            service_request = GatewayServiceRequest(request, method="GET")
            view = IssueDetailAPIEndpoint()
            view.request = service_request
            view.kwargs = {"slug": workspace_slug, "project_id": project_id}
            response = view.get(service_request, slug=workspace_slug, project_id=project_id, pk=issue_id)
        else:
            service_request = GatewayServiceRequest(request, method="PATCH", data={"name": parsed_input["name"]})
            view = IssueDetailAPIEndpoint()
            view.request = service_request
            view.kwargs = {"slug": workspace_slug, "project_id": project_id}
            response = view.patch(service_request, slug=workspace_slug, project_id=project_id, pk=issue_id)
        return response.status_code, response.data

    def _bound_result(self, raw_result: dict[str, Any], *, max_bytes: int, ambiguous: bool) -> dict[str, Any]:
        bounded = {field: raw_result.get(field) for field in READ_RESULT_FIELDS if field in raw_result}
        result = json.loads(canonical_json({"work_item": bounded}))
        if len(canonical_json(result).encode("utf-8")) > max_bytes:
            raise GatewayFailure("RESULT_TOO_LARGE", "The operation result exceeded its limit.", 409, False, ambiguous)
        return result

    def _finish_success(
        self,
        *,
        record: OperationGatewayIdempotency,
        descriptor: OperationDescriptor,
        workspace_slug: str,
        caller_id: str,
        request_digest: str,
        result: dict[str, Any],
    ) -> tuple[GatewaySuccessEnvelope, int]:
        audit = self._write_audit(
            phase=OperationGatewayAudit.Phase.OUTCOME,
            outcome=OperationGatewayAudit.Outcome.SUCCESS,
            descriptor=descriptor,
            record=record,
            workspace_slug=workspace_slug,
            caller_id=caller_id,
            request_digest=request_digest,
            result=result,
        )
        record.state = OperationGatewayIdempotency.State.SUCCEEDED
        record.result = result
        record.error = None
        record.audit_receipt = audit.id
        record.save(update_fields=["state", "result", "error", "audit_receipt", "updated_at"])
        return self._success_envelope(record, descriptor, workspace_slug, caller_id, audit.id, result, False), 200

    def _finish_failure(
        self,
        *,
        record: OperationGatewayIdempotency,
        descriptor: OperationDescriptor,
        workspace_slug: str,
        caller_id: str,
        request_digest: str,
        failure: GatewayFailure,
    ) -> tuple[GatewayFailureEnvelope, int]:
        is_denied = failure.code == "NOT_AUTHORIZED"
        outcome_unknown = failure.ambiguous
        state = (
            OperationGatewayIdempotency.State.DENIED
            if is_denied
            else OperationGatewayIdempotency.State.OUTCOME_UNKNOWN
            if outcome_unknown
            else OperationGatewayIdempotency.State.FAILED_PRECOMMIT
        )
        code = "OUTCOME_UNKNOWN" if outcome_unknown else failure.code
        message = "The operation outcome cannot be safely determined." if outcome_unknown else failure.message
        status_code = 409 if outcome_unknown else failure.http_status
        error: GatewayError = {"code": code, "message": message, "retryable": failure.retryable and not outcome_unknown}
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
            workspace_slug=workspace_slug,
            caller_id=caller_id,
            request_digest=request_digest,
            error=error,
        )
        record.state = state
        record.result = None
        record.error = error
        record.audit_receipt = audit.id
        record.save(update_fields=["state", "result", "error", "audit_receipt", "updated_at"])
        return (
            self._failure_envelope(record, descriptor, workspace_slug, caller_id, audit.id, error, False),
            status_code,
        )

    def _finish_conflict(
        self,
        *,
        descriptor: OperationDescriptor,
        workspace_slug: str,
        idempotency_key: str,
        correlation_id: str,
        caller_id: str,
        request_digest: str,
    ) -> tuple[GatewayFailureEnvelope, int]:
        request_id = uuid.uuid4()
        OperationGatewayAudit.objects.create(
            phase=OperationGatewayAudit.Phase.INTENT,
            outcome=OperationGatewayAudit.Outcome.INTENT,
            request_id=request_id,
            operation_id=descriptor.operation_id,
            workspace_slug=workspace_slug,
            caller_id=caller_id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            request_digest=request_digest,
        )
        outcome_audit = OperationGatewayAudit.objects.create(
            phase=OperationGatewayAudit.Phase.OUTCOME,
            outcome=OperationGatewayAudit.Outcome.DENIED,
            request_id=request_id,
            operation_id=descriptor.operation_id,
            workspace_slug=workspace_slug,
            caller_id=caller_id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            request_digest=request_digest,
            error_code="IDEMPOTENCY_CONFLICT",
        )
        error: GatewayError = {
            "code": "IDEMPOTENCY_CONFLICT",
            "message": "The idempotency key was already used for another request.",
            "retryable": False,
        }
        envelope = self._envelope_base(
            descriptor.operation_id,
            workspace_slug,
            caller_id,
            request_id,
            idempotency_key,
            correlation_id,
            str(outcome_audit.id),
            False,
            False,
        )
        envelope.update({"ok": False, "error": error})
        return envelope, 409

    def _replay_terminal(
        self,
        record: OperationGatewayIdempotency,
        descriptor: OperationDescriptor,
        workspace_slug: str,
        caller_id: str,
    ) -> tuple[GatewayEnvelope, int] | None:
        if record.state == OperationGatewayIdempotency.State.SUCCEEDED and record.result is not None:
            return (
                self._success_envelope(
                    record,
                    descriptor,
                    workspace_slug,
                    caller_id,
                    record.audit_receipt,
                    record.result,
                    True,
                ),
                200,
            )
        if record.state == OperationGatewayIdempotency.State.DENIED:
            return (
                self._failure_envelope(
                    record,
                    descriptor,
                    workspace_slug,
                    caller_id,
                    record.audit_receipt,
                    record.error
                    or {
                        "code": "NOT_AUTHORIZED",
                        "message": "Operation is not authorized for this caller.",
                        "retryable": False,
                    },
                    True,
                ),
                403,
            )
        if record.state == OperationGatewayIdempotency.State.OUTCOME_UNKNOWN:
            return (
                self._failure_envelope(
                    record,
                    descriptor,
                    workspace_slug,
                    caller_id,
                    record.audit_receipt,
                    record.error
                    or {
                        "code": "OUTCOME_UNKNOWN",
                        "message": "The operation outcome cannot be safely determined.",
                        "retryable": False,
                    },
                    True,
                ),
                409,
            )
        return None

    def _finish_outcome_unknown(
        self,
        record: OperationGatewayIdempotency,
        descriptor: OperationDescriptor,
        workspace_slug: str,
        caller_id: str,
    ) -> tuple[GatewayFailureEnvelope, int]:
        error: GatewayError = {
            "code": "OUTCOME_UNKNOWN",
            "message": "The operation outcome cannot be safely determined.",
            "retryable": False,
        }
        audit = self._write_audit(
            phase=OperationGatewayAudit.Phase.OUTCOME,
            outcome=OperationGatewayAudit.Outcome.OUTCOME_UNKNOWN,
            descriptor=descriptor,
            record=record,
            workspace_slug=workspace_slug,
            caller_id=caller_id,
            request_digest=record.request_digest,
            error=error,
        )
        record.state = OperationGatewayIdempotency.State.OUTCOME_UNKNOWN
        record.error = error
        record.audit_receipt = audit.id
        record.save(update_fields=["state", "error", "audit_receipt", "updated_at"])
        return self._failure_envelope(record, descriptor, workspace_slug, caller_id, audit.id, error, True), 409

    def _write_audit(
        self,
        *,
        phase: str,
        outcome: str,
        descriptor: OperationDescriptor,
        record: OperationGatewayIdempotency,
        workspace_slug: str,
        caller_id: str,
        request_digest: str,
        result: dict[str, Any] | None = None,
        error: GatewayError | None = None,
    ) -> OperationGatewayAudit:
        return OperationGatewayAudit.objects.create(
            phase=phase,
            outcome=outcome,
            request_id=record.request_id,
            operation_id=descriptor.operation_id,
            workspace_slug=workspace_slug,
            caller_id=caller_id,
            idempotency_key=record.idempotency_key,
            correlation_id=record.correlation_id,
            request_digest=request_digest,
            result=result,
            error_code=error["code"] if error else None,
        )

    def _request_digest(
        self, descriptor: OperationDescriptor, workspace_slug: str, parsed_input: dict[str, Any]
    ) -> str:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "operation_id": descriptor.operation_id,
            "workspace_slug": workspace_slug,
            "input": parsed_input,
        }
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()

    def _success_envelope(
        self,
        record: OperationGatewayIdempotency,
        descriptor: OperationDescriptor,
        workspace_slug: str,
        caller_id: str,
        audit_receipt: uuid.UUID | None,
        result: dict[str, Any],
        replayed: bool,
    ) -> GatewaySuccessEnvelope:
        envelope = self._envelope_base(
            descriptor.operation_id,
            workspace_slug,
            caller_id,
            record.request_id,
            record.idempotency_key,
            record.correlation_id,
            str(audit_receipt),
            replayed,
            True,
        )
        envelope.update({"ok": True, "result": result})
        return envelope

    def _failure_envelope(
        self,
        record: OperationGatewayIdempotency,
        descriptor: OperationDescriptor,
        workspace_slug: str,
        caller_id: str,
        audit_receipt: uuid.UUID | None,
        error: GatewayError,
        replayed: bool,
    ) -> GatewayFailureEnvelope:
        envelope = self._envelope_base(
            descriptor.operation_id,
            workspace_slug,
            caller_id,
            record.request_id,
            record.idempotency_key,
            record.correlation_id,
            str(audit_receipt) if audit_receipt else None,
            replayed,
            False,
        )
        envelope.update({"ok": False, "error": error})
        return envelope

    def _failure_without_receipt(
        self,
        *,
        operation_id: str,
        workspace_slug: str,
        idempotency_key: str,
        correlation_id: str,
        caller_id: str,
        failure: GatewayFailure,
    ) -> tuple[GatewayFailureEnvelope, int]:
        error: GatewayError = {"code": failure.code, "message": failure.message, "retryable": failure.retryable}
        envelope = self._envelope_base(
            operation_id,
            workspace_slug,
            caller_id,
            uuid.uuid4(),
            idempotency_key,
            correlation_id,
            None,
            False,
            False,
        )
        envelope.update({"ok": False, "error": error})
        return envelope, failure.http_status

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
        include_workspace_id: bool,
    ) -> dict[str, Any]:
        workspace_id = None
        if include_workspace_id:
            workspace = Workspace.objects.filter(slug=workspace_slug).only("id").first()
            workspace_id = str(workspace.id) if workspace else None
        return {
            "schema_version": SCHEMA_VERSION,
            "operation_id": operation_id,
            "request_id": str(request_id),
            "caller": {"type": "user", "id": caller_id},
            "workspace": {"slug": workspace_slug, "id": workspace_id},
            "idempotency": {"key": idempotency_key, "replayed": replayed},
            "correlation_id": correlation_id,
            "audit_receipt": audit_receipt,
        }
