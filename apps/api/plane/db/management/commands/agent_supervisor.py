"""Run one persisted Agent invocation through the Plane supervisor entrypoint."""

from __future__ import annotations

import json
import shlex
import secrets
import threading
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import OperationalError, close_old_connections

from plane.agent.lifecycle import record_provider_attempt_notice
from plane.agent.runtime import (
    HostBoundSubprocessRuntimeTransport,
    PlaneHostHTTPServer,
    RemoteRuntimeTransport,
    RuntimeCredentialBroker,
    RuntimeCredentialError,
    credential_source_from_configuration,
    RuntimeDispatchError,
    RuntimeHostEndpoint,
    RuntimeSupervisorError,
    build_gateway_host_port,
    run_runtime_invocation,
    runtime_transport_kind,
    terminalize_pre_dispatch_failure,
    validate_runtime_command,
)
from plane.agent.runtime.credentials import credential_failure_subreason
from plane.agent.runtime.provenance import RuntimeProvenanceError, preflight_runtime_provenance
from plane.db.models import RuntimeInvocation
from plane.operation_gateway.gateway import OperationGateway


def _provider_attempt_notice_for_plane(invocation, call):
    """Translate the runtime run reference into Plane's model identity.

    Runtime contracts use the namespaced ``run:<uuid>`` reference.  The
    lifecycle writer accepts the persisted Django UUID as ``runId``.  Keep
    this conversion at the trusted host boundary and reject any mismatch
    before lifecycle mutation.
    """

    persisted_run_id = str(invocation.run_id)
    expected_runtime_run_ref = f"run:{persisted_run_id}"
    snapshot = getattr(invocation.run, "snapshot", None)
    if (
        not isinstance(snapshot, dict)
        or snapshot.get("runId") != expected_runtime_run_ref
        or call.run_id != expected_runtime_run_ref
        or call.invocation_id != invocation.invocation_id
    ):
        raise RuntimeDispatchError("runtime provider attempt binding is invalid")
    notice = dict(call.input)
    notice.update({"runId": persisted_run_id, "invocationId": invocation.invocation_id})
    return notice


