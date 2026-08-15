#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/docker-compose-test.yml"
API_TEST_IMAGE="${PLANE_API_TEST_IMAGE:-plane-g3-external-client-api-tests:prepared}"
API_TEST_IMAGE_DIGEST="${PLANE_API_TEST_IMAGE_DIGEST:-}"
API_TEST_IMAGE_TAG="${PLANE_API_TEST_IMAGE_TAG:-${API_TEST_IMAGE}}"
API_SOURCE_REVISION="${PLANE_API_SOURCE_REVISION:-}"
PROJECT_NAME="plane-migration-verify-$$-${RANDOM}"
NETWORK_NAME="${PROJECT_NAME}_test_env"
CURRENT_STEP="preflight"

compose() {
    PLANE_TEST_ENV_FILE="${ROOT_DIR}/apps/api/.env.example" \
        docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" "$@"
}

run_sql() {
    compose exec -T test-db psql -U plane -d plane -X -v ON_ERROR_STOP=1 -Atqc "$1"
}

API_ENV=(
    --env "DJANGO_SETTINGS_MODULE=plane.settings.test"
    --env "POSTGRES_HOST=test-db"
    --env "POSTGRES_USER=plane"
    --env "POSTGRES_PASSWORD=plane"
    --env "POSTGRES_DB=plane"
    --env "DATABASE_URL=postgresql://plane:plane@test-db:5432/plane"
    --env "DATABASE_RUNTIME_URL=postgresql://plane:plane@test-db:5432/plane"
    --env "DATABASE_MIGRATION_URL=postgresql://plane:plane@test-db:5432/plane"
    --env "PLANE_AUDIT_MIGRATION_ROLE=plane"
    --env "REDIS_HOST=test-redis"
    --env "REDIS_URL=redis://test-redis:6379/"
    --env "RABBITMQ_HOST=test-mq"
    --env "AWS_S3_ENDPOINT_URL=http://test-minio:9000"
    --env "AWS_ACCESS_KEY_ID=access-key"
    --env "AWS_SECRET_ACCESS_KEY=secret-key"
    --env "AWS_S3_BUCKET_NAME=uploads"
    --env "EMAIL_HOST=test-smtp.invalid"
)

run_api() {
    docker run --rm \
        --network "${NETWORK_NAME}" \
        "${API_ENV[@]}" \
        --entrypoint /bin/sh \
        --workdir /workspace/apps/api \
        "${API_TEST_IMAGE}" -c 'exec "$@"' -- "$@"
}

fail() {
    local expected="$1"
    local actual="$2"
    local suggestion="$3"
    printf 'event=api.migration.verifier actor=release-engineering operation=%s expected=%s actual=%s suggestion=%s\n' \
        "${CURRENT_STEP}" "${expected}" "${actual}" "${suggestion}" >&2
    exit 1
}

check_comment_reaction_index() {
    local index_count index_definition
    index_count="$(run_sql "SELECT count(*) FROM pg_indexes WHERE tablename = 'comment_reactions' AND indexdef LIKE '%(comment_id, actor_id, reaction)%' AND indexdef LIKE '%deleted_at IS NULL%';")"
    [[ "${index_count}" == "1" ]] || fail "one partial comment-reaction unique index" "${index_count}" "inspect db.0073 and the PostgreSQL catalog"
    index_definition="$(run_sql "SELECT indexname || '|' || indexdef FROM pg_indexes WHERE tablename = 'comment_reactions' AND indexdef LIKE '%(comment_id, actor_id, reaction)%' AND indexdef LIKE '%deleted_at IS NULL%';")"
    printf 'comment_reaction_index=%s\n' "${index_definition}"
}

verify_migration_state() {
    CURRENT_STEP="django-check"
    run_api python manage.py check --database default
    CURRENT_STEP="migration-plan"
    run_api python manage.py migrate --plan --verbosity 1
    CURRENT_STEP="migration-drift"
    run_api python manage.py migrate --check --verbosity 1
    run_api python manage.py makemigrations --check --dry-run --verbosity 1
    CURRENT_STEP="migration-leaf"
    run_api python manage.py shell -c '
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

executor = MigrationExecutor(connection)
leaves = set(executor.loader.graph.leaf_nodes("db"))
applied = set(executor.recorder.applied_migrations())
missing = leaves - applied
expected = {("db", "0144_provider_attempt_diagnostics")}
if leaves != expected or missing:
    raise SystemExit(f"db migration leaf state is invalid: leaves={sorted(leaves)} missing={sorted(missing)}")
print(f"db_migration_leaf={sorted(leaves)[0]}")
'
}

assert_migration_leaf() {
    local expected="$1"
    run_api python manage.py shell -c "
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

executor = MigrationExecutor(connection)
applied = set(executor.recorder.applied_migrations())
expected = {('db', '${expected}')}
assert expected <= applied, (applied, expected)
if '${expected}' == '0138_agentactor_chief_of_staff_for_and_more':
    assert ('db', '0139_delegation_lineage_scope_guard') not in applied, applied
    assert ('db', '0140_invocation_free_cancellation_integrity') not in applied, applied
    assert ('db', '0141_operationgateway_quotas') not in applied, applied
    assert ('db', '0142_runtime_provider_attempts') not in applied, applied
else:
    assert ('db', '0139_delegation_lineage_scope_guard') in applied, applied
    assert ('db', '0140_invocation_free_cancellation_integrity') in applied, applied
    assert ('db', '0141_operationgateway_quotas') in applied, applied
print(f'db_migration_applied={sorted(expected)[0]}')
"
}

