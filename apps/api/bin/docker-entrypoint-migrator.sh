#!/bin/bash
set -eu

# This entrypoint is a migration authority boundary. It must never inherit a
# runtime database URL or decide its mode from a defaulted environment.
if [ "${PLANE_DB_MIGRATION_MODE:-}" != "1" ]; then
  echo "PLANE_DB_MIGRATION_MODE=1 is required for the migrator entrypoint" >&2
  exit 64
fi
if [ -z "${DATABASE_MIGRATION_URL:-}" ]; then
  echo "DATABASE_MIGRATION_URL is required for the migrator entrypoint" >&2
  exit 64
fi
if [ -n "${DATABASE_RUNTIME_URL:-}" ]; then
  echo "DATABASE_RUNTIME_URL must not be provided to the migrator entrypoint" >&2
  exit 64
fi
if [ -n "${DATABASE_PROVISIONER_URL:-}" ] || [ -n "${PLANE_AUDIT_MIGRATION_PASSWORD:-}" ]; then
  echo "Provisioner credentials must not be provided to the migrator entrypoint" >&2
  exit 64
fi
if [ -n "${DATABASE_URL:-}" ] && [ "${DATABASE_URL}" != "${DATABASE_MIGRATION_URL}" ]; then
  echo "DATABASE_URL must match DATABASE_MIGRATION_URL for the migrator entrypoint" >&2
  exit 64
fi

export DATABASE_URL="${DATABASE_MIGRATION_URL}"
export PLANE_DB_MIGRATION_MODE=1

python manage.py wait_for_db "$@"
python manage.py verify_operation_gateway_migration_boundary "$@"
python manage.py migrate "$@"
