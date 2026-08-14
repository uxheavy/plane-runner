# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import threading
from uuid import uuid4

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import DatabaseError, close_old_connections, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from plane.agent.lifecycle import (
    AgentDomainError,
    IdempotencyConflictError,
    InvalidTransitionError,
    RecoveryIntentRequiredError,
    accept_outcome,
    create_actor,
    create_assignment,
    create_profile,
    create_run,
    finalize_invocation,
    lock_invocation_path,
    propose_outcome,
    record_input_event,
    record_invocation,
    record_provider_attempt_notice,
    reconcile_provider_attempts,
    provider_attempts_reconciled,
    request_revision,
    review_outcome,
    transition_run,
)
from plane.agent.lifecycle.services import _normalise_idempotency
from plane.agent.runtime.supervisor import request_runtime_cancellation
from plane.agent.lifecycle.runtime_contract import (
    ARTIFACT_DIRECTORY,
    command_fingerprint,
    contract_digests,
    contract_manifest,
    legacy_command_fingerprint,
    namespaced_ref,
    snapshot_digest,
    validate_invocation_envelope,
    validate_run_snapshot,
)
from plane.agent.runtime import dispatch_invocation
from plane.db.models import (
    AgentRole,
    AssignmentContract,
    AssignmentState,
    InputEventKind,
    InvocationState,
    OutcomeState,
    Project,
    RecoveryIntent,
    RunLineageReason,
    RunAttempt,
    RunInputEvent,
    RunState,
    TerminalEventKind,
    RunTerminalEvent,
    RuntimeControlState,
    RuntimeInvocationControl,
    RuntimeInvocation,
    RuntimeProviderAttempt,
    RuntimeProviderAttemptPhase,
    ProfileVersion,
)


AGENT_TEST_HEAD = ("db", "0140_invocation_free_cancellation_integrity")


@pytest.fixture(scope="session")
def django_db_use_migrations():
    """Install the lifecycle-owned PostgreSQL triggers in this test database."""

    return True


def _restore_agent_test_head():
    call_command("bootstrap_operation_gateway_audit", phase="before-migrate", verbosity=0)
    executor = MigrationExecutor(connection)
    current_leaves = tuple(executor.loader.graph.leaf_nodes("db"))
    if len(current_leaves) != 1:
        raise RuntimeError(f"requires one current db migration leaf, found {current_leaves}")
    executor.migrate([current_leaves[0]])
    call_command("bootstrap_operation_gateway_audit", phase="after-migrate", verbosity=0)


@pytest.fixture
def project(workspace):
    return Project.objects.create(
        workspace=workspace,
        name="Agent project",
        identifier="AGENT",
        description="Agent domain test project",
    )


@pytest.fixture
def actor(workspace, project):
    return create_actor(workspace=workspace, project=project, display_name="Worker")


@pytest.fixture
def profile(actor):
    return create_profile(actor, role=AgentRole.WORKER, instructions="Complete the assigned objective.")


@pytest.fixture
def assignment(actor, project, create_user):
    return create_assignment(
        actor,
        project=project,
        target_ref="issue:123",
        objective="Produce the requested result.",
        acceptance_criteria=["The result is reviewable."],
        created_by=create_user,
    )


@pytest.fixture
def evaluator(workspace):
    evaluator = create_actor(workspace=workspace, display_name="Evaluator")
    create_profile(evaluator, role=AgentRole.EVALUATOR, instructions="Review the submitted result.")
    return evaluator


@pytest.mark.django_db
def test_five_plane_records_bind_to_one_actor_and_an_exact_l1_snapshot(assignment, profile):
    run = create_run(assignment, profile, idempotency_key="idempotency:create-run")

    assert assignment.workspace_id == profile.workspace_id == run.workspace_id
    assert assignment.project_id == profile.project_id == run.project_id
    assert run.assignment_id == assignment.id
    assert run.profile_version_id == profile.id
    assert run.state == RunState.QUEUED
    assert assignment.state == AssignmentState.ACTIVE
    assert profile.role == AgentRole.WORKER
    assert profile.actor.active_profile_id == profile.id
    assert set(run.snapshot) == {
        "protocol",
        "workspaceRef",
        "runId",
        "assignment",
        "actorRef",
        "profile",
        "context",
        "toolCatalog",
        "runtimePolicy",
        "totalBudget",
        "contractDigests",
        "contentDigest",
    }
    assert run.snapshot["contractDigests"] == contract_digests()
    assert run.snapshot["assignment"]["targetRef"].startswith("target:")
    assert run.snapshot["profile"]["profileRef"].startswith("profile-version:")
    validate_run_snapshot(run.snapshot)


@pytest.mark.django_db(transaction=True)
def test_profile_defaults_resolve_into_an_immutable_snapshot_and_exact_envelope_dispatch(assignment, profile):
    profile = create_profile(
        profile.actor,
        role=AgentRole.WORKER,
        instructions="Resolve the configured runtime policy exactly.",
        model_defaults={"provider": "fake-provider", "model": "fake-model"},
        runtime_defaults={
            "adapter": "hermes",
            "maxEventPayloadBytes": 8192,
            "maxArtifactBytes": 16384,
            "maxReceiptBytes": 4096,
            "maxCodeModeInputBytes": 2048,
            "maxCodeModeOutputBytes": 3072,
            "maxCodeModeCalls": 0,
            "totalBudget": {"inputTokens": 12, "outputTokens": 8, "durationMs": 5000},
        },
    )
    run = create_run(assignment, profile, idempotency_key="idempotency:resolved-policy-run")
    invocation = record_invocation(run, idempotency_key="idempotency:resolved-policy-invocation")

    expected_policy = {
        "model": {"provider": "fake-provider", "model": "fake-model"},
        "adapter": "hermes",
        "isolation": "single-invocation",
        "maxEventPayloadBytes": 8192,
        "maxArtifactBytes": 16384,
        "maxReceiptBytes": 4096,
        "maxCodeModeInputBytes": 2048,
        "maxCodeModeOutputBytes": 3072,
        "maxCodeModeCalls": 0,
    }
    assert run.snapshot["runtimePolicy"] == expected_policy
    assert run.snapshot["totalBudget"] == {"inputTokens": 12, "outputTokens": 8, "durationMs": 5000}
    assert invocation.envelope["runSnapshotDigest"] == run.snapshot["contentDigest"]
    assert invocation.envelope["remainingBudget"] == run.snapshot["totalBudget"]

    class CaptureTransport:
        def __init__(self):
            self.calls = []

        def dispatch(self, snapshot_json, envelope_json):
            self.calls.append((json.loads(snapshot_json), json.loads(envelope_json)))
            return ("{\"status\":\"accepted\"}",)

    transport = CaptureTransport()
    assert dispatch_invocation(invocation, transport) == ('{"status":"accepted"}',)
    assert len(transport.calls) == 1
    dispatched_snapshot, dispatched_envelope = transport.calls[0]
    assert dispatched_snapshot == RunAttempt.objects.get(pk=run.pk).snapshot
    assert dispatched_envelope == RuntimeInvocation.objects.get(pk=invocation.pk).envelope
    assert dispatched_snapshot["runtimePolicy"] == expected_policy
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            RunAttempt.objects.filter(pk=run.pk).update(snapshot={"tampered": True})
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            RuntimeInvocation.objects.filter(pk=invocation.pk).update(envelope={"tampered": True})