def _supervisor_result_output(
    result,
    *,
    host_operation_failure: dict[str, str] | None = None,
) -> str:
    output = (
        f"invocation={result.invocation_id} state={result.state} "
        f"terminal={result.terminal_kind or 'none'} frames={result.accepted_frames}"
    )
    if result.failure is not None:
        failure = dict(result.failure)
        if (
            host_operation_failure is not None
            and result.failure.get("failureCause") == "host_operation_failure"
        ):
            host_failure = dict(host_operation_failure)
            for field in ("callbackPhase", "operationRefDigest"):
                if field in failure:
                    host_failure[field] = failure[field]
            failure["hostOperationFailure"] = host_failure
        output += " failure=" + json.dumps(
            failure,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    return output


class _SupervisorSetupFailure(RuntimeError):
    """An expected setup rejection with a safe public classification."""

    def __init__(self, stage: str, failure: dict[str, str]) -> None:
        super().__init__("runtime supervisor setup was rejected")
        self.stage = stage
        self.failure = failure


def _setup_failure_subreason(stage: str, error: BaseException) -> str:
    if stage == "credential_state":
        return "credential_state_invalid"
    if stage == "credential_source":
        if not isinstance(error, RuntimeCredentialError):
            return "credential_source_invalid"
        subreason = credential_failure_subreason(error)
        return subreason if subreason != "runtime_configuration_rejected" else "credential_source_invalid"
    return "runtime_configuration_rejected"


@contextmanager
def _supervisor_setup_stage(stage: str):
    """Keep setup ownership explicit without serializing exception details."""

    try:
        yield
    except _SupervisorSetupFailure:
        raise
    except (
        CommandError,
        OSError,
        RuntimeCredentialError,
        RuntimeProvenanceError,
        RuntimeSupervisorError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        raise _SupervisorSetupFailure(
            stage,
            {
                "failureCode": "runtime_configuration_pre_dispatch_failure",
                "failurePhase": "runtime_configuration",
                "failureDetail": "dispatch_rejected",
                "failureSubreason": _setup_failure_subreason(stage, exc),
            },
        ) from exc


class Command(BaseCommand):
    help = "Claim and run one persisted Plane Agent invocation through the configured Hermes runtime."

    def add_arguments(self, parser):
        parser.add_argument("--invocation-ref", required=True)
        parser.add_argument("--worker-id", default="plane-agent-worker")
        parser.add_argument("--lease-seconds", type=int, default=300)
        parser.add_argument("--runtime-command", nargs="+")
        parser.add_argument("--runtime-cwd")
        parser.add_argument("--runtime-checkout")
        parser.add_argument("--runtime-sha")
        parser.add_argument("--ledger-path")
        parser.add_argument("--model-call-allowance", type=int)

    def handle(self, *args, **options):
        invocation = None
        credential_broker = None
        monitor = None
        monitor_stop = threading.Event()
        result = None
        host_operation_failure = None
        try:
            try:
                invocation = RuntimeInvocation.objects.filter(invocation_id=options["invocation_ref"]).first()
            except OperationalError as lookup_error:
                # A second lookup is only a bounded rebind for terminalization;
                # runtime dispatch is never retried after an infrastructure error.
                close_old_connections()
                try:
                    invocation = RuntimeInvocation.objects.filter(invocation_id=options["invocation_ref"]).first()
                except OperationalError:
                    raise lookup_error
                if invocation is None:
                    raise lookup_error
                terminalize_pre_dispatch_failure(invocation)
                raise CommandError("agent supervisor invocation lookup failed before runtime dispatch") from None
            if invocation is None:
                raise CommandError("invocation-ref does not identify a persisted Plane invocation")
            runtime_url = getattr(settings, "PLANE_AGENT_RUNTIME_URL", "")
            shared_secret = getattr(settings, "PLANE_AGENT_RUNTIME_SHARED_SECRET", "")
            checkout = options.get("runtime_checkout") or getattr(settings, "PLANE_AGENT_RUNTIME_CHECKOUT", None)
            expected_sha = options.get("runtime_sha") or getattr(settings, "PLANE_AGENT_RUNTIME_SHA", None)
            with _supervisor_setup_stage("runtime_transport"):
                transport_kind = runtime_transport_kind(runtime_url, shared_secret)
            with _supervisor_setup_stage("runtime_provenance"):
                preflight_runtime_provenance(
                    str(checkout) if checkout else None,
                    str(expected_sha) if expected_sha else None,
                    remote_runtime=transport_kind == "remote",
                )
            with _supervisor_setup_stage("runtime_command"):
                command = options.get("runtime_command") or getattr(settings, "PLANE_AGENT_RUNTIME_COMMAND", None)
                if isinstance(command, str):
                    command = shlex.split(command)
                if not command and checkout:
                    command = (
                        "python3",
                        "-m",
                        "plane_runtime.g1_runtime_image.bootstrap",
                        "--once",
                        "--g1-production",
                    )
                if not command:
                    raise CommandError("Configure PLANE_AGENT_RUNTIME_COMMAND or pass --runtime-command")
                command = validate_runtime_command(tuple(command))
            with _supervisor_setup_stage("credential_source"):
                credential_source = credential_source_from_configuration(
                    getattr(settings, "PLANE_AGENT_RUNTIME_CREDENTIAL_RESOLVER", "")
                )
            with _supervisor_setup_stage("runtime_environment"):
                runtime_environment = getattr(settings, "PLANE_AGENT_RUNTIME_ENVIRONMENT", {})
                if not isinstance(runtime_environment, dict) or any(
                    not isinstance(key, str)
                    or not key
                    or "\x00" in key
                    or not isinstance(value, str)
                    or "\x00" in value
                    for key, value in runtime_environment.items()
                ):
                    raise CommandError("PLANE_AGENT_RUNTIME_ENVIRONMENT must be a bounded host-only string mapping")
            with _supervisor_setup_stage("credential_state"):
                ledger_path = options.get("ledger_path") or getattr(
                    settings,
                    "PLANE_AGENT_RUNTIME_LEDGER_PATH",
                    "/tmp/plane-agent-runtime-ledger.sqlite",
                )
                credential_state_file = getattr(
                    settings,
                    "PLANE_AGENT_RUNTIME_CREDENTIAL_STATE_FILE",
                    "/run/plane-agent-credentials/revocations.json",
                )
                credential_broker = RuntimeCredentialBroker(
                    credential_source,
                    state_file=credential_state_file,
                )

            def credential_control(current_invocation):
                actor_ref = current_invocation.run.snapshot["actorRef"]
                _lease, values = credential_broker.issue(
                    agent_ref=actor_ref,
                    credential_ref="runtime",
                    invocation_ref=current_invocation.invocation_id,
                )
                return values

            with _supervisor_setup_stage("runtime_safety_stop"):
                safety_stop_file = Path(
                    getattr(settings, "PLANE_AGENT_RUNTIME_SAFETY_STOP_FILE", "/run/plane-agent-runtime/safety-stop")
                )

            def local_cancelled() -> bool:
                from plane.agent.runtime.supervisor import runtime_invocation_cancelled

                return runtime_invocation_cancelled(invocation.pk) or safety_stop_file.exists()

            def revoke_on_stop() -> None:
                from plane.agent.runtime.supervisor import runtime_invocation_cancellation_requested

                while not monitor_stop.wait(0.05):
                    if runtime_invocation_cancellation_requested(invocation.pk) or safety_stop_file.exists():
                        credential_broker.revoke_invocation(invocation.invocation_id)

            with _supervisor_setup_stage("runtime_monitor"):
                monitor = threading.Thread(
                    target=revoke_on_stop,
                    name="plane-runtime-credential-revoker",
                    daemon=True,
                )
                monitor.start()

            with _supervisor_setup_stage("runtime_transport"):
                if transport_kind == "remote":
                    host_url = getattr(settings, "PLANE_AGENT_RUNTIME_HOST_URL", "")
                    host_parsed = urlsplit(host_url)
                    if (
                        host_parsed.scheme != "http"
                        or not host_parsed.hostname
                        or host_parsed.username
                        or host_parsed.password
                        or host_parsed.query
                        or host_parsed.fragment
                    ):
                        raise CommandError("PLANE_AGENT_RUNTIME_HOST_URL must be an internal HTTP URL")
                    host_port = getattr(settings, "PLANE_AGENT_RUNTIME_HOST_PORT", 8091)
                    if host_parsed.port is not None:
                        host_port = host_parsed.port

                    @contextmanager
                    def host_endpoint(invocation_ref: str):
                        nonlocal host_operation_failure
                        if invocation_ref != invocation.invocation_id:
                            raise RuntimeDispatchError("runtime host endpoint invocation binding is invalid")
                        token = secrets.token_urlsafe(32)
                        server = None

                        def provider_attempt_recorder(call):
                            notice = _provider_attempt_notice_for_plane(invocation, call)
                            attempt = record_provider_attempt_notice(invocation, notice)
                            return {
                                "accepted": True,
                                "attemptRef": f"provider-attempt:{attempt.id}",
                                "phase": attempt.phase,
                                "upstreamInitiated": attempt.upstream_initiated,
                            }

                        host_port_adapter = build_gateway_host_port(
                            invocation=invocation,
                            gateway=OperationGateway(),
                            provider_attempt_recorder=provider_attempt_recorder,
                        )
                        server = PlaneHostHTTPServer(
                            bind_host=getattr(settings, "PLANE_AGENT_RUNTIME_HOST_BIND", "0.0.0.0"),
                            advertised_host=host_parsed.hostname,
                            port=host_port,
                            auth_token=token,
                            invoke=host_port_adapter.invoke,
                        )
                        server.start()
                        try:
                            yield RuntimeHostEndpoint(url=server.url, token=token)
                        finally:
                            if server is not None:
                                host_operation_failure = server.failure_evidence
                            server.close()

                    transport = RemoteRuntimeTransport(
                        runtime_url=runtime_url,
                        shared_secret=shared_secret,
                        dispatch_path=getattr(settings, "PLANE_AGENT_RUNTIME_DISPATCH_PATH", "/v1/runtime/dispatch"),
                        timeout_seconds=getattr(settings, "PLANE_AGENT_RUNTIME_TIMEOUT_SECONDS", 300.0),
                        max_request_bytes=getattr(settings, "PLANE_AGENT_RUNTIME_MAX_REQUEST_BYTES", 256 * 1024),
                        max_response_bytes=getattr(settings, "PLANE_AGENT_RUNTIME_MAX_RESPONSE_BYTES", 512 * 1024),
                        host_endpoint_factory=host_endpoint,
                        credential_broker=credential_broker,
                        model_call_allowance=options.get("model_call_allowance"),
                    )
                else:
                    transport = HostBoundSubprocessRuntimeTransport(
                        command=tuple(command),
                        cwd=options.get("runtime_cwd")
                        or getattr(settings, "PLANE_AGENT_RUNTIME_CWD", None)
                        or checkout,
                        ledger_path=Path(ledger_path),
                        gateway=OperationGateway(),
                        bootstrap_command=True,
                        model_call_allowance=options.get("model_call_allowance"),
                        environment=dict(runtime_environment),
                        credential_control=credential_control,
                        is_cancelled=local_cancelled,
                    )
            result = run_runtime_invocation(
                invocation,
                transport=transport,
                worker_id=options["worker_id"],
                lease_seconds=options["lease_seconds"],
            )
            host_operation_failure = host_operation_failure or getattr(transport, "host_operation_failure", None)
        except _SupervisorSetupFailure as exc:
            terminalize_pre_dispatch_failure(invocation, exc.failure)
            raise CommandError("agent supervisor setup was rejected") from None
        except CommandError:
            raise
        except (ValueError, OSError, RuntimeCredentialError, RuntimeSupervisorError):
            if invocation is not None:
                terminalize_pre_dispatch_failure(invocation)
            raise CommandError("agent supervisor could not establish a bounded runtime result") from None
        except Exception:
            if invocation is not None:
                terminalize_pre_dispatch_failure(invocation)
            raise CommandError("agent supervisor setup did not produce a bounded runtime result") from None
        finally:
            monitor_stop.set()
            if monitor is not None:
                monitor.join(timeout=1)
            if credential_broker is not None and invocation is not None:
                try:
                    credential_broker.revoke_invocation(invocation.invocation_id)
                except Exception:
                    if result is not None:
                        raise CommandError("agent supervisor credential cleanup failed") from None
        self.stdout.write(
            self.style.SUCCESS(
                _supervisor_result_output(result, host_operation_failure=host_operation_failure)
            )
        )
