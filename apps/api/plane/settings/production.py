# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Production settings"""

# The settings module intentionally imports the complete common settings surface.
# Ruff cannot infer names supplied by that established settings pattern.
# ruff: noqa: F403, F405

import os
import re
import unicodedata
from urllib.parse import unquote_to_bytes
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured

from .common import *  # noqa

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = int(os.environ.get("DEBUG", 0)) == 1


_MALFORMED_PERCENT_ESCAPE = re.compile(r"%(?![0-9a-fA-F]{2})")

# Keep this private, versioned inventory in lockstep with the PostgreSQL/libpq
# baseline. These names can select connection authority, credentials, client
# security behavior, or session behavior and must never be inherited by a
# normal runtime process. The legacy PGCHANNELBIND spelling is included only
# so callers cannot use the old typo as an unreviewed alias.
_LIBPQ_CONNECTION_ENVIRONMENT_NAMES_V1 = frozenset(
    {
        "PGAPPNAME",
        "PGCHANNELBINDING",
        "PGCHANNELBIND",
        "PGCLIENTENCODING",
        "PGCONNECTTIMEOUT",
        "PGCONNECT_TIMEOUT",
        "PGDATABASE",
        "PGDATESTYLE",
        "PGGEQO",
        "PGGSSENCMODE",
        "PGGSSLIB",
        "PGHOST",
        "PGHOSTADDR",
        "PGKRBSRVNAME",
        "PGLOADBALANCEHOSTS",
        "PGLOCALEDIR",
        "PGOPTIONS",
        "PGPASSFILE",
        "PGPASSWORD",
        "PGPORT",
        "PGREQUIREPEER",
        "PGREQUIRESSL",
        "PGSERVICE",
        "PGSERVICEFILE",
        "PGSSLCERT",
        "PGSSLCOMPRESSION",
        "PGSSLCRL",
        "PGSSLCRLDIR",
        "PGSSLKEY",
        "PGSSLMAXPROTOCOLVERSION",
        "PGSSLMINPROTOCOLVERSION",
        "PGSSLMODE",
        "PGSSLROOTCERT",
        "PGSSLSNI",
        "PGSYSCONFDIR",
        "PGTARGETSESSIONATTRS",
        "PGTZ",
        "PGUSER",
    }
)
_MIGRATION_DATABASE_ENVIRONMENT_NAMES_V1 = frozenset(
    {
        *_LIBPQ_CONNECTION_ENVIRONMENT_NAMES_V1,
        # PostgreSQL image/bootstrap aliases.
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
        # Migrator-only Plane credentials.
        "PLANE_AUDIT_RUNTIME_PASSWORD",
        "PLANE_AUDIT_MIGRATION_PASSWORD",
        "DATABASE_PROVISIONER_URL",
    }
)
_MIGRATION_DATABASE_ENVIRONMENT_PREFIXES = (
    "DATABASE_MIGRATION_",
    "DATABASE_BOOTSTRAP_",
    "DATABASE_MIGRATOR_",
    "DATABASE_ADMIN_",
    "DATABASE_SUPERUSER_",
)


def _is_migration_database_environment_name(name):
    return name in _MIGRATION_DATABASE_ENVIRONMENT_NAMES_V1 or name.startswith(_MIGRATION_DATABASE_ENVIRONMENT_PREFIXES)


def _decode_database_url_component(value):
    if _MALFORMED_PERCENT_ESCAPE.search(value):
        raise ImproperlyConfigured("Database URL contains malformed credential encoding")
    try:
        return unquote_to_bytes(value).decode("utf-8")
    except UnicodeDecodeError as error:
        raise ImproperlyConfigured("Database URL contains invalid credential encoding") from error


def _database_url_user(value):
    if not value:
        return None
    try:
        parsed = urlparse(value)
        username = parsed.username
        password = parsed.password
    except ValueError as error:
        raise ImproperlyConfigured("Database URL contains invalid credential encoding") from error
    if username is None:
        return None
    # Decode both credential components so malformed escapes cannot be hidden
    # in a password while the username check is being performed. The password
    # is deliberately discarded and never included in an error message.
    decoded_username = _decode_database_url_component(username)
    if password is not None:
        _decode_database_url_component(password)
    return decoded_username