@pytest.mark.django_db
@pytest.mark.parametrize("mutation", ["missing", "mismatched"])
def test_run_creation_rejects_unresolved_snapshot_policy_without_dispatch_side_effects(assignment, profile, mutation):
    from plane.agent.lifecycle.services import _build_snapshot

    supplied_snapshot = _build_snapshot(assignment, profile, uuid4())
    if mutation == "missing":
        supplied_snapshot["runtimePolicy"] = {"model": supplied_snapshot["runtimePolicy"]["model"]}
    else:
        supplied_snapshot["runtimePolicy"]["adapter"] = "unresolved-adapter"
    supplied_snapshot["contentDigest"] = snapshot_digest(
        {key: value for key, value in supplied_snapshot.items() if key != "contentDigest"}
    )
    run_count = RunAttempt.objects.count()
    invocation_count = RuntimeInvocation.objects.count()

    with pytest.raises(AgentDomainError):
        create_run(
            assignment,
            profile,
            snapshot=supplied_snapshot,
            idempotency_key=f"idempotency:rejected-policy-{mutation}",
        )

    assert RunAttempt.objects.count() == run_count
    assert RuntimeInvocation.objects.count() == invocation_count


def test_g4_live_idempotency_namespace_is_accepted_by_lifecycle_normalizer():
    valid = (
        "idempotency:g4-live-run-focused",
        "idempotency:g4-live-invocation-focused",
    )
    for value in valid:
        assert _normalise_idempotency(value, "g4 live idempotency_key") == value

    for value in ("g4-live-run:focused", "g4-live-invocation:focused"):
        with pytest.raises(AgentDomainError):
            _normalise_idempotency(value, "g4 live idempotency_key")


@pytest.mark.django_db
def test_manifest_bytes_are_the_contract_source_of_truth():
    manifest = contract_manifest()
    assert manifest["protocol"] == "plane.agent-runtime/v1"
    assert set(manifest["schemas"]) == {
        "run-snapshot",
        "invocation-envelope",
        "runtime-event",
        "runtime-exit",
        "runtime-durable-state",
    }
    assert contract_digests() == {
        "runSnapshot": "308101c6a2c9f56e7deb5c6a07c8bc74b59831b92cbbb5b07c5a7eefc21f4947",
        "invocationEnvelope": "b7a15d74406f1624cdb7cd95b42edfd1ffee596abe57e4f00ed60e2e23ded995",
        "runtimeEvent": "78da5ce9d112b6545ea471e5fcae25ff5dfeb2e5db74a8d5796d0ee026823a27",
        "runtimeExit": "86b5acaa14271b1c5f0f0fadc30f48bc5cd24ac8db0ff03ba8a91d02bceecf65",
        "runtimeDurableState": "444c944ec8a5054f33c8662470529a1f4565d42ff06138438beceeef7967a0da",
    }


@pytest.mark.django_db
def test_host_and_api_artifact_bytes_are_identical():
    source_directory = Path(__file__).resolve().parents[6] / "packages/agent-runtime-contract/schemas/v1"
    for artifact in ARTIFACT_DIRECTORY.glob("*.json"):
        assert artifact.read_bytes() == (source_directory / artifact.name).read_bytes()


@pytest.mark.django_db
def test_missing_or_tampered_contract_artifacts_fail_closed(tmp_path, monkeypatch):
    import shutil

    artifact_directory = tmp_path / "v1"
    shutil.copytree(ARTIFACT_DIRECTORY, artifact_directory)
    monkeypatch.setattr("plane.agent.lifecycle.runtime_contract.ARTIFACT_DIRECTORY", artifact_directory)
    contract_manifest.cache_clear()
    (artifact_directory / "manifest.json").unlink()
    with pytest.raises(ValueError, match="manifest is unavailable"):
        contract_manifest()

    shutil.copy2(ARTIFACT_DIRECTORY / "manifest.json", artifact_directory / "manifest.json")
    (artifact_directory / "run-snapshot.schema.json").write_bytes(b"tampered")
    contract_manifest.cache_clear()
    with pytest.raises(ValueError, match="digest drifted"):
        contract_manifest()
    monkeypatch.setattr("plane.agent.lifecycle.runtime_contract.ARTIFACT_DIRECTORY", ARTIFACT_DIRECTORY)
    contract_manifest.cache_clear()


@pytest.mark.django_db
def test_profile_and_snapshot_are_immutable_and_direct_state_changes_use_lifecycle(assignment, profile):
    run = create_run(assignment, profile)
    invocation = record_invocation(run, idempotency_key="idempotency:model-immutability-invocation")

    profile.instructions = "Changed after resolution."
    with pytest.raises(ValidationError):
        profile.save()

    run.snapshot = deepcopy(run.snapshot)
    run.snapshot["assignment"]["objective"] = "Changed after resolution."
    with pytest.raises(ValidationError):
        run.save()

    invocation.envelope = deepcopy(invocation.envelope)
    invocation.envelope["runId"] = "run:tampered"
    with pytest.raises(ValidationError):
        invocation.save()

    run.refresh_from_db()
    invocation.refresh_from_db()
    run.save()
    invocation.save()

    transition_run(run, RunState.WAITING_FOR_INPUT, pending_input_ref="event:model-immutability-question")
    run.refresh_from_db()
    invocation.refresh_from_db()
    assert run.state == RunState.WAITING_FOR_INPUT
    assert invocation.state == InvocationState.WAITING_FOR_INPUT

    assignment.state = AssignmentState.COMPLETED
    with pytest.raises(ValidationError):
        assignment.save()


@pytest.mark.django_db(transaction=True)
def test_postgres_guards_reject_hostile_bulk_and_raw_mutations(assignment, profile, actor, project):
    run = create_run(assignment, profile)
    invocation = record_invocation(run, idempotency_key="idempotency:hostile-probe")
    other_assignment = create_assignment(
        actor,
        project=project,
        target_ref="issue:hostile",
        objective="A second binding.",
        acceptance_criteria=["The result is reviewable."],
    )
    other_run = create_run(other_assignment, profile)
    other_actor = create_actor(workspace=assignment.workspace, display_name="Other worker")
    with pytest.raises(DatabaseError):
        ProfileVersion.objects.filter(pk=profile.pk).update(instructions="bulk rewrite")
    with pytest.raises(DatabaseError):
        RunAttempt.objects.filter(pk=run.pk).update(snapshot={"tampered": True})
    with pytest.raises(DatabaseError):
        RunAttempt.objects.filter(pk=run.pk).update(invocation_count=99)
    with pytest.raises(DatabaseError):
        RunAttempt.objects.filter(pk=run.pk).update(actor_id=other_actor.id)
    with pytest.raises(DatabaseError):
        AssignmentContract.objects.filter(pk=assignment.pk).update(state=AssignmentState.COMPLETED)
    with pytest.raises(DatabaseError):
        RunAttempt.objects.filter(pk=run.pk).update(state=RunState.SUCCEEDED)
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE agent_run_attempts SET snapshot_content_digest = %s WHERE id = %s",
                    ["snapshot:" + "0" * 64, run.id],
                )
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE agent_run_attempts SET snapshot = %s::jsonb WHERE id = %s",
                    [json.dumps({"tampered": True}), run.id],
                )
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE agent_runtime_invocations SET envelope = %s::jsonb WHERE id = %s",
                    [json.dumps({"tampered": True}), invocation.id],
                )
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO agent_run_terminal_events
                        (id, created_at, updated_at, workspace_id, project_id, invocation_id, run_id,
                         kind, source, product_ref, product_event_ref, idempotency_key, reason, visible)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'run_failure', 'supervisor',
                            %s, %s, %s, %s, TRUE)
                    """,
                    [
                        uuid4(),
                        timezone.now(),
                        timezone.now(),
                        run.workspace_id,
                        run.project_id,
                        invocation.id,
                        other_run.id,
                        "product-event:hostile",
                        "product-event:hostile",
                        "idempotency:hostile-terminal",
                        "mismatched run binding",
                    ],
                )


@pytest.mark.django_db(transaction=True)
def test_postgres_lifecycle_immutable_triggers_are_installed():
    if connection.vendor != "postgresql":
        pytest.fail("Run lifecycle immutability requires the supported PostgreSQL test database")

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT relation.relname, tg.tgname, tg.tgenabled
            FROM pg_trigger AS tg
            JOIN pg_class AS relation ON relation.oid = tg.tgrelid
            JOIN pg_namespace AS schema_info ON schema_info.oid = relation.relnamespace
            WHERE schema_info.nspname = current_schema()
              AND NOT tg.tgisinternal
              AND relation.relname IN ('agent_run_attempts', 'agent_runtime_invocations')
              AND tg.tgname IN ('agent_run_immutable_guard', 'agent_invocation_immutable_guard')
            """
        )
        triggers = {(table, trigger, enabled) for table, trigger, enabled in cursor.fetchall()}

    assert triggers == {
        ("agent_run_attempts", "agent_run_immutable_guard", "O"),
        ("agent_runtime_invocations", "agent_invocation_immutable_guard", "O"),
    }


