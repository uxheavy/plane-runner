#!/bin/bash
set -eu

# This entrypoint is the only deployment path allowed to receive the
# provisioner credential. It never starts the application or migration code.
if [ "${PLANE_DB_PROVISIONER_MODE:-}" != "1" ]; then
  echo "PLANE_DB_PROVISIONER_MODE=1 is required for the provisioner entrypoint" >&2
  exit 64
fi
if [ -z "${DATABASE_PROVISIONER_URL:-}" ]; then
  echo "DATABASE_PROVISIONER_URL is required for the provisioner entrypoint" >&2
  exit 64
fi
if [ -n "${DATABASE_RUNTIME_URL:-}" ] || [ -n "${DATABASE_MIGRATION_URL:-}" ]; then
  echo "The provisioner entrypoint must not receive runtime or migration database URLs" >&2
  exit 64
fi

case "${1:-}" in
  --phase=before-migrate|--phase=after-migrate|--phase=before-reverse|--phase=after-reverse)
    phase="${1#--phase=}"
    ;;
  *)
    echo "A provisioning phase is required" >&2
    exit 64
    ;;
esac

export DATABASE_URL="${DATABASE_PROVISIONER_URL}"
export PLANE_DB_PROVISIONER_MODE=1

python manage.py wait_for_db
python manage.py bootstrap_operation_gateway_audit --phase="${phase}"
