"""Typed, persisted, credential-free host RPC for Code Mode."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any, Callable

from django.core.exceptions import ValidationError

from plane.agent.lifecycle import (
    AgentDomainError,
    code_mode_reserved_totals,
    code_mode_usage_totals,
    reap_code_mode_reservations,
    reconcile_code_mode_usage,
    reserve_code_mode_usage,
)
from plane.agent.lifecycle.runtime_contract import (
    RuntimeContractError,
    canonical_json,
    validate_invocation_envelope,
    validate_run_snapshot,
)
from plane.agent.runtime.dispatch import RuntimeDispatchError, _dispatch_binding
from plane.db.models import (
    InvocationState,
    OperationGatewayIdempotency,
    OutcomeSubmission,
    RunAttempt,
    RunState,
    RunTerminalEvent,
    RuntimeInvocation,
)
from plane.operation_gateway.catalog import CATALOG_DIGEST, code_mode_callback_names, get_operation
from plane.operation_gateway.gateway import OperationGateway, work_item_target_digest

from .contracts import (
    CODE_MODE_SCHEMA_VERSION,
    MAX_CODE_MODE_INLINE_RESULT_BYTES,
    MAX_CODE_MODE_OBSERVATIONS,
    MAX_CODE_MODE_OBSERVATIONS_BYTES,
    MAX_CODE_MODE_OBSERVATION_BYTES,
    CodeModeBudget,
    CodeModeExecutionRequest,
    HostBinding,
    SandboxPolicy,
)


class CodeModeBindingError(ValueError):
    """The callback was not bound to the immutable Plane runtime records."""


class CodeModeObservationError(AgentDomainError):
    """The bounded callback observation receipt cannot be extended safely."""

    code = "OBSERVATION_LIMIT"


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
        (
            self.run,
            self.invocation,
            self.binding,
            self._snapshot,
            self.gateway_request,
        ) = self._load_trusted_binding(run, invocation)
        self.run = reap_code_mode_reservations(self.run)
        self.budget = self._remaining_budget(self.run, self._snapshot)
        self.budget.spill_bytes = min(self.budget.spill_bytes, self.sandbox.max_spill_bytes)
        self._local_reserved = {
            "inputTokens": 0,
            "outputTokens": 0,
            "durationMs": 0,
            "codeModeInputBytes": 0,
            "codeModeOutputBytes": 0,
            "codeModeCalls": 0,
            "codeModeSpillBytes": 0,
        }
        self._execution_reservation = None
        self._started_at = time.monotonic()
        self._code_mode_observations: list[dict[str, Any]] = []
        self._code_mode_active = False
        self.max_inline_result_bytes = MAX_CODE_MODE_INLINE_RESULT_BYTES

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
        receipt = self._call_operation(
            operation_id,
            input_data,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            workspace_slug=workspace_slug,
        )
        self._record_code_mode_observation(operation_id, receipt)
        return receipt

    def _call_operation(
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
        if operation_id in {"agent.outcome.submit", "agent.outcome.publish"} and isinstance(raw["input"], Mapping):
            # The callback envelope is the trusted binding boundary.  A
            # model-supplied run_ref is redundant payload and is normalized
            # rather than allowed to redirect or poison this bound callback.
            raw["input"] = {**raw["input"], "run_ref": self.binding.run_ref}
        invalid = self._preflight(raw)
        if invalid is not None:
            return invalid
        terminal_observation = self._terminal_outcome_observation(raw)
        if terminal_observation is not None:
            return terminal_observation
        terminal_mutation_observation = self._terminal_mutation_observation(raw)
        if terminal_mutation_observation is not None:
            return terminal_mutation_observation
        if operation_id == "agent.outcome.publish":
            self.invocation.refresh_from_db(fields=["state"])
            if self.invocation.state in {
                InvocationState.SUCCEEDED,
                InvocationState.FAILED,
                InvocationState.BLOCKED,
                InvocationState.CANCELLED,
                InvocationState.OUTCOME_UNKNOWN,
            }:
                return self._publish_terminal_outcome(raw)
        descriptor = get_operation(operation_id)
        if descriptor is None:
            return self._reject(raw, "UNKNOWN_OPERATION", 404)
        input_size = self._input_size(raw["input"])
        output_reservation = descriptor.max_result_bytes + 4096
        if output_reservation > self._available("output_bytes"):
            return self._reject(raw, "BUDGET_EXCEEDED", 429)
        try:
            reservation = self._reserve(
                input_bytes=self._input_size(raw["input"]),
                output_bytes=output_reservation,
                calls=1,
                duration_ms=self._duration_reservation(),
            )
        except AgentDomainError:
            return self._reject(raw, "BUDGET_EXCEEDED", 429)
        reconciled = False
        terminalizes_invocation = operation_id in {"agent.outcome.submit", "agent.outcome.publish"}
        try:
            if terminalizes_invocation:
                # Outcome callbacks can transition the current invocation to a
                # terminal state. Commit this callback's bounded usage before
                # entering that lifecycle transition; reconciliation after it
                # would correctly reject usage on a terminal invocation.
                self._reconcile(
                    reservation,
                    input_bytes=input_size,
                    output_bytes=output_reservation,
                    calls=1,
                    duration_ms=max(1, int((time.monotonic() - self._started_at) * 1000)),
                )
                reconciled = True
            response, _status = self.gateway.execute(self.gateway_request, raw)
            response = self._stable_replay_response(raw, response)
            receipt = self._receipt(raw, response)
            encoded_size = len(canonical_json(receipt).encode("utf-8"))
            if encoded_size > output_reservation:
                return self._receipt_error(raw, response, "RESULT_TOO_LARGE", 409)
            if not terminalizes_invocation:
                self._reconcile(
                    reservation,
                    input_bytes=input_size,
                    output_bytes=encoded_size,
                    calls=1,
                    duration_ms=(
                        0
                        if self._execution_reservation is not None
                        else max(1, int((time.monotonic() - self._started_at) * 1000))
                    ),
                )
                reconciled = True
            return receipt
        finally:
            if not reconciled:
                self._release(reservation)

    def _terminal_outcome_observation(self, raw: Mapping[str, Any]) -> dict[str, Any] | None:
        """Return a stable observation for a duplicate submit after terminalization."""

        if raw.get("operation_id") != "agent.outcome.submit":
            return None
        input_data = raw.get("input")
        if not isinstance(input_data, Mapping):
            return None
        self.invocation.refresh_from_db(fields=["state"])
        self.run.refresh_from_db(fields=["state"])
        if self.run.state not in {
            RunState.SUCCEEDED,
            RunState.FAILED,
            RunState.BLOCKED,
            RunState.CANCELLED,
        }:
            return None
        outcome = OutcomeSubmission.objects.filter(run_id=self.run.id).order_by("created_at", "id").first()
        if outcome is None:
            return None
        terminal = RunTerminalEvent.objects.filter(invocation_id=self.invocation.pk, visible=True).first()
        outcome_result = {
            "outcomeRef": f"outcome-submission:{outcome.id}",
            "state": outcome.state,
            "summary": outcome.summary,
            "artifacts": outcome.artifacts,
            "evidence": outcome.evidence,
        }
        if terminal is not None:
            outcome_result["productEventRef"] = terminal.product_event_ref
        matches = all(
            input_data.get(field, []) == getattr(outcome, field)
            for field in ("artifacts", "evidence")
        ) and input_data.get("summary") == outcome.summary
        response: dict[str, Any]
        if matches:
            response = {
                "ok": True,
                "replayed": True,
                "correlation_id": raw["correlation_id"],
                "idempotency": {"key": raw["idempotency_key"], "replayed": True},
                "result": {"outcome": outcome_result},
            }
        else:
            response = {
                "ok": False,
                "replayed": False,
                "correlation_id": raw["correlation_id"],
                "idempotency": {"key": raw["idempotency_key"], "replayed": False},
                "error": {
                    "code": "PLANE_CONFLICT",
                    "message": "The current run already has a different terminal outcome.",
                    "retryable": False,
                },
            }
        receipt = self._receipt(raw, response)
        receipt["terminalObservation"] = True
        return receipt

    def _terminal_mutation_observation(self, raw: Mapping[str, Any]) -> dict[str, Any] | None:
        """Prevent a later same-batch mutation after terminal publication."""

        operation_id = raw.get("operation_id")
        if operation_id in {"agent.outcome.submit", "agent.outcome.publish"}:
            return None
        descriptor = get_operation(operation_id) if isinstance(operation_id, str) else None
        if descriptor is None or descriptor.kind != "mutation":
            return None
        self.run.refresh_from_db(fields=["state"])
        if self.run.state not in {
            RunState.SUCCEEDED,
            RunState.FAILED,
            RunState.BLOCKED,
            RunState.CANCELLED,
            RunState.OUTCOME_UNKNOWN,
        }:
            return None
        response = {
            "ok": False,
            "replayed": False,
            "correlation_id": raw["correlation_id"],
            "idempotency": {"key": raw["idempotency_key"], "replayed": False},
            "error": {
                "code": "PLANE_CONFLICT",
                "message": "The current run is terminal; no later mutation was applied.",
                "retryable": False,
            },
        }
        receipt = self._receipt(raw, response)
        receipt["terminalObservation"] = True
        return receipt

    def _publish_terminal_outcome(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        """Publish an existing outcome without adding usage after terminalization."""

        response, _status = self.gateway.execute(self.gateway_request, raw)
        response = self._stable_replay_response(raw, response)
        receipt = self._receipt(raw, response)
        descriptor = get_operation(raw["operation_id"])
        if descriptor is None:
            return self._receipt_error(raw, response, "UNKNOWN_OPERATION", 404)
        if len(canonical_json(receipt).encode("utf-8")) > descriptor.max_result_bytes + 4096:
            return self._receipt_error(raw, response, "RESULT_TOO_LARGE", 409)
        return receipt

    def execute_typescript(self, request: CodeModeExecutionRequest) -> dict[str, Any]:
        """Run one bounded generated module in the existing child isolate."""

        from .isolate import CodeModeIsolateRunner

        self._code_mode_observations = []
        self._code_mode_active = True
        try:
            result = CodeModeIsolateRunner().run(
                self,
                request.source,
                request.input_data,
            )
        finally:
            self._code_mode_active = False
        return {
            "schemaVersion": CODE_MODE_SCHEMA_VERSION,
            "actorRef": self.binding.actor_ref,
            "principalRef": self.binding.principal_ref,
            "workspaceRef": f"workspace:{self.run.workspace_id}",
            "runRef": self.binding.run_ref,
            "invocationRef": self.binding.invocation_ref,
            "result": result,
            "observations": list(self._code_mode_observations),
        }

    def _record_code_mode_observation(self, operation_id: str, receipt: Mapping[str, Any]) -> None:
        if not self._code_mode_active:
            return
        if len(self._code_mode_observations) >= MAX_CODE_MODE_OBSERVATIONS:
            raise CodeModeObservationError("Code Mode observation budget is exhausted")
        error = receipt.get("error")
        observation: dict[str, Any] = {
            "source": "code",
            "action": "code",
            "operationRef": f"operation:{operation_id}",
            "status": "replayed" if receipt.get("replayed") else ("ok" if receipt.get("ok") else "denied"),
            "requestId": receipt.get("requestId"),
            "gatewayReceipt": receipt.get("gatewayReceipt"),
            "auditReceipt": receipt.get("auditReceipt"),
        }
        if isinstance(error, Mapping) and isinstance(error.get("code"), str):
            observation["errorCode"] = error["code"]
        target_digest = receipt.get("targetDigest")
        if isinstance(target_digest, str):
            observation["targetDigest"] = target_digest
        if len(canonical_json(observation).encode("utf-8")) > MAX_CODE_MODE_OBSERVATION_BYTES:
            raise CodeModeObservationError("Code Mode observation exceeds its size bound")
        if (
            len(canonical_json(self._code_mode_observations + [observation]).encode("utf-8"))
            > MAX_CODE_MODE_OBSERVATIONS_BYTES
        ):
            raise CodeModeObservationError("Code Mode observations exceed their size bound")
        self._code_mode_observations.append(observation)

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
        invalid = self._preflight(raw)
        if invalid is not None:
            return invalid
        if size > self._available("spill_bytes"):
            return self._reject(raw, "SPILL_EXCEEDED", 409)
        output_reservation = 1024 + 4096
        if output_reservation > self._available("output_bytes"):
            return self._reject(raw, "BUDGET_EXCEEDED", 429)
        try:
            reservation = self._reserve(
                input_bytes=self._input_size(raw["input"]),
                output_bytes=output_reservation,
                calls=1,
                spill_bytes=size,
                duration_ms=self._duration_reservation(),
            )
        except AgentDomainError:
            return self._reject(raw, "SPILL_EXCEEDED", 409)
        reconciled = False
        try:
            response, _status = self.gateway.execute(self.gateway_request, raw)
            response = self._stable_replay_response(raw, response)
            receipt = self._receipt(raw, response)
            encoded_size = len(canonical_json(receipt).encode("utf-8"))
            if encoded_size > output_reservation:
                return self._receipt_error(raw, response, "RESULT_TOO_LARGE", 409)
            self._reconcile(
                reservation,
                input_bytes=self._input_size(raw["input"]),
                output_bytes=encoded_size,
                calls=1,
                spill_bytes=size,
                duration_ms=(
                    0
                    if self._execution_reservation is not None
                    else max(1, int((time.monotonic() - self._started_at) * 1000))
                ),
            )
            reconciled = True
            return receipt
        finally:
            if not reconciled:
                self._release(reservation)

    def record_execution_usage(
        self,
        *,
        input_bytes=0,
        input_tokens=0,
        output_tokens=0,
        duration_ms: int | None = None,
    ) -> None:
        """Persist model usage reported by the trusted runner boundary."""

        elapsed = max(1, int((time.monotonic() - self._started_at) * 1000))
        if duration_ms is not None and (not isinstance(duration_ms, int) or duration_ms <= 0):
            raise AgentDomainError("Code Mode duration must be positive")
        effective_duration = elapsed if duration_ms is None else duration_ms
        reservation = self._execution_reservation
        if reservation is None:
            reservation = self._reserve(
                input_bytes=input_bytes,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=effective_duration,
            )
        self._reconcile(
            reservation,
            input_bytes=input_bytes,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=effective_duration,
        )
        self._execution_reservation = None

    def reserve_execution_budget(self, *, input_bytes=0, input_tokens=0, output_tokens=0) -> None:
        """Reserve trusted runner usage before generated code can invoke Plane."""

        if self._execution_reservation is not None:
            return
        if self.budget.input_tokens <= 0 or self.budget.output_tokens <= 0 or self.budget.duration_ms <= 0:
            raise AgentDomainError("Code Mode execution budget is exhausted")
        self._execution_reservation = self._reserve(
            input_bytes=input_bytes,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=self.budget.duration_ms,
        )

    def release_execution_budget(self) -> None:
        if self._execution_reservation is not None:
            self._release(self._execution_reservation)
            self._execution_reservation = None

    def _load_trusted_binding(self, run: RunAttempt, invocation: RuntimeInvocation):
        request_actor_ref = getattr(self.request, "agent_actor_ref", None)
        if not isinstance(request_actor_ref, str) or not request_actor_ref:
            raise CodeModeBindingError("request.agent_actor_ref is required")
        try:
            stored_run = RunAttempt.objects.select_related(
                "actor", "actor__principal", "profile_version", "assignment", "workspace"
            ).get(pk=run.pk)
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
        principal = stored_run.actor.principal
        if not principal.is_active or not principal.is_bot:
            raise CodeModeBindingError("AgentActor principal is not an active dedicated Plane identity")
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
            principal_ref=str(principal.id),
            workspace_slug=stored_run.workspace.slug,
            run_ref=snapshot["runId"],
            invocation_ref=stored_invocation.invocation_id,
            catalog_digest=CATALOG_DIGEST,
        )
        if expected_workspace_ref != f"workspace:{stored_run.workspace_id}":
            raise CodeModeBindingError("workspace reference is not bound to the stored run")
        gateway_request = SimpleNamespace(
            user=principal,
            META=getattr(self.request, "META", {}),
            agent_actor_ref=expected_actor_ref,
            agent_workspace_ref=expected_workspace_ref,
            agent_run_ref=snapshot["runId"],
            agent_invocation_ref=stored_invocation.invocation_id,
        )
        return stored_run, stored_invocation, binding, snapshot, gateway_request

    @staticmethod
    def _remaining_budget(run: RunAttempt, snapshot: Mapping[str, Any]) -> CodeModeBudget:
        used = run.cumulative_usage or {}
        code_mode_used = code_mode_usage_totals(run)
        code_mode_reserved = code_mode_reserved_totals(run)
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
                0,
                int(total["inputTokens"]) - int(used.get("inputTokens", 0)) - code_mode_reserved["inputTokens"],
            ),
            output_tokens=max(
                0,
                int(total["outputTokens"]) - int(used.get("outputTokens", 0)) - code_mode_reserved["outputTokens"],
            ),
            input_bytes=max(
                0,
                int(limits["input_bytes"])
                - code_mode_used["codeModeInputBytes"]
                - code_mode_reserved["codeModeInputBytes"],
            ),
            output_bytes=max(
                0,
                int(limits["output_bytes"])
                - code_mode_used["codeModeOutputBytes"]
                - code_mode_reserved["codeModeOutputBytes"],
            ),
            duration_ms=max(
                0,
                int(total["durationMs"]) - int(used.get("durationMs", 0)) - code_mode_reserved["durationMs"],
            ),
            calls=max(
                0,
                int(limits["calls"]) - code_mode_used["codeModeCalls"] - code_mode_reserved["codeModeCalls"],
            ),
            spill_bytes=max(
                0,
                int(limits["spill_bytes"])
                - code_mode_used["codeModeSpillBytes"]
                - code_mode_reserved["codeModeSpillBytes"],
            ),
        )

    @staticmethod
    def _input_size(value: Any) -> int:
        return len(canonical_json(value).encode("utf-8"))

    def _available(self, field: str) -> int:
        local_field = {
            "input_tokens": "inputTokens",
            "output_tokens": "outputTokens",
            "duration_ms": "durationMs",
            "input_bytes": "codeModeInputBytes",
            "output_bytes": "codeModeOutputBytes",
            "calls": "codeModeCalls",
            "spill_bytes": "codeModeSpillBytes",
        }[field]
        if field == "duration_ms" and self._execution_reservation is not None:
            return self.budget.duration_ms
        return max(0, getattr(self.budget, field) - self._local_reserved[local_field])

    def _duration_reservation(self) -> int:
        if self._execution_reservation is not None:
            return 0
        return max(1, self.budget.duration_ms)

    def _reserve(
        self,
        *,
        input_tokens=0,
        output_tokens=0,
        duration_ms=0,
        input_bytes=0,
        output_bytes=0,
        calls=0,
        spill_bytes=0,
    ):
        self.run, reservation = reserve_code_mode_usage(
            self.run,
            self.invocation,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
            input_bytes=input_bytes,
            output_bytes=output_bytes,
            calls=calls,
            spill_bytes=spill_bytes,
        )
        for field, amount in {
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "durationMs": duration_ms,
            "codeModeInputBytes": input_bytes,
            "codeModeOutputBytes": output_bytes,
            "codeModeCalls": calls,
            "codeModeSpillBytes": spill_bytes,
        }.items():
            self._local_reserved[field] += amount
        return reservation

    def _reconcile(
        self,
        reservation,
        *,
        input_tokens=0,
        output_tokens=0,
        duration_ms=0,
        input_bytes=0,
        output_bytes=0,
        calls=0,
        spill_bytes=0,
    ):
        self.run = reconcile_code_mode_usage(
            self.run,
            self.invocation,
            reservation,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
            input_bytes=input_bytes,
            output_bytes=output_bytes,
            calls=calls,
            spill_bytes=spill_bytes,
        )
        for field, reserved_amount, actual_amount in (
            ("inputTokens", reservation["usage"].get("inputTokens", 0), input_tokens),
            ("outputTokens", reservation["usage"].get("outputTokens", 0), output_tokens),
            ("durationMs", reservation["usage"].get("durationMs", 0), duration_ms),
            ("codeModeInputBytes", reservation["usage"].get("codeModeInputBytes", 0), input_bytes),
            ("codeModeOutputBytes", reservation["usage"].get("codeModeOutputBytes", 0), output_bytes),
            ("codeModeCalls", reservation["usage"].get("codeModeCalls", 0), calls),
            ("codeModeSpillBytes", reservation["usage"].get("codeModeSpillBytes", 0), spill_bytes),
        ):
            self._local_reserved[field] -= reserved_amount
            budget_field = {
                "inputTokens": "input_tokens",
                "outputTokens": "output_tokens",
                "durationMs": "duration_ms",
                "codeModeInputBytes": "input_bytes",
                "codeModeOutputBytes": "output_bytes",
                "codeModeCalls": "calls",
                "codeModeSpillBytes": "spill_bytes",
            }[field]
            setattr(self.budget, budget_field, max(0, getattr(self.budget, budget_field) - actual_amount))

    def _release(self, reservation):
        self._reconcile(reservation)

    def _preflight(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        if self._code_mode_active:
            try:
                self._load_trusted_binding(self.run, self.invocation)
            except CodeModeBindingError:
                return self._reject(raw, "CALLBACK_BINDING_INVALID", 403)
        if self.binding.catalog_digest != CATALOG_DIGEST:
            return self._reject(raw, "CATALOG_MISMATCH", 409)
        if raw["workspace_slug"] != self.binding.workspace_slug:
            return self._reject(raw, "CALLBACK_BINDING_INVALID", 403)
        if str(getattr(getattr(self.request, "user", None), "id", "")) != self.binding.principal_ref:
            return self._reject(raw, "NOT_AUTHORIZED", 403)
        if getattr(self.request, "agent_actor_ref", None) != self.binding.actor_ref:
            return self._reject(raw, "CALLBACK_BINDING_INVALID", 403)
        if not isinstance(raw["input"], Mapping):
            return self._reject(raw, "VALIDATION_ERROR", 400)
        input_size = self._input_size(raw["input"])
        if input_size > self._available("input_bytes"):
            return self._reject(raw, "BUDGET_EXCEEDED", 429)
        if (
            self._available("output_bytes") <= 0
            or self._available("spill_bytes") <= 0
            or self._available("calls") <= 0
            or self.budget.input_tokens <= 0
            or self.budget.output_tokens <= 0
            or self.budget.duration_ms <= 0
        ):
            return self._reject(raw, "BUDGET_EXCEEDED", 429)
        if (time.monotonic() - self._started_at) * 1000 >= self.budget.duration_ms:
            return self._reject(raw, "BUDGET_EXCEEDED", 429)
        if self.is_cancelled():
            return self._reject(raw, "CANCELLED", 409)
        return None

    def _record_output(self, size: int) -> bool:
        if size > self._available("output_bytes"):
            return False
        try:
            reservation = self._reserve(output_bytes=size)
            self._reconcile(reservation, output_bytes=size)
        except AgentDomainError:
            return False
        return True

    def _reject(self, raw: Mapping[str, Any], code: str, status_code: int) -> dict[str, Any]:
        response, _status = self.gateway.record_invalid_request(
            self.gateway_request,
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
            "principalRef": self.binding.principal_ref,
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
        target_digest = self._target_digest(raw)
        if target_digest is not None:
            receipt["targetDigest"] = target_digest
        return receipt

    @staticmethod
    def _target_digest(raw: Mapping[str, Any]) -> str | None:
        """Expose only a stable discriminator for semantic work-item targets."""

        return work_item_target_digest(raw.get("operation_id"), raw.get("input"))

    def _stable_replay_response(self, raw: Mapping[str, Any], response: Mapping[str, Any]) -> Mapping[str, Any]:
        """Keep replay results stable, except where publication needs disposition."""

        if not response.get("idempotency", {}).get("replayed"):
            return response
        record = OperationGatewayIdempotency.objects.filter(
            workspace_slug=raw["workspace_slug"],
            caller_id=self.gateway_request.user.id,
            operation_id=raw["operation_id"],
            idempotency_key=raw["idempotency_key"],
        ).first()
        if record is None:
            return response
        stable = dict(response)
        stable["request_id"] = str(record.request_id)
        stable["correlation_id"] = record.correlation_id
        stable["audit_receipt"] = str(record.audit_receipt) if record.audit_receipt else response.get("audit_receipt")
        stable["idempotency"] = {
            "key": raw["idempotency_key"],
            "replayed": raw["operation_id"] == "agent.outcome.publish",
        }
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