@pytest.mark.django_db(transaction=True)
def test_non_superuser_owner_cannot_truncate_or_rebind_keyed_records(assignment, profile):
    run = create_run(assignment, profile, idempotency_key="idempotency:truncate-run")
    record_invocation(run, idempotency_key="idempotency:truncate-initial")
    transition_run(run, RunState.WAITING_FOR_INPUT, pending_input_ref="event:truncate-question")
    input_event = record_input_event(
        run,
        payload={"answer": "original"},
        pending_input_ref="event:truncate-question",
        idempotency_key="idempotency:truncate-input",
    )
    invocation = record_invocation(
        run,
        trigger="human_input",
        input_event=input_event,
        idempotency_key="idempotency:truncate-invocation",
    )
    propose_outcome(
        run,
        summary="original",
        artifacts=["artifact:original"],
        evidence=["evidence:original"],
        idempotency_key="idempotency:truncate-outcome",
    )
    terminal_event = run.__class__.all_objects.get(pk=run.pk).terminal_events.get()
    tables = (
        ("agent_run_attempts", "creation_idempotency_key", run.id, "snapshot"),
        ("agent_run_input_events", "idempotency_key", input_event.id, "payload"),
        ("agent_runtime_invocations", "idempotency_key", invocation.id, "envelope"),
        (
            "agent_outcome_submissions",
            "submission_idempotency_key",
            run.outcome_submission.id,
            "artifacts",
        ),
        ("agent_run_terminal_events", "idempotency_key", terminal_event.id, "product_ref"),
    )

    def quote_identifier(value):
        return '"' + value.replace('"', '""') + '"'

    expected = {}
    owners = {}
    owner_role = f"agent_truncate_owner_{uuid4().hex}"
    role_identifier = quote_identifier(owner_role)
    with connection.cursor() as cursor:
        for table, key_column, row_id, material_column in tables:
            cursor.execute(
                """
                SELECT pg_get_userbyid(c.relowner)
                FROM pg_class AS c
                JOIN pg_namespace AS n ON n.oid = c.relnamespace
                WHERE n.nspname = current_schema() AND c.relname = %s
                """,
                [table],
            )
            owners[table] = cursor.fetchone()[0]
            cursor.execute(
                f"""
                SELECT id::text, {quote_identifier(key_column)}::text,
                       command_fingerprint, {quote_identifier(material_column)}::text
                FROM {quote_identifier(table)} WHERE id = %s
                """,
                [row_id],
            )
            expected[table] = cursor.fetchone()

        cursor.execute(f"CREATE ROLE {role_identifier} NOLOGIN NOSUPERUSER NOREPLICATION NOBYPASSRLS NOINHERIT")
        try:
            cursor.execute(
                """
                SELECT c.relname, t.tgname, t.tgenabled
                FROM pg_trigger AS t
                JOIN pg_class AS c ON c.oid = t.tgrelid
                WHERE tgname IN (
                    'agent_run_keyed_truncate_guard',
                    'agent_input_keyed_truncate_guard',
                    'agent_invocation_keyed_truncate_guard',
                    'agent_outcome_keyed_truncate_guard',
                    'agent_terminal_keyed_truncate_guard'
                )
                """
            )
            assert {row for row in cursor.fetchall()} == {
                ("agent_run_attempts", "agent_run_keyed_truncate_guard", "O"),
                ("agent_run_input_events", "agent_input_keyed_truncate_guard", "O"),
                ("agent_runtime_invocations", "agent_invocation_keyed_truncate_guard", "O"),
                ("agent_outcome_submissions", "agent_outcome_keyed_truncate_guard", "O"),
                ("agent_run_terminal_events", "agent_terminal_keyed_truncate_guard", "O"),
            }
            for table, _, _, _ in tables:
                cursor.execute(f"ALTER TABLE {quote_identifier(table)} OWNER TO {role_identifier}")

            cursor.execute(
                """
                SELECT r.rolsuper, r.rolreplication
                FROM pg_roles AS r
                WHERE r.rolname = %s
                """,
                [owner_role],
            )
            assert cursor.fetchone() == (False, False)

            truncate_statements = [
                *(f"TRUNCATE {quote_identifier(table)}" for table, _, _, _ in tables),
                "TRUNCATE " + ", ".join(quote_identifier(table) for table, _, _, _ in tables),
                f"TRUNCATE {quote_identifier(tables[0][0])} CASCADE",
                "TRUNCATE " + ", ".join(quote_identifier(table) for table, _, _, _ in tables) + " CASCADE",
            ]

            def assert_rows_remain_bound():
                for table, key_column, _, material_column in tables:
                    cursor.execute(
                        f"""
                        SELECT id::text, {quote_identifier(key_column)}::text,
                               command_fingerprint,
                               {quote_identifier(material_column)}::text
                        FROM {quote_identifier(table)} WHERE id = %s
                        """,
                        [expected[table][0]],
                    )
                    assert cursor.fetchone() == expected[table]

            for statement in truncate_statements:
                with pytest.raises(DatabaseError):
                    with transaction.atomic():
                        cursor.execute(f"SET LOCAL ROLE {role_identifier}")
                        cursor.execute(
                            "SELECT current_user, current_setting('session_replication_role'), "
                            "rolsuper, rolreplication "
                            "FROM pg_roles WHERE rolname = current_user"
                        )
                        assert cursor.fetchone() == (owner_role, "origin", False, False)
                        cursor.execute(statement)
                assert_rows_remain_bound()

            reinsert_statements = {
                "agent_run_attempts": """
                    INSERT INTO agent_run_attempts
                    SELECT (jsonb_populate_record(
                        NULL::agent_run_attempts,
                        to_jsonb(source) || jsonb_build_object(
                            'id', %s::uuid,
                            'snapshot', '{\"answer\":\"substituted\"}'::jsonb,
                            'snapshot_content_digest', 'snapshot:' || repeat('0', 64),
                            'command_fingerprint', 'command:' || repeat('1', 64)
                        )
                    )).*
                    FROM agent_run_attempts AS source WHERE source.id = %s
                """,
                "agent_run_input_events": """
                    INSERT INTO agent_run_input_events
                    SELECT (jsonb_populate_record(
                        NULL::agent_run_input_events,
                        to_jsonb(source) || jsonb_build_object(
                            'id', %s::uuid,
                            'event_ref', 'event:substituted',
                            'payload', '{\"answer\":\"substituted\"}'::jsonb,
                            'payload_digest', 'content:' || repeat('0', 64),
                            'command_fingerprint', 'command:' || repeat('1', 64)
                        )
                    )).*
                    FROM agent_run_input_events AS source WHERE source.id = %s
                """,
                "agent_runtime_invocations": """
                    INSERT INTO agent_runtime_invocations
                    SELECT (jsonb_populate_record(
                        NULL::agent_runtime_invocations,
                        to_jsonb(source) || jsonb_build_object(
                            'id', %s::uuid,
                            'invocation_id', 'invocation:substituted',
                            'envelope', '{\"substituted\":true}'::jsonb,
                            'command_fingerprint', 'command:' || repeat('1', 64)
                        )
                    )).*
                    FROM agent_runtime_invocations AS source WHERE source.id = %s
                """,
                "agent_outcome_submissions": """
                    INSERT INTO agent_outcome_submissions
                    SELECT (jsonb_populate_record(
                        NULL::agent_outcome_submissions,
                        to_jsonb(source) || jsonb_build_object(
                            'id', %s::uuid,
                            'summary', 'substituted',
                            'artifacts', '[\"artifact:substituted\"]'::jsonb,
                            'evidence', '[\"evidence:substituted\"]'::jsonb,
                            'command_fingerprint', 'command:' || repeat('1', 64)
                        )
                    )).*
                    FROM agent_outcome_submissions AS source WHERE source.id = %s
                """,
                "agent_run_terminal_events": """
                    INSERT INTO agent_run_terminal_events
                    SELECT (jsonb_populate_record(
                        NULL::agent_run_terminal_events,
                        to_jsonb(source) || jsonb_build_object(
                            'id', %s::uuid,
                            'product_ref', 'product-event:substituted',
                            'product_event_ref', 'product-event:substituted',
                            'command_fingerprint', 'command:' || repeat('1', 64)
                        )
                    )).*
                    FROM agent_run_terminal_events AS source WHERE source.id = %s
                """,
            }
            for table, _, row_id, _ in tables:
                with pytest.raises(DatabaseError):
                    with transaction.atomic():
                        cursor.execute(f"SET LOCAL ROLE {role_identifier}")
                        cursor.execute(reinsert_statements[table], [uuid4(), row_id])
                assert_rows_remain_bound()
        finally:
            cursor.execute("RESET ROLE")
            for table, _, _, _ in tables:
                cursor.execute(f"ALTER TABLE {quote_identifier(table)} OWNER TO {quote_identifier(owners[table])}")
            cursor.execute(f"DROP ROLE {role_identifier}")


