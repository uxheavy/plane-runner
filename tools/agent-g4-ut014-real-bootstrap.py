"""Provider-free UT-014 regression for the exact G4 runtime bootstrap path.

Run this file as stdin to the pinned runtime image with ``--network none``.
The fake upstream is installed only in the trusted parent relay, after the
real Hermes bootstrap has imported its tools and constructed its OpenAI
Responses client.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import threading
from contextlib import nullcontext
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from plane.agent.runtime import (
    AgentRuntimeConfiguration,
    RemoteRuntimeTransport,
    RuntimeCredentialBroker,
    RuntimeHostEndpoint,
    RuntimeSafetyController,
)
from plane.agent.runtime.provider_egress import ProviderResponse
from plane.agent.runtime.service import RuntimeDispatchExecutor, _RuntimeHTTPServer
from plane_runtime.g1_contract import G1_CONTRACT_DIGESTS, content_digest, snapshot_digest


def _expires() -> str:
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5)).isoformat().replace("+00:00", "Z")


def _snapshot() -> dict[str, Any]:
    value: dict[str, Any] = {
        "protocol": "plane.agent-runtime/v1",
        "workspaceRef": "workspace:ut014",
        "runId": "run:ut014",
        "assignment": {
            "assignmentRef": "assignment:ut014",
            "revision": "1",
            "targetRef": "target:ut014",
            "objective": "Return the bounded provider-free smoke result.",
            "acceptanceCriteria": ["The exact runtime path reaches provider-attempt intent."],
        },
        "actorRef": "actor:ut014",
        "profile": {
            "profileRef": "profile-version:ut014",
            "revision": "1",
            "role": "worker",
            "behavioralPrompt": "Use the configured runtime and return a short result.",
        },
        "context": [],
        "toolCatalog": {"catalogDigest": content_digest({"catalog": "ut014"}), "eagerOperations": []},
        "runtimePolicy": {
            "model": {"provider": "openai-codex", "model": "gpt-5.6-luna"},
            "adapter": "openai-compatible",
            "isolation": "single-invocation",
            "maxEventPayloadBytes": 8192,
            "maxArtifactBytes": 8192,
            "maxReceiptBytes": 8192,
            "maxCodeModeInputBytes": 4096,
            "maxCodeModeOutputBytes": 4096,
            "maxCodeModeCalls": 4,
        },
        "totalBudget": {"inputTokens": 1000, "outputTokens": 256, "durationMs": 120000},
        "contractDigests": G1_CONTRACT_DIGESTS,
    }
    value["contentDigest"] = snapshot_digest(value)
    return value


def _invocation(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "protocol": "plane.agent-runtime/v1",
        "workspaceRef": snapshot["workspaceRef"],
        "actorRef": snapshot["actorRef"],
        "runId": snapshot["runId"],
        "invocationId": "invocation:ut014",
        "runSnapshotDigest": snapshot["contentDigest"],
        "trigger": {"kind": "initial"},
        "newContextEventRefs": [],
        "remainingBudget": {"inputTokens": 1000, "outputTokens": 256, "durationMs": 120000},
        "lease": {"leaseId": "lease:ut014", "expiresAt": _expires(), "renewAfterMs": 60000},
        "cancellationRef": "cancellation:ut014",
        "causationRef": "causation:ut014",
        "correlationId": "correlation:ut014",
        "idempotencyKey": "idempotency:ut014",
    }


class _HostHandler(BaseHTTPRequestHandler):
    phases: list[str] = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        call = json.loads(self.rfile.read(length))
        self.phases.append(str(call["input"]["phase"]))
        response = {
            "correlationId": call["correlationId"],
            "idempotencyKey": call["idempotencyKey"],
            "output": None,
            "protocol": "plane.agent-runtime/v1",
            "replayed": False,
            "requestRef": call["requestRef"],
            "status": "ok",
        }
        encoded = json.dumps(response, sort_keys=True, separators=(",", ":")).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_args: object) -> None:
        return


class _LocalHostServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


PROVIDER_CALLS = 0


def _fake_provider(_request: Any, credentials: dict[str, str], _cancelled: Any) -> ProviderResponse:
    global PROVIDER_CALLS
    PROVIDER_CALLS += 1
    if credentials != {"api_key": "synthetic-provider-secret"}:
        raise RuntimeError("unexpected credential shape")
    response = {
        "id": "resp_ut014",
        "model": "gpt-5.6-luna",
        "object": "response",
        "output": [
            {
                "content": [{"text": "provider-free ok", "type": "output_text"}],
                "id": "msg_ut014",
                "role": "assistant",
                "status": "completed",
                "type": "message",
            }
        ],
        "output_text": "provider-free ok",
        "status": "completed",
        "usage": {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
    }
    message = response["output"][0]
    events = (
        {"item": {**message, "status": "in_progress"}, "type": "response.output_item.added"},
        {"delta": "provider-free ok", "type": "response.output_text.delta"},
        {"item": message, "type": "response.output_item.done"},
        {"response": response, "type": "response.completed"},
    )
    body = b"".join(b"data: " + json.dumps(event, separators=(",", ":")).encode() + b"\n\n" for event in events)
    return ProviderResponse(status_code=200, headers={"content-type": "text/event-stream"}, body_chunks=(body,))


class _ExactExecutor(RuntimeDispatchExecutor):
    def open_provider_relay(self, **kwargs: Any):  # type: ignore[no-untyped-def]
        return super().open_provider_relay(upstream=_fake_provider, **kwargs)


def main() -> int:
    root = Path("/tmp") / f"ut014-real-{os.getpid()}"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    home = root / "home"
    home.mkdir(mode=0o700, exist_ok=True)
    environment = {
        "PLANE_AGENT_RUNTIME_URL": "http://127.0.0.1:1",
        "PLANE_AGENT_RUNTIME_SECRET": "s" * 40,
        "PLANE_AGENT_RUNTIME_LEDGER_PATH": str(root / "ledger.sqlite"),
        "PLANE_AGENT_RUNTIME_SAFETY_STOP_FILE": str(root / "safety-stop"),
        "PLANE_AGENT_RUNTIME_CREDENTIAL_STATE_FILE": str(root / "revocations.json"),
        "PLANE_AGENT_RUNTIME_PROVIDER": "openai-codex",
        "PLANE_AGENT_RUNTIME_PROVIDER_HOST": "chatgpt.com",
        "PLANE_AGENT_RUNTIME_PROVIDER_PATH": "/backend-api/codex/responses",
        "PLANE_AGENT_RUNTIME_PROVIDER_MODELS": "gpt-5.6-luna",
        "PLANE_AGENT_RUNTIME_ENVIRONMENT_JSON": json.dumps(
            {
                "HOME": str(home),
                "HERMES_HOME": str(home),
                "LANG": "C.UTF-8",
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "PYTHONPATH": "/opt/plane:/opt:/opt/hermes",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONNOUSERSITE": "1",
                "TMPDIR": "/tmp",
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
    }
    configuration = AgentRuntimeConfiguration.from_environment(environment)
    controller = RuntimeSafetyController(configured=True, stop_file=configuration.safety_stop_file)
    controller.mark_ready()

    host = _LocalHostServer(("127.0.0.1", 0), _HostHandler)
    host_thread = threading.Thread(target=host.serve_forever, daemon=True)
    host_thread.start()
    host_url = f"http://127.0.0.1:{host.server_port}/v1/host"
    broker = RuntimeCredentialBroker(
        {"runtime": {"api_key": "synthetic-provider-secret"}},
        state_file=configuration.credential_state_file,
    )
    executor = _ExactExecutor(configuration, controller)
    runtime = _RuntimeHTTPServer(("127.0.0.1", 0), controller, configuration, executor=executor)
    runtime_thread = threading.Thread(target=runtime.serve_forever, daemon=True)
    runtime_thread.start()

    def host_endpoint(_invocation_id: str):
        return nullcontext(RuntimeHostEndpoint(host_url, "host-token"))

    transport = RemoteRuntimeTransport(
        runtime_url=f"http://127.0.0.1:{runtime.server_port}",
        shared_secret=configuration.shared_secret,
        credential_broker=broker,
        host_endpoint_factory=host_endpoint,
        model_call_allowance=1,
        timeout_seconds=45,
    )
    snapshot = _snapshot()
    invocation = _invocation(snapshot)
    try:
        frames = tuple(
            json.loads(frame)
            for frame in transport.dispatch(
                json.dumps(snapshot, sort_keys=True, separators=(",", ":")),
                json.dumps(invocation, sort_keys=True, separators=(",", ":")),
            )
        )
        result = {
            "eventBodies": [item.get("body", {}).get("kind") for item in frames if "body" in item],
            "exit": frames[-1].get("kind") if frames else "none",
            "network": "none",
            "providerCalls": PROVIDER_CALLS,
            "providerPhases": _HostHandler.phases,
        }
        if result["exit"] != "completed" or result["providerCalls"] != 1 or result["providerPhases"] != [
            "intent",
            "started",
            "completed",
        ]:
            raise RuntimeError("exact bootstrap regression did not complete")
        print(json.dumps({"result": "completed", **result}, sort_keys=True, separators=(",", ":")))
        return 0
    except Exception:
        print(
            json.dumps(
                {
                    "result": "failed",
                    "failure": "exact_bootstrap_regression_failed",
                    "network": "none",
                    "providerCalls": PROVIDER_CALLS,
                    "providerPhases": _HostHandler.phases,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 1
    finally:
        runtime.shutdown()
        runtime.server_close()
        runtime_thread.join(timeout=2)
        host.shutdown()
        host.server_close()
        host_thread.join(timeout=2)


if __name__ == "__main__":
    raise SystemExit(main())
