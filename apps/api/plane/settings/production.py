# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Production settings"""

# The settings module intentionally imports the complete common settings surface.
# Ruff cannot infer names supplied by that established settings pattern.
# ruff: noqa: F403, F405

import os
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured

from .common import *  # noqa

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = int(os.environ.get("DEBUG", 0)) == 1

def _database_url_user(value):
    return urlparse(value).username if value else None


def _validate_production_database_boundary():
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
            raise ImproperlyConfigured(
                "Production migration mode requires " + ", ".join(missing)
            )
        if os.environ.get("DATABASE_RUNTIME_URL"):
            raise ImproperlyConfigured("The one-shot migrator must not receive DATABASE_RUNTIME_URL")
        database_url = os.environ.get("DATABASE_URL")
        if database_url and database_url != migration_url:
            raise ImproperlyConfigured("The one-shot migrator DATABASE_URL must be DATABASE_MIGRATION_URL")
        return

    if not PLANE_AUDIT_ENFORCE_ROLE_SEPARATION or DEBUG:
        return

    if not os.environ.get("DATABASE_RUNTIME_URL"):
        raise ImproperlyConfigured("Production runtime requires DATABASE_RUNTIME_URL")
    if "DATABASE_MIGRATION_URL" in os.environ:
        raise ImproperlyConfigured("Normal production processes must not receive DATABASE_MIGRATION_URL")
    migration_env = (
        "PGHOST",
        "PGDATABASE",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
    )
    leaked_migration_env = [name for name in migration_env if name in os.environ]
    if leaked_migration_env:
        raise ImproperlyConfigured(
            "Normal production processes must not receive migration POSTGRES variables: "
            + ", ".join(leaked_migration_env)
        )

    privileged_roles = {
        PLANE_AUDIT_MIGRATION_ROLE,
        PLANE_AUDIT_GOVERNANCE_ROLE,
        "postgres",
        "root",
    }
    for name, value in (
        ("DATABASE_RUNTIME_URL", DATABASE_RUNTIME_URL),
        ("DATABASE_URL", os.environ.get("DATABASE_URL")),
    ):
        if _database_url_user(value) in privileged_roles:
            raise ImproperlyConfigured(f"{name} must use the non-privileged runtime database role")


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
