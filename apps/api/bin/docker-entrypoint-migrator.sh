#!/bin/bash
set -e

# Production migrations and audit-role provisioning must use the migration
# authority. Runtime processes keep their separate DATABASE_URL credential.
if [ "${PLANE_AUDIT_ENFORCE_ROLE_SEPARATION:-0}" = "1" ]; then
  : "${DATABASE_MIGRATION_URL:?DATABASE_MIGRATION_URL is required for production migrations}"
  export DATABASE_URL="${DATABASE_MIGRATION_URL}"
  export PLANE_DB_MIGRATION_MODE=1
fi

python manage.py wait_for_db $1
python manage.py bootstrap_operation_gateway_audit $1

python manage.py migrate $1