@pytest.mark.django_db
def test_cross_workspace_profile_and_assignment_binding_is_rejected(assignment, profile, create_user):
    other_workspace = assignment.workspace.__class__.objects.create(
        name="Other workspace",
        owner=create_user,
        slug=f"other-{uuid4().hex[:8]}",
    )
    other_actor = create_actor(workspace=other_workspace, display_name="Other")
    other_profile = create_profile(other_actor, role=AgentRole.WORKER, instructions="Other work.")

    with pytest.raises(AgentDomainError):
        create_run(assignment, other_profile)

    with pytest.raises(ValidationError):
        profile.workspace_id = other_workspace.id
        profile.save()


@pytest.mark.django_db
def test_invocations_resume_the_same_run_and_keep_the_frozen_snapshot(assignment, profile):
    run = create_run(assignment, profile)
    snapshot = deepcopy(run.snapshot)
    first = record_invocation(run, idempotency_key="idempotency:first-invocation", usage={"inputTokens": 4})
    transition_run(run, RunState.WAITING_FOR_INPUT, pending_input_ref="event:input-question")
    answer = record_input_event(
        run,
        payload={"answer": "Continue"},
        kind=InputEventKind.HUMAN_INPUT,
        pending_input_ref="event:input-question",
        idempotency_key="idempotency:answer",
    )
    second = record_invocation(
        run,
        idempotency_key="idempotency:second-invocation",
        trigger="human_input",
        input_event=answer,
        usage={"outputTokens": 6},
    )

    run.refresh_from_db()
    assert first.run_id == second.run_id == run.id
    assert run.invocation_count == 2
    assert run.snapshot == snapshot
    assert second.envelope["trigger"]["kind"] == "human_input"
    assert second.envelope["trigger"]["eventRef"] == answer.event_ref
    assert second.envelope["runSnapshotDigest"] == snapshot["contentDigest"]
    assert run.cumulative_usage == {"inputTokens": 4, "outputTokens": 6, "durationMs": 0}
    assert second.state == InvocationState.RUNNING
    validate_invocation_envelope(second.envelope)


@pytest.mark.django_db
def test_input_events_require_current_waiting_question_and_converge_on_replay(assignment, profile):
    run = create_run(assignment, profile)
    with pytest.raises(AgentDomainError):
        record_input_event(
            run,
            payload={"answer": "too early"},
            pending_input_ref="event:question-before-waiting",
            idempotency_key="idempotency:input-before-waiting",
        )
    initial = record_invocation(run, idempotency_key="idempotency:input-initial")
    pending_ref = "event:current-question"
    transition_run(run, RunState.WAITING_FOR_INPUT, pending_input_ref=pending_ref)
    with pytest.raises(AgentDomainError):
        record_input_event(
            run,
            payload={"answer": "wrong question"},
            pending_input_ref="event:stale-question",
            idempotency_key="idempotency:input-wrong-question",
        )
    event = record_input_event(
        run,
        payload={"answer": "accepted"},
        pending_input_ref=pending_ref,
        idempotency_key="idempotency:input-answer",
    )
    assert event.sequence == 1
    assert event.is_authoritative is True
    run.refresh_from_db()
    initial.refresh_from_db()
    assert run.state == RunState.RUNNING
    assert run.pending_input_ref is None
    assert initial.state == InvocationState.RUNNING
    assert (
        record_input_event(
            run,
            payload={"answer": "accepted"},
            pending_input_ref=pending_ref,
            idempotency_key="idempotency:input-answer",
        ).id
        == event.id
    )
    continued = record_invocation(
        run,
        trigger="human_input",
        input_event=event,
        idempotency_key="idempotency:input-continuation",
    )
    assert continued.run_id == initial.run_id == run.id
    run.refresh_from_db()
    assert run.state == RunState.RUNNING
    assert run.pending_input_ref is None

    before_events = RunInputEvent.objects.filter(run=run).count()
    with pytest.raises(IdempotencyConflictError):
        record_input_event(
            run,
            payload={"answer": "terminal or nonwaiting mutation"},
            pending_input_ref=pending_ref,
            idempotency_key="idempotency:input-nonwaiting",
        )
    assert RunInputEvent.objects.filter(run=run).count() == before_events


