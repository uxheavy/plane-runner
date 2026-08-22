from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import patch


API_ROOT = Path(__file__).resolve().parents[2] / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

# Import the dependency-free runtime package without importing Plane's Django
# application package or requiring the host's API environment.
import types

plane = types.ModuleType("plane")
plane.__path__ = [str(API_ROOT / "plane")]
sys.modules.setdefault("plane", plane)
agent = types.ModuleType("plane.agent")
agent.__path__ = [str(API_ROOT / "plane" / "agent")]
sys.modules.setdefault("plane.agent", agent)

from plane.agent.runtime.contracts import runtime_budget_seconds  # noqa: E402
from plane.agent.runtime.provider_egress import (  # noqa: E402
    ProviderRelayAudit,
    ProviderRelayBinding,
    ProviderRelayPolicy,
    ProviderRelayServer,
    ProviderResponse,
)
from plane.agent.runtime.subprocess import (  # noqa: E402
    RuntimeProcessPolicy,
    SubprocessRuntimeTransport,
)


class RuntimeBudgetBoundaryTest(unittest.TestCase):
    def test_progressing_provider_request_stays_inside_plane_budget(self) -> None:
        with tempfile.TemporaryDirectory(prefix="plane-runtime-budget-", dir="/private/tmp") as temporary:
            root = Path(temporary)
            started = threading.Event()
            audits: list[ProviderRelayAudit] = []

            def upstream(_request, _credentials, _cancelled):
                def body_chunks():
                    started.set()
                    time.sleep(0.15)
                    yield b"data: response.completed\n\n"

                return ProviderResponse(
                    status_code=200,
                    headers={"content-type": "text/event-stream"},
                    body_chunks=body_chunks(),
                )

            relay = ProviderRelayServer(
                socket_path=root / "provider.sock",
                binding=ProviderRelayBinding(
                    run_id="run:unittest",
                    invocation_id="invocation:unittest",
                    provider="xai",
                    model="grok-4",
                ),
                policy=ProviderRelayPolicy(
                    provider="xai",
                    host="api.x.ai",
                    path="/v1/chat/completions",
                    models=("grok-4",),
                    timeout_seconds=1.0,
                ),
                credentials={"api_key": "provider-secret"},
                upstream=upstream,
                audit=audits.append,
            )
            relay.start()

            child = textwrap.dedent(
                """
                import json
                import socket
                import sys

                socket_path = sys.argv[sys.argv.index('--provider-relay-socket') + 1]
                json.loads(sys.stdin.buffer.readline())
                credentials = json.loads(sys.stdin.buffer.readline())['credentials']
                json.loads(sys.stdin.buffer.readline())
                body = b'{"model":"grok-4","messages":[]}'
                wire = (
                    b'POST /v1/chat/completions HTTP/1.1\\r\\n'
                    b'Host: plane-provider-relay.invalid\\r\\n'
                    + ('Authorization: Bearer ' + credentials['relayToken'] + '\\r\\n').encode()
                    + b'Content-Type: application/json\\r\\n'
                    + ('Content-Length: ' + str(len(body)) + '\\r\\n').encode()
                    + b'X-Request-ID: request:unittest\\r\\n\\r\\n'
                    + body
                )
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
                    channel.connect(socket_path)
                    channel.sendall(wire)
                    response = bytearray()
                    while True:
                        chunk = channel.recv(4096)
                        if not chunk:
                            break
                        response.extend(chunk)
                if b'200 OK' not in response:
                    raise RuntimeError('relay did not return a completed response')
                print('{"status":"completed"}', flush=True)
                """
            )
            transport = SubprocessRuntimeTransport(
                command=(sys.executable, "-c", child),
                environment=dict(os.environ),
                ledger_path=root / "ledger.sqlite",
                timeout_seconds=0.05,
                process_policy=RuntimeProcessPolicy(enforce_kernel_policy=False),
            )
            invocation = {
                "remainingBudget": {"durationMs": 300},
                "lease": {
                    "expiresAt": (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
                },
            }
            budget_seconds = runtime_budget_seconds(invocation)

            try:
                with patch.object(RuntimeProcessPolicy, "preexec_fn", return_value=lambda: None):
                    frames = transport.dispatch_payload(
                        payload=(
                            b'{"modelCallAllowance":1}\n'
                            + json.dumps(
                                {
                                    "credentials": {
                                        "host": "plane-provider-relay.invalid",
                                        "invocationSocket": str(relay.descriptor.socket_path),
                                        "path": "/v1/chat/completions",
                                        "provider": "xai",
                                        "relayToken": relay.descriptor.token,
                                    }
                                }
                            ).encode()
                            + b"\n{}\n"
                        ),
                        run_id="run:unittest",
                        invocation_id="invocation:unittest",
                        request_digest="budget-boundary",
                        command=(sys.executable, "-c", child, "--provider-relay-socket", str(relay.descriptor.socket_path)),
                        timeout_seconds=budget_seconds,
                        process_policy=replace(
                            transport._process_policy,
                            cpu_seconds=max(1, int(budget_seconds + 0.999)),
                        ),
                    )
            except Exception as exc:
                self.fail(f"provider-free boundary dispatch failed: {getattr(exc, 'public_failure', lambda: str(exc))()}")
            finally:
                relay.close()

            self.assertTrue(started.is_set())
            self.assertEqual(frames, ('{"status":"completed"}',))
            self.assertEqual([audit.phase for audit in audits], ["intent", "started", "completed"])

    def test_expired_lease_is_not_promoted_to_a_process_budget(self) -> None:
        invocation = {
            "remainingBudget": {"durationMs": 300},
            "lease": {"expiresAt": "2026-08-22T11:59:59Z"},
        }
        with self.assertRaisesRegex(ValueError, "outside its allowed range"):
            runtime_budget_seconds(invocation, now=datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
