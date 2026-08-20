"""Migration-backed lifecycle guards for deliberate runs after unknown outcomes."""

from __future__ import annotations

from django.utils import timezone
import pytest

from plane.agent.lifecycle import (
    RecoveryIntentRequiredError,
    create_actor,
    create_assignment,
    create_profile,
    create_run,
    record_invocation,
    transition_run,
)
from plane.db.models import (
    AgentRole,
    FreshAssignmentDecision,
    ReconciliationState,
    RecoveryIntent,
    RunLineageReason,
    RunState,
    RuntimeReconciliation,
)


def _unknown_run(workspace, create_user, *, suffix):
    actor = create_actor(workspace=workspace, display_name=f"Reconciliation guard {suffix}", created_by=create_user)
    profile = create_profile(
        actor,
        role=AgentRole.WORKER,
        instructions="Run only after a safe operator reconciliation.",
        created_by=create_user,
    )
    assignment = create_assignment(
        actor,
        target_ref=f"issue:reconciliation-guard-{suffix}",
        objective="Prove safe fresh-run gating.",
        acceptance_criteria=["A safe reconciliation is required."],
        created_by=create_user,
    )
    run = create_run(assignment, profile, created_by=create_user)
    invocation = record_invocation(run, idempotency_key=f"idempotency:reconciliation-guard-{suffix}")
    transition_run(run, RunState.OUTCOME_UNKNOWN)
    return actor, profile, assignment, run, invocation


def _reconciliation(run, invocation, create_user, decision):
    return RuntimeReconciliation.objects.create(
        workspace=run.workspace,
        project=run.project,
        invocation=invocation,
        run=run,
        state=ReconciliationState.RECONCILED,
        fresh_assignment_decision=decision,
        terminal_event_ref=f"terminal:reconciliation-guard-{run.id}",
        runtime_exit_ref=f"runtime-exit:reconciliation-guard-{run.id}",
        evidence={"providerAttempts": 0},
        idempotency_key=f"idempotency:reconciliation-guard-reconcile-{run.id}",
        command_fingerprint="command:" + "a" * 64,
        reconciled_by=create_user,
        reconciled_at=timezone.now(),
        created_by=create_user,
    )


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_unknown_run_without_reconciliation_cannot_start_recovery(workspace, create_user):
    _actor, profile, assignment, run, _invocation = _unknown_run(workspace, create_user, suffix="missing")

    with pytest.raises(RecoveryIntentRequiredError, match="SAFE runtime reconciliation"):
        create_run(
            assignment,
            profile,
            recovery_of=run,
            recovery_intent=RecoveryIntent.RECONCILE,
            idempotency_key="idempotency:reconciliation-guard-missing-recovery",
            created_by=create_user,
        )

    assert run.recovery_runs.count() == 0


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_unknown_run_with_unsafe_reconciliation_cannot_start_fresh_run(workspace, create_user):
    _actor, profile, assignment, run, invocation = _unknown_run(workspace, create_user, suffix="unsafe")
    _reconciliation(run, invocation, create_user, FreshAssignmentDecision.UNSAFE)

    with pytest.raises(RecoveryIntentRequiredError, match="SAFE runtime reconciliation"):
        create_run(
            assignment,
            profile,
            lineage_of=run,
            lineage_reason=RunLineageReason.FRESH_RUN,
            idempotency_key="idempotency:reconciliation-guard-unsafe-fresh",
            created_by=create_user,
        )

    assert run.lineage_children.count() == 0


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_unknown_run_requires_reconciliation_bound_to_current_invocation(workspace, create_user):
    _actor, profile, assignment, run, _invocation = _unknown_run(workspace, create_user, suffix="conflict")
    _other_actor, _other_profile, _other_assignment, _other_run, other_invocation = _unknown_run(
        workspace, create_user, suffix="conflict-other"
    )
    RuntimeReconciliation.objects.bulk_create(
        [
            RuntimeReconciliation(
                workspace=run.workspace,
                project=run.project,
                invocation=other_invocation,
                run=run,
                state=ReconciliationState.RECONCILED,
                fresh_assignment_decision=FreshAssignmentDecision.SAFE,
                evidence={"providerAttempts": 0},
                idempotency_key="idempotency:reconciliation-guard-conflict",
                command_fingerprint="command:" + "b" * 64,
                reconciled_by=create_user,
                reconciled_at=timezone.now(),
                created_by=create_user,
            )
        ]
    )

    with pytest.raises(RecoveryIntentRequiredError, match="SAFE runtime reconciliation"):
        create_run(
            assignment,
            profile,
            recovery_of=run,
            recovery_intent=RecoveryIntent.RECONCILE,
            idempotency_key="idempotency:reconciliation-guard-conflict-recovery",
            created_by=create_user,
        )

    assert run.recovery_runs.count() == 0


@pytest.mark.contract
@pytest.mark.django_db(transaction=True)
def test_safe_reconciliation_allows_fresh_and_recovery_runs(workspace, create_user):
    _actor, profile, assignment, run, invocation = _unknown_run(workspace, create_user, suffix="safe")
    _reconciliation(run, invocation, create_user, FreshAssignmentDecision.SAFE)

    fresh = create_run(
        assignment,
        profile,
        lineage_of=run,
        lineage_reason=RunLineageReason.FRESH_RUN,
        idempotency_key="idempotency:reconciliation-guard-safe-fresh",
        created_by=create_user,
    )
    recovery = create_run(
        assignment,
        profile,
        recovery_of=run,
        recovery_intent=RecoveryIntent.RECONCILE,
        idempotency_key="idempotency:reconciliation-guard-safe-recovery",
        created_by=create_user,
    )

    assert fresh.lineage_of_id == run.id
    assert recovery.recovery_of_id == run.id
