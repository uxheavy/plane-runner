from datetime import timedelta
from uuid import uuid4

import pytest
from django.core.management import call_command
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from plane.agent.lifecycle import create_actor, create_assignment, create_profile, create_run
from plane.api.serializers.agent_admin import RunInputEventAdminSerializer
from plane.db.models import AgentRole, InputEventKind, Project, RunInputEvent


PRE_HEAD = ("db", "0132_agent_input_event_sequence")
HEAD = ("db", "0133_agent_input_durability")
KEYED_TRIGGERS = {
    "agent_run_keyed_binding_guard",
    "agent_input_keyed_binding_guard",
    "agent_invocation_keyed_binding_guard",
    "agent_outcome_keyed_binding_guard",
    "agent_terminal_keyed_binding_guard",
}
TRIGGER_TABLES = {
    "agent_run_keyed_binding_guard": "agent_run_attempts",
    "agent_input_keyed_binding_guard": "agent_run_input_events",
    "agent_invocation_keyed_binding_guard": "agent_runtime_invocations",
    "agent_outcome_keyed_binding_guard": "agent_outcome_submissions",
    "agent_terminal_keyed_binding_guard": "agent_run_terminal_events",
}


def _move(target):
    if target == PRE_HEAD:
        call_command("bootstrap_operation_gateway_audit", phase="before-reverse", verbosity=0)
    else:
        call_command("bootstrap_operation_gateway_audit", phase="before-migrate", verbosity=0)
    MigrationExecutor(connection).migrate([target])
    if target == HEAD:
        call_command("bootstrap_operation_gateway_audit", phase="after-migrate", verbosity=0)


def _legacy_snapshot(run_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, pending_input_ref, payload, sequence
            FROM agent_run_input_events
            WHERE run_id = %s
            ORDER BY id
            """,
            [run_id],
        )
        return cursor.fetchall()


def _sequence_metadata_snapshot():
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('agent_run_input_sequence_legacy_metadata')")
        if cursor.fetchone()[0] is None:
            return None
        cursor.execute(
            """
            SELECT run_input_event_id, original_sequence, original_sequence_was_null
            FROM agent_run_input_sequence_legacy_metadata
            ORDER BY run_input_event_id
            """
        )
        return cursor.fetchall()


def _insert_legacy_event(run, *, sequence, pending_ref, index, created_at):
    event_id = uuid4()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO agent_run_input_events (
                id, created_at, updated_at, deleted_at, created_by_id, updated_by_id,
                workspace_id, project_id, run_id, event_ref, kind, sequence, payload,
                payload_digest, pending_input_ref, idempotency_key, command_fingerprint
            ) VALUES (
                %s, %s, %s, NULL, NULL, NULL,
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s
            )
            """,
            [
                event_id,
                created_at,
                created_at,
                run.workspace_id,
                run.project_id,
                run.id,
                f"event:migration-{index}",
                InputEventKind.HUMAN_INPUT,
                sequence,
                {"answer": f"legacy-{index}"},
                f"content:{index:064d}",
                pending_ref,
                f"idempotency:migration-{index}",
                f"legacy1:{index:064x}",
            ],
        )
    return event_id


