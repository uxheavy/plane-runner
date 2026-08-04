"""Internal JSON HTTP adapter for the shared Operation Gateway."""

from __future__ import annotations

import uuid
from typing import Any

from rest_framework import status
from rest_framework.response import Response

from plane.api.views.base import BaseAPIView

from .contracts import OperationGatewayRequestSerializer, SCHEMA_VERSION
from .gateway import OperationGateway


class OperationGatewayAPIEndpoint(BaseAPIView):
    """POST one versioned gateway envelope using the live API-key caller."""

    def post(self, request: Any) -> Response:
        serializer = OperationGatewayRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                self._validation_error(request, serializer),
                status=status.HTTP_400_BAD_REQUEST,
            )

        envelope, http_status = OperationGateway().execute(request, serializer.validated_data)
        return Response(envelope, status=http_status)

    def _validation_error(self, request: Any, serializer: OperationGatewayRequestSerializer) -> dict[str, Any]:
        operation_id = request.data.get("operation_id", "unknown") if isinstance(request.data, dict) else "unknown"
        workspace_slug = request.data.get("workspace_slug", "unknown") if isinstance(request.data, dict) else "unknown"
        idempotency_key = (
            request.data.get("idempotency_key", "unbound") if isinstance(request.data, dict) else "unbound"
        )
        correlation_id = (
            request.data.get("correlation_id", str(uuid.uuid4()))
            if isinstance(request.data, dict)
            else str(uuid.uuid4())
        )
        return {
            "ok": False,
            "schema_version": SCHEMA_VERSION,
            "operation_id": str(operation_id)[:128],
            "request_id": str(uuid.uuid4()),
            "caller": {"type": "user", "id": str(request.user.id)},
            "workspace": {"slug": str(workspace_slug)[:255], "id": None},
            "idempotency": {"key": str(idempotency_key)[:128], "replayed": False},
            "correlation_id": str(correlation_id)[:128],
            "audit_receipt": None,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Operation request is invalid.",
                "retryable": False,
            },
        }