@pytest.mark.django_db
def test_assignment_and_profile_boundaries_reject_unrunnable_or_credential_data(actor, assignment, profile):
    before_assignments = AssignmentContract.objects.filter(assignee=actor).count()
    for criteria in ([], ["criterion"] * 33, [{"criterion": "not a string"}]):
        with pytest.raises(AgentDomainError):
            create_assignment(
                actor,
                target_ref="issue:invalid-criteria",
                objective="Must not persist.",
                acceptance_criteria=criteria,
            )
    assert AssignmentContract.objects.filter(assignee=actor).count() == before_assignments

    before_profiles = ProfileVersion.objects.filter(actor=actor).count()
    for defaults in (
        {"stop": [{"X-API-Key": "canary"}]},
        {"totalBudget": {"Cookie": "canary"}},
        {"headers": {"Authorization": "Bearer canary"}},
        {"model": "Bearer canary-credential"},
        {"model": "API-Key/canary-credential"},
        {"model": "sk-canary-credential"},
    ):
        with pytest.raises(AgentDomainError):
            create_profile(
                actor,
                role=AgentRole.WORKER,
                instructions="Credential-shaped profile data is forbidden.",
                model_defaults=defaults,
            )
    assert ProfileVersion.objects.filter(actor=actor).count() == before_profiles


@pytest.mark.django_db
def test_invocation_and_outcome_commands_are_idempotent(assignment, profile):
    run = create_run(assignment, profile)
    first = record_invocation(run, idempotency_key="idempotency:repeatable-invocation")
    repeated = record_invocation(run, idempotency_key="idempotency:repeatable-invocation")
    assert repeated.id == first.id

    outcome = propose_outcome(
        run,
        summary="A result",
        artifacts=["artifact:1"],
        evidence=["evidence:1"],
        idempotency_key="idempotency:repeatable-outcome",
    )
    repeated_outcome = propose_outcome(
        run,
        summary="A result",
        artifacts=["artifact:1"],
        evidence=["evidence:1"],
        idempotency_key="idempotency:repeatable-outcome",
    )
    assert repeated_outcome.id == outcome.id
    assert run.__class__.objects.get(pk=run.pk).terminal_events.count() == 1
    assert (
        run.__class__.objects.get(pk=run.pk).invocations.get(pk=first.pk).terminal_event.kind
        == TerminalEventKind.OUTCOME_SUBMISSION
    )

    with pytest.raises(IdempotencyConflictError):
        record_invocation(run, idempotency_key="idempotency:repeatable-outcome")


@pytest.mark.django_db(transaction=True)
def test_migrated_outcome_terminal_replay_promotes_legacy_binding_without_duplication(assignment, profile, request):
    """Exercise the real 0125 reverse/reapply boundary before replaying the terminal command."""

    executor = MigrationExecutor(connection)
    try:
        applied = executor.recorder.applied_migrations()
    except DatabaseError:
        pytest.skip("requires a migration-backed test database; pytest --nomigrations is a known environment gap")
    if ("db", "0125_agent_lifecycle_append_only_integrity") not in applied:
        pytest.skip("requires a migration-backed test database; pytest --nomigrations is a known environment gap")
    request.addfinalizer(_restore_agent_test_head)

    run = create_run(assignment, profile, idempotency_key="idempotency:migration-replay-run")
    invocation = record_invocation(run, idempotency_key="idempotency:migration-replay-invocation")
    outcome = propose_outcome(
        run,
        summary="A migrated result",
        artifacts=["artifact:migrated"],
        evidence=["evidence:migrated"],
        idempotency_key="idempotency:migration-replay-outcome",
    )
    terminal = RunTerminalEvent.all_objects.get(invocation=invocation)
    original_id = terminal.id
    original_event_ref = terminal.product_event_ref

    call_command("bootstrap_operation_gateway_audit", phase="before-reverse", verbosity=0)
    executor.migrate([("db", "0124_agent_lifecycle_database_integrity")])
    executor = MigrationExecutor(connection)
    executor.migrate([("db", "0125_agent_lifecycle_append_only_integrity")])

    migrated_terminal = RunTerminalEvent.all_objects.get(pk=original_id)
    assert migrated_terminal.command_fingerprint == legacy_command_fingerprint(
        "record_terminal_event",
        {
            "invocationId": str(invocation.id),
            "runId": str(run.id),
            "kind": TerminalEventKind.OUTCOME_SUBMISSION,
            "source": "runtime",
            "productRef": namespaced_ref("outcome-submission", str(outcome.id)),
            "productEventRef": original_event_ref,
            "idempotencyKey": namespaced_ref("idempotency", f"outcome-{outcome.id}"),
            "reason": "",
            "cancellationRef": None,
        },
    )

    call_command("bootstrap_operation_gateway_audit", phase="before-migrate", verbosity=0)
    executor = MigrationExecutor(connection)
    executor.migrate([AGENT_TEST_HEAD])
    call_command("bootstrap_operation_gateway_audit", phase="after-migrate", verbosity=0)

    replayed_outcome = propose_outcome(
        run,
        summary="A migrated result",
        artifacts=["artifact:migrated"],
        evidence=["evidence:migrated"],
        idempotency_key="idempotency:migration-replay-outcome",
    )

    replayed_outcome.refresh_from_db()
    replayed = RunTerminalEvent.all_objects.get(pk=original_id)
    assert replayed_outcome.id == outcome.id
    assert replayed_outcome.command_fingerprint == command_fingerprint(
        "propose_outcome",
        {
            "runId": str(run.id),
            "summary": "A migrated result",
            "artifacts": ["artifact:migrated"],
            "evidence": ["evidence:migrated"],
            "createdBy": None,
        },
    )
    assert replayed.id == original_id
    assert replayed.product_event_ref == original_event_ref
    assert replayed.command_fingerprint == command_fingerprint(
        "record_terminal_event",
        {
            "invocationId": str(invocation.id),
            "runId": str(run.id),
            "kind": TerminalEventKind.OUTCOME_SUBMISSION,
            "source": "runtime",
            "productRef": namespaced_ref("outcome-submission", str(outcome.id)),
            "productEventRef": original_event_ref,
            "idempotencyKey": namespaced_ref("idempotency", f"outcome-{outcome.id}"),
            "reason": "",
            "cancellationRef": None,
        },
    )
    assert RunTerminalEvent.all_objects.filter(invocation=invocation).count() == 1

    with pytest.raises(IdempotencyConflictError):
        propose_outcome(
            run,
            summary="Changed material",
            artifacts=["artifact:migrated"],
            evidence=["evidence:migrated"],
            idempotency_key="idempotency:migration-replay-outcome",
        )

    with pytest.raises(IdempotencyConflictError):
        finalize_invocation(
            invocation,
            kind=TerminalEventKind.RUN_FAILURE,
            idempotency_key=namespaced_ref("idempotency", f"outcome-{outcome.id}"),
        )


