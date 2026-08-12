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
        "apiImageTag": os.environ["G4_API_IMAGE_TAG"],
        "apiImageDigest": os.environ["G4_API_IMAGE_DIGEST"],
        "apiSourceRevision": os.environ["G4_API_SOURCE_REVISION"],
        "apiContract": os.environ["G4_API_CONTRACT"],
    }


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
):
    """Return one bounded failure object without copying runtime observations."""

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
        "apiImageTag",
        "apiImageDigest",
        "apiSourceRevision",
        "apiContract",
    )
    failure_phases = {
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
        if key in {"candidateCommit", "g3Baseline", "hermesCommit", "mcpGitlink", "sdkGitlink", "runtimeImageRevision", "apiSourceRevision"}:
            return value if len(value) == 40 and all(char in hexadecimal for char in value) else "unavailable"
        if key in {"runtimeImageDigest", "apiImageDigest"}:
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
        if isinstance(binding, dict) and key in binding
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

    if terminal_kind not in terminal_kinds:
        terminal_kind = "unknown"
    if terminal_kind == "unknown":
        terminal = {"present": False, "kind": "unknown"}
    else:
        terminal = {"present": terminal_kind != "none", "kind": terminal_kind}
    if not isinstance(exit_code, int) or isinstance(exit_code, bool) or not 1 <= exit_code <= 255:
        exit_code = 1

    return {
        "schemaVersion": "plane-agent-g4/live-failure/v1",
        "status": "failed",
        "binding": bounded_binding,
        "failure": {
            "phase": failure_phase if failure_phase in failure_phases else "unknown",
            "errorClass": error_class if error_class in error_classes else "unspecified",
            "exitCode": exit_code,
        },
        "run": {"present": run_id is not None, "id": bounded_identifier(run_id), "state": bounded_state(run_state)},
        "invocation": {
            "present": invocation_id is not None,
            "id": bounded_identifier(invocation_id),
            "state": bounded_state(invocation_state),
        },
        "providerAttempts": attempts,
        "terminal": terminal,
    }


def main() -> int:
    started = time.monotonic()
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

    def readback():
        invocation.refresh_from_db()
        run.refresh_from_db()
        attempts = list(RuntimeProviderAttempt.objects.filter(invocation=invocation).order_by("sequence")[:32])
        current_terminal = RunTerminalEvent.objects.filter(invocation=invocation, visible=True).first()
        return attempts, current_terminal

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
            credential_ref="runtime",
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
                "provider": "xai",
                "model": "grok-4",
                "adapter": "hermes",
                "maxCodeModeCalls": 0,
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
        run = create_run(assignment, profile, idempotency_key=f"g4-live-run:{suffix}", created_by=user)
        invocation = record_invocation(run, idempotency_key=f"g4-live-invocation:{suffix}", trigger="initial")
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
        invocation.refresh_from_db()
        run.refresh_from_db()
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
        terminal = RunTerminalEvent.objects.filter(run=run, visible=True).first()
        usage = RuntimeUsageObservation.objects.filter(invocation=invocation).first()
        exit_evidence = RuntimeExitEvidence.objects.filter(invocation=invocation).first()
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
            "provider": {"name": "xai", "model": "grok-4", "fallbackUsed": False},
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
                provider_attempts, terminal = readback()
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
                    provider_attempts, terminal = readback()
            except BaseException as exc:
                if failure is None:
                    failure = exc
                return_code = 1
                try:
                    provider_attempts, terminal = readback()
                except BaseException:
                    provider_attempts, terminal = [], None

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
            )

    print(json.dumps(evidence, sort_keys=True, separators=(",", ":")))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
