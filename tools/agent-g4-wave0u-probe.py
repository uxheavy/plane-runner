#!/usr/bin/env python3
"""Provider-free Wave 0U boundary probe for the pinned runtime image."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path


IMAGE = os.environ.get("PLANE_G4_RUNTIME_IMAGE", "plane-agent-runtime:hermes-d2e65510-g4-codex-fix")
ROOT = Path(__file__).resolve().parents[1]


def _red_team_module():
    source = ROOT / "tools" / "agent-g4-runtime-red-team.py"
    spec = importlib.util.spec_from_file_location("agent_g4_red_team", source)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load the pinned-image fixture source")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sixteen_call_shim(source: str) -> str:
    read_call = (
        '        ("tool_call", {"name": "plane_operation", "arguments": '
        '{"action": "read", "operationRef": "operation:work_item.read", '
        '"input": {"issue_ref": "issue:red-team"}}}),\n'
    )
    outcome_line = '        ("tool_call", {"name": "plane_operation", "arguments": {"action": "mutate", "operationRef": "operation:agent.outcome.submit", "input": {"run_ref": "run:red-team", "summary": "Exact-image runtime chain completed.", "artifacts": ["artifact:g4-exact-image"], "evidence": ["evidence:g4-exact-image"]}}}),\n'
    publication_line = '        ("tool_call", {"name": "plane_publish", "arguments": {"kind": "outcome", "operationRef": "operation:agent.outcome.publish", "resourceRef": "outcome-submission:red-team", "content": "Explicit exact-image outcome publication."}}),\n'
    if outcome_line not in source or publication_line not in source:
        raise RuntimeError("the deterministic fixture publication plan was not found")
    updated = source.replace(outcome_line, read_call, 1).replace(publication_line, read_call, 1)
    plan_end = "    )\n\n    def create(self, **kwargs):"
    if plan_end not in updated:
        raise RuntimeError("the deterministic fixture plan terminator was not found")
    updated = updated.replace(plan_end, read_call * 5 + plan_end, 1)
    marker = "        else:\n            if call_number != len(self._PLAN):"
    if marker not in updated:
        raise RuntimeError("the deterministic fixture terminal branch was not found")
    updated = updated.replace(
        marker,
        '        elif call_number >= len(self._PLAN):\n'
        '            raise RuntimeError("provider model-call budget is exhausted")\n'
        "        else:\n            if call_number != len(self._PLAN):",
        1,
    )
    updated = updated.replace(
        "        _TRANSPORT_CALLS += 1\n",
        "        _TRANSPORT_CALLS += 1\n"
        "        pathlib.Path('/tmp/g4-provider-call-count').write_text(str(_TRANSPORT_CALLS), encoding='utf-8')\n",
        1,
    )
    return updated


def main() -> int:
    fixture = _red_team_module()
    raw_body, _digest = fixture.request_body("http://127.0.0.1:1", "unused-host-token")
    body = json.loads(raw_body)
    body["host"] = {"url": "http://127.0.0.1:8091/v1/host", "token": "unused-host-token"}
    shim = _sixteen_call_shim(fixture.PROVIDER_TRANSPORT_SHIM)
    program = f"""
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

Path('/tmp/openai.py').write_text({shim!r}, encoding='utf-8')
Path('/tmp/gateway.py').write_text({fixture.GATEWAY_SHIM!r}, encoding='utf-8')
body = {body!r}
secret = 'provider-free-wave0u-runtime-secret-1234567890'
host_token = 'unused-host-token'
environment = os.environ.copy()
environment.update({{
    'PLANE_AGENT_RUNTIME_URL': 'http://127.0.0.1:8080',
    'PLANE_AGENT_RUNTIME_SECRET': secret,
    'PLANE_AGENT_RUNTIME_COMMAND': 'python3 -m plane_runtime.g1_runtime_image.bootstrap --once --g1-production',
    'PLANE_AGENT_RUNTIME_BIND': '127.0.0.1',
    'PLANE_AGENT_RUNTIME_PORT': '8080',
    'PLANE_AGENT_RUNTIME_LEDGER_PATH': '/tmp/wave0u-ledger.sqlite',
    'PLANE_AGENT_RUNTIME_SAFETY_STOP_FILE': '/tmp/wave0u-safety-stop',
    'PLANE_AGENT_RUNTIME_ENVIRONMENT_JSON': json.dumps({{
        'HOME': '/tmp',
        'HERMES_HOME': '/tmp/hermes-home',
        'LANG': 'C.UTF-8',
        'LC_ALL': 'C.UTF-8',
        'PATH': '/usr/local/bin:/usr/bin:/bin',
        'PYTHONPATH': '/tmp:/opt:/opt/hermes',
        'PYTHONUNBUFFERED': '1',
    }}, sort_keys=True, separators=(',', ':')),
}})
gateway = subprocess.Popen(
    [sys.executable, '/tmp/gateway.py', host_token],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)
