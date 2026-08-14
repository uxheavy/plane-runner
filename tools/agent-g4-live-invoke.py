"""One disposable Plane supervisor invocation for the configured G4 proof."""

from __future__ import annotations

# Django must be initialized before importing Plane models and lifecycle services.
# ruff: noqa: E402

import io
import json
import os
import secrets
import sys
import time
import uuid

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plane.settings.test")
sys.path.insert(0, "/workspace/apps/api")

import django

django.setup()

from django.core.management import call_command
from plane.agent.lifecycle import (
    create_actor,
    create_assignment,
    create_profile,
    create_run,
    finalize_invocation,
    record_invocation,
    reconcile_provider_attempts,
)
from plane.db.models import (
    AgentRole,
    InvocationState,
    Issue,
    OutcomeSubmission,
    Project,
    ProjectMember,
    RunTerminalEvent,
    RuntimeInvocationControl,
    RuntimeProviderAttempt,
    RuntimeEventIngress,
    RuntimeExitEvidence,
    RuntimeUsageObservation,
    State,
    User,
    Workspace,
    WorkspaceMember,
)
from plane.db.models.operation_gateway import OperationGatewayAudit


def _binding() -> dict[str, str]:
    candidate = os.environ["G4_CANDIDATE"]
    expected_candidate = os.environ["G4_EXPECTED_CANDIDATE"]
    if (
        len(candidate) != 40
        or len(expected_candidate) != 40
        or any(character not in "0123456789abcdef" for character in candidate + expected_candidate)
        or candidate != expected_candidate
    ):
        raise RuntimeError("live invocation candidate does not match the external expectedCandidate")
    return {
        "candidateCommit": candidate,
        "g3Baseline": os.environ["G4_G3_BASELINE"],
        "hermesCommit": os.environ["G4_HERMES"],
        "mcpGitlink": os.environ["G4_MCP"],
        "sdkGitlink": os.environ["G4_SDK"],
        "runtimeImageTag": os.environ["G4_RUNTIME_IMAGE_TAG"],
        "runtimeImageDigest": os.environ["G4_RUNTIME_IMAGE_DIGEST"],
        "runtimeImageRevision": os.environ["G4_RUNTIME_IMAGE_REVISION"],
        "runtimeContract": os.environ["G4_RUNTIME_CONTRACT"],
        "apiArtifact": {
            "imageTag": os.environ["G4_API_IMAGE_TAG"],
            "imageDigest": os.environ["G4_API_IMAGE_DIGEST"],
            "sourceRevision": os.environ["G4_API_SOURCE_REVISION"],
            "contract": os.environ["G4_API_CONTRACT"],
        },
    }


def _provider_descriptor() -> dict[str, str]:
    """Require the API invocation environment to equal validated authority data."""

    try:
        descriptor = json.loads(os.environ["G4_PROVIDER_DESCRIPTOR_JSON"])
    except (KeyError, json.JSONDecodeError) as exc:
        raise RuntimeError("live invocation provider descriptor is unavailable") from exc
    fields = {
        "name": "PLANE_AGENT_RUNTIME_PROVIDER",
        "model": "PLANE_AGENT_RUNTIME_PROVIDER_MODELS",
        "baseUrl": "PLANE_AGENT_RUNTIME_PROVIDER_BASE_URL",
        "host": "PLANE_AGENT_RUNTIME_PROVIDER_HOST",
        "path": "PLANE_AGENT_RUNTIME_PROVIDER_PATH",
        "credentialSource": "PLANE_AGENT_RUNTIME_PROVIDER_CREDENTIAL_SOURCE",
        "credentialRef": "PLANE_AGENT_RUNTIME_PROVIDER_CREDENTIAL_REF",
        "credentialName": "PLANE_AGENT_RUNTIME_PROVIDER_CREDENTIAL_NAME",
    }
    if set(descriptor) != set(fields) or any(
        not isinstance(descriptor[key], str) or not descriptor[key] for key in fields
    ):
        raise RuntimeError("live invocation provider descriptor is malformed")
    if any(os.environ.get(environment_key) != descriptor[key] for key, environment_key in fields.items()):
        raise RuntimeError("live invocation provider descriptor environment mismatch")
    return descriptor