cleanup() {
    local status=$?
    local cleanup_status=0
    local leftover_containers leftover_networks
    trap - EXIT INT TERM
    compose down -v --remove-orphans >/dev/null 2>&1 || cleanup_status=$?
    leftover_containers="$(docker ps -aq --filter "label=com.docker.compose.project=${PROJECT_NAME}")"
    leftover_networks="$(docker network ls -q --filter "label=com.docker.compose.project=${PROJECT_NAME}")"
    if [[ -n "${leftover_containers}" || -n "${leftover_networks}" ]]; then
        cleanup_status=1
    fi
    if [[ ${status} -ne 0 || ${cleanup_status} -ne 0 ]]; then
        printf 'event=api.migration.verifier actor=release-engineering operation=cleanup expected=isolated project removed actual=verification failed at %s suggestion=inspect the preceding evidence and rerun after cleanup\n' \
            "${CURRENT_STEP}" >&2
        if [[ ${status} -eq 0 ]]; then
            status=${cleanup_status}
        fi
    else
        printf 'event=api.migration.verifier actor=release-engineering operation=cleanup expected=isolated project removed actual=passed project=%s\n' \
            "${PROJECT_NAME}"
    fi
    exit "${status}"
}

trap cleanup EXIT
trap 'exit 130' INT TERM

command -v docker >/dev/null 2>&1 || fail "docker command" "docker is unavailable" "install or enable Docker before running the verifier"
image_id="$(docker image inspect "${API_TEST_IMAGE}" --format '{{.Id}}' 2>/dev/null)" || fail "existing API test image" "${API_TEST_IMAGE} is unavailable" "build the repository API test image outside this verifier; this check never installs dependencies"
if [[ -n "${API_TEST_IMAGE_DIGEST}" ]]; then
    [[ "${image_id}" == "${API_TEST_IMAGE_DIGEST}" ]] || fail "bound API image digest=${API_TEST_IMAGE_DIGEST}" "actual=${image_id}" "use the immutable API artifact"
fi
[[ "${API_TEST_IMAGE}" == "${API_TEST_IMAGE_TAG}" ]] || fail "bound API image tag=${API_TEST_IMAGE_TAG}" "actual=${API_TEST_IMAGE}" "use the manifest-bound API image tag"
if [[ -n "${API_SOURCE_REVISION}" ]]; then
    source_label="$(docker image inspect "${API_TEST_IMAGE}" --format '{{index .Config.Labels "org.uxheavy.plane.api.source.revision"}}')"
    [[ "${source_label}" == "${API_SOURCE_REVISION}" ]] || fail "bound API source revision=${API_SOURCE_REVISION}" "actual=${source_label}" "use the exact API artifact"
fi

CURRENT_STEP="start-empty-postgres"
compose up --pull never -d test-db >/dev/null
for attempt in $(seq 1 30); do
    if compose exec -T test-db pg_isready -U plane -d plane >/dev/null 2>&1; then
        break
    fi
    if [[ "${attempt}" == "30" ]]; then
        fail "healthy PostgreSQL service" "test-db did not become ready" "inspect the unique Compose project logs"
    fi
    sleep 1
done

CURRENT_STEP="empty-database-preflight"
migration_table="$(run_sql "SELECT COALESCE(to_regclass('public.django_migrations')::text, '');")"
[[ -z "${migration_table}" ]] || fail "no django_migrations table before bootstrap" "${migration_table}" "remove stale database state and rerun with a unique Compose project"

CURRENT_STEP="bootstrap-before-migrate"
run_api python manage.py bootstrap_operation_gateway_audit --phase=before-migrate

CURRENT_STEP="apply-pre-agent-migrations"
run_api python manage.py migrate db 0122 --noinput --verbosity 1

CURRENT_STEP="pre-agent-comment-reaction-catalog"
check_comment_reaction_index

CURRENT_STEP="apply-agent-migration-chain"
run_api python manage.py migrate --noinput --verbosity 1

CURRENT_STEP="bootstrap-after-migrate"
run_api python manage.py bootstrap_operation_gateway_audit --phase=after-migrate

CURRENT_STEP="post-agent-comment-reaction-catalog"
check_comment_reaction_index
verify_migration_state

CURRENT_STEP="reverse-to-0138"
run_api python manage.py migrate db 0138_agentactor_chief_of_staff_for_and_more --noinput --verbosity 1
assert_migration_leaf "0138_agentactor_chief_of_staff_for_and_more"

CURRENT_STEP="reapply-0144"
run_api python manage.py migrate db 0144_provider_attempt_diagnostics --noinput --verbosity 1
assert_migration_leaf "0144_provider_attempt_diagnostics"

CURRENT_STEP="bootstrap-before-reverse"
run_api python manage.py bootstrap_operation_gateway_audit --phase=before-reverse

CURRENT_STEP="reverse-to-pre-agent-migrations"
run_api python manage.py migrate db 0122 --noinput --verbosity 1

CURRENT_STEP="reversed-pre-agent-comment-reaction-catalog"
check_comment_reaction_index

CURRENT_STEP="bootstrap-before-reapply"
run_api python manage.py bootstrap_operation_gateway_audit --phase=before-migrate

CURRENT_STEP="reapply-agent-migration-chain"
run_api python manage.py migrate --noinput --verbosity 1

CURRENT_STEP="bootstrap-after-reapply"
run_api python manage.py bootstrap_operation_gateway_audit --phase=after-migrate

CURRENT_STEP="final-comment-reaction-catalog"
check_comment_reaction_index
verify_migration_state
printf 'event=api.migration.verifier actor=release-engineering operation=complete expected=clean and upgrade-shaped migration paths with no drift actual=passed suggestion=retain this verifier for integrated G2-G4 candidates\n'
