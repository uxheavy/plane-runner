"""Typed, persisted, credential-free host RPC for Code Mode."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Mapping
from typing import Any, Callable

from django.core.exceptions import ValidationError

from plane.agent.lifecycle import AgentDomainError, code_mode_usage_totals, record_code_mode_usage
from plane.agent.lifecycle.runtime_contract import (
    RuntimeContractError,
    canonical_json,
    validate_invocation_envelope,
    validate_run_snapshot,
)
from plane.agent.runtime.dispatch import RuntimeDispatchError, _dispatch_binding
from plane.db.models import InvocationState, OperationGatewayIdempotency, RunState, RunAttempt, RuntimeInvocation
from plane.operation_gateway.catalog import CATALOG_DIGEST, code_mode_callback_names, get_operation
from plane.operation_gateway.gateway import OperationGateway

from .contracts import CODE_MODE_SCHEMA_VERSION, CodeModeBudget, HostBinding, SandboxPolicy


class CodeModeBindingError(ValueError):
    """The callback was not bound to the immutable Plane runtime records."""


class CodeModeHostRPC:
    """Expose only typed callbacks after revalidating the persisted G1 binding."""

    def __init__(
        self,
        *,
        gateway: OperationGateway,
        request: Any,
        run: RunAttempt,
        invocation: RuntimeInvocation,
        is_cancelled: Callable[[], bool],
        sandbox: SandboxPolicy | None = None,
    ) -> None:
        self.gateway = gateway
        self.request = request
        self.is_cancelled = is_cancelled
        self.sandbox = sandbox or SandboxPolicy()
        self.run, self.invocation, self.binding, self._snapshot = self._load_trusted_binding(run, invocation)
        self.budget = self._remaining_budget(self.run, self._snapshot)
        self.budget.spill_bytes = min(self.budget.spill_bytes, self.sandbox.max_spill_bytes)
        self._started_at = time.monotonic()

    @classmethod
    def from_invocation(
        cls,
        *,
        gateway: OperationGateway,
        request: Any,
        invocation: RuntimeInvocation,
        is_cancelled: Callable[[], bool],
        sandbox: SandboxPolicy | None = None,
    ) -> "CodeModeHostRPC":
        """Construct a host from one persisted invocation, never caller refs."""

        return cls(
            gateway=gateway,
            request=request,
            run=invocation.run,
            invocation=invocation,
            is_cancelled=is_cancelled,
            sandbox=sandbox,
        )

    @classmethod
    def from_run(
        cls,
        *,
        gateway: OperationGateway,
        request: Any,
        run: RunAttempt,
        invocation: RuntimeInvocation,
        is_cancelled: Callable[[], bool],
        sandbox: SandboxPolicy | None = None,
    ) -> "CodeModeHostRPC":
        """Compatibility constructor that still requires the persisted invocation."""

        return cls(
            gateway=gateway,
            request=request,
            run=run,
            invocation=invocation,
            is_cancelled=is_cancelled,
            sandbox=sandbox,
        )

    @staticmethod
    def callback_surface() -> dict[str, str]:
        """Return callback names from the canonical operation catalog."""

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
        try:
            record_code_mode_usage(
                self.run,
                self.invocation,
                input_bytes=self._input_size(raw["input"]),
                calls=1,
            )
        except AgentDomainError:
            return self._reject(raw, "BUDGET_EXCEEDED", 429)
        input_size = self._input_size(raw["input"])
        self.budget.input_bytes -= input_size
        self.budget.calls -= 1
        response, _status = self.gateway.execute(self.request, raw)
        response = self._stable_replay_response(raw, response)
        receipt = self._receipt(raw, response)
        encoded_size = len(canonical_json(receipt).encode("utf-8"))
        if encoded_size > self.budget.output_bytes:
            spill = self.spill_result(canonical_json(receipt))
            if spill.get("ok"):
                receipt.pop("result", None)
                receipt["result"] = {"spilled": spill}
                encoded_size = len(canonical_json(receipt).encode("utf-8"))
            else:
                return self._receipt_error(raw, response, "RESULT_TOO_LARGE", 409)
        if not self._record_output(encoded_size):
            return self._receipt_error(raw, response, "BUDGET_EXCEEDED", 429)
        return receipt

    def spill_result(self, payload: str | bytes) -> dict[str, Any]:
        """Route oversized bytes as bounded metadata through the audited gateway."""

        encoded = payload.encode("utf-8") if isinstance(payload, str) else payload
        size = len(encoded)
        raw = {
            "schema_version": "plane.operation/v1",
            "operation_id": "code_mode.spill",
            "workspace_slug": self.binding.workspace_slug,
            "idempotency_key": f"spill:{self.binding.invocation_ref}:{hashlib.sha256(encoded).hexdigest()}",
            "correlation_id": f"correlation:{self.binding.invocation_ref}",
            "input": {"size_bytes": size, "content_digest": hashlib.sha256(encoded).hexdigest()},
        }
        if size > self.budget.spill_bytes:
            return self._reject(raw, "SPILL_EXCEEDED", 409)
        invalid = self._preflight(raw)
        if invalid is not None:
            return invalid
        try:
            record_code_mode_usage(
                self.run,
                self.invocation,
                input_bytes=self._input_size(raw["input"]),
                calls=1,
                spill_bytes=size,
            )
        except AgentDomainError:
            return self._reject(raw, "SPILL_EXCEEDED", 409)
        self.budget.input_bytes -= self._input_size(raw["input"])
        self.budget.calls -= 1
        self.budget.spill_bytes -= size
        response, _status = self.gateway.execute(self.request, raw)
        response = self._stable_replay_response(raw, response)
        receipt = self._receipt(raw, response)
        if not self._record_output(len(canonical_json(receipt).encode("utf-8"))):
            return self._receipt_error(raw, response, "BUDGET_EXCEEDED", 429)
        return receipt

    def record_execution_usage(self, *, input_tokens=0, output_tokens=0, duration_ms: int | None = None) -> None:
        """Persist model usage reported by the trusted runner boundary."""

        elapsed = max(1, int((time.monotonic() - self._started_at) * 1000))
        if duration_ms is not None and (not isinstance(duration_ms, int) or duration_ms <= 0):
            raise AgentDomainError("Code Mode duration must be positive")
        effective_duration = elapsed if duration_ms is None else duration_ms
        record_code_mode_usage(
            self.run,
            self.invocation,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=effective_duration,
        )
        self.budget.input_tokens -= input_tokens
        self.budget.output_tokens -= output_tokens
        self.budget.duration_ms -= effective_duration

    def _load_trusted_binding(self, run: RunAttempt, invocation: RuntimeInvocation):
        request_actor_ref = getattr(self.request, "agent_actor_ref", None)
        if not isinstance(request_actor_ref, str) or not request_actor_ref:
            raise CodeModeBindingError("request.agent_actor_ref is required")
        try:
            stored_run = RunAttempt.objects.select_related("actor", "profile_version", "assignment", "workspace").get(
                pk=run.pk
            )
            stored_invocation = RuntimeInvocation.objects.select_related(
                "run", "run__actor", "run__profile_version", "run__workspace"
            ).get(pk=invocation.pk)
            snapshot = validate_run_snapshot(stored_run.snapshot)
            envelope = validate_invocation_envelope(stored_invocation.envelope)
            stored_run.validate_agent_scope()
            stored_invocation.validate_agent_scope()
            _dispatch_binding(snapshot, envelope, stored_invocation)
        except (
            AgentDomainError,
            ValidationError,
            RuntimeContractError,
            RuntimeDispatchError,
            RunAttempt.DoesNotExist,
            RuntimeInvocation.DoesNotExist,
        ) as exc:
            raise CodeModeBindingError("persisted Code Mode binding is invalid") from exc
        if stored_invocation.run_id != stored_run.id:
            raise CodeModeBindingError("invocation is not bound to the supplied run")
        if not stored_run.actor.is_active:
            raise CodeModeBindingError("AgentActor is inactive")
        if stored_run.state not in {RunState.QUEUED, RunState.RUNNING, RunState.WAITING_FOR_INPUT}:
            raise CodeModeBindingError("run is not active")
        if stored_invocation.state in {
            InvocationState.SUCCEEDED,
            InvocationState.FAILED,
            InvocationState.BLOCKED,
            InvocationState.CANCELLED,
            InvocationState.OUTCOME_UNKNOWN,
        }:
            raise CodeModeBindingError("invocation is terminal")
        expected_actor_ref = snapshot["actorRef"]
        expected_workspace_ref = snapshot["workspaceRef"]
        if request_actor_ref != expected_actor_ref:
            raise CodeModeBindingError("request actor is not bound to the stored run")
        request_workspace = getattr(self.request, "agent_workspace_ref", None)
        if request_workspace is not None and request_workspace != expected_workspace_ref:
            raise CodeModeBindingError("request workspace is not bound to the stored run")
        if stored_run.snapshot_content_digest != snapshot["contentDigest"]:
            raise CodeModeBindingError("run snapshot digest is not immutable")
        binding = HostBinding(
            actor_ref=expected_actor_ref,
            workspace_slug=stored_run.workspace.slug,
            run_ref=snapshot["runId"],
            invocation_ref=stored_invocation.invocation_id,
            catalog_digest=CATALOG_DIGEST,
        )
        if expected_workspace_ref != f"workspace:{stored_run.workspace_id}":
            raise CodeModeBindingError("workspace reference is not bound to the stored run")
        return stored_run, stored_invocation, binding, snapshot

    @staticmethod
    def _remaining_budget(run: RunAttempt, snapshot: Mapping[str, Any]) -> CodeModeBudget:
        used = run.cumulative_usage or {}
        code_mode_used = code_mode_usage_totals(run)
        total = snapshot["totalBudget"]
        policy = snapshot["runtimePolicy"]
        limits = {
            "input_bytes": policy.get("maxCodeModeInputBytes"),
            "output_bytes": policy.get("maxCodeModeOutputBytes"),
            "calls": policy.get("maxCodeModeCalls"),
            "spill_bytes": policy.get("maxArtifactBytes"),
        }
        if any(value is None for value in limits.values()):
            raise CodeModeBindingError("Code Mode limits are absent from the immutable run snapshot")
        return CodeModeBudget(
            input_tokens=max(
                0, int(total["inputTokens"]) - int(used.get("inputTokens", 0)) - code_mode_used["inputTokens"]
            ),
            output_tokens=max(
                0, int(total["outputTokens"]) - int(used.get("outputTokens", 0)) - code_mode_used["outputTokens"]
            ),
            input_bytes=max(0, int(limits["input_bytes"]) - code_mode_used["codeModeInputBytes"]),
            output_bytes=max(0, int(limits["output_bytes"]) - code_mode_used["codeModeOutputBytes"]),
            duration_ms=max(
                0, int(total["durationMs"]) - int(used.get("durationMs", 0)) - code_mode_used["durationMs"]
            ),
            calls=max(0, int(limits["calls"]) - code_mode_used["codeModeCalls"]),
            spill_bytes=max(0, int(limits["spill_bytes"]) - code_mode_used["codeModeSpillBytes"]),
        )

    @staticmethod
    def _input_size(value: Any) -> int:
        return len(canonical_json(value).encode("utf-8"))

    def _preflight(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        if self.binding.catalog_digest != CATALOG_DIGEST:
            return self._reject(raw, "CATALOG_MISMATCH", 409)
        if raw["workspace_slug"] != self.binding.workspace_slug:
            return self._reject(raw, "CALLBACK_BINDING_INVALID", 403)
        if getattr(self.request, "agent_actor_ref", None) != self.binding.actor_ref:
            return self._reject(raw, "CALLBACK_BINDING_INVALID", 403)
        if not isinstance(raw["input"], Mapping):
            return self._reject(raw, "VALIDATION_ERROR", 400)
        input_size = self._input_size(raw["input"])
        if input_size > self.budget.input_bytes:
            return self._reject(raw, "BUDGET_EXCEEDED", 429)
        if self.budget.calls <= 0 or self.budget.duration_ms <= 0:
            return self._reject(raw, "BUDGET_EXCEEDED", 429)
        if (time.monotonic() - self._started_at) * 1000 >= self.budget.duration_ms:
            return self._reject(raw, "BUDGET_EXCEEDED", 429)
        if self.is_cancelled():
            return self._reject(raw, "CANCELLED", 409)
        return None

    def _record_output(self, size: int) -> bool:
        if size > self.budget.output_bytes:
            return False
        try:
            record_code_mode_usage(self.run, self.invocation, output_bytes=size)
        except AgentDomainError:
            return False
        self.budget.output_bytes -= size
        return True

    def _reject(self, raw: Mapping[str, Any], code: str, status_code: int) -> dict[str, Any]:
        response, _status = self.gateway.record_invalid_request(
            self.request,
            dict(raw),
            code=code,
            status_code=status_code,
        )
        return self._receipt(raw, response)

    def _receipt(self, raw: Mapping[str, Any], response: Mapping[str, Any]) -> dict[str, Any]:
        idempotency = response.get("idempotency", {})
        receipt = {
            "schemaVersion": CODE_MODE_SCHEMA_VERSION,
            "callback": self.callback_surface().get(
                "spill" if raw["operation_id"] == "code_mode.spill" else "operation"
            ),
            "operationId": raw["operation_id"],
            "operationRef": f"operation:{raw['operation_id']}",
            "actorRef": self.binding.actor_ref,
            "workspaceRef": f"workspace:{self.run.workspace_id}",
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

    def _stable_replay_response(self, raw: Mapping[str, Any], response: Mapping[str, Any]) -> Mapping[str, Any]:
        """Make an exact host receipt replayable while preserving gateway audit."""

        if not response.get("idempotency", {}).get("replayed"):
            return response
        record = OperationGatewayIdempotency.objects.filter(
            workspace_slug=raw["workspace_slug"],
            caller_id=self.request.user.id,
            operation_id=raw["operation_id"],
            idempotency_key=raw["idempotency_key"],
        ).first()
        if record is None:
            return response
        stable = dict(response)
        stable["request_id"] = str(record.request_id)
        stable["correlation_id"] = record.correlation_id
        stable["audit_receipt"] = str(record.audit_receipt) if record.audit_receipt else response.get("audit_receipt")
        stable["idempotency"] = {"key": raw["idempotency_key"], "replayed": False}
        return stable

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
