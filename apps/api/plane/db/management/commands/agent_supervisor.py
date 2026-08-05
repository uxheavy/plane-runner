"""Run one persisted Agent invocation through the Plane supervisor entrypoint."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from plane.agent.runtime import (
    HostBoundSubprocessRuntimeTransport,
    RuntimeSupervisorError,
    run_runtime_invocation,
)
from plane.db.models import RuntimeInvocation
from plane.operation_gateway.gateway import OperationGateway


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
        invocation = RuntimeInvocation.objects.filter(invocation_id=options["invocation_ref"]).first()
        if invocation is None:
            raise CommandError("invocation-ref does not identify a persisted Plane invocation")
        checkout = options.get("runtime_checkout") or getattr(settings, "PLANE_AGENT_RUNTIME_CHECKOUT", None)
        expected_sha = options.get("runtime_sha") or getattr(settings, "PLANE_AGENT_RUNTIME_SHA", None)
        if bool(checkout) != bool(expected_sha):
            raise CommandError("Hermes runtime checkout and SHA must be configured together")
        if checkout:
            try:
                actual_sha = subprocess.run(
                    ["git", "-C", str(checkout), "rev-parse", "HEAD"],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=5,
                ).stdout.strip()
            except (OSError, subprocess.SubprocessError) as exc:
                raise CommandError("Hermes runtime checkout could not be verified") from exc
            if actual_sha != str(expected_sha):
                raise CommandError("Hermes runtime checkout does not match the configured SHA")
        command = options.get("runtime_command") or getattr(settings, "PLANE_AGENT_RUNTIME_COMMAND", None)
        if isinstance(command, str):
            command = shlex.split(command)
        if not command and checkout:
            command = ("python3", "-m", "plane_runtime.g1_runtime_image.bootstrap", "--once", "--g1-production")
        if not command:
            raise CommandError("Configure PLANE_AGENT_RUNTIME_COMMAND or pass --runtime-command")
        if not any("plane_runtime.g1_runtime_image.bootstrap" in part for part in command):
            raise CommandError("the production runtime command must use plane_runtime.g1_runtime_image.bootstrap")
        runtime_credentials = getattr(settings, "PLANE_AGENT_RUNTIME_CREDENTIALS", {})
        if not isinstance(runtime_credentials, dict):
            raise CommandError("PLANE_AGENT_RUNTIME_CREDENTIALS must be a host-only mapping")
        ledger_path = options.get("ledger_path") or getattr(
            settings,
            "PLANE_AGENT_RUNTIME_LEDGER_PATH",
            "/tmp/plane-agent-runtime-ledger.sqlite",
        )
        try:
            transport = HostBoundSubprocessRuntimeTransport(
                command=tuple(command),
                cwd=options.get("runtime_cwd")
                or getattr(settings, "PLANE_AGENT_RUNTIME_CWD", None)
                or checkout,
                ledger_path=Path(ledger_path),
                gateway=OperationGateway(),
                bootstrap_command=True,
                model_call_allowance=options.get("model_call_allowance"),
                credential_control=lambda _invocation: dict(runtime_credentials),
            )
            result = run_runtime_invocation(
                invocation,
                transport=transport,
                worker_id=options["worker_id"],
                lease_seconds=options["lease_seconds"],
            )
        except (ValueError, OSError, RuntimeSupervisorError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"invocation={result.invocation_id} state={result.state} "
                f"terminal={result.terminal_kind or 'none'} frames={result.accepted_frames}"
            )
        )