@pytest.mark.django_db(transaction=True)
def test_concurrent_invocation_retries_share_one_idempotent_record(assignment, profile):
    run = create_run(assignment, profile)

    def invoke():
        close_old_connections()
        try:
            return record_invocation(run, idempotency_key="idempotency:concurrent-invocation")
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = executor.map(lambda _: invoke(), range(2))

    run.refresh_from_db()
    assert first.id == second.id
    assert run.invocation_count == 1
    assert run.invocations.count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_invocations_on_different_runs_return_typed_conflict(assignment, profile, actor, project):
    other_assignment = create_assignment(
        actor,
        project=project,
        target_ref="issue:124",
        objective="Produce the requested result.",
        acceptance_criteria=["The result is reviewable."],
    )
    first_run = create_run(assignment, profile)
    second_run = create_run(other_assignment, profile)

    def invoke(run):
        close_old_connections()
        try:
            try:
                return record_invocation(run, idempotency_key="idempotency:cross-run-race")
            except IdempotencyConflictError:
                return "conflict"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(invoke, (first_run, second_run)))
    assert results.count("conflict") == 1
    assert sum(result != "conflict" for result in results) == 1
    assert RuntimeInvocation.objects.filter(idempotency_key="idempotency:cross-run-race").count() == 1


@pytest.mark.django_db(transaction=True)
def test_runtime_lock_seam_acquires_assignment_run_invocation_in_order(assignment, profile):
    run = create_run(assignment, profile)
    invocation = record_invocation(run, idempotency_key="idempotency:lock-order-invocation")

    with CaptureQueriesContext(connection) as captured:
        with transaction.atomic():
            locked_assignment, locked_run, locked_invocation = lock_invocation_path(invocation.pk)

    assert locked_assignment.pk == assignment.pk
    assert locked_run.pk == run.pk
    assert locked_invocation.pk == invocation.pk
    lock_queries = [query["sql"].lower() for query in captured.captured_queries if "for update" in query["sql"].lower()]
    assignment_table = AssignmentContract._meta.db_table
    run_table = RunAttempt._meta.db_table
    invocation_table = RuntimeInvocation._meta.db_table
    assignment_index = next(index for index, sql in enumerate(lock_queries) if assignment_table in sql)
    run_index = next(index for index, sql in enumerate(lock_queries) if run_table in sql)
    invocation_index = next(index for index, sql in enumerate(lock_queries) if invocation_table in sql)
    assert assignment_index < run_index < invocation_index


@pytest.mark.django_db(transaction=True)
def test_concurrent_runtime_cancellation_and_transition_serialize_to_one_terminal_event(assignment, profile):
    run = create_run(assignment, profile)
    invocation = record_invocation(run, idempotency_key="idempotency:lock-race-invocation")
    start = threading.Barrier(2)

    def cancel():
        close_old_connections()
        try:
            start.wait(timeout=10)
            return request_runtime_cancellation(invocation, reason="concurrent cancellation")
        finally:
            close_old_connections()

    def fail():
        close_old_connections()
        try:
            start.wait(timeout=10)
            return transition_run(run, RunState.FAILED)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        cancellation_future = executor.submit(cancel)
        transition_future = executor.submit(fail)
        cancellation_result = cancellation_future.result(timeout=15)
        try:
            transition_result = transition_future.result(timeout=15)
        except InvalidTransitionError as exc:
            transition_result = exc

    assert not isinstance(cancellation_result, BaseException)
    assert not isinstance(transition_result, DatabaseError)
    assert transition_result is not None

    run.refresh_from_db()
    invocation.refresh_from_db()
    control = RuntimeInvocationControl.objects.get(invocation=invocation)
    terminal = RunTerminalEvent.objects.get(invocation=invocation)
    final_state = (
        run.state,
        invocation.state,
        terminal.kind,
        control.state,
        control.cancellation_requested_at is not None,
    )
    assert final_state in {
        (
            RunState.CANCELLED,
            InvocationState.CANCELLED,
            TerminalEventKind.RUN_CANCELLATION,
            RuntimeControlState.RELEASED,
            True,
        ),
        (
            RunState.FAILED,
            InvocationState.FAILED,
            TerminalEventKind.RUN_FAILURE,
            RuntimeControlState.AVAILABLE,
            False,
        ),
    }
    assert RunTerminalEvent.objects.filter(invocation=invocation, visible=True).count() == 1


@pytest.mark.django_db(transaction=True)
def test_assignment_actor_can_rebind_before_execution_but_not_after(assignment, profile, actor, project):
    other_actor = create_actor(workspace=assignment.workspace, project=project, display_name="Other worker")
    other_profile = create_profile(other_actor, role=AgentRole.WORKER, instructions="Other instructions.")

    AssignmentContract.objects.filter(pk=assignment.pk).update(assignee_id=other_actor.id)
    assignment.refresh_from_db()
    assert assignment.assignee_id == other_actor.id
    run = create_run(assignment, other_profile)

    assignment.assignee_id = actor.id
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            AssignmentContract.objects.bulk_update([assignment], ["assignee"])
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE agent_assignment_contracts SET assignee_id = %s WHERE id = %s",
                    [actor.id, run.assignment_id],
                )


@pytest.mark.django_db(transaction=True)
def test_invocation_usage_and_ordinals_are_append_only_and_aggregated(assignment, profile):
    run = create_run(assignment, profile)
    first = record_invocation(
        run,
        idempotency_key="idempotency:append-only",
        usage={"inputTokens": 4},
    )
    repeated = record_invocation(
        run,
        idempotency_key="idempotency:append-only",
        usage={"inputTokens": 4},
    )
    assert repeated.id == first.id
    run.refresh_from_db()
    assert first.ordinal == 1
    assert first.usage == {"inputTokens": 4, "outputTokens": 0, "durationMs": 0}
    assert run.invocation_count == 1
    assert run.cumulative_usage == {"inputTokens": 4, "outputTokens": 0, "durationMs": 0}

    with pytest.raises(IdempotencyConflictError):
        record_invocation(run, idempotency_key="idempotency:append-only", usage={"inputTokens": 5})
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            RuntimeInvocation.objects.filter(pk=first.pk).update(ordinal=2)
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            RuntimeInvocation.objects.filter(pk=first.pk).update(usage={"inputTokens": 999})
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE agent_run_attempts SET invocation_count = 2, last_invocation_id = %s WHERE id = %s",
                    [first.invocation_id, run.id],
                )
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM agent_runtime_invocations WHERE id = %s",
                    [first.id],
                )


@pytest.mark.django_db
def test_warm_contract_validator_rechecks_missing_and_tampered_artifacts(assignment, profile, tmp_path, monkeypatch):
    run = create_run(assignment, profile)
    validate_run_snapshot(run.snapshot)
    import shutil

    artifact_directory = tmp_path / "v1"
    shutil.copytree(ARTIFACT_DIRECTORY, artifact_directory)
    monkeypatch.setattr("plane.agent.lifecycle.runtime_contract.ARTIFACT_DIRECTORY", artifact_directory)
    (artifact_directory / "run-snapshot.schema.json").unlink()
    with pytest.raises(ValueError, match="schema is unavailable"):
        validate_run_snapshot(run.snapshot)