def _canonical_database_role(value):
    if not value:
        return None
    return unicodedata.normalize("NFKC", value).casefold()


_PRIVILEGED_DATABASE_ROLE_NAMES = frozenset(
    {
        "plane_audit_owner",
        "plane_migrator",
        "plane_runtime",
        "postgres",
        "root",
    }
)


def _reject_confusable_privileged_role(value):
    """Reject normalized aliases without using normalization as identity."""

    normalized = _canonical_database_role(value)
    if value and value != normalized and normalized in _PRIVILEGED_DATABASE_ROLE_NAMES:
        raise ImproperlyConfigured("A database role is a PostgreSQL-distinct confusable privileged role")


def _database_role_matches(value, role):
    return value is not None and role is not None and value == role


def _reject_migration_environment_leakage():
    leaked = sorted(name for name in os.environ if _is_migration_database_environment_name(name))
    if leaked:
        raise ImproperlyConfigured(
            "Normal production processes must not receive migration database environment variables: "
            + ", ".join(leaked)
        )


def _validate_production_database_boundary():
    if PLANE_DB_PROVISIONER_MODE:
        provisioner_url = os.environ.get("DATABASE_PROVISIONER_URL")
        required_provisioner_env = (
            "DATABASE_PROVISIONER_URL",
            "PGHOST",
            "PGDATABASE",
            "POSTGRES_PORT",
            "POSTGRES_DB",
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
        )
        missing = [name for name in required_provisioner_env if not os.environ.get(name)]
        if missing:
            raise ImproperlyConfigured("Production provisioner mode requires " + ", ".join(missing))
        if os.environ.get("DATABASE_RUNTIME_URL") or os.environ.get("DATABASE_MIGRATION_URL"):
            raise ImproperlyConfigured("The provisioner must not receive runtime or migration database URLs")
        provisioner_url_role = _database_url_user(provisioner_url)
        if not provisioner_url_role:
            raise ImproperlyConfigured("The provisioner database URL must declare the provisioner role")
        _reject_confusable_privileged_role(provisioner_url_role)
        if not _database_role_matches(provisioner_url_role, PLANE_AUDIT_PROVISIONER_ROLE):
            raise ImproperlyConfigured("The provisioner database URL must use the configured provisioner role")
        if not _database_role_matches(DATABASES["default"].get("USER"), provisioner_url_role):
            raise ImproperlyConfigured("The provisioner database settings must use the provisioner role")
        return

    if PLANE_DB_MIGRATION_MODE:
        migration_url = os.environ.get("DATABASE_MIGRATION_URL")
        required_migration_env = (
            "DATABASE_MIGRATION_URL",
            "PGHOST",
            "PGDATABASE",
            "POSTGRES_PORT",
            "POSTGRES_DB",
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
        )
        missing = [name for name in required_migration_env if not os.environ.get(name)]
        if missing:
            raise ImproperlyConfigured("Production migration mode requires " + ", ".join(missing))
        if os.environ.get("DATABASE_RUNTIME_URL"):
            raise ImproperlyConfigured("The one-shot migrator must not receive DATABASE_RUNTIME_URL")
        migration_url_role = _database_url_user(migration_url)
        if not migration_url_role:
            raise ImproperlyConfigured("The migration database URL must declare the migration role")
        _reject_confusable_privileged_role(migration_url_role)
        _reject_confusable_privileged_role(DATABASES["default"].get("USER"))
        _reject_confusable_privileged_role(PLANE_AUDIT_MIGRATION_ROLE)
        database_url = os.environ.get("DATABASE_URL")
        database_url_role = _database_url_user(database_url)
        if database_url and not _database_role_matches(database_url_role, migration_url_role):
            raise ImproperlyConfigured("The one-shot migrator DATABASE_URL must use the migration role")
        migration_settings_match = _database_role_matches(
            DATABASES["default"].get("USER"), migration_url_role
        ) and _database_role_matches(migration_url_role, PLANE_AUDIT_MIGRATION_ROLE)
        if not migration_settings_match:
            raise ImproperlyConfigured("The migration database settings must use the migration role")
        return

    if not PLANE_AUDIT_ENFORCE_ROLE_SEPARATION or DEBUG:
        return

    if not os.environ.get("DATABASE_RUNTIME_URL"):
        raise ImproperlyConfigured("Production runtime requires DATABASE_RUNTIME_URL")
    _reject_migration_environment_leakage()

    runtime_url_role = _database_url_user(DATABASE_RUNTIME_URL)
    resolved_runtime_role = DATABASES["default"].get("USER")
    _reject_confusable_privileged_role(runtime_url_role)
    _reject_confusable_privileged_role(resolved_runtime_role)
    _reject_confusable_privileged_role(PLANE_AUDIT_RUNTIME_ROLE)
    if (
        not runtime_url_role
        or not resolved_runtime_role
        or not _database_role_matches(runtime_url_role, resolved_runtime_role)
        or not _database_role_matches(runtime_url_role, PLANE_AUDIT_RUNTIME_ROLE)
    ):
        raise ImproperlyConfigured("The runtime database URL must declare the resolved runtime role")

    privileged_roles = {
        PLANE_AUDIT_MIGRATION_ROLE,
        PLANE_AUDIT_GOVERNANCE_ROLE,
        PLANE_AUDIT_PROVISIONER_ROLE,
        "postgres",
        "root",
    }
    for name, value in (
        ("DATABASE_RUNTIME_URL", DATABASE_RUNTIME_URL),
        ("DATABASE_URL", os.environ.get("DATABASE_URL")),
    ):
        if _canonical_database_role(_database_url_user(value)) in {
            _canonical_database_role(role) for role in privileged_roles
        }:
            raise ImproperlyConfigured(f"{name} must use the non-privileged runtime database role")
    database_url_role = _database_url_user(os.environ.get("DATABASE_URL"))
    if database_url_role and not _database_role_matches(database_url_role, runtime_url_role):
        raise ImproperlyConfigured("DATABASE_URL must use the configured runtime database role")
    if _canonical_database_role(resolved_runtime_role) in {_canonical_database_role(role) for role in privileged_roles}:
        raise ImproperlyConfigured("The resolved production database must use the non-privileged runtime database role")


