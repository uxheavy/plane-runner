import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from plane.tests.contract.api.libpq_environment_baseline import LIBPQ_CONNECTION_ENVIRONMENT_NAMES_V1


API_ROOT = Path(__file__).resolve().parents[4]
REPOSITORY_ROOT = API_ROOT.parents[1]
COMPOSE_FILE = REPOSITORY_ROOT / "deployments/cli/community/docker-compose.yml"
MIGRATOR_ENTRYPOINT = API_ROOT / "bin/docker-entrypoint-migrator.sh"
PROVISIONER_ENTRYPOINT = API_ROOT / "bin/docker-entrypoint-provisioner.sh"


MIGRATION_POSTGRES_VARS = (
    "PGHOST",
    "PGDATABASE",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
)
MIGRATION_ENV_VARS = (
    *LIBPQ_CONNECTION_ENVIRONMENT_NAMES_V1,
    "PGDATA",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_INITDB_ARGS",
    "POSTGRES_INITDB_WALDIR",
    "POSTGRES_HOST_AUTH_METHOD",
    "POSTGRES_READ_REPLICA_DB",
    "POSTGRES_READ_REPLICA_USER",
    "POSTGRES_READ_REPLICA_PASSWORD",
    "POSTGRES_READ_REPLICA_HOST",
    "POSTGRES_READ_REPLICA_PORT",
    "DATABASE_READ_REPLICA_URL",
    "PLANE_AUDIT_RUNTIME_PASSWORD",
    "PLANE_AUDIT_MIGRATION_PASSWORD",
    "DATABASE_MIGRATION_URL",
    "DATABASE_PROVISIONER_URL",
)
MIGRATION_DATABASE_PREFIXES = (
    "DATABASE_MIGRATION_",
    "DATABASE_BOOTSTRAP_",
    "DATABASE_MIGRATOR_",
    "DATABASE_ADMIN_",
    "DATABASE_SUPERUSER_",
)


def _settings_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in list(environment):
        if name in MIGRATION_ENV_VARS or name.startswith(MIGRATION_DATABASE_PREFIXES):
            environment.pop(name, None)
    for name in ("DATABASE_URL", "DATABASE_RUNTIME_URL", "PLANE_DB_MIGRATION_MODE", "PLANE_DB_PROVISIONER_MODE"):
        environment.pop(name, None)
    environment.update(
        {
            "DJANGO_SETTINGS_MODULE": "plane.settings.production",
            "DEBUG": "0",
            "PLANE_AUDIT_ENFORCE_ROLE_SEPARATION": "1",
            "PLANE_AUDIT_RUNTIME_ROLE": "plane_runtime",
            "PLANE_AUDIT_GOVERNANCE_ROLE": "plane_audit_owner",
            "PLANE_AUDIT_MIGRATION_ROLE": "plane_migrator",
            "PLANE_AUDIT_PROVISIONER_ROLE": "plane_provisioner",
            "REDIS_URL": "redis://127.0.0.1:6379/",
            "SECRET_KEY": "runtime-settings-test-key",
            "LIVE_SERVER_SECRET_KEY": "runtime-settings-test-key",
            "CORS_ALLOWED_ORIGINS": "http://localhost",
            "PLANE_AGENT_RUNTIME_URL": "http://agent-runtime:8080",
            "PLANE_AGENT_RUNTIME_HOST_URL": "http://api:8091",
            "PLANE_AGENT_RUNTIME_SECRET": "runtime-settings-agent-secret-0123456789",
        }
    )
    return environment


def _resolved_community_services() -> dict[str, dict]:
    """Read the host-resolved Compose model when the verifier has provided it."""

    configured_path = os.environ.get("PLANE_COMMUNITY_COMPOSE_CONFIG")
    if configured_path:
        path = Path(configured_path)
        assert path.is_file(), f"required resolved Compose model is missing: {path}"
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload["services"]

    docker = shutil.which("docker")
    assert docker is not None, (
        "Docker is required for the production credential-topology proof; this check cannot be skipped"
    )
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
    return json.loads(result.stdout)["services"]


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


