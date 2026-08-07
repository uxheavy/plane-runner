from __future__ import annotations

from .test_production_runtime_configuration import _boot_settings, _settings_environment


def test_agent_runtime_production_accepts_a_bound_url_and_disposable_secret():
    environment = _settings_environment()
    environment.update(
        {
            "DATABASE_RUNTIME_URL": "postgresql://plane_runtime:runtime@db/plane",
            "DATABASE_URL": "postgresql://plane_runtime:runtime@db/plane",
        }
    )
    result = _boot_settings(environment)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "plane_runtime"


def test_agent_runtime_production_rejects_missing_runtime_url():
    environment = _settings_environment()
    environment.pop("PLANE_AGENT_RUNTIME_URL")
    result = _boot_settings(environment)
    assert result.returncode != 0
    assert "PLANE_AGENT_RUNTIME_URL" in result.stderr


def test_agent_runtime_production_rejects_invalid_url_without_silent_none_fallback():
    environment = _settings_environment()
    environment["PLANE_AGENT_RUNTIME_URL"] = "not-a-url"
    result = _boot_settings(environment)
    assert result.returncode != 0
    assert "Production Agent runtime configuration is invalid" in result.stderr
    assert "not-a-url" not in result.stderr


def test_agent_runtime_production_rejects_missing_runtime_credential():
    environment = _settings_environment()
    environment.pop("PLANE_AGENT_RUNTIME_SECRET")
    result = _boot_settings(environment)
    assert result.returncode != 0
    assert "PLANE_AGENT_RUNTIME_SECRET" in result.stderr


def test_agent_runtime_production_rejects_placeholder_runtime_credential():
    environment = _settings_environment()
    environment["PLANE_AGENT_RUNTIME_SECRET"] = "change-this-runtime-password"
    result = _boot_settings(environment)
    assert result.returncode != 0
    assert "Production Agent runtime configuration is invalid" in result.stderr
