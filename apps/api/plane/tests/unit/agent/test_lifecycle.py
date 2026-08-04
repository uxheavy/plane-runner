# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from uuid import uuid4

import pytest
from django.core.exceptions import ValidationError
from django.db import close_old_connections

from plane.agent.lifecycle import (
    AgentDomainError,
    IdempotencyConflictError,
    InvalidTransitionError,
    RecoveryIntentRequiredError,
    TerminalEventRequiredError,
    accept_outcome,
    create_actor,
    create_assignment,
    create_profile,
    create_run,
    finalize_invocation,
    propose_outcome,
    record_input_event,
    record_invocation,
    request_revision,
    review_outcome,
    transition_assignment,
    transition_run,
)
from plane.agent.lifecycle.runtime_contract import (
    contract_digests,
    contract_manifest,
    validate_invocation_envelope,
    validate_run_snapshot,
)
from plane.db.models import (
    AgentRole,
    AssignmentState,
    InputEventKind,
    InvocationState,
    OutcomeState,
    Project,
    RecoveryIntent,
    RunLineageReason,
    RunState,
    TerminalEventKind,
)


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
        "runSnapshot": "e538fe79ede53e6bb2e307600dbefea507e30b996c002c3dab32d543ca0e36a2",
        "invocationEnvelope": "b7a15d74406f1624cdb7cd95b42edfd1ffee596abe57e4f00ed60e2e23ded995",
        "runtimeEvent": "fcbf67ce71fa90dd9661a8f2a739b8119c59357c8bf01afabf4fe92a13de9425",
        "runtimeExit": "055792eb1bf4931dafe19de456b15037522f0b5e8f6a0d2fedfe0e0d1d1d1c05",
        "runtimeDurableState": "444c944ec8a5054f33c8662470529a1f4565d42ff06138438beceeef7967a0da",
    }


@pytest.mark.django_db
def test_profile_and_snapshot_are_immutable_and_direct_state_changes_use_lifecycle(assignment, profile):
    run = create_run(assignment, profile)

    profile.instructions = "Changed after resolution."
    with pytest.raises(ValidationError):
        profile.save()

    run.snapshot = deepcopy(run.snapshot)
    run.snapshot["assignment"]["objective"] = "Changed after resolution."
    with pytest.raises(ValidationError):
        run.save()

    assignment.state = AssignmentState.COMPLETED
    with pytest.raises(ValidationError):
        assignment.save()


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
    transition_run(run, RunState.WAITING_FOR_INPUT)
    answer = record_input_event(
        run,
        payload={"answer": "Continue"},
        kind=InputEventKind.HUMAN_INPUT,
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
    assert run.__class__.objects.get(pk=run.pk).invocations.get(pk=first.pk).terminal_event.kind == TerminalEventKind.OUTCOME_SUBMISSION

    with pytest.raises(IdempotencyConflictError):
        record_invocation(run, idempotency_key="idempotency:repeatable-outcome")


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
        reason="ignored on the idempotent retry",
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

    with pytest.raises(TerminalEventRequiredError):
        finalize_invocation(invocation, kind=TerminalEventKind.RUN_CANCELLATION)


@pytest.mark.django_db
def test_evaluator_review_precedes_human_acceptance_and_revision_has_lineage(assignment, profile, create_user, evaluator):
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
