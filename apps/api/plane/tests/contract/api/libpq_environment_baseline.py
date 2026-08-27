# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Reviewed PostgreSQL/libpq connection environment baseline.

This is intentionally independent from ``plane.settings.production``. The
contract test compares the production denylist against this exact reviewed
PostgreSQL 15/libpq baseline in both directions, so deleting an alias cannot
silently delete its own test case.
"""

LIBPQ_CONNECTION_ENVIRONMENT_NAMES_V1 = frozenset(
    {
        "PGAPPNAME",
        "PGCHANNELBINDING",
        # Retained as a denied legacy spelling for compatibility hardening.
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