def _keyed_trigger_names():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT trigger_info.tgname
            FROM pg_trigger AS trigger_info
            JOIN pg_class AS table_info ON table_info.oid = trigger_info.tgrelid
            WHERE table_info.relname IN (
                'agent_run_attempts', 'agent_run_input_events',
                'agent_runtime_invocations', 'agent_outcome_submissions',
                'agent_run_terminal_events'
            )
              AND NOT trigger_info.tgisinternal
              AND trigger_info.tgname = ANY(%s)
            """,
            [list(KEYED_TRIGGERS)],
        )
        return {row[0] for row in cursor.fetchall()}


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_0133_preserves_duplicate_input_evidence_and_recovers_keyed_guards(workspace):
    project = Project.objects.create(workspace=workspace, name="Agent migration contract", identifier="AMC")
    actor = create_actor(workspace=workspace, project=project, display_name="Migration contract actor")
    profile = create_profile(actor, role=AgentRole.WORKER, instructions="Migration contract")
    assignment = create_assignment(
        actor,
        project=project,
        target_ref="issue:migration-contract",
        objective="Preserve duplicate evidence",
        acceptance_criteria=["Legacy evidence remains readable"],
    )
    run = create_run(assignment, profile, idempotency_key="idempotency:migration-contract-run")

    _move(PRE_HEAD)
    base_time = timezone.now() - timedelta(days=2)
    first_id = _insert_legacy_event(
        run, sequence=7, pending_ref="event:duplicate-a", index=1, created_at=base_time + timedelta(hours=2)
    )
    canonical_id = _insert_legacy_event(
        run, sequence=2, pending_ref="event:duplicate-a", index=2, created_at=base_time + timedelta(hours=1)
    )
    legacy_id = _insert_legacy_event(
        run, sequence=None, pending_ref="event:duplicate-a", index=3, created_at=base_time + timedelta(hours=3)
    )
    second_a_id = _insert_legacy_event(
        run, sequence=None, pending_ref="event:duplicate-b", index=4, created_at=base_time + timedelta(hours=4)
    )
    second_b_id = _insert_legacy_event(
        run, sequence=None, pending_ref="event:duplicate-b", index=5, created_at=base_time + timedelta(hours=5)
    )
    before = _legacy_snapshot(run.id)

    _move(HEAD)
    canonical = _legacy_snapshot(run.id)
    rows = list(
        RunInputEvent.all_objects.filter(run_id=run.id)
        .order_by("sequence")
        .values("id", "pending_input_ref", "payload", "sequence", "is_authoritative")
    )
    assert len(rows) == 5
    assert {row["id"] for row in rows} == {row[0] for row in before}
    assert [row["sequence"] for row in rows] == [1, 2, 3, 4, 5]
    assert RunInputEvent.objects.get(pk=canonical_id).is_authoritative is True
    assert RunInputEvent.objects.get(pk=first_id).is_authoritative is False
    assert RunInputEvent.objects.get(pk=legacy_id).is_authoritative is False
    assert RunInputEvent.objects.get(pk=second_a_id).is_authoritative is True
    assert RunInputEvent.objects.get(pk=second_b_id).is_authoritative is False
    assert (
        RunInputEvent.objects.filter(
            run_id=run.id, pending_input_ref="event:duplicate-a", is_authoritative=True
        ).count()
        == 1
    )
    assert (
        RunInputEvent.objects.filter(
            run_id=run.id, pending_input_ref="event:duplicate-b", is_authoritative=True
        ).count()
        == 1
    )
    expected_metadata = {
        first_id: (7, False),
        canonical_id: (2, False),
        legacy_id: (0, True),
        second_a_id: (0, True),
        second_b_id: (0, True),
    }
    assert {row[0]: (row[1], row[2]) for row in _sequence_metadata_snapshot()} == expected_metadata
    with pytest.raises(DatabaseError), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE agent_run_input_sequence_legacy_metadata "
                "SET original_sequence = 8 WHERE run_input_event_id = %s",
                [canonical_id],
            )
    with pytest.raises(DatabaseError), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM agent_run_input_sequence_legacy_metadata WHERE run_input_event_id = %s",
                [canonical_id],
            )
    assert {row[0]: (row[1], row[2]) for row in _sequence_metadata_snapshot()} == expected_metadata
    with pytest.raises(IntegrityError), transaction.atomic():
        _insert_legacy_event(
            run,
            sequence=6,
            pending_ref="event:duplicate-a",
            index=6,
            created_at=base_time + timedelta(hours=6),
        )
    readback = RunInputEventAdminSerializer(RunInputEvent.objects.get(pk=legacy_id)).data
    assert readback["is_authoritative"] is False
    assert "payload" not in readback
    assert "original_sequence" not in readback

    _move(PRE_HEAD)
    assert _legacy_snapshot(run.id) == before
    assert _sequence_metadata_snapshot() is None
    _move(HEAD)
    assert _legacy_snapshot(run.id) == canonical
    assert {row[0]: (row[1], row[2]) for row in _sequence_metadata_snapshot()} == expected_metadata

    for missing in KEYED_TRIGGERS:
        _move(PRE_HEAD)
        with connection.cursor() as cursor:
            cursor.execute(f"DROP TRIGGER IF EXISTS {missing} ON {TRIGGER_TABLES[missing]}")
        _move(HEAD)
        assert _keyed_trigger_names() == KEYED_TRIGGERS

    _move(PRE_HEAD)
    with connection.cursor() as cursor:
        cursor.execute("DROP FUNCTION IF EXISTS agent_guard_keyed_record_binding_immutable() CASCADE")
    _move(HEAD)
    assert _keyed_trigger_names() == KEYED_TRIGGERS

    _move(PRE_HEAD)
    with connection.cursor() as cursor:
        cursor.execute("CREATE UNIQUE INDEX agent_input_run_pending_ref_unique ON agent_run_input_events (id)")
    failed_before = _legacy_snapshot(run.id)
    with pytest.raises(DatabaseError):
        _move(HEAD)
    connection.close()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'agent_run_input_events' AND column_name = 'is_authoritative'
            )
            """
        )
        assert cursor.fetchone()[0] is False
    assert _legacy_snapshot(run.id) == failed_before
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('agent_run_input_sequence_legacy_metadata')")
        assert cursor.fetchone()[0] is None
    with connection.cursor() as cursor:
        cursor.execute("DROP INDEX agent_input_run_pending_ref_unique")
    _move(HEAD)