@pytest.mark.django_db
def test_idempotency_fingerprints_reject_material_command_changes(assignment, profile):
    run = create_run(assignment, profile, idempotency_key="idempotency:fingerprint-run")
    assert create_run(assignment, profile, idempotency_key="idempotency:fingerprint-run").id == run.id
    changed_snapshot = deepcopy(run.snapshot)
    changed_snapshot["totalBudget"]["inputTokens"] += 1
    changed_snapshot["contentDigest"] = snapshot_digest(
        {key: value for key, value in changed_snapshot.items() if key != "contentDigest"}
    )
    with pytest.raises(IdempotencyConflictError):
        create_run(
            assignment,
            profile,
            snapshot=changed_snapshot,
            idempotency_key="idempotency:fingerprint-run",
        )

    record_invocation(run, idempotency_key="idempotency:fingerprint-initial")
    transition_run(run, RunState.WAITING_FOR_INPUT, pending_input_ref="event:fingerprint-question")
    input_event = record_input_event(
        run,
        payload={"answer": "one"},
        pending_input_ref="event:fingerprint-question",
        idempotency_key="idempotency:fingerprint-input",
    )
    assert (
        record_input_event(
            run,
            payload={"answer": "one"},
            idempotency_key="idempotency:fingerprint-input",
        ).id
        == input_event.id
    )
    with pytest.raises(IdempotencyConflictError):
        record_input_event(
            run,
            payload={"answer": "two"},
            pending_input_ref="event:fingerprint-question",
            idempotency_key="idempotency:fingerprint-input",
        )
    with pytest.raises(IdempotencyConflictError):
        record_input_event(
            run,
            payload={"answer": "one"},
            pending_input_ref="event:another-question",
            idempotency_key="idempotency:fingerprint-input",
        )

    invocation = record_invocation(
        run,
        trigger="human_input",
        input_event=input_event,
        idempotency_key="idempotency:fingerprint-invocation",
    )
    with pytest.raises(IdempotencyConflictError):
        record_invocation(
            run,
            invocation_id=invocation.invocation_id,
            usage={"outputTokens": 1},
            idempotency_key="idempotency:fingerprint-invocation",
        )
    with pytest.raises(IdempotencyConflictError):
        record_invocation(
            run,
            trigger="continuation",
            idempotency_key="idempotency:fingerprint-invocation",
        )

    outcome = propose_outcome(
        run,
        summary="first",
        artifacts=["artifact:one"],
        evidence=["evidence:one"],
        idempotency_key="idempotency:fingerprint-outcome",
    )
    assert outcome.summary == "first"
    assert (
        propose_outcome(
            run,
            summary="first",
            artifacts=["artifact:one"],
            evidence=["evidence:one"],
            idempotency_key="idempotency:fingerprint-outcome",
        ).id
        == outcome.id
    )
    with pytest.raises(IdempotencyConflictError):
        propose_outcome(
            run,
            summary="second",
            artifacts=["artifact:one"],
            evidence=["evidence:one"],
            idempotency_key="idempotency:fingerprint-outcome",
        )
    with pytest.raises(IdempotencyConflictError):
        propose_outcome(
            run,
            summary="first",
            artifacts=["artifact:two"],
            evidence=["evidence:one"],
            idempotency_key="idempotency:fingerprint-outcome",
        )
    with pytest.raises(IdempotencyConflictError):
        propose_outcome(
            run,
            summary="first",
            artifacts=["artifact:one"],
            evidence=["evidence:two"],
            idempotency_key="idempotency:fingerprint-outcome",
        )


@pytest.mark.django_db
def test_cancellation_terminal_retry_reuses_the_same_event(assignment, profile):
    run = create_run(assignment, profile)
    invocation = record_invocation(run, idempotency_key="idempotency:retryable-cancellation")

    first = finalize_invocation(invocation, kind=TerminalEventKind.RUN_CANCELLATION)
    repeated = finalize_invocation(invocation, kind=TerminalEventKind.RUN_CANCELLATION)

    assert repeated.id == first.id
    assert repeated.cancellation_ref == f"cancellation:terminal-{invocation.id}"


@pytest.mark.django_db
def test_supervisor_failure_has_exactly_one_visible_terminal_event(assignment, profile):
    run = create_run(assignment, profile)
    invocation = record_invocation(run, idempotency_key="idempotency:supervised-invocation")
    event = finalize_invocation(
        invocation,
        kind=TerminalEventKind.RUN_FAILURE,
        reason="The isolated process died before it published an exit.",
        idempotency_key="idempotency:supervised-failure",
    )
    repeated = finalize_invocation(
        invocation,
        kind=TerminalEventKind.RUN_FAILURE,
        reason="The isolated process died before it published an exit.",
        idempotency_key="idempotency:supervised-failure",
    )
    run.refresh_from_db()
    invocation.refresh_from_db()
    assert event.id == repeated.id
    assert event.visible is True
    assert event.product_ref == event.product_event_ref
    assert run.state == RunState.FAILED
    assert invocation.state == InvocationState.FAILED
    assert run.terminal_events.count() == 1

    with pytest.raises(IdempotencyConflictError):
        finalize_invocation(
            invocation,
            kind=TerminalEventKind.RUN_FAILURE,
            reason="A different reason is a different command.",
            idempotency_key="idempotency:supervised-failure",
        )

    with pytest.raises(IdempotencyConflictError):
        finalize_invocation(invocation, kind=TerminalEventKind.RUN_CANCELLATION)


@pytest.mark.django_db
def test_evaluator_review_precedes_human_acceptance_and_revision_has_lineage(
    assignment, profile, create_user, evaluator
):
    run = create_run(assignment, profile)
    record_invocation(run, idempotency_key="idempotency:review-invocation")
    outcome = propose_outcome(run, summary="Needs another pass", idempotency_key="idempotency:review-outcome")

    with pytest.raises(InvalidTransitionError):
        accept_outcome(outcome, human_reviewer=create_user)

    reviewed = review_outcome(outcome, evaluator=evaluator, feedback="Add evidence.")
    revised = request_revision(reviewed, human_reviewer=create_user, decision_note="Please add evidence.")
    assignment.refresh_from_db()
    assert revised.state == OutcomeState.REVISION_REQUESTED
    assert assignment.state == AssignmentState.REVISION
    assert assignment.revision == 2

    new_run = create_run(
        assignment,
        profile,
        lineage_of=run,
        lineage_reason=RunLineageReason.HUMAN_REVISION,
        idempotency_key="idempotency:revision-run",
    )
    assert new_run.id != run.id
    assert new_run.lineage_of_id == run.id
    assert new_run.snapshot["assignment"]["revision"] == "2"


@pytest.mark.django_db
def test_review_and_decision_notes_are_utf8_bounded_before_state_mutation(assignment, profile, create_user, evaluator):
    run = create_run(assignment, profile)
    record_invocation(run, idempotency_key="idempotency:review-bounds-invocation")
    outcome = propose_outcome(run, summary="A bounded review", idempotency_key="idempotency:review-bounds-outcome")

    reviewed = review_outcome(outcome, evaluator=evaluator, feedback="é" * 2048)
    assert reviewed.state == OutcomeState.EVALUATOR_REVIEWED
    with pytest.raises(AgentDomainError):
        accept_outcome(reviewed, human_reviewer=create_user, decision_note="é" * 2049)
    outcome.refresh_from_db()
    assert outcome.state == OutcomeState.EVALUATOR_REVIEWED
    assert outcome.human_reviewer_id is None

    accepted = accept_outcome(reviewed, human_reviewer=create_user, decision_note="é" * 2048)
    assert accepted.state == OutcomeState.ACCEPTED


