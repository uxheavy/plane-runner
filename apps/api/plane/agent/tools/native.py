"""Native Plane tool adapter; all execution terminates at the gateway."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from plane.operation_gateway.catalog import get_operation
from plane.operation_gateway.gateway import OperationGateway


class NativeToolAdapter:
    """Bind a trusted Plane request to semantic catalog operations."""

    def __init__(
        self,
        *,
        request: Any,
        workspace_slug: str,
        actor_ref: str | None = None,
        gateway: OperationGateway | None = None,
    ) -> None:
        self.request = request
        self.workspace_slug = workspace_slug
        self.actor_ref = actor_ref
        self.gateway = gateway or OperationGateway()

    def invoke(
        self,
        operation_id: str,
        input_data: Mapping[str, Any],
        *,
        idempotency_key: str,
        correlation_id: str,
        workspace_slug: str | None = None,
    ):
        envelope = {
            "schema_version": "plane.operation/v1",
            "operation_id": operation_id,
            "workspace_slug": workspace_slug or self.workspace_slug,
            "idempotency_key": idempotency_key,
            "correlation_id": correlation_id,
            "input": dict(input_data) if isinstance(input_data, Mapping) else input_data,
        }
        invalid = self._binding_failure(envelope)
        if invalid is not None:
            return invalid
        if get_operation(operation_id) is None:
            return self.gateway.record_invalid_request(
                self.request,
                envelope,
                code="UNKNOWN_OPERATION",
                status_code=404,
            )
        return self.gateway.execute(self.request, envelope)

    def _binding_failure(self, envelope: dict[str, Any]):
        if envelope["workspace_slug"] != self.workspace_slug:
            return self.gateway.record_invalid_request(
                self.request,
                envelope,
                code="CALLBACK_BINDING_INVALID",
                status_code=403,
            )
        request_actor_ref = getattr(self.request, "agent_actor_ref", None)
        if not isinstance(request_actor_ref, str) or not request_actor_ref:
            return self.gateway.record_invalid_request(
                self.request,
                envelope,
                code="CALLBACK_BINDING_INVALID",
                status_code=403,
            )
        if self.actor_ref != request_actor_ref:
            return self.gateway.record_invalid_request(
                self.request,
                envelope,
                code="CALLBACK_BINDING_INVALID",
                status_code=403,
            )
        return None
