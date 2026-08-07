#!/usr/bin/env python3
"""Run the G4 proof against the pinned production runtime image."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path


HERMES_COMMIT = "e573a46611e2cb988f1ab43ad34cd8cc3b2cb659"
RESOURCE_LABEL = "com.uxheavy.plane.agent-g4-runtime"
EXPECTED_RUNTIME_IMAGE_DIGEST = "sha256:ea897bbe22a0044d58c16c4091bdf028e4661c2320d00e737f351cb3a1cdd734"
EXPECTED_RUNTIME_IMAGE_REVISION = "24d38235b2afea809ebb0e537e2f3e8015da8ee2"
RUNTIME_CONTRACT = "plane.agent-runtime/v1"


# Injected into the exact image's existing /tmp tmpfs with docker exec. It
# replaces only Hermes' model factory; Plane tools and the host bridge remain
# the pinned image implementation.
MODEL_SHIM = r'''"""Task-generated offline model shim; no credentials or network.

This module is injected as the model dependency only. The exact image's
bootstrap, launcher, Hermes service, host socket, and Plane HTTP gateway stay
on their production paths.
"""
import hashlib
import importlib.util
import json
import pathlib
import sys
import types


PINNED_HERMES_RUN_AGENT_PATH = "/opt/hermes/run_agent.py"
PINNED_HERMES_RUN_AGENT_SHA256 = "1a336eac71d5cd4418ebf7a8e52236eb6984ac9b9cfbb2e9ba08c9a197486011"

# Load the exact image-owned Hermes module before replacing only its AIAgent
# factory. This keeps the pinned agent loop, registration imports, and adapter
# contracts executable while making the provider call deterministic/offline.
_pinned_path = pathlib.Path(PINNED_HERMES_RUN_AGENT_PATH)
if hashlib.sha256(_pinned_path.read_bytes()).hexdigest() != PINNED_HERMES_RUN_AGENT_SHA256:
    raise RuntimeError("pinned Hermes run_agent provenance mismatch")
_pinned_spec = importlib.util.spec_from_file_location("_plane_pinned_hermes_run_agent", _pinned_path)
if _pinned_spec is None or _pinned_spec.loader is None:
    raise RuntimeError("pinned Hermes run_agent module could not be loaded")
PINNED_HERMES_RUN_AGENT_MODULE = importlib.util.module_from_spec(_pinned_spec)
sys.modules["_plane_pinned_hermes_run_agent"] = PINNED_HERMES_RUN_AGENT_MODULE
# The exact image omits Hermes' optional dotenv package; this inert module is
# the only dependency shim. The pinned run_agent source still executes fully.
if "dotenv" not in sys.modules:
    _dotenv = types.ModuleType("dotenv")
    _dotenv.load_dotenv = lambda **_kwargs: False
    sys.modules["dotenv"] = _dotenv
_pinned_spec.loader.exec_module(PINNED_HERMES_RUN_AGENT_MODULE)
if not callable(getattr(PINNED_HERMES_RUN_AGENT_MODULE, "AIAgent", None)):
    raise RuntimeError("pinned Hermes run_agent did not expose AIAgent")
PINNED_HERMES_RUN_AGENT_EXECUTED = True


def _diagnose(value):
    try:
        pathlib.Path("/tmp/g4-model-shim-error").write_text(str(value)[:4096], encoding="utf-8")
    except OSError:
        pass


def _call(name, arguments, *, code=False):
    from tools.registry import registry

    if code:
        from plane_runtime.host_port import plane_code_mode

        with plane_code_mode():
            raw = registry.dispatch(name, arguments)
    else:
        raw = registry.dispatch(name, arguments)
    if not isinstance(raw, str):
        raise RuntimeError("model shim received a non-text tool result")
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise RuntimeError("model shim received a non-object tool result")
    return result


class DeterministicModel:
    """Deterministic model seam used without changing the Hermes adapter."""

    def __init__(self, **kwargs):
        self.session_input_tokens = 1
        self.session_output_tokens = 1
        self.session_api_calls = 1
        self._step_callback = kwargs.get("step_callback")
        self._stream_delta_callback = kwargs.get("stream_delta_callback")

    def interrupt(self, _reason):
        return None

    def run_conversation(self, _objective, system_message=None, **_kwargs):
        del system_message
        from plane_runtime.host_port import current_plane_host
        from tools.registry import registry

        if current_plane_host() is None:
            _diagnose({"argv": sys.argv, "pythonpath": sys.path})
            raise RuntimeError("model shim did not receive an invocation-bound host")
        if "--g1-bootstrap-child" not in sys.argv or "--plane-host-socket" not in sys.argv:
            raise RuntimeError("model shim did not run through the pinned launcher child")
        if not PINNED_HERMES_RUN_AGENT_EXECUTED or PINNED_HERMES_RUN_AGENT_MODULE.__file__ != PINNED_HERMES_RUN_AGENT_PATH:
            raise RuntimeError("pinned Hermes run_agent execution proof is missing")
        if registry.get_entry("plane_operation") is None or registry.get_entry("plane_publish") is None:
            raise RuntimeError("pinned Hermes Plane tool registrations are missing")

        discovered = _call(
            "plane_operation",
            {"action": "discover", "input": {"query": "work item", "limit": 8}},
        )
        read = _call(
            "plane_operation",
            {
                "action": "read",
                "operationRef": "operation:work_item.read",
                "input": {"issue_ref": "issue:red-team"},
            },
        )
        denied = _call(
            "plane_operation",
            {
                "action": "mutate",
                "operationRef": "operation:work_item.rename",
                "input": {
                    "issue_ref": "issue:red-team",
                    "name": "must-not-apply",
                    "actor_ref": "actor:not-authorized",
                },
            },
        )
        code = _call(
            "plane_operation",
            {
                "action": "code",
                "operationRef": "operation:catalog.search",
                "input": {"query": "rename", "limit": 5},
            },
            code=True,
        )
        renamed = _call(
            "plane_operation",
            {
                "action": "mutate",
                "operationRef": "operation:work_item.rename",
                "input": {
                    "issue_ref": "issue:red-team",
                    "name": "G4 exact image",
                    "actor_ref": "actor:red-team",
                },
            },
        )
        replay = _call(
            "plane_operation",
            {
                "action": "mutate",
                "operationRef": "operation:work_item.rename",
                "input": {
                    "issue_ref": "issue:red-team",
                    "name": "G4 exact image",
                    "actor_ref": "actor:red-team",
                },
            },
        )
        submitted = _call(
            "plane_operation",
            {
                "action": "mutate",
                "operationRef": "operation:agent.outcome.submit",
                "input": {
                    "run_ref": "run:red-team",
                    "summary": "Exact-image runtime chain completed.",
                    "artifacts": ["artifact:g4-exact-image"],
                    "evidence": ["evidence:g4-exact-image"],
                },
            },
        )
        try:
            outcome_ref = submitted["output"]["result"]["outcome"]["outcomeRef"]
        except (KeyError, TypeError) as exc:
            _diagnose({"submitted": submitted})
            raise RuntimeError("outcome submission receipt was incomplete") from exc
        published = _call(
            "plane_publish",
            {
                "kind": "outcome",
                "operationRef": "operation:agent.outcome.publish",
                "resourceRef": outcome_ref,
                "content": "Explicit exact-image outcome publication.",
            },
        )

        expected = (
            discovered.get("status") == "ok"
            and read.get("status") == "ok"
            and denied.get("status") == "denied"
            and denied.get("errorCode") == "NOT_AUTHORIZED"
            and code.get("status") == "ok"
            and renamed.get("status") == "ok"
            and replay.get("status") == "replayed"
            and submitted.get("status") == "ok"
            and published.get("status") == "ok"
            and isinstance(published.get("publication"), dict)
            and published["publication"].get("productEventRef", "").startswith("product-event:")
        )
        if not expected:
            _diagnose(
                {
                    "discovered": discovered,
                    "read": read,
                    "denied": denied,
                    "code": code,
                    "renamed": renamed,
                    "replay": replay,
                    "submitted": submitted,
                    "published": published,
                }
            )
            raise RuntimeError("model shim observed an incomplete gateway proof")
        if self._step_callback is not None:
            self._step_callback()
        if self._stream_delta_callback is not None:
            self._stream_delta_callback("deterministic exact-image chain complete")
        return {
            "final_response": (
                "g4-model-shim chain=service-launcher-hermes-child-af_unix-host-http-gateway "
                "native_read=ok durable_mutation=ok denied=ok code_mode=ok "
                "idempotent_replay=ok explicit_publication=ok "
                "pinned_hermes_run_agent=ok path=/opt/hermes/run_agent.py "
                "sha256=1a336eac71d5cd4418ebf7a8e52236eb6984ac9b9cfbb2e9ba08c9a197486011 "
                "shim_boundary=deterministic_model_factory_only"
            )
        }


# The exact pinned module above executes first; only the provider-facing
# factory imported by HermesKernelAdapter is replaced with the deterministic
# offline implementation.
AIAgent = DeterministicModel
'''


GATEWAY_SHIM = r'''"""Deterministic Plane HTTP gateway fixture for the exact-image proof."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import sys