_validate_production_database_boundary()

# Honor the 'X-Forwarded-Proto' header for request.is_secure()
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS += ("scout_apm.django",)  # noqa


# Scout Settings
SCOUT_MONITOR = os.environ.get("SCOUT_MONITOR", False)
SCOUT_KEY = os.environ.get("SCOUT_KEY", "")
SCOUT_NAME = "Plane"

LOG_DIR = os.path.join(BASE_DIR, "logs")  # noqa

if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Logging configuration
LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "formatters": {
        "verbose": {"format": "%(asctime)s [%(process)d] %(levelname)s %(name)s: %(message)s"},
        "json": {
            "()": "pythonjsonlogger.json.JsonFormatter",
            "fmt": "%(levelname)s %(asctime)s %(module)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "level": "INFO",
        },
        "file": {
            "class": "plane.utils.logging.SizedTimedRotatingFileHandler",
            "filename": (
                os.path.join(BASE_DIR, "logs", "plane-debug.log")  # noqa
                if DEBUG
                else os.path.join(BASE_DIR, "logs", "plane-error.log")  # noqa
            ),
            "when": "s",
            "maxBytes": 1024 * 1024 * 1,
            "interval": 1,
            "backupCount": 5,
            "formatter": "json",
            "level": "DEBUG" if DEBUG else "ERROR",
        },
    },
    "loggers": {
        "plane.api.request": {
            "level": "DEBUG" if DEBUG else "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
        "plane.api": {
            "level": "DEBUG" if DEBUG else "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
        "plane.worker": {
            "level": "DEBUG" if DEBUG else "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
        "plane.exception": {
            "level": "DEBUG" if DEBUG else "ERROR",
            "handlers": ["console", "file"],
            "propagate": False,
        },
        "plane.external": {
            "level": "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
        "plane.authentication": {
            "level": "DEBUG" if DEBUG else "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
        "plane.migrations": {
            "level": "DEBUG" if DEBUG else "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
    },
}
