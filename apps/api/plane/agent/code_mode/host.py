"""Typed host RPC for generated TypeScript Code Mode."""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any, Callable

from plane.operation_gateway.catalog import CATALOG_DIGEST, code_mode_callback_names, get_operation
from plane.operation_gateway.contracts import canonical_json
from plane.operation_gateway.gateway import OperationGateway

from .contracts import CODE_MODE_SCHEMA_VERSION, CodeModeBudget, HostBinding, SandboxPolicy


class CodeModeHostRPC:
    """Expose only typed, credential-free callbacks to a restricted child isolate."""

    def __init__(
        self,
        *,
        gateway: OperationGateway,
        request: Any,
        binding: HostBinding,
        budget: CodeModeBudget,
        is_cancelled: Callable[[], bool],
        sandbox: SandboxPolicy | None = None,
    ) -> None:
        self.gateway = gateway
        self.request = request
        self.binding = binding
        self.budget = budget
        self.is_cancelled = is_cancelled
        self.sandbox = sandbox or SandboxPolicy(max_spill_bytes=budget.spill_bytes)
        self._started_at = time.monotonic()

    @classmethod
    def from_run(
        cls,
        *,
        gateway: OperationGateway,
        request: Any,
        binding: HostBinding,
        run: Any,
        is_cancelled: Callable[[], bool],
        sandbox: SandboxPolicy | None = None,
    ) -> "CodeModeHostRPC":
        snapshot = run.snapshot if hasattr(run, "snapshot") else run["snapshot"]
        used = run.cumulative_usage if hasattr(run, "cumulative_usage") else run.get("cumulativeUsage", {})
        total = snapshot["totalBudget"]
        budget = CodeModeBudget(
            input_bytes=max(0, int(total.get("inputTokens", 0)) - int(used.get("inputTokens", 0))),
            output_bytes=max(0, int(total.get("outputTokens", 0)) - int(used.get("outputTokens", 0))),
            duration_ms=max(0, int(total.get("durationMs", 0)) - int(used.get("durationMs", 0))),
            calls=max(0, int(snapshot.get("runtimePolicy", {}).get("maxCodeModeCalls", 128))),
            spill_bytes=int(snapshot.get("runtimePolicy", {}).get("maxArtifactBytes", 64 * 1024)),
        )
        return cls(
            gateway=gateway,
            request=request,
            binding=binding,
            budget=budget,
            is_cancelled=is_cancelled,
            sandbox=sandbox,
        )

    @staticmethod
    def callback_surface() -> dict[str, str]:
        """Return names from the catalog instead of freezing bare callbacks."""

        return code_mode_callback_names()

    def search_operations(
        self,
        query: str = "",
        *,
        idempotency_key: str,
        correlation_id: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        return self.call_operation(
            "catalog.search",
            {"query": query, "limit": limit},
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        )

    def describe_operation(
        self,
        operation_id: str,
        *,
        idempotency_key: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        return self.call_operation(
            "catalog.describe",
            {"operation_id": operation_id},
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        )

    def call_operation(
        self,
        operation_id: str,
        input_data: Mapping[str, Any],
        *,
        idempotency_key: str,
        correlation_id: str,
        workspace_slug: str | None = None,
    ) -> dict[str, Any]:
        raw = {
            "schema_version": "plane.operation/v1",
            "operation_id": operation_id,
            "workspace_slug": workspace_slug or self.binding.workspace_slug,
            "idempotency_key": idempotency_key,
            "correlation_id": correlation_id,
            "input": dict(input_data) if isinstance(input_data, Mapping) else input_data,
        }
        invalid = self._preflight(raw)
        if invalid is not None:
            return invalid
        if get_operation(operation_id) is None:
            return self._reject(raw, "UNKNOWN_OPERATION", 404)

        self.budget.calls -= 1
        response, _status = self.gateway.execute(self.request, raw)
        receipt = self._receipt(raw, response)
        encoded_size = len(canonical_json(receipt).encode("utf-8"))
        if encoded_size > self.budget.output_bytes:
            return self._receipt_error(raw, response, "RESULT_TOO_LARGE", 409)
        self.budget.output_bytes -= encoded_size
        return receipt

    def account_spill(self, payload: str | bytes) -> dict[str, Any]:
        size = len(payload.encode("utf-8") if isinstance(payload, str) else payload)
        if size > self.budget.spill_bytes:
            raise ValueError("Code Mode spill exceeds the run bound")
        self.budget.spill_bytes -= size
        return {"ok": True, "bytes": size, "remainingBytes": self.budget.spill_bytes}

    def _preflight(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        if self.binding.catalog_digest != CATALOG_DIGEST:
            return self._reject(raw, "CATALOG_MISMATCH", 409)
        if raw["workspace_slug"] != self.binding.workspace_slug:
            return self._reject(raw, "CALLBACK_BINDING_INVALID", 403)
        request_actor_ref = getattr(self.request, "agent_actor_ref", None)
        if request_actor_ref is not None and request_actor_ref != self.binding.actor_ref:
            return self._reject(raw, "CALLBACK_BINDING_INVALID", 403)
        if not isinstance(raw["input"], Mapping):
            return self._reject(raw, "VALIDATION_ERROR", 400)
        input_size = len(canonical_json(raw["input"]).encode("utf-8"))
        if input_size > self.budget.input_bytes:
            return self._reject(raw, "BUDGET_EXCEEDED", 429)
        if self.budget.calls <= 0:
            return self._reject(raw, "BUDGET_EXCEEDED", 429)
        if self.budget.duration_ms and (time.monotonic() - self._started_at) * 1000 > self.budget.duration_ms:
            return self._reject(raw, "BUDGET_EXCEEDED", 429)
        if self.is_cancelled():
            return self._reject(raw, "CANCELLED", 409)
        self.budget.input_bytes -= input_size
        return None

    def _reject(self, raw: dict[str, Any], code: str, status_code: int) -> dict[str, Any]:
        response, _status = self.gateway.record_invalid_request(
            self.request,
            raw,
            code=code,
            status_code=status_code,
        )
        return self._receipt(raw, response)

    def _receipt(self, raw: Mapping[str, Any], response: Mapping[str, Any]) -> dict[str, Any]:
        idempotency = response.get("idempotency", {})
        receipt = {
            "schemaVersion": CODE_MODE_SCHEMA_VERSION,
            "callback": self.callback_surface()["operation"],
            "operationId": raw["operation_id"],
            "operationRef": f"operation:{raw['operation_id']}",
            "runRef": self.binding.run_ref,
            "invocationRef": self.binding.invocation_ref,
            "idempotencyKey": raw["idempotency_key"],
            "correlationId": response.get("correlation_id", raw["correlation_id"]),
            "requestId": response.get("request_id"),
            "gatewayReceipt": response.get("audit_receipt"),
            "auditReceipt": response.get("audit_receipt"),
            "replayed": bool(idempotency.get("replayed", False)),
            "ok": bool(response.get("ok", False)),
        }
        if response.get("ok"):
            receipt["result"] = response.get("result", {})
        else:
            receipt["error"] = response.get("error", {"code": "INTERNAL_ERROR", "retryable": False})
        return receipt

    def _receipt_error(
        self,
        raw: Mapping[str, Any],
        response: Mapping[str, Any],
        code: str,
        status_code: int,
    ) -> dict[str, Any]:
        receipt = self._receipt(raw, response)
        receipt.pop("result", None)
        receipt["ok"] = False
        receipt["error"] = {"code": code, "retryable": False, "status": status_code}
        return receipt
