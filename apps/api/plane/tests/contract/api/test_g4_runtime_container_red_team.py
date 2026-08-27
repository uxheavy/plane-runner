# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


def test_g4_runtime_container_red_team_proves_the_pinned_real_image_and_cleans_labeled_resources():
    docker = shutil.which("docker")
    if docker is None:
        pytest.fail("external_required: Docker CLI is unavailable; container proof cannot be skipped")
    root = Path(__file__).resolve().parents[6]
    compose = root / "deployments/cli/community/docker-compose.yml"
    variables = root / "deployments/cli/community/variables.env"
    resolved = subprocess.run(
        [docker, "compose", "-f", str(compose), "--env-file", str(variables), "config", "--format", "json"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if resolved.returncode != 0:
        pytest.fail(f"external_required: Compose could not resolve the runtime image: {resolved.stderr[-512:]}")
    image = json.loads(resolved.stdout)["services"]["agent-runtime"]["image"]
    image_id = subprocess.run(
        [docker, "image", "inspect", image, "--format", "{{.Id}}"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if image_id.returncode != 0:
        pytest.fail(f"external_required: configured runtime image is unavailable: {image}")
    tool = root / "tools/agent-g4-runtime-red-team.py"
    result = subprocess.run(
        [os.environ.get("PYTHON", "python3"), str(tool)],
        cwd=root,
        env={
            **os.environ,
            "PLANE_G4_RUNTIME_IMAGE": image,
            "PLANE_G4_RUNTIME_IMAGE_DIGEST": image_id.stdout.strip(),
        },
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "dispatch_http=passed" in result.stdout
    assert "full_chain=passed" in result.stdout
    assert "hermes_agent_loop=passed" in result.stdout
    assert "provider_transport_seam=passed" in result.stdout
    assert "agent_identity=passed" in result.stdout
    assert "tamper_guard=passed" in result.stdout
    assert "filesystem_confinement=passed" in result.stdout
    assert "cleanup_failed" not in result.stdout