def _production_libpq_environment_names() -> frozenset[str]:
    environment = _settings_environment()
    environment["DATABASE_RUNTIME_URL"] = "postgresql://plane_runtime:runtime@db/plane"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import django; django.setup(); "
            "from plane.settings.production import _LIBPQ_CONNECTION_ENVIRONMENT_NAMES_V1 as names; "
            "import json; print(json.dumps(sorted(names)))",
        ],
        cwd=API_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return frozenset(json.loads(result.stdout))


def _run_migrator(environment: dict[str, str], tmp_path: Path) -> tuple[subprocess.CompletedProcess[str], Path]:
    probe_path = tmp_path / "python-calls"
    fake_python = tmp_path / "python"
    fake_python.write_text(
        "#!/bin/sh\n"
        'printf \'%s\\n\' "DATABASE_URL=$DATABASE_URL" "DATABASE_MIGRATION_URL=$DATABASE_MIGRATION_URL" '
        '"PLANE_DB_MIGRATION_MODE=$PLANE_DB_MIGRATION_MODE" "ARGS=$*" >> "$MIGRATOR_PROBE"\n'
    )
    fake_python.chmod(0o755)
    result = subprocess.run(
        ["bash", str(MIGRATOR_ENTRYPOINT), "--probe"],
        cwd=API_ROOT,
        env={
            **environment,
            "PATH": f"{tmp_path}:{os.environ.get('PATH', '')}",
            "MIGRATOR_PROBE": str(probe_path),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    return result, probe_path


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
def test_provisioner_boots_only_with_explicit_provisioner_authority():
    environment = _settings_environment()
    provisioner_url = "postgresql://plane_provisioner:provisioner@db/plane"
    environment.update(
        {
            "PLANE_DB_PROVISIONER_MODE": "1",
            "DATABASE_URL": provisioner_url,
            "DATABASE_PROVISIONER_URL": provisioner_url,
            "PGHOST": "db",
            "PGDATABASE": "plane",
            "POSTGRES_PORT": "5432",
            "POSTGRES_DB": "plane",
            "POSTGRES_USER": "plane_provisioner",
            "POSTGRES_PASSWORD": "provisioner",
            "PLANE_AUDIT_MIGRATION_PASSWORD": "migration",
        }
    )

    result = _boot_settings(environment)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "plane_provisioner"


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
    assert "migration database environment variables" in result.stderr


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
@pytest.mark.parametrize(
    "database_url",
    (
        "postgresql://plane%5Fmigrator:runtime@db/plane",
        "postgresql://PLANE_MIGRATOR:runtime@db/plane",
        "postgresql://plane%EF%BC%BFmigrator:runtime@db/plane",
        "postgresql://PLANE_RUNTIME:runtime@db/plane",
        "postgresql://plane%EF%BC%BFruntime:runtime@db/plane",
        "postgresql://plane%ZZ:runtime@db/plane",
        "postgresql://plane_runtime:pass%ZZ@db/plane",
    ),
)
def test_normal_runtime_rejects_encoded_ambiguous_or_malformed_database_roles(database_url):
    environment = _settings_environment()
    environment.update({"DATABASE_RUNTIME_URL": database_url})

    result = _boot_settings(environment)

    assert result.returncode != 0
    assert "plane_migrator" not in result.stderr
    assert "postgresql://" not in result.stderr


@pytest.mark.contract
def test_normal_runtime_accepts_percent_encoded_exact_role_and_delimited_password():
    environment = _settings_environment()
    environment.update(
        {
            "DATABASE_RUNTIME_URL": "postgresql://plane%5Fruntime:p%40ss%3Awith%2Fdelimiters@db/plane",
        }
    )

    result = _boot_settings(environment)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "plane_runtime"


@pytest.mark.contract
def test_normal_runtime_accepts_delimited_password_and_does_not_compare_secrets():
    environment = _settings_environment()
    environment.update(
        {
            "DATABASE_RUNTIME_URL": "postgresql://plane_runtime:p%40ss%3Awith%2Fdelimiters@db/plane",
            "DATABASE_URL": "postgresql://plane_runtime:a-different-secret@db/plane",
        }
    )

    result = _boot_settings(environment)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "plane_runtime"


@pytest.mark.contract
@pytest.mark.parametrize("name", MIGRATION_ENV_VARS)
def test_normal_runtime_rejects_each_supported_migration_database_alias(name):
    environment = _settings_environment()
    environment.update(
        {
            "DATABASE_RUNTIME_URL": "postgresql://plane_runtime:runtime@db/plane",
            name: "migration-only-value",
        }
    )

    result = _boot_settings(environment)

    assert result.returncode != 0
    assert "migration database environment variables" in result.stderr


@pytest.mark.contract
@pytest.mark.parametrize(
    "name",
    (
        "DATABASE_MIGRATION_USER",
        "DATABASE_BOOTSTRAP_PASSWORD",
        "DATABASE_MIGRATOR_HOST",
        "DATABASE_ADMIN_URL",
        "DATABASE_SUPERUSER_PASSWORD",
    ),
)
def test_normal_runtime_rejects_supported_database_authority_prefixes(name):
    environment = _settings_environment()
    environment.update(
        {
            "DATABASE_RUNTIME_URL": "postgresql://plane_runtime:runtime@db/plane",
            name: "migration-only-value",
        }
    )

    result = _boot_settings(environment)

    assert result.returncode != 0
    assert "migration database environment variables" in result.stderr


@pytest.mark.contract
def test_normal_runtime_allows_unrelated_database_environment_names():
    environment = _settings_environment()
    environment.update(
        {
            "DATABASE_RUNTIME_URL": "postgresql://plane_runtime:runtime@db/plane",
            "PG_CUSTOM_APPLICATION_FLAG": "allowed",
        }
    )

    result = _boot_settings(environment)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "plane_runtime"


@pytest.mark.contract
def test_migration_settings_compare_roles_without_comparing_passwords():
    environment = _settings_environment()
    environment.update(
        {
            "PLANE_DB_MIGRATION_MODE": "1",
            "DATABASE_URL": "postgresql://plane_migrator:legacy-secret@db/plane",
            "DATABASE_MIGRATION_URL": "postgresql://plane_migrator:migration%3Asecret@db/plane",
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
def test_migration_settings_require_exact_configured_migration_role():
    environment = _settings_environment()
    environment.update(
        {
            "PLANE_DB_MIGRATION_MODE": "1",
            "DATABASE_URL": "postgresql://PLANE_MIGRATOR:legacy-secret@db/plane",
            "DATABASE_MIGRATION_URL": "postgresql://plane_migrator:migration@db/plane",
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
    assert "one-shot migrator DATABASE_URL" in result.stderr
    assert "postgresql://" not in result.stderr


@pytest.mark.contract
def test_runtime_denylist_matches_the_independent_reviewed_libpq_baseline():
    production_names = _production_libpq_environment_names()
    assert not LIBPQ_CONNECTION_ENVIRONMENT_NAMES_V1 - production_names
    assert not production_names - LIBPQ_CONNECTION_ENVIRONMENT_NAMES_V1
    assert {"PGUSER", "PGPASSWORD", "PGHOST"} <= LIBPQ_CONNECTION_ENVIRONMENT_NAMES_V1
    assert "PGCONNECTTIMEOUT" in LIBPQ_CONNECTION_ENVIRONMENT_NAMES_V1
    assert "PGCHANNELBINDING" in LIBPQ_CONNECTION_ENVIRONMENT_NAMES_V1
    assert "PGCHANNELBIND" in LIBPQ_CONNECTION_ENVIRONMENT_NAMES_V1


@pytest.mark.contract
def test_independent_libpq_inventory_detects_add_and_remove_mutations():
    def assert_exact(actual):
        assert not LIBPQ_CONNECTION_ENVIRONMENT_NAMES_V1 - actual
        assert not actual - LIBPQ_CONNECTION_ENVIRONMENT_NAMES_V1

    with pytest.raises(AssertionError):
        assert_exact(LIBPQ_CONNECTION_ENVIRONMENT_NAMES_V1 - {"PGUSER"})
    with pytest.raises(AssertionError):
        assert_exact(LIBPQ_CONNECTION_ENVIRONMENT_NAMES_V1 | {"PG_UNREVIEWED_ALIAS"})


@pytest.mark.contract
@pytest.mark.parametrize(
    ("environment_overrides", "expected_message"),
    (
        ({"DATABASE_MIGRATION_URL": "postgresql://plane_migrator:migration@db/plane"}, "PLANE_DB_MIGRATION_MODE=1"),
        ({"PLANE_DB_MIGRATION_MODE": "1"}, "DATABASE_MIGRATION_URL"),
        (
            {
                "PLANE_DB_MIGRATION_MODE": "1",
                "DATABASE_MIGRATION_URL": "postgresql://plane_migrator:migration@db/plane",
                "DATABASE_RUNTIME_URL": "postgresql://plane_runtime:runtime@db/plane",
            },
            "DATABASE_RUNTIME_URL",
        ),
        (
            {
                "PLANE_DB_MIGRATION_MODE": "1",
                "DATABASE_MIGRATION_URL": "postgresql://plane_migrator:migration@db/plane",
                "DATABASE_URL": "postgresql://plane_runtime:runtime@db/plane",
            },
            "DATABASE_URL",
        ),
        (
            {
                "PLANE_DB_MIGRATION_MODE": "0",
                "DATABASE_MIGRATION_URL": "postgresql://plane_migrator:migration@db/plane",
            },
            "PLANE_DB_MIGRATION_MODE=1",
        ),
    ),
)
def test_migrator_rejects_invalid_authority_before_python(environment_overrides, expected_message, tmp_path):
    environment = _settings_environment()
    environment.update(environment_overrides)

    result, probe_path = _run_migrator(environment, tmp_path)

    assert result.returncode != 0
    assert expected_message in result.stderr
    assert not probe_path.exists()


@pytest.mark.contract
def test_migrator_sets_exact_migration_authority_before_every_python_call(tmp_path):
    environment = _settings_environment()
    migration_url = "postgresql://plane_migrator:migration@db/plane"
    environment.update(
        {
            "PLANE_DB_MIGRATION_MODE": "1",
            "DATABASE_MIGRATION_URL": migration_url,
        }
    )

    result, probe_path = _run_migrator(environment, tmp_path)

    assert result.returncode == 0, result.stderr
    calls = probe_path.read_text().splitlines()
    assert len(calls) == 12
    assert all(f"DATABASE_URL={migration_url}" in call for call in calls[0::4])
    assert all(f"DATABASE_MIGRATION_URL={migration_url}" in call for call in calls[1::4])
    assert all("PLANE_DB_MIGRATION_MODE=1" in call for call in calls[2::4])
    assert "verify_operation_gateway_migration_boundary" in calls[7]


@pytest.mark.contract
def test_resolved_community_compose_scopes_database_credentials_by_process():
    services = _resolved_community_services()

    for service in ("api", "worker", "beat-worker"):
        environment = services[service]["environment"]
        assert environment["DATABASE_RUNTIME_URL"]
        assert "DATABASE_MIGRATION_URL" not in environment
        assert "DATABASE_PROVISIONER_URL" not in environment
        assert "PLANE_AUDIT_MIGRATION_PASSWORD" not in environment
        assert "PLANE_DB_MIGRATION_MODE" not in environment
        assert not any(name in environment for name in MIGRATION_ENV_VARS)

    migrator_environment = services["migrator"]["environment"]
    assert migrator_environment["PLANE_DB_MIGRATION_MODE"] == "1"
    assert migrator_environment["DATABASE_MIGRATION_URL"]
    assert migrator_environment["DATABASE_URL"] == migrator_environment["DATABASE_MIGRATION_URL"]
    assert "DATABASE_RUNTIME_URL" not in migrator_environment
    assert "DATABASE_PROVISIONER_URL" not in migrator_environment
    assert "PLANE_AUDIT_MIGRATION_PASSWORD" not in migrator_environment
    assert all(name in migrator_environment for name in MIGRATION_POSTGRES_VARS)

    provisioner_environment = services["provisioner"]["environment"]
    assert provisioner_environment["PLANE_DB_PROVISIONER_MODE"] == "1"
    assert provisioner_environment["DATABASE_PROVISIONER_URL"]
    assert "DATABASE_MIGRATION_URL" not in provisioner_environment
    assert "DATABASE_RUNTIME_URL" not in provisioner_environment
    assert provisioner_environment["PLANE_AUDIT_MIGRATION_PASSWORD"]
    assert services["migrator"]["depends_on"]["provisioner"]["condition"] == "service_completed_successfully"
    assert services["provisioner-final"]["depends_on"]["migrator"]["condition"] == "service_completed_successfully"


@pytest.mark.contract
def test_agent_runtime_production_compose_has_an_isolated_readiness_and_secret_boundary():
    services = _resolved_community_services()
    resolver = API_ROOT / "bin/plane-agent-runtime-credential-resolver"
    assert resolver.is_file()
    assert resolver.stat().st_mode & 0o111
    installed_resolver = (
        "COPY ./bin/plane-agent-runtime-credential-resolver "
        "/usr/local/bin/plane-agent-runtime-credential-resolver"
    )
    assert installed_resolver in (API_ROOT / "Dockerfile.api").read_text(encoding="utf-8")
    runtime = services["agent-runtime"]
    runtime_environment = runtime["environment"]
    assert runtime["image"].startswith("uxheavy/plane-agent-runtime:hermes-114eabf9-g4-879c679")
    assert "network_mode" not in runtime
    assert "agent_runtime_internal" in runtime["networks"]
    assert not runtime.get("ports")
    assert "agent_runtime_internal" in services["api"]["networks"]
    assert "agent_runtime_internal" in services["worker"]["networks"]
    assert runtime["read_only"] is True
    assert runtime["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in runtime["security_opt"]
    assert runtime["pids_limit"] > 0
    assert runtime["mem_limit"]
    assert runtime["cpus"]
    assert runtime_environment["PLANE_AGENT_RUNTIME_NETWORK_POLICY"] == "none"
    assert runtime_environment["PLANE_AGENT_RUNTIME_SECRET_FILE"] == "/run/secrets/plane_agent_runtime"
    assert "PLANE_AGENT_RUNTIME_SECRET" not in runtime_environment
    assert "PLANE_AGENT_RUNTIME_CREDENTIAL_RESOLVER" not in runtime_environment
    assert "PLANE_AGENT_RUNTIME_CREDENTIALS_JSON" not in runtime_environment
    healthcheck = runtime["healthcheck"]
    assert healthcheck["test"][0] == "CMD-SHELL"
    assert "/health/ready" in healthcheck["test"][1]
    assert services["api"]["environment"]["PLANE_AGENT_RUNTIME_SECRET_FILE"] == "/run/secrets/plane_agent_runtime"
    assert "PLANE_AGENT_RUNTIME_SECRET" not in services["api"]["environment"]
    assert services["api"]["environment"]["PLANE_AGENT_RUNTIME_CREDENTIAL_RESOLVER"].startswith("command:")
    assert services["api"]["environment"]["PLANE_AGENT_RUNTIME_CREDENTIAL_RESOLVER"] == (
        "command:/usr/local/bin/plane-agent-runtime-credential-resolver"
    )
    provider_secret = next(
        secret for secret in services["api"]["secrets"] if secret["source"] == "plane_agent_provider_credentials"
    )
    assert provider_secret["target"] == "/run/secrets/plane_agent_provider_credentials"
    assert all(
        secret["source"] != "plane_agent_provider_credentials"
        for secret in services["agent-runtime"].get("secrets", [])
    )
    assert services["api"]["environment"]["PLANE_AGENT_RUNTIME_CREDENTIAL_STATE_FILE"] == (
        "/run/plane-agent-credentials/revocations.json"
    )
    assert any(
        (volume.get("source") if isinstance(volume, dict) else volume).startswith("agent_runtime_credential_state")
        for volume in services["api"].get("volumes", [])
    )