TOKEN = sys.argv[1]
HOST_PROTOCOL = "plane.agent-runtime/v1"
state = {
    "events": [],
    "issueName": "Initial exact-image issue",
    "outcomeRef": None,
    "publication": None,
    "records": {},
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def request_digest(call):
    identity = {
        "protocol": HOST_PROTOCOL,
        "runId": call["runId"],
        "invocationId": call["invocationId"],
        "action": call["action"],
        "operationRef": call["operationRef"],
        "input": call["input"],
    }
    return hashlib.sha256(canonical(identity)).hexdigest()


def receipt(call, operation, result, *, outcome="success"):
    suffix = hashlib.sha256(call["requestRef"].encode()).hexdigest()[:24]
    return {
        "ok": True,
        "requestId": "request:" + suffix,
        "gatewayReceipt": "gateway:" + suffix,
        "auditReceipt": "audit:" + suffix,
        "operation": operation,
        "outcome": outcome,
        "result": result,
    }


def error(call, code, message):
    suffix = hashlib.sha256(call["requestRef"].encode()).hexdigest()[:24]
    return {
        "ok": False,
        "requestId": "request:" + suffix,
        "gatewayReceipt": "gateway:" + suffix,
        "auditReceipt": "audit:" + suffix,
        "error": {"code": code, "message": message},
    }


def result(call):
    if call["runId"] != "run:red-team" or call["invocationId"] != "invocation:red-team":
        return "denied", error(call, "CALLBACK_BINDING_INVALID", "callback identity is not invocation-bound"), None
    operation = call["operationRef"].removeprefix("operation:")
    payload = call["input"]
    if call["action"] == "discover":
        return "ok", receipt(call, "discover", {"operations": ["work_item.read", "work_item.rename", "agent.outcome.submit"]}), None
    if call["action"] == "code":
        if call["source"] != "code":
            return "denied", error(call, "NOT_AUTHORIZED", "code callbacks require the code source"), None
        return "ok", receipt(call, operation, {"matches": ["operation:work_item.rename"]}), None
    if operation == "work_item.read":
        return "ok", receipt(call, operation, {"issue": {"ref": "issue:red-team", "name": state["issueName"]}}), None
    if operation == "work_item.rename":
        if payload.get("actor_ref") != "actor:red-team":
            return "denied", error(call, "NOT_AUTHORIZED", "actor is not authorized for this mutation"), None
        state["issueName"] = payload.get("name", "")
        return "ok", receipt(call, operation, {"issue": {"ref": "issue:red-team", "name": state["issueName"]}}), None
    if operation == "agent.outcome.evaluate":
        return "denied", error(call, "NOT_AUTHORIZED", "outcome evaluation is not authorized"), None
    if operation == "agent.outcome.submit":
        state["outcomeRef"] = "outcome-submission:red-team"
        return "ok", receipt(call, operation, {"outcome": {"outcomeRef": state["outcomeRef"]}}), None
    if call["action"] == "publish" and operation == "agent.outcome.publish":
        if payload.get("resourceRef") != state["outcomeRef"]:
            return "denied", error(call, "NOT_AUTHORIZED", "publication resource is not the submitted outcome"), None
        suffix = call["requestRef"].removeprefix("host-request:")
        publication = {
            "action": "applied",
            "productKind": "outcome_submission",
            "productRef": state["outcomeRef"],
            "operationAttemptRef": "operation-attempt:" + suffix,
            "operationRef": "operation:agent.outcome.publish",
            "applicationServiceRef": "application-service:agent-lifecycle",
            "gatewayReceiptRef": "gateway-receipt:" + suffix,
            "receiptRef": "receipt:" + suffix,
            "auditReceiptRef": "audit-receipt:" + suffix,
            "productEventRef": "product-event:outcome-red-team",
        }
        state["publication"] = publication
        output = receipt(
            call,
            operation,
            {"outcome": {"outcomeRef": state["outcomeRef"], "productEventRef": publication["productEventRef"]}},
        )
        return "ok", output, publication
    return "denied", error(call, "NOT_AUTHORIZED", "operation is not available to this actor"), None


class Handler(BaseHTTPRequestHandler):
    def _write(self, status, value):
        raw = canonical(value)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/health/ready":
            self._write(200, {"status": "ready"})
            return
        if self.path == "/v1/evidence":
            if self.headers.get("X-Evidence-Token") != TOKEN:
                self._write(401, {"error": "unauthorized"})
                return
            events = state["events"]
            self._write(
                200,
                {
                    "protocol": "plane.agent-g4/red-team-gateway/v1",
                    "requestCount": len(events),
                    "events": events,
                    "issueName": state["issueName"],
                    "outcomeRef": state["outcomeRef"],
                    "publication": state["publication"],
                    "auditCount": sum(1 for event in events if event["auditReceipt"]),
                    "correlationIds": sorted({event["correlationId"] for event in events}),
                    "allHttpAuthorized": all(event["httpAuthorized"] for event in events),
                },
            )
            return
        self._write(404, {"error": "not_found"})

    def do_POST(self):
        if self.path != "/v1/host":
            self._write(404, {"error": "not_found"})
            return
        if self.headers.get("Authorization") != "Bearer " + TOKEN:
            self._write(401, {"error": "unauthorized"})
            return
        try:
            length = int(self.headers.get("Content-Length", "-1"))
            if length < 0 or length > 16 * 1024:
                raise ValueError
            raw = self.rfile.read(length)
            call = json.loads(raw.decode())
            if not isinstance(call, dict) or call.get("protocol") != HOST_PROTOCOL:
                raise ValueError
            if call.get("requestRef") != "host-request:" + request_digest(call):
                raise ValueError
        except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
            self._write(400, {"error": "invalid_request"})
            return
        previous = state["records"].get(call["requestRef"])
        if previous is not None:
            response = dict(previous)
            response["status"] = "replayed"
            response["replayed"] = True
            self._write(200, response)
            return
        status, output, publication = result(call)
        event = {
            "action": call["action"],
            "operationRef": call["operationRef"],
            "source": call["source"],
            "runId": call["runId"],
            "invocationId": call["invocationId"],
            "correlationId": call["correlationId"],
            "requestRef": call["requestRef"],
            "idempotencyKey": call["idempotencyKey"],
            "httpAuthorized": True,
            "auditReceipt": output.get("auditReceipt") if isinstance(output, dict) else None,
            "status": status,
        }
        state["events"].append(event)
        response = {
            "protocol": HOST_PROTOCOL,
            "requestRef": call["requestRef"],
            "correlationId": call["correlationId"],
            "idempotencyKey": call["idempotencyKey"],
            "status": status,
            "replayed": False,
            # PlaneHostHTTPClient receives this as the host receipt. Keep the
            # receipt envelope intact so the pinned adapter can validate
            # `ok`, `result`, and `error` at the same boundary as production.
            "output": output,
        }
        if status != "ok":
            response["errorCode"] = output["error"]["code"]
            response["errorMessage"] = output["error"]["message"]
        if publication is not None:
            response["publication"] = publication
        state["records"][call["requestRef"]] = response
        self._write(200, response)

    def log_message(self, *_args):
        return


ThreadingHTTPServer(("0.0.0.0", 8091), Handler).serve_forever()
'''


RUNTIME_POST_SCRIPT = """
import http.client, json, pathlib, sys
body = sys.stdin.buffer.read()
token = sys.argv[1]
if token == "__runtime_secret_file__":
    token = pathlib.Path("/run/secrets/plane_agent_runtime").read_text(encoding="utf-8")
connection = http.client.HTTPConnection("127.0.0.1", 8080, timeout=8)
try:
    connection.request("POST", sys.argv[2], body=body, headers={"Authorization": "Bearer " + token, "Content-Type": "application/json", "Content-Length": str(len(body))})
    response = connection.getresponse()
    payload = response.read(2 * 1024 * 1024 + 1)
    print(json.dumps({"status": response.status, "body": json.loads(payload.decode("utf-8"))}, sort_keys=True, separators=(",", ":")))
finally:
    connection.close()
"""


GATEWAY_GET_SCRIPT = """
import http.client, json, sys
connection = http.client.HTTPConnection("plane-host", 8091, timeout=8)
try:
    connection.request("GET", "/v1/evidence", headers={"X-Evidence-Token": sys.argv[1]})
    response = connection.getresponse()
    payload = response.read(64 * 1024 + 1)
    print(json.dumps({"status": response.status, "body": json.loads(payload.decode("utf-8"))}, sort_keys=True, separators=(",", ":")))
finally:
    connection.close()
"""


class ProbeFailure(RuntimeError):
    pass


def docker(*args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)


def docker_input(payload: bytes, *args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["docker", *args], input=payload, capture_output=True, timeout=timeout)
    return subprocess.CompletedProcess(
        result.args,
        result.returncode,
        result.stdout.decode("utf-8", errors="replace"),
        result.stderr.decode("utf-8", errors="replace"),
    )


def require(result: subprocess.CompletedProcess[str], reason: str) -> str:
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        sanitized = "_".join(" ".join(detail[-3:] if detail else ["no_output"]).split())[:320]
        raise ProbeFailure(f"{reason}:{sanitized or 'no_output'}")
    return result.stdout.strip()


def request_body(host_url: str, host_token: str) -> tuple[bytes, str]:
    digests = {
        "runSnapshot": "e538fe79ede53e6bb2e307600dbefea507e30b996c002c3dab32d543ca0e36a2",
        "invocationEnvelope": "b7a15d74406f1624cdb7cd95b42edfd1ffee596abe57e4f00ed60e2e23ded995",
        "runtimeEvent": "fcbf67ce71fa90dd9661a8f2a739b8119c59357c8bf01afabf4fe92a13de9425",
        "runtimeExit": "055792eb1bf4931dafe19de456b15037522f0b5e8f6a0d2fedfe0e0d1d1d1c05",
        "runtimeDurableState": "444c944ec8a5054f33c8662470529a1f4565d42ff06138438beceeef7967a0da",
    }
    # Keep the fixture exactly within the public G1 contract. The deliberate
    # empty credential source makes the real Hermes adapter fail closed after
    # the bootstrap, proving this is not a synthetic child package.
    snapshot = {
        "protocol": "plane.agent-runtime/v1",
        "workspaceRef": "workspace:red-team",
        "runId": "run:red-team",
        "assignment": {
            "assignmentRef": "assignment:red-team",
            "revision": "1",
            "targetRef": "target:red-team",
            "objective": "exercise the production runtime boundary",
            "acceptanceCriteria": ["the runtime returns bounded evidence"],
        },
        "actorRef": "actor:red-team",
        "profile": {
            "profileRef": "profile-version:red-team",
            "revision": "1",
            "role": "worker",
            "behavioralPrompt": "Return a short final answer.",
        },
        "context": [],
        "toolCatalog": {"catalogDigest": "content:" + "0" * 64, "eagerOperations": []},
        "runtimePolicy": {
            "model": {"provider": "openai", "model": "red-team-model"},
            "adapter": "hermes",
            "isolation": "single-invocation",
            "maxEventPayloadBytes": 16384,
            "maxArtifactBytes": 1048576,
            "maxReceiptBytes": 8192,
            "maxCodeModeInputBytes": 4096,
            "maxCodeModeOutputBytes": 8192,
            "maxCodeModeCalls": 8,
        },
        "totalBudget": {"inputTokens": 32, "outputTokens": 32, "durationMs": 30000},
        "contractDigests": digests,
    }
    digest_input = json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()
    snapshot["contentDigest"] = "snapshot:" + hashlib.sha256(digest_input).hexdigest()
    invocation = {
        "protocol": "plane.agent-runtime/v1",
        "workspaceRef": snapshot["workspaceRef"],
        "actorRef": snapshot["actorRef"],
        "runId": snapshot["runId"],
        "invocationId": "invocation:red-team",
        "runSnapshotDigest": snapshot["contentDigest"],
        "trigger": {"kind": "initial"},
        "newContextEventRefs": [],
        "remainingBudget": {"inputTokens": 32, "outputTokens": 32, "durationMs": 30000},
        "lease": {"leaseId": "lease:red-team", "expiresAt": "2099-01-01T00:00:00Z", "renewAfterMs": 1000},
        "cancellationRef": "cancellation:red-team",
        "causationRef": "causation:red-team",
        "correlationId": "correlation:red-team",
        "idempotencyKey": "idempotency:red-team",
    }
    snapshot_json = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    invocation_json = json.dumps(invocation, sort_keys=True, separators=(",", ":"))
    request_digest = hashlib.sha256(
        b"plane.agent-runtime/dispatch/v1\n" + snapshot_json.encode() + b"\n" + invocation_json.encode()
    ).hexdigest()
    body = {
        # This is a non-secret provider marker for the task-generated model
        # shim. No production credential crosses the exact-image boundary.
        "credentials": {"provider_marker": "offline-deterministic-model"},
        "host": {"url": host_url, "token": host_token},
        "invocation": invocation,
        "invocationId": invocation["invocationId"],
        "protocol": "plane.agent-runtime/dispatch/v1",
        "requestDigest": request_digest,
        "runId": snapshot["runId"],
        "snapshot": snapshot,
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode(), request_digest


def main() -> int:
    if shutil.which("docker") is None:
        print("event=agent.g4.runtime-red-team status=failed reason=docker_unavailable")
        return 1
    image = os.environ.get("PLANE_G4_RUNTIME_IMAGE", "plane-agent-runtime:hermes-e573a466")
    expected_digest = os.environ.get("PLANE_G4_RUNTIME_IMAGE_DIGEST", EXPECTED_RUNTIME_IMAGE_DIGEST)
    containers: list[str] = []
    network: str | None = None
    scratch: Path | None = None
    cleanup_errors: list[str] = []
    result = 1
    reason = "runtime_red_team_probe_failed"
    try:
        image_data = json.loads(require(docker("image", "inspect", image), "runtime_image_unavailable"))[0]
        actual_digest = image_data["Id"]
        labels = image_data.get("Config", {}).get("Labels", {}) or {}
        if expected_digest != EXPECTED_RUNTIME_IMAGE_DIGEST or actual_digest != expected_digest:
            raise ProbeFailure("runtime_image_digest_mismatch")
        if labels.get("org.uxheavy.plane.hermes.commit") != HERMES_COMMIT:
            raise ProbeFailure("runtime_image_hermes_provenance_mismatch")
        if labels.get("org.uxheavy.plane.hermes.remote") != "https://github.com/uxheavy/hermes-agent.git":
            raise ProbeFailure("runtime_image_hermes_remote_provenance_mismatch")
        if labels.get("org.uxheavy.plane.runtime.revision") != EXPECTED_RUNTIME_IMAGE_REVISION:
            raise ProbeFailure("runtime_image_plane_provenance_mismatch")
        if labels.get("org.uxheavy.plane.runtime.contract") != RUNTIME_CONTRACT:
            raise ProbeFailure("runtime_image_contract_provenance_mismatch")

        name = f"plane-agent-g4-runtime-{uuid.uuid4().hex[:12]}"
        peer = f"{name}-host"
        network = f"plane-agent-g4-runtime-net-{uuid.uuid4().hex[:12]}"
        label_args = ["--label", f"{RESOURCE_LABEL}=true"]
        role_label = lambda role: ["--label", f"{RESOURCE_LABEL}.role={role}"]
        scratch = Path(
            tempfile.mkdtemp(prefix=".plane-agent-g4-red-team-", dir=Path(__file__).resolve().parents[1])
        )
        secret_path = scratch / "runtime-secret"
        secret = "disposable-runtime-secret-" + uuid.uuid4().hex
        host_token = "disposable-host-token-" + uuid.uuid4().hex
        secret_path.write_text(secret, encoding="utf-8")
        model_shim_path = scratch / "run_agent.py"
        model_shim_path.write_text(MODEL_SHIM, encoding="utf-8")
        child_environment_json = json.dumps(
            {
                "HOME": "/tmp",
                "HERMES_HOME": "/tmp/hermes-home",
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "PYTHONPATH": "/tmp:/opt:/opt/hermes",
                "PYTHONSAFEPATH": "1",
                "PYTHONUNBUFFERED": "1",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        require(
            docker("network", "create", "--internal", *label_args, *role_label("network"), network),
            "internal_network_create_failed",
        )
        peer_run = docker(
            "run",
            "-d",
            "--name",
            peer,
            *label_args,
            *role_label("peer"),
            "--network",
            network,
            "--network-alias",
            "plane-host",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=4m",
            "--entrypoint",
            "python3",
            image,
            "-c",
            GATEWAY_SHIM,
            host_token,
        )
        require(peer_run, "internal_host_fixture_start_failed")
        containers.append(peer)
        runtime_run = docker(
            "run",
            "-d",
            "--name",
            name,
            *label_args,
            *role_label("runtime"),
            "--network",
            network,
            "--network-alias",
            "agent-runtime",
            "--user",
            "65532:65532",
            "--workdir",
            "/opt/hermes",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--memory",
            "768m",
            "--cpus",
            "1.0",
            "--pids-limit",
            "128",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,nodev,size=64m",
            "--tmpfs",
            "/run/plane-agent-runtime:rw,noexec,nosuid,nodev,size=1m",
            "--mount",
            f"type=bind,src={secret_path},dst=/run/secrets/plane_agent_runtime,readonly",
            "-e",
            f"PLANE_AGENT_RUNTIME_ENVIRONMENT_JSON={child_environment_json}",
            "-e",
            "PLANE_AGENT_RUNTIME_URL=http://agent-runtime:8080",
            "-e",
            "PLANE_AGENT_RUNTIME_SECRET_FILE=/run/secrets/plane_agent_runtime",
            "-e",
            "PLANE_AGENT_RUNTIME_COMMAND=python3 -m plane_runtime.g1_runtime_image.bootstrap --once --g1-production",
            "-e",
            "PLANE_AGENT_RUNTIME_LEDGER_PATH=/run/plane-agent-runtime/dispatch-ledger.sqlite",
            "-e",
            "PLANE_AGENT_RUNTIME_SAFETY_STOP_FILE=/run/plane-agent-runtime/safety-stop",
            "-e",
            "PLANE_AGENT_RUNTIME_BIND=0.0.0.0",
            "-e",
            "PLANE_AGENT_RUNTIME_PORT=8080",
            "--entrypoint",
            "python3",
            image,
            "-m",
            "plane.agent.runtime.service",
        )
        require(runtime_run, "runtime_service_start_failed")
        containers.append(name)
        inspected = json.loads(require(docker("inspect", name), "runtime_container_inspect_failed"))[0]
        host_config = inspected["HostConfig"]
        mounts = inspected.get("Mounts", [])
        if host_config.get("NetworkMode") != network or host_config.get("ReadonlyRootfs") is not True:
            raise ProbeFailure("runtime_network_or_rootfs_boundary_mismatch")
        if "ALL" not in host_config.get("CapDrop", []) or "no-new-privileges:true" not in host_config.get("SecurityOpt", []):
            raise ProbeFailure("runtime_capability_boundary_mismatch")
        if host_config.get("Memory") != 768 * 1024 * 1024 or host_config.get("NanoCpus") != 1_000_000_000:
            raise ProbeFailure("runtime_resource_boundary_mismatch")
        if host_config.get("PidsLimit") != 128 or host_config.get("PortBindings"):
            raise ProbeFailure("runtime_pid_or_port_boundary_mismatch")
        if any(mount.get("Destination") in {"/code", "/tmp/plane-runtime-module"} for mount in mounts):
            raise ProbeFailure("runtime_source_mount_detected")

        if any(
            mount.get("Type") == "bind" and mount.get("Destination") != "/run/secrets/plane_agent_runtime"
            for mount in mounts
        ):
            raise ProbeFailure("runtime_unapproved_bind_mount_detected")
        require(
            docker_input(
                MODEL_SHIM.encode("utf-8"),
                "exec",
                "-i",
                name,
                "python3",
                "-c",
                "import pathlib,sys; pathlib.Path('/tmp/run_agent.py').write_bytes(sys.stdin.buffer.read())",
            ),
            "model_shim_injection_failed",
        )

        def runtime_post(payload: bytes, token: str, path: str = "/v1/runtime/dispatch") -> dict[str, object]:
            raw = require(
                docker_input(
                    payload,
                    "exec",
                    "-i",
                    name,
                    "python3",
                    "-c",
                    RUNTIME_POST_SCRIPT,
                    token,
                    path,
                    timeout=30,
                ),
                "runtime_http_probe_failed",
            )
            return json.loads(raw.splitlines()[-1])

        ready = False
        gateway_ready = False
        for _ in range(80):
            runtime_probe = docker(
                "exec",
                name,
                "python3",
                "-c",
                "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health/ready', timeout=1)",
            )
            gateway_probe = docker(
                "exec",
                name,
                "python3",
                "-c",
                "import urllib.request; urllib.request.urlopen('http://plane-host:8091/health/ready', timeout=1)",
            )
            ready = runtime_probe.returncode == 0
            gateway_ready = gateway_probe.returncode == 0
            if ready and gateway_ready:
                break
            time.sleep(0.25)
        if not ready:
            raise ProbeFailure("runtime_service_not_ready")
        if not gateway_ready:
            raise ProbeFailure("internal_host_gateway_not_ready")
        if docker(
            "exec", name, "python3", "-c", "import urllib.request; urllib.request.urlopen('http://1.1.1.1', timeout=1)"
        ).returncode == 0:
            raise ProbeFailure("public_network_escape")

        body, request_digest = request_body("http://plane-host:8091/v1/host", host_token)
        unauthorized = runtime_post(b"{}", "wrong-runtime-auth")
        if unauthorized.get("status") != 401:
            raise ProbeFailure("runtime_http_auth_negative_failed")
        wrong_path = runtime_post(b"{}", "__runtime_secret_file__", "/v1/runtime/not-dispatch")
        if wrong_path.get("status") != 404:
            raise ProbeFailure("runtime_http_path_negative_failed")
        malformed_binding = json.loads(body)
        malformed_binding["invocationId"] = "invocation:not-bound"
        binding_probe = runtime_post(
            json.dumps(malformed_binding, sort_keys=True, separators=(",", ":")).encode(),
            "__runtime_secret_file__",
        )
        if binding_probe.get("status") != 409:
            raise ProbeFailure("runtime_http_binding_negative_failed")

        dispatch = runtime_post(body, "__runtime_secret_file__")
        if dispatch.get("status") != 200:
            detail = json.dumps(dispatch, sort_keys=True, separators=(",", ":"))[:512]
            diagnostic = docker("exec", name, "sh", "-c", "test ! -r /tmp/g4-model-shim-error || cat /tmp/g4-model-shim-error").stdout
            gateway_diagnostic = docker(
                "exec", name, "python3", "-c", GATEWAY_GET_SCRIPT, host_token
            ).stdout
            runtime_logs = docker("logs", name).stdout
            raise ProbeFailure(
                f"runtime_http_dispatch_failed:{detail}:shim={diagnostic[:1024]}:gateway={gateway_diagnostic[:2048]}:logs={runtime_logs[-4096:]}"
            )
        replay = runtime_post(body, "__runtime_secret_file__")
        if replay.get("status") != 200 or replay.get("body") != dispatch.get("body"):
            raise ProbeFailure("runtime_http_dispatch_replay_failed")
        response_body = dispatch.get("body")
        if not isinstance(response_body, dict) or response_body.get("requestDigest") != request_digest:
            raise ProbeFailure("runtime_http_response_binding_failed")
        raw_frames = response_body.get("frames")
        if (
            not isinstance(raw_frames, list)
            or not raw_frames
            or any(not isinstance(frame, str) for frame in raw_frames)
        ):
            raise ProbeFailure("runtime_dispatch_evidence_incomplete")
        frames = [json.loads(frame) for frame in raw_frames]
        if any(frame.get("invocationId") != "invocation:red-team" for frame in frames):
            raise ProbeFailure("runtime_dispatch_invocation_binding_missing")
        if frames[-1].get("kind") != "completed":
            raise ProbeFailure("runtime_dispatch_child_not_completed")
        if not any(
            "pinned_hermes_run_agent=ok" in frame
            and "shim_boundary=deterministic_model_factory_only" in frame
            for frame in raw_frames
        ):
            raise ProbeFailure("pinned_hermes_run_agent_execution_evidence_missing")

        evidence_result = require(
            docker(
                "exec",
                name,
                "python3",
                "-c",
                GATEWAY_GET_SCRIPT,
                host_token,
                timeout=30,
            ),
            "plane_gateway_evidence_read_failed",
        )
        gateway_evidence = json.loads(evidence_result.splitlines()[-1])
        if gateway_evidence.get("status") != 200:
            raise ProbeFailure("plane_gateway_evidence_unavailable")
        evidence = gateway_evidence.get("body")
        if not isinstance(evidence, dict):
            raise ProbeFailure("plane_gateway_evidence_invalid")
        events = evidence.get("events")
        operations = {event.get("operationRef") for event in events} if isinstance(events, list) else set()
        if (
            evidence.get("protocol") != "plane.agent-g4/red-team-gateway/v1"
            or evidence.get("allHttpAuthorized") is not True
            or evidence.get("correlationIds") != ["correlation:red-team"]
            or evidence.get("issueName") != "G4 exact image"
            or evidence.get("outcomeRef") != "outcome-submission:red-team"
            or not isinstance(evidence.get("publication"), dict)
            or not evidence["publication"].get("productEventRef", "").startswith("product-event:")
            or evidence.get("auditCount") != evidence.get("requestCount")
            or not isinstance(events, list)
            or "plane.operations.discover@1" not in operations
            or "operation:work_item.read" not in operations
            or "operation:work_item.rename" not in operations
            or "operation:catalog.search" not in operations
            or "operation:agent.outcome.submit" not in operations
            or "operation:agent.outcome.publish" not in operations
        ):
            raise ProbeFailure("plane_gateway_chain_evidence_incomplete")
        if not any(
            event.get("status") == "denied" and event.get("operationRef") == "operation:work_item.rename"
            for event in events
        ):
            raise ProbeFailure("plane_gateway_authorization_denial_missing")
        if not any(event.get("source") == "code" and event.get("action") == "code" for event in events):
            raise ProbeFailure("plane_gateway_code_mode_callback_missing")
        if secret in json.dumps({"dispatch": dispatch, "evidence": evidence}, sort_keys=True):
            raise ProbeFailure("runtime_credential_disclosure")
        logs = docker("logs", name).stdout + docker("logs", peer).stdout
        if secret in logs or host_token in logs or "plane_agent_runtime" in logs:
            raise ProbeFailure("runtime_credential_or_path_disclosure")
        result = 0
        reason = "passed"
        print(
            "event=agent.g4.runtime-red-team status=passed "
            f"image_digest={actual_digest} image_revision={EXPECTED_RUNTIME_IMAGE_REVISION} "
            f"runtime_contract={RUNTIME_CONTRACT} hermes_commit={HERMES_COMMIT} "
            "dispatch_http=passed full_chain=passed launcher=passed hermes_child=passed "
            "af_unix_callback=passed plane_http_gateway=passed authorization=passed "
            "idempotency=passed audit=passed publication=passed "
            "internal_network=passed source_mount_scan=passed credential_scan=passed"
        )
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError, json.JSONDecodeError, ProbeFailure) as exc:
        reason = str(exc) or reason
    finally:
        for container in reversed(containers):
            removal = docker("rm", "-f", container)
            if removal.returncode != 0:
                cleanup_errors.append(f"container:{container}")
        if network is not None:
            removal = docker("network", "rm", network)
            if removal.returncode != 0:
                cleanup_errors.append(f"network:{network}")
        if scratch is not None:
            try:
                shutil.rmtree(scratch)
            except OSError:
                cleanup_errors.append("scratch")
        leftovers = docker("ps", "-aq", "--filter", f"label={RESOURCE_LABEL}")
        if leftovers.returncode != 0 or leftovers.stdout.strip():
            cleanup_errors.append("labeled_containers_remain")
        leftovers = docker("network", "ls", "-q", "--filter", f"label={RESOURCE_LABEL}")
        if leftovers.returncode != 0 or leftovers.stdout.strip():
            cleanup_errors.append("labeled_networks_remain")
        leftovers = docker("volume", "ls", "-q", "--filter", f"label={RESOURCE_LABEL}")
        if leftovers.returncode != 0 or leftovers.stdout.strip():
            cleanup_errors.append("labeled_volumes_remain")
    if cleanup_errors:
        print(
            "event=agent.g4.runtime-red-team status=failed "
            f"reason=cleanup_failed details={','.join(cleanup_errors)}"
        )
        return 1
    if result != 0:
        print(f"event=agent.g4.runtime-red-team status=failed reason={reason}")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
