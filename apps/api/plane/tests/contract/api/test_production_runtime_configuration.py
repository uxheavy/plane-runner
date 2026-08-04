import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


API_ROOT = Path(__file__).resolve().parents[4]
REPOSITORY_ROOT = API_ROOT.parents[1]
COMPOSE_FILE = REPOSITORY_ROOT / "deployments/cli/community/docker-compose.yml"
MIGRATION_POSTGRES_VARS = (
    "PGHOST",
    "PGDATABASE",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
)
MIGRATION_ENV_VARS = (*MIGRATION_POSTGRES_VARS, "POSTGRES_HOST")


def _settings_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in (
        "DATABASE_URL",
        "DATABASE_RUNTIME_URL",
        "DATABASE_MIGRATION_URL",
        "PLANE_DB_MIGRATION_MODE",
        *MIGRATION_ENV_VARS,
    ):
        environment.pop(name, None)
    environment.update(
        {
            "DJANGO_SETTINGS_MODULE": "plane.settings.production",
            "DEBUG": "0",
            "PLANE_AUDIT_ENFORCE_ROLE_SEPARATION": "1",
            "PLANE_AUDIT_RUNTIME_ROLE": "plane_runtime",
            "PLANE_AUDIT_GOVERNANCE_ROLE": "plane_audit_owner",
            "PLANE_AUDIT_MIGRATION_ROLE": "plane_migrator",
            "REDIS_URL": "redis://127.0.0.1:6379/",
            "SECRET_KEY": "runtime-settings-test-key",
            "LIVE_SERVER_SECRET_KEY": "runtime-settings-test-key",
            "CORS_ALLOWED_ORIGINS": "http://localhost",
        }
    )
    return environment


def _boot_settings(environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "import django; django.setup(); from django.conf import settings; "
            "print(settings.DATABASES['default']['USER'])",
        ],
        cwd=API_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.contract
@pytest.mark.parametrize("service", ("api", "worker", "beat"))
def test_runtime_services_boot_with_only_runtime_database_credentials(service):
    environment = _settings_environment()
    environment.update(
        {
            "PLANE_RUNTIME_SERVICE": service,
            "DATABASE_RUNTIME_URL": "postgresql://plane_runtime:runtime@db/plane",
        }
    )

    result = _boot_settings(environment)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "plane_runtime"


@pytest.mark.contract
def test_migrator_boots_only_in_explicit_migration_mode():
    environment = _settings_environment()
    migration_url = "postgresql://plane_migrator:migration@db/plane"
    environment.update(
        {
            "PLANE_DB_MIGRATION_MODE": "1",
            "DATABASE_URL": migration_url,
            "DATABASE_MIGRATION_URL": migration_url,
            "PGHOST": "db",
            "PGDATABASE": "plane",
            "POSTGRES_PORT": "5432",
            "POSTGRES_DB": "plane",
            "POSTGRES_USER": "plane_migrator",
            "POSTGRES_PASSWORD": "migration",
        }
    )

    result = _boot_settings(environment)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "plane_migrator"


@pytest.mark.contract
def test_migrator_without_migration_url_fails_closed():
    environment = _settings_environment()
    environment.update(
        {
            "PLANE_DB_MIGRATION_MODE": "1",
            "PGHOST": "db",
            "PGDATABASE": "plane",
            "POSTGRES_PORT": "5432",
            "POSTGRES_DB": "plane",
            "POSTGRES_USER": "plane_migrator",
            "POSTGRES_PASSWORD": "migration",
        }
    )

    result = _boot_settings(environment)

    assert result.returncode != 0
    assert "DATABASE_MIGRATION_URL" in result.stderr


@pytest.mark.contract
def test_normal_runtime_rejects_migration_environment_leakage():
    environment = _settings_environment()
    environment.update(
        {
            "DATABASE_URL": "postgresql://plane_runtime:runtime@db/plane",
            "DATABASE_RUNTIME_URL": "postgresql://plane_runtime:runtime@db/plane",
            "DATABASE_MIGRATION_URL": "postgresql://plane_migrator:migration@db/plane",
        }
    )

    result = _boot_settings(environment)

    assert result.returncode != 0
    assert "must not receive DATABASE_MIGRATION_URL" in result.stderr


@pytest.mark.contract
def test_normal_runtime_rejects_privileged_database_url_without_migration_secret():
    environment = _settings_environment()
    environment.update(
        {
            "DATABASE_RUNTIME_URL": "postgresql://plane_migrator:migration@db/plane",
        }
    )

    result = _boot_settings(environment)

    assert result.returncode != 0
    assert "non-privileged runtime database role" in result.stderr


@pytest.mark.contract
def test_resolved_community_compose_scopes_database_credentials_by_process():
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("docker is not available in this test environment")

    result = subprocess.run(
        [docker, "compose", "-f", str(COMPOSE_FILE), "config", "--format", "json"],
        cwd=REPOSITORY_ROOT,
        env={
            **os.environ,
            "CORS_ALLOWED_ORIGINS": "http://localhost",
            "LIVE_SERVER_SECRET_KEY": "compose-test-key",
            "SECRET_KEY": "compose-test-key",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    services = json.loads(result.stdout)["services"]

    for service in ("api", "worker", "beat-worker"):
        environment = services[service]["environment"]
        assert environment["DATABASE_RUNTIME_URL"]
        assert "DATABASE_MIGRATION_URL" not in environment
        assert "PLANE_DB_MIGRATION_MODE" not in environment
        assert not any(name in environment for name in MIGRATION_ENV_VARS)

    migrator_environment = services["migrator"]["environment"]
    assert migrator_environment["PLANE_DB_MIGRATION_MODE"] == "1"
    assert migrator_environment["DATABASE_MIGRATION_URL"]
    assert migrator_environment["DATABASE_URL"] == migrator_environment["DATABASE_MIGRATION_URL"]
    assert "DATABASE_RUNTIME_URL" not in migrator_environment
    assert all(name in migrator_environment for name in MIGRATION_POSTGRES_VARS)