@pytest.mark.django_db
def test_failed_and_unknown_runs_require_deliberate_new_run_lineage(assignment, profile):
    failed_run = create_run(assignment, profile)
    record_invocation(failed_run, idempotency_key="idempotency:failed-invocation")
    transition_run(failed_run, RunState.FAILED)
    with pytest.raises(RecoveryIntentRequiredError):
        create_run(assignment, profile)

    fresh_run = create_run(
        assignment,
        profile,
        lineage_of=failed_run,
        lineage_reason=RunLineageReason.FRESH_RUN,
        idempotency_key="idempotency:fresh-run",
    )
    assert fresh_run.lineage_of_id == failed_run.id

    record_invocation(fresh_run, idempotency_key="idempotency:unknown-invocation")
    unknown = transition_run(fresh_run, RunState.OUTCOME_UNKNOWN)
    with pytest.raises(RecoveryIntentRequiredError):
        create_run(assignment, profile)
    with pytest.raises(RecoveryIntentRequiredError):
        create_run(assignment, profile, recovery_of=unknown)

    recovered = create_run(
        assignment,
        profile,
        recovery_of=unknown,
        recovery_intent=RecoveryIntent.RECONCILE,
        idempotency_key="idempotency:recovered-run",
    )
    assert recovered.recovery_of_id == unknown.id
    assert recovered.lineage_of_id == unknown.id
    assert recovered.lineage_reason == RunLineageReason.RECOVERY
    with pytest.raises(InvalidTransitionError):
        record_invocation(unknown, idempotency_key="idempotency:blind-replay")


@pytest.mark.django_db
def test_invalid_snapshot_digest_and_tool_allowlist_are_rejected(assignment, actor):
    with pytest.raises(AgentDomainError):
        create_profile(
            actor,
            role=AgentRole.WORKER,
            instructions="No hidden permissions.",
            tool_presentation={"permissions": ["operation:secret"]},
        )

    profile = create_profile(actor, role=AgentRole.WORKER, instructions="Create a valid run.")
    run = create_run(assignment, profile)
    invalid = deepcopy(run.snapshot)
    invalid["contentDigest"] = "snapshot:" + "0" * 64
    with pytest.raises(AgentDomainError):
        validate_run_snapshot(invalid)


@pytest.mark.django_db
def test_identifiers_are_strict_and_target_references_are_lossless(assignment, profile, actor, project):
    run = create_run(assignment, profile)
    for malformed in ("client:key", "client key", "idempotency:client:key", "idempotency:" + "a" * 120):
        with pytest.raises(AgentDomainError):
            record_invocation(run, idempotency_key=malformed)

    other_assignment = create_assignment(
        actor,
        project=project,
        target_ref="issue 123",
        objective="Produce the requested result.",
        acceptance_criteria=["The result is reviewable."],
    )
    other_run = create_run(other_assignment, profile)
    assert run.snapshot["assignment"]["targetRef"] != other_run.snapshot["assignment"]["targetRef"]
    assert namespaced_ref("target", "literal-69737375653a313233") == run.snapshot["assignment"]["targetRef"]


def _provider_attempt_notice(invocation, *, phase, upstream_initiated, sequence=1, status_class=None, error_code=None):
    terminal = phase in {
        RuntimeProviderAttemptPhase.COMPLETED,
        RuntimeProviderAttemptPhase.FAILED,
        RuntimeProviderAttemptPhase.OUTCOME_UNKNOWN,
    }
    return {
        "phase": phase,
        "runId": str(invocation.run_id),
        "invocationId": invocation.invocation_id,
        "leaseId": "lease:provider-attempt",
        "provider": "xai",
        "model": "grok-4",
        "destinationHost": "api.x.ai",
        "destinationPath": "/v1/chat/completions",
        "requestId": "request:provider-attempt",
        "idempotencyKey": f"provider-attempt:sequence-{sequence}",
        "sequence": sequence,
        "upstreamInitiated": upstream_initiated,
        "statusClass": status_class if status_class is not None else ("unknown" if terminal else ""),
        "errorCode": error_code if error_code is not None else ("outcome_unknown" if terminal else ""),
    }


@pytest.mark.django_db(transaction=True)
def test_provider_attempt_reconciles_process_loss_after_external_send(assignment, profile):
    run = create_run(assignment, profile)
    invocation = record_invocation(run, idempotency_key="idempotency:provider-attempt-unknown")
    record_provider_attempt_notice(
        invocation,
        _provider_attempt_notice(invocation, phase=RuntimeProviderAttemptPhase.INTENT, upstream_initiated=False),
    )
    record_provider_attempt_notice(
        invocation,
        _provider_attempt_notice(invocation, phase=RuntimeProviderAttemptPhase.STARTED, upstream_initiated=True),
    )

    reconciled = reconcile_provider_attempts(invocation)
    attempt = RuntimeProviderAttempt.objects.get(invocation=invocation)

    assert len(reconciled) == 1
    assert attempt.phase == RuntimeProviderAttemptPhase.OUTCOME_UNKNOWN
    assert attempt.upstream_initiated is True
    assert attempt.status_class == "unknown"
    assert attempt.error_code == "outcome_unknown"
    assert attempt.terminal_at is not None
    assert provider_attempts_reconciled(invocation) is True


@pytest.mark.django_db(transaction=True)
def test_provider_attempt_reconciles_pre_send_failure_without_external_send(assignment, profile):
    run = create_run(assignment, profile)
    invocation = record_invocation(run, idempotency_key="idempotency:provider-attempt-not-sent")
    record_provider_attempt_notice(
        invocation,
        _provider_attempt_notice(invocation, phase=RuntimeProviderAttemptPhase.INTENT, upstream_initiated=False),
    )

    reconcile_provider_attempts(invocation)
    attempt = RuntimeProviderAttempt.objects.get(invocation=invocation)

    assert attempt.phase == RuntimeProviderAttemptPhase.FAILED
    assert attempt.upstream_initiated is False
    assert attempt.status_class == "not_sent"
    assert attempt.error_code == "pre_send_failure"
    assert provider_attempts_reconciled(invocation) is True


@pytest.mark.django_db(transaction=True)
def test_provider_attempt_reconciliation_leaves_completed_attempt_completed(assignment, profile):
    run = create_run(assignment, profile)
    invocation = record_invocation(run, idempotency_key="idempotency:provider-attempt-completed")
    record_provider_attempt_notice(
        invocation,
        _provider_attempt_notice(invocation, phase=RuntimeProviderAttemptPhase.INTENT, upstream_initiated=False),
    )
    record_provider_attempt_notice(
        invocation,
        _provider_attempt_notice(
            invocation,
            phase=RuntimeProviderAttemptPhase.STARTED,
            upstream_initiated=True,
        ),
    )
    record_provider_attempt_notice(
        invocation,
        _provider_attempt_notice(
            invocation,
            phase=RuntimeProviderAttemptPhase.COMPLETED,
            upstream_initiated=True,
            status_class="2xx",
            error_code="",
        ),
    )
    completed_at = RuntimeProviderAttempt.objects.get(invocation=invocation).terminal_at

    reconciled = reconcile_provider_attempts(invocation)
    attempt = RuntimeProviderAttempt.objects.get(invocation=invocation)

    assert reconciled == ()
    assert attempt.phase == RuntimeProviderAttemptPhase.COMPLETED
    assert attempt.upstream_initiated is True
    assert attempt.status_class == "2xx"
    assert attempt.error_code == ""
    assert attempt.terminal_at == completed_at
    assert provider_attempts_reconciled(invocation) is True