def build_failure_evidence(
    *,
    binding,
    failure_phase,
    error_class,
    exit_code,
    run_id,
    run_state,
    invocation_id,
    invocation_state,
    provider_attempts,
    terminal_kind,
    failure_code=None,
    failure_reason=None,
    runtime_exit=None,
    runtime_event_kind_counts=None,
    terminal_code=None,
    terminal_reason=None,
    plane_host_operation_receipts=False,
):
    """Return one bounded failure object without copying runtime observations."""

    import json

    binding_fields = (
        "candidateCommit",
        "g3Baseline",
        "hermesCommit",
        "mcpGitlink",
        "sdkGitlink",
        "runtimeImageTag",
        "runtimeImageDigest",
        "runtimeImageRevision",
        "runtimeContract",
        "apiArtifact",
    )
    failure_stages = {
        "initialization",
        "compose",
        "audit-bootstrap",
        "runtime-start",
        "runtime-health",
        "api-invocation",
    }
    error_classes = {
        "CommandError",
        "ConnectionError",
        "FileNotFoundError",
        "ImportError",
        "ImproperlyConfigured",
        "ModuleNotFoundError",
        "OperationalError",
        "PermissionError",
        "RuntimeError",
        "TimeoutError",
    }
    invocation_states = {
        "queued",
        "running",
        "waiting_for_input",
        "succeeded",
        "failed",
        "blocked",
        "cancelled",
        "outcome_unknown",
    }
    attempt_phases = {"intent", "started", "completed", "failed", "outcome_unknown"}
    status_classes = {"", "not_sent", "unknown", "2xx", "4xx", "5xx"}
    error_codes = {"", "pre_send_failure", "outcome_unknown", "provider_error", "runtime_error", "upstream_error"}
    terminal_kinds = {"none", "outcome_submission", "run_failure", "run_blocker", "run_cancellation"}
    failure_codes = {
        "runtime_transport_pre_dispatch_failure",
        "runtime_configuration_pre_dispatch_failure",
        "runtime_process_failed",
        "runtime_process_timeout",
        "runtime_process_cancelled",
        "runtime_process_output_invalid",
        "runtime_supervisor_pre_dispatch_failure",
        "budget_exhausted",
        "runtime_error",
        "missing_outcome",
        "outcome_unknown",
    }
    reason_phases = {"runtime_transport", "runtime_configuration", "runtime_process", "launcher", "runtime_supervisor"}
    failure_details = {
        "dispatch_rejected",
        "process_start_failed",
        "process_exit",
        "bootstrap_argv_rejected",
        "process_timeout",
        "process_cancelled",
        "process_output_invalid",
        "unclassified_exception",
        "missing_outcome",
    }
    failure_subreasons = {
        "credential_reference_not_allowed",
        "credential_source_unavailable",
        "credential_source_invalid",
        "credential_source_oversized",
        "credential_resolver_failed",
        "credential_resolver_output_invalid",
        "credential_lease_binding",
        "credential_lease_expired",
        "credential_lease_revoked",
        "credential_lease_rotated",
        "credential_lease_metadata_invalid",
        "credential_state_unavailable",
        "credential_state_invalid",
        "provider_attempt_evidence_rejected",
        "runtime_configuration_rejected",
        "model_call_budget_exhausted",
        "runtime_execution_failed",
        "completed_without_explicit_outcome",
    }
    runtime_exit_kinds = {"completed", "waiting_for_input", "failed", "blocked", "cancelled"}
    runtime_failure_codes = {"budget_exhausted", "runtime_error"}
    runtime_event_kinds = {
        "progress_observed",
        "conversation_publication_observed",
        "input_request_observed",
        "artifact_observed",
        "usage_observed",
        "outcome_submission_observed",
        "failure_observed",
        "blocker_observed",
    }
    terminal_reason_categories = failure_details | failure_subreasons

    def bounded_identifier(value):
        if value is None:
            return None
        text = str(value)
        allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.:-"
        if (
            len(text.encode("utf-8")) > 128
            or not text
            or any(char not in allowed for char in text)
            or any(ord(char) < 0x20 or ord(char) == 0x7F for char in text)
        ):
            return "unavailable"
        return text

    def bounded_binding_value(key, value):
        if not isinstance(value, str) or len(value.encode("utf-8")) > 128:
            return "unavailable"
        hexadecimal = "0123456789abcdef"
        if key in {"candidateCommit", "g3Baseline", "hermesCommit", "mcpGitlink", "sdkGitlink", "runtimeImageRevision"}:
            return value if len(value) == 40 and all(char in hexadecimal for char in value) else "unavailable"
        if key == "runtimeImageDigest":
            digest_prefix, separator, digest = value.partition(":")
            return (
                value
                if digest_prefix == "sha256"
                and separator
                and len(digest) == 64
                and all(char in hexadecimal for char in digest)
                else "unavailable"
            )
        allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._:/-"
        if not value or any(char not in allowed for char in value):
            return "unavailable"
        return value

    def bounded_state(value):
        return value if value in invocation_states else "unknown"

    bounded_binding = {
        key: bounded_binding_value(key, binding[key])
        for key in binding_fields
        if isinstance(binding, dict) and key in binding and key != "apiArtifact"
    }
    if isinstance(binding, dict) and "apiArtifact" in binding:
        artifact = binding["apiArtifact"]
        if not isinstance(artifact, dict) or set(artifact) != {"imageTag", "imageDigest", "sourceRevision", "contract"}:
            bounded_binding["apiArtifact"] = {
                "imageTag": "unavailable",
                "imageDigest": "unavailable",
                "sourceRevision": "unavailable",
                "contract": "unavailable",
            }
        else:
            bounded_binding["apiArtifact"] = {
                "imageTag": bounded_binding_value("apiImageTag", artifact["imageTag"]),
                "imageDigest": bounded_binding_value("runtimeImageDigest", artifact["imageDigest"]),
                "sourceRevision": bounded_binding_value("runtimeImageRevision", artifact["sourceRevision"]),
                "contract": bounded_binding_value("apiContract", artifact["contract"]),
            }
    attempts = []
    for row in list(provider_attempts or [])[:32]:
        if not isinstance(row, dict):
            continue
        phase = row.get("phase") if row.get("phase") in attempt_phases else "unknown"
        status_class = row.get("statusClass") if row.get("statusClass") in status_classes else "unknown"
        error_code = row.get("errorCode") if row.get("errorCode") in error_codes else "unspecified"
        sequence = row.get("sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1 or sequence > 256:
            sequence = 0
        attempts.append(
            {
                "sequence": sequence,
                "phase": phase,
                "upstreamInitiated": row.get("upstreamInitiated") is True,
                "statusClass": status_class,
                "errorCode": error_code,
            }
        )

    if not isinstance(exit_code, int) or isinstance(exit_code, bool) or not 1 <= exit_code <= 255:
        exit_code = 1

    reason = {}
    if isinstance(failure_reason, str):
        try:
            candidate = json.loads(failure_reason)
        except (TypeError, ValueError):
            candidate = None
        if isinstance(candidate, dict) and set(candidate) in (
            {"failureCode", "failurePhase", "failureDetail"},
            {"failureCode", "failurePhase", "failureDetail", "failureSubreason"},
        ):
            reason = candidate
    reason_code = reason.get("failureCode")
    bounded_failure_code = (
        reason_code
        if isinstance(reason_code, str) and reason_code in failure_codes
        else failure_code
        if isinstance(failure_code, str) and failure_code in failure_codes
        else "unspecified"
    )
    reason_phase = reason.get("failurePhase")
    reason_detail = reason.get("failureDetail")
    bounded_failure_phase = (
        reason_phase if isinstance(reason_phase, str) and reason_phase in reason_phases else "unavailable"
    )
    bounded_failure_detail = (
        reason_detail if isinstance(reason_detail, str) and reason_detail in failure_details else "unavailable"
    )
    reason_subreason = reason.get("failureSubreason")
    bounded_failure_subreason = (
        reason_subreason
        if isinstance(reason_subreason, str) and reason_subreason in failure_subreasons
        else "unavailable"
    )

    bounded_runtime_exit = {"present": False, "kind": "unknown", "failure": None}
    if isinstance(runtime_exit, dict):
        runtime_exit_kind = runtime_exit.get("kind")
        bounded_runtime_exit["present"] = True
        bounded_runtime_exit["kind"] = (
            runtime_exit_kind if runtime_exit_kind in runtime_exit_kinds else "unknown"
        )
        runtime_failure = runtime_exit.get("failure")
        if isinstance(runtime_failure, dict):
            runtime_failure_code = runtime_failure.get("code")
            bounded_runtime_exit["failure"] = {
                "code": runtime_failure_code if runtime_failure_code in runtime_failure_codes else "unavailable",
                "retryable": runtime_failure.get("retryable") is True,
            }

    bounded_event_kind_counts = {}
    if isinstance(runtime_event_kind_counts, dict):
        for kind, count in list(runtime_event_kind_counts.items())[: len(runtime_event_kinds)]:
            if kind not in runtime_event_kinds:
                continue
            if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 256:
                continue
            bounded_event_kind_counts[kind] = count

    bounded_terminal_code = (
        terminal_code if isinstance(terminal_code, str) and terminal_code in failure_codes else "unavailable"
    )
    bounded_terminal_reason_category = "unavailable"
    if isinstance(terminal_reason, str):
        try:
            terminal_reason_value = json.loads(terminal_reason)
        except (TypeError, ValueError):
            terminal_reason_value = None
        if isinstance(terminal_reason_value, dict):
            category = terminal_reason_value.get("failureSubreason") or terminal_reason_value.get("failureDetail")
            if category in terminal_reason_categories:
                bounded_terminal_reason_category = category

    if terminal_kind not in terminal_kinds:
        terminal_kind = "unknown"
    if terminal_kind == "unknown":
        terminal = {"present": False, "kind": "unknown"}
    else:
        terminal = {"present": terminal_kind != "none", "kind": terminal_kind}
    if terminal["present"]:
        terminal.update(
            {
                "code": bounded_terminal_code,
                "reasonCategory": bounded_terminal_reason_category,
            }
        )

    return {
        "schemaVersion": "plane-agent-g4/live-failure/v1",
        "status": "failed",
        "binding": bounded_binding,
        "failure": {
            "phase": failure_phase if failure_phase in failure_stages else "unknown",
            "errorClass": error_class if error_class in error_classes else "unspecified",
            "exitCode": exit_code,
            "reasonCode": bounded_failure_code,
            "reasonPhase": bounded_failure_phase,
            "reasonDetail": bounded_failure_detail,
            "reasonSubreason": bounded_failure_subreason,
        },
        "run": {"present": run_id is not None, "id": bounded_identifier(run_id), "state": bounded_state(run_state)},
        "invocation": {
            "present": invocation_id is not None,
            "id": bounded_identifier(invocation_id),
            "state": bounded_state(invocation_state),
        },
        "runtimeExit": bounded_runtime_exit,
        "runtimeEventIngress": {"kindCounts": bounded_event_kind_counts},
        "providerAttempts": attempts,
        "terminal": terminal,
        "planeHostOperationReceipts": plane_host_operation_receipts is True,
    }


def _supervisor_failure_reason(output):
    """Extract only the bounded dispatch classification emitted by Plane."""

    import json

    if not isinstance(output, str):
        return None
    allowed_keys = {
        "failureCode",
        "failurePhase",
        "failureDetail",
        "failureSubreason",
    }
    required_keys = allowed_keys - {"failureSubreason"}
    for line in reversed(output.splitlines()):
        marker = " failure="
        if marker not in line:
            continue
        raw = line.rsplit(marker, 1)[1]
        try:
            value = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if not isinstance(value, dict) or set(value) not in (required_keys, allowed_keys):
            continue
        if not all(isinstance(item, str) for item in value.values()):
            continue
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return None


def main() -> int:
    started = time.monotonic()
    provider = _provider_descriptor()
    suffix = uuid.uuid4().hex[:12]
    run = None
    invocation = None
    actor = None
    binding = {}
    evidence = None
    failure = None
    return_code = 0
    provider_attempts = []
    terminal = None
    control = None
    exit_evidence = None
    runtime_event_kind_counts = {}
    plane_host_operation_receipts = False
    supervisor_failure_reason = None

    def readback():
        invocation.refresh_from_db()
        run.refresh_from_db()
        attempts = list(RuntimeProviderAttempt.objects.filter(invocation=invocation).order_by("sequence")[:32])
        current_terminal = RunTerminalEvent.objects.filter(invocation=invocation, visible=True).first()
        control = RuntimeInvocationControl.objects.filter(invocation=invocation).first()
        current_exit = RuntimeExitEvidence.objects.filter(invocation=invocation).first()
        event_kind_counts = {}
        for kind in RuntimeEventIngress.objects.filter(invocation=invocation).order_by("sequence").values_list(
            "kind", flat=True
        )[:256]:
            event_kind_counts[kind] = min(event_kind_counts.get(kind, 0) + 1, 256)
        host_receipts = OperationGatewayAudit.objects.filter(correlation_id=f"correlation:{run.id}").exists()
        return attempts, current_terminal, control, current_exit, event_kind_counts, host_receipts

    try:
        email = f"g4-live-{suffix}@plane.test"
        user = User.objects.create(email=email, username=email, first_name="G4", last_name="Live")
        user.set_password(secrets.token_urlsafe(32))
        user.save(update_fields=["password"])
        workspace = Workspace.objects.create(name=f"G4 Live {suffix}", owner=user, slug=f"g4-live-{suffix}")
        WorkspaceMember.objects.create(workspace=workspace, member=user, role=20)
        project = Project.objects.create(
            name="G4 Live Project", identifier=f"G{suffix[:2].upper()}", workspace=workspace, created_by=user
        )
        ProjectMember.objects.create(project=project, member=user, role=20, is_active=True)
        State.objects.create(
            name="Backlog",
            color="#000000",
            group="backlog",
            default=True,
            project=project,
            workspace=workspace,
            created_by=user,
        )
        issue = Issue.objects.create(name="G4 Live Issue", project=project, workspace=workspace, created_by=user)
        actor = create_actor(
            workspace=workspace,
            project=project,
            display_name="G4 configured provider worker",
            credential_ref="plane-credential:g4-live",
            created_by=user,
        )
        profile = create_profile(
            actor,
            role=AgentRole.WORKER,
            instructions=(
                "Complete this one live G4 chain check through Plane tools. First discover and read the assigned issue "
                "using a permitted operation. Then deliberately attempt agent.outcome.evaluate as this worker so the "
                "authorization canary is denied. Finally call agent.outcome.submit and then agent.outcome.publish with "
                "a minimal structural summary. Do not stop at ordinary assistant text: the explicit submit and publish "
                "product operations are required terminal evidence. Do not use Code Mode or external tools."
            ),
            runtime_defaults={
                "provider": provider["name"],
                "model": provider["model"],
                "adapter": "hermes",
            },
            created_by=user,
        )
        assignment = create_assignment(
            actor,
            project=project,
            target_ref=f"issue:{issue.id}",
            objective="Perform one live provider-backed read, authorization canary, and explicit published outcome.",
            acceptance_criteria=[
                "A permitted read, denied evaluation, and explicit submitted and published outcome exist."
            ],
            created_by=user,
        )
        run = create_run(assignment, profile, idempotency_key=f"idempotency:g4-live-run-{suffix}", created_by=user)
        invocation = record_invocation(run, idempotency_key=f"idempotency:g4-live-invocation-{suffix}", trigger="initial")
        stdout = io.StringIO()
        stderr = io.StringIO()
        call_command(
            "agent_supervisor",
            invocation_ref=invocation.invocation_id,
            worker_id="g4-live-configured-worker",
            lease_seconds=300,
            model_call_allowance=16,
            stdout=stdout,
            stderr=stderr,
        )
        supervisor_failure_reason = _supervisor_failure_reason(stdout.getvalue())
        (
            provider_attempts,
            terminal,
            control,
            exit_evidence,
            runtime_event_kind_counts,
            plane_host_operation_receipts,
        ) = readback()
        correlation_id = f"correlation:{run.id}"
        audits = OperationGatewayAudit.objects.filter(correlation_id=correlation_id)
        permitted = audits.filter(phase="outcome", outcome="success", operation_id="work_item.read").exists()
        if not permitted:
            permitted = audits.filter(phase="outcome", outcome="success", operation_id="catalog.search").exists()
        denied = audits.filter(
            phase="outcome", outcome="denied", operation_id="agent.outcome.evaluate", error_code="NOT_AUTHORIZED"
        ).exists()
        submitted = audits.filter(phase="outcome", outcome="success", operation_id="agent.outcome.submit").exists()
        published = audits.filter(phase="outcome", outcome="success", operation_id="agent.outcome.publish").exists()
        usage = RuntimeUsageObservation.objects.filter(invocation=invocation).first()
        event_count = RuntimeEventIngress.objects.filter(invocation=invocation).count()
        outcome_count = OutcomeSubmission.objects.filter(run=run).count()
        if (
            invocation.state != InvocationState.SUCCEEDED
            or not permitted
            or not denied
            or not submitted
            or not published
            or terminal is None
            or outcome_count != 1
            or usage is None
            or exit_evidence is None
        ):
            raise RuntimeError("live product lifecycle or canary evidence was incomplete")
        duration_ms = round((time.monotonic() - started) * 1000, 3)
        binding = _binding()
        evidence = {
            "schemaVersion": "plane-agent-g4/live-evidence/v1",
            "status": "passed",
            "providerRelay": {
                "protocol": "plane.agent-runtime/provider-relay/v1",
                "transport": "AF_UNIX",
                "childNetworkPolicy": "none",
                "externalEgressOwner": "agent-runtime",
                "hostGatewaySeparate": True,
                "hermesHookStatus": "integrated",
            },
            "binding": binding,
            "provider": {**provider, "fallbackUsed": False},
            "canaries": {
                "permitted": {"id": os.environ["G4_PERMITTED_CANARY"], "status": "allowed", "passed": True},
                "denied": {"id": os.environ["G4_DENIED_CANARY"], "status": "denied", "passed": True},
            },
            "thresholds": {
                "profile": "g4-live-minimal-single-invocation",
                "approved": {
                    "permittedSuccessRateMin": 1.0,
                    "deniedRejectionRateMin": 1.0,
                    "maxLatencyP95Ms": 600000.0,
                    "maxErrorRate": 0.0,
                },
                "observed": {
                    "permittedSuccessRate": 1.0,
                    "deniedRejectionRate": 1.0,
                    "latencyP95Ms": duration_ms,
                    "errorRate": 0.0,
                },
            },
            "readback": {
                "audit": {
                    "passed": True,
                    "eventCount": audits.count(),
                    "permittedOutcome": "success",
                    "deniedOutcome": "denied",
                    "submitOutcome": "success",
                    "publishOutcome": "success",
                },
                "version": {"passed": True, "binding": binding, "source": "candidate-manifest"},
            },
            "summary": {
                "counts": {"collected": 1, "passed": 1, "failed": 0, "skipped": 0, "xfail": 0, "deselected": 0},
                "durationMs": duration_ms,
                "migrationLeaf": "db.0142_runtime_provider_attempts",
                "workload": {
                    "invocationRef": str(invocation.invocation_id),
                    "runRef": str(run.id),
                    "actorRef": str(actor.principal_id),
                    "terminalEventRef": str(terminal.product_event_ref),
                    "terminalKind": terminal.kind,
                    "invocationState": invocation.state,
                    "outcomeCount": outcome_count,
                    "runtimeEventCount": event_count,
                    "providerHttpStatusClass": "2xx",
                    "usage": {key: value for key, value in usage.usage.items() if isinstance(value, (int, float))},
                },
            },
        }
    except BaseException as exc:
        failure = exc
        return_code = 1
    finally:
        if invocation is not None:
            try:
                reconcile_provider_attempts(invocation)
                (
                    provider_attempts,
                    terminal,
                    control,
                    exit_evidence,
                    runtime_event_kind_counts,
                    plane_host_operation_receipts,
                ) = readback()
                if (
                    failure is not None
                    and terminal is None
                    and invocation.state
                    not in {
                        InvocationState.SUCCEEDED,
                        InvocationState.FAILED,
                        InvocationState.BLOCKED,
                        InvocationState.CANCELLED,
                        InvocationState.OUTCOME_UNKNOWN,
                    }
                ):
                    initiated = any(attempt.upstream_initiated for attempt in provider_attempts)
                    finalize_invocation(
                        invocation,
                        kind="run_blocker" if initiated else "run_failure",
                        reason=(
                            "Provider request outcome is unknown; explicit reconciliation is required."
                            if initiated
                            else "Live G4 supervisor invocation failed before provider completion."
                        ),
                    )
                    (
                        provider_attempts,
                        terminal,
                        control,
                        exit_evidence,
                        runtime_event_kind_counts,
                        plane_host_operation_receipts,
                    ) = readback()
            except BaseException as exc:
                if failure is None:
                    failure = exc
                return_code = 1
                try:
                    (
                        provider_attempts,
                        terminal,
                        control,
                        exit_evidence,
                        runtime_event_kind_counts,
                        plane_host_operation_receipts,
                    ) = readback()
                except BaseException:
                    provider_attempts, terminal, control = [], None, None
                    exit_evidence, runtime_event_kind_counts = None, {}
                    plane_host_operation_receipts = False

        if failure is not None:
            try:
                failure_binding = binding or _binding()
            except BaseException:
                failure_binding = {}
            evidence = build_failure_evidence(
                binding=failure_binding,
                failure_phase="api-invocation",
                error_class=type(failure).__name__,
                exit_code=return_code,
                run_id=str(run.id) if run is not None else None,
                run_state=run.state if run is not None else None,
                invocation_id=invocation.invocation_id if invocation is not None else None,
                invocation_state=invocation.state if invocation is not None else None,
                provider_attempts=[
                    {
                        "sequence": attempt.sequence,
                        "phase": attempt.phase,
                        "upstreamInitiated": attempt.upstream_initiated,
                        "statusClass": attempt.status_class,
                        "errorCode": attempt.error_code,
                    }
                    for attempt in provider_attempts
                ],
                terminal_kind=terminal.kind if terminal is not None else "none",
                failure_code=control.failure_code if control is not None else None,
                failure_reason=supervisor_failure_reason
                or (control.failure_reason if control is not None else None),
                runtime_exit=(
                    {
                        "kind": exit_evidence.kind,
                        "failure": (
                            exit_evidence.raw_payload.get("failure")
                            if isinstance(exit_evidence.raw_payload, dict)
                            else None
                        ),
                    }
                    if exit_evidence is not None
                    else None
                ),
                runtime_event_kind_counts=runtime_event_kind_counts,
                terminal_code=control.failure_code if control is not None else None,
                terminal_reason=terminal.reason if terminal is not None else None,
                plane_host_operation_receipts=plane_host_operation_receipts,
            )

    print(json.dumps(evidence, sort_keys=True, separators=(",", ":")))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
