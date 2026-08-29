# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


PREVIOUS_MIGRATION = ("db", "0145_runtime_reconciliation")
CURRENT_MIGRATION = ("db", "0146_runtime_reconciliation_audit_fields")


def _table_columns():
    with connection.cursor() as cursor:
        return {
            column.name: column
            for column in connection.introspection.get_table_description(cursor, "agent_runtime_reconciliations")
        }


def _restore_migration_head(target):
    MigrationExecutor(connection).migrate([target])


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_runtime_reconciliation_audit_fields_apply_and_reverse(request):
    executor = MigrationExecutor(connection)
    current_leaves = tuple(executor.loader.graph.leaf_nodes("db"))
    if len(current_leaves) != 1:
        raise RuntimeError(f"requires one current db migration leaf, found {current_leaves}")
    current_leaf = current_leaves[0]
    request.addfinalizer(lambda: _restore_migration_head(current_leaf))

    executor.migrate([PREVIOUS_MIGRATION])
    before_columns = _table_columns()
    assert "created_by_id" not in before_columns
    assert "updated_by_id" not in before_columns

    executor = MigrationExecutor(connection)
    executor.migrate([CURRENT_MIGRATION])
    after_columns = _table_columns()
    assert after_columns["created_by_id"].null_ok is True
    assert after_columns["updated_by_id"].null_ok is True

    current_apps = MigrationExecutor(connection).loader.project_state(CURRENT_MIGRATION).apps
    reconciliation = current_apps.get_model("db", "RuntimeReconciliation")
    assert reconciliation._meta.get_field("created_by").remote_field.model._meta.label == "db.User"
    assert reconciliation._meta.get_field("updated_by").remote_field.model._meta.label == "db.User"
