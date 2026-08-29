from django.db import migrations


FORWARD_SQL = r"""
CREATE OR REPLACE FUNCTION agent_check_run_terminal() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.state IN ('succeeded', 'failed', 'blocked', 'cancelled') AND NOT (
        (
            NEW.state = 'cancelled'
            AND NEW.last_invocation_id IS NULL
            AND NEW.invocation_count = 0
            AND EXISTS (
                SELECT 1
                FROM agent_assignment_contracts a
                WHERE a.id = NEW.assignment_id AND a.state = 'cancelled'
            )
        )
        OR EXISTS (
            SELECT 1
            FROM agent_runtime_invocations i
            JOIN agent_run_terminal_events e ON e.invocation_id = i.id
            WHERE i.run_id = NEW.id AND e.run_id = NEW.id
              AND i.invocation_id IS NOT DISTINCT FROM NEW.last_invocation_id
        )
    ) THEN
        RAISE EXCEPTION 'Terminal runs require a matching visible terminal event' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END;
$$;
"""


REVERSE_SQL = r"""
CREATE OR REPLACE FUNCTION agent_check_run_terminal() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.state IN ('succeeded', 'failed', 'blocked', 'cancelled') AND NOT EXISTS (
        SELECT 1 FROM agent_runtime_invocations i
        JOIN agent_run_terminal_events e ON e.invocation_id = i.id
        WHERE i.run_id = NEW.id AND e.run_id = NEW.id
          AND i.invocation_id IS NOT DISTINCT FROM NEW.last_invocation_id
    ) THEN
        RAISE EXCEPTION 'Terminal runs require a matching visible terminal event' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END;
$$;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("db", "0139_delegation_lineage_scope_guard"),
    ]

    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