service = subprocess.Popen(
    [sys.executable, '-m', 'plane.agent.runtime.service'],
    env=environment,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)
try:
    gateway_ready = False
    for _ in range(100):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8091/health/ready', timeout=0.2) as response:
                if response.status == 200:
                    gateway_ready = True
                    break
        except OSError:
            time.sleep(0.05)
    if not gateway_ready:
        raise RuntimeError('host gateway did not become ready')
    ready = False
    for _ in range(200):
        if service.poll() is not None:
            break
        try:
            with urllib.request.urlopen('http://127.0.0.1:8080/health/ready', timeout=0.2) as response:
                if response.status == 200:
                    ready = True
                    break
        except OSError:
            time.sleep(0.05)
    if not ready:
        raise RuntimeError('runtime service did not become ready')
    body['modelCallAllowance'] = 16
    raw = json.dumps(body, sort_keys=True, separators=(',', ':')).encode()
    request = urllib.request.Request(
        'http://127.0.0.1:8080/v1/runtime/dispatch',
        data=raw,
        method='POST',
        headers={{'Authorization': 'Bearer ' + secret, 'Content-Type': 'application/json'}},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            response_status = response.status
            response_body = response.read().decode()
    except urllib.error.HTTPError as error:
        response_status = error.code
        response_body = error.read().decode()
    response_value = json.loads(response_body)
    frames = [json.loads(frame) for frame in response_value.get('frames', [])]
    terminal = frames[-1] if frames else None
    if response_status != 200 or not isinstance(terminal, dict) or terminal.get('kind') != 'failed':
        raise RuntimeError('runtime did not return a failed terminal frame at the bounded boundary')
    if terminal.get('failure', {{}}).get('code') != 'budget_exhausted':
        raise RuntimeError('runtime did not preserve budget_exhausted from Hermes')
    print(json.dumps({{
        'status': response_status,
        'frameKinds': [frame.get('body', {{}}).get('kind', frame.get('kind')) for frame in frames],
        'terminal': terminal,
    }}, sort_keys=True))
finally:
    if service.poll() is None:
        service.send_signal(signal.SIGTERM)
    stdout, stderr = service.communicate(timeout=10)
    if gateway.poll() is None:
        gateway.send_signal(signal.SIGTERM)
    gateway_stdout, gateway_stderr = gateway.communicate(timeout=10)
    provider_calls = Path('/tmp/g4-provider-call-count').read_text(encoding='utf-8') if Path('/tmp/g4-provider-call-count').exists() else 'missing'
    if provider_calls != '17':
        raise RuntimeError(
            f'bounded provider call count was {{provider_calls!r}}, expected 16 successful exchanges plus one boundary rejection'
        )
    print(json.dumps({{'serviceReturncode': service.returncode, 'serviceStdout': stdout[-2000:], 'serviceStderr': stderr[-4000:], 'gatewayReturncode': gateway.returncode, 'gatewayStderr': gateway_stderr[-1000:], 'providerCalls': provider_calls}}, sort_keys=True))
"""
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-i",
            "--network",
            "none",
            "--read-only",
            "--user",
            "65532:65532",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,nodev,size=64m",
            "--entrypoint",
            "python3",
            IMAGE,
            "-",
        ],
        input=program,
        text=True,
        capture_output=True,
        timeout=120,
    )
    print(f"program-bytes={len(program)}", file=sys.stderr)
    print(f"host-docker-returncode={result.returncode} stdout-bytes={len(result.stdout)} stderr-bytes={len(result.stderr)}", file=sys.stderr)
    print(result.stdout, end="")
    print(result.stderr, end="", file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
