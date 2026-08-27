# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from .test_production_runtime_configuration import _boot_settings, _settings_environment


def _local_environment() -> dict[str, str]:
    environment = _settings_environment()
    environment.update(
        {
            "DJANGO_SETTINGS_MODULE": "plane.settings.local",
            "DEBUG": "1",
            "PLANE_AUDIT_ENFORCE_ROLE_SEPARATION": "0",
            "DATABASE_URL": "postgresql://plane:plane@db/plane",
            "DATABASE_RUNTIME_URL": "postgresql://plane:plane@db/plane",
        }
    )
    return environment


def test_local_runtime_disabled_does_not_require_runtime_configuration():
    environment = _local_environment()
    environment["PLANE_AGENT_RUNTIME_ENABLED"] = "0"
    environment.pop("PLANE_AGENT_RUNTIME_URL")
    environment.pop("PLANE_AGENT_RUNTIME_SECRET")

    result = _boot_settings(environment)

    assert result.returncode == 0, result.stderr


def test_local_runtime_enabled_accepts_the_shared_validated_boundary():
    environment = _local_environment()
    environment["PLANE_AGENT_RUNTIME_ENABLED"] = "1"

    result = _boot_settings(environment)

    assert result.returncode == 0, result.stderr


def test_local_runtime_enabled_rejects_missing_runtime_url():
    environment = _local_environment()
    environment["PLANE_AGENT_RUNTIME_ENABLED"] = "1"
    environment.pop("PLANE_AGENT_RUNTIME_URL")

    result = _boot_settings(environment)

    assert result.returncode != 0
    assert "Local Agent runtime configuration is invalid" in result.stderr
    assert "PLANE_AGENT_RUNTIME_URL" in result.stderr


def test_local_runtime_enabled_rejects_invalid_runtime_url_without_leaking_value():
    environment = _local_environment()
    environment["PLANE_AGENT_RUNTIME_ENABLED"] = "1"
    environment["PLANE_AGENT_RUNTIME_URL"] = "not-a-url"

    result = _boot_settings(environment)

    assert result.returncode != 0
    assert "Local Agent runtime configuration is invalid" in result.stderr
    assert "not-a-url" not in result.stderr
