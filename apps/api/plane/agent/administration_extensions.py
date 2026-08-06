# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Concrete, bounded adapters for the merged Agent governance records."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Mapping, TypedDict
from uuid import UUID

from django.db import transaction

from plane.agent.administration import (
    AGENT_ADMIN_L7_ACTIONS,
    AgentAdminExtensionCommand,
    AgentAdminExtensionError,
    agent_admin_extension,
    redact_admin_value,
    register_agent_admin_extension,
)
from plane.agent.lifecycle import (
    accept_outcome,
    cancel_assignment,
    decide_hr_proposal,
    propose_chief_of_staff,
    request_revision,
    review_outcome,
)
from plane.agent.readback import AgentReadbackTooLarge, validate_readback_limit
from plane.agent.validation import MAX_AGENT_READBACK_BYTES, validate_bounded_json
from plane.db.models import (
    AgentActor,
    AgentHRProposal,
    AssignmentContract,
    EvaluatorReview,
    OutcomeState,
    OutcomeSubmission,
    RuntimeInvocation,
    User,
    Workspace,
    WorkspaceMember,
)


RESOURCE_NAME = "plane.agent.governance"
RESOURCE_ALL = "workspace"


class AssignmentGovernanceProjection(TypedDict):
    id: str
    parent_assignment_id: str | None
    root_assignment_id: str | None
    delegated_by_id: str | None
    assignee_id: str
    delegation_depth: int
    revision: int
    state: str
    target_ref: str
    scope: Mapping[str, Any]
    budget: Mapping[str, Any]
    created_at: str


class HRProposalGovernanceProjection(TypedDict):
    id: str
    kind: str
    state: str
    proposed_by_id: str
    subject_actor_id: str | None
    subject_user_id: str | None
    target_assignment_id: str | None
    requested_assignee_id: str | None
    requested_role: str | None
    requested_display_name: str
    rationale: str
    reviewed_by_id: str | None
    reviewed_at: str | None
    review_note: str
    applied_actor_id: str | None
    created_at: str


class EvaluatorReviewGovernanceProjection(TypedDict):
    id: str
    outcome_id: str
    run_id: str
    outcome_state: str
    evaluator_id: str
    evaluator_profile_id: str
    criteria: list[Any]
    verdict: str
    recommendation: str
    provenance: Mapping[str, Any]
    reviewed_at: str


class GovernanceReadback(TypedDict):
    assignments: list[AssignmentGovernanceProjection]
    hr_proposals: list[HRProposalGovernanceProjection]
    evaluator_reviews: list[EvaluatorReviewGovernanceProjection]


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _safe_text(value: Any, *, max_chars: int = 2048) -> str:
    if value is None:
        return ""
    return str(redact_admin_value(str(value)))[:max_chars]


def _safe_json(value: Any, field_name: str, *, fallback: Any) -> Any:
    value = redact_admin_value(value if value is not None else fallback)
    validate_bounded_json(value, field_name, max_bytes=MAX_AGENT_READBACK_BYTES, reject_credentials=False)
    return value


def assignment_governance_projection(assignment: AssignmentContract) -> AssignmentGovernanceProjection:
    return {
        "id": str(assignment.id),
        "parent_assignment_id": str(assignment.lineage_of_id) if assignment.lineage_of_id else None,
        "root_assignment_id": str(assignment.root_assignment_id) if assignment.root_assignment_id else None,
        "delegated_by_id": str(assignment.delegated_by_id) if assignment.delegated_by_id else None,
        "assignee_id": str(assignment.assignee_id),
        "delegation_depth": assignment.delegation_depth,
        "revision": assignment.revision,
        "state": assignment.state,
        "target_ref": _safe_text(assignment.target_ref, max_chars=512),
        "scope": _safe_json(assignment.scope, "assignment.scope", fallback={}),
        "budget": _safe_json(assignment.budget, "assignment.budget", fallback={}),
        "created_at": assignment.created_at.isoformat(),
    }


def hr_proposal_governance_projection(proposal: AgentHRProposal) -> HRProposalGovernanceProjection:
    return {
        "id": str(proposal.id),
        "kind": proposal.kind,
        "state": proposal.state,
        "proposed_by_id": str(proposal.proposed_by_id),
        "subject_actor_id": str(proposal.subject_actor_id) if proposal.subject_actor_id else None,
        "subject_user_id": str(proposal.subject_user_id) if proposal.subject_user_id else None,
        "target_assignment_id": str(proposal.target_assignment_id) if proposal.target_assignment_id else None,
        "requested_assignee_id": str(proposal.requested_assignee_id) if proposal.requested_assignee_id else None,
        "requested_role": proposal.requested_role,
        "requested_display_name": _safe_text(proposal.requested_display_name, max_chars=255),
        "rationale": _safe_text(proposal.rationale),
        "reviewed_by_id": str(proposal.reviewed_by_id) if proposal.reviewed_by_id else None,
        "reviewed_at": _iso(proposal.reviewed_at),
        "review_note": _safe_text(proposal.review_note),
        "applied_actor_id": str(proposal.applied_actor_id) if proposal.applied_actor_id else None,
        "created_at": proposal.created_at.isoformat(),
    }


def evaluator_review_governance_projection(review: EvaluatorReview) -> EvaluatorReviewGovernanceProjection:
    outcome = review.outcome
    return {
        "id": str(review.id),
        "outcome_id": str(review.outcome_id),
        "run_id": str(review.run_id),
        "outcome_state": outcome.state,
        "evaluator_id": str(review.evaluator_id),
        "evaluator_profile_id": str(review.evaluator_profile_id),
        "criteria": _safe_json(review.criteria, "evaluator_review.criteria", fallback=[]),
        "verdict": review.verdict,
        "recommendation": _safe_text(review.recommendation, max_chars=4096),
        "provenance": _safe_json(review.provenance, "evaluator_review.provenance", fallback={}),
        "reviewed_at": review.reviewed_at.isoformat(),
    }


def _resource_parts(resource_id: str | None) -> tuple[str | None, UUID | None]:
    if resource_id is None or resource_id in {"", RESOURCE_ALL, "all"}:
        return None, None
    if ":" in resource_id:
        prefix, value = resource_id.split(":", 1)
    else:
        prefix, value = "", resource_id
    try:
        parsed = UUID(value)
    except (AttributeError, ValueError):
        raise AgentAdminExtensionError("The requested governance resource is unavailable") from None
    prefixes = {
        "assignment": "assignment",
        "hr-proposal": "hr_proposal",
        "outcome-submission": "outcome",
        "evaluator-review": "evaluator_review",
    }
    kind = prefixes.get(prefix)
    if kind is None:
        raise AgentAdminExtensionError("The requested governance resource is unavailable")
    return kind, parsed


def _bounded_readback(payload: GovernanceReadback) -> GovernanceReadback:
    redacted = redact_admin_value(payload)
    encoded = json.dumps(redacted, sort_keys=True, default=str).encode("utf-8")
    if len(encoded) > MAX_AGENT_READBACK_BYTES:
        raise AgentReadbackTooLarge("governance readback exceeds the 8KB bounded output ceiling; reduce the limit")
    return redacted


def build_governance_readback(
    workspace: Workspace,
    *,
    limit: int,
    resource_id: str | None = None,
) -> GovernanceReadback:
    """Return the same bounded L7 projection for API and management command."""

    limit = validate_readback_limit(limit)
    resource_kind, parsed_id = _resource_parts(resource_id)
    assignments = AssignmentContract.objects.filter(workspace=workspace).order_by("-created_at", "-id")
    proposals = AgentHRProposal.objects.filter(workspace=workspace).order_by("-created_at", "-id")
    reviews = (
        EvaluatorReview.objects.filter(workspace=workspace).select_related("outcome").order_by("-created_at", "-id")
    )
    if resource_kind == "assignment":
        assignments = assignments.filter(pk=parsed_id)
        proposals = proposals.none()
        reviews = reviews.none()
    elif resource_kind == "hr_proposal":
        assignments = assignments.none()
        proposals = proposals.filter(pk=parsed_id)
        reviews = reviews.none()
    elif resource_kind == "outcome":
        assignments = assignments.none()
        proposals = proposals.none()
        reviews = reviews.filter(outcome_id=parsed_id)
    elif resource_kind == "evaluator_review":
        assignments = assignments.none()
        proposals = proposals.none()
        reviews = reviews.filter(pk=parsed_id)
    payload: GovernanceReadback = {
        "assignments": [assignment_governance_projection(row) for row in assignments[:limit]],
        "hr_proposals": [hr_proposal_governance_projection(row) for row in proposals[:limit]],
        "evaluator_reviews": [evaluator_review_governance_projection(row) for row in reviews[:limit]],
    }
    return _bounded_readback(payload)


def _uuid(value: Any, field_name: str) -> UUID:
    try:
        return UUID(str(value))
    except (AttributeError, ValueError):
        raise AgentAdminExtensionError("The governance command is unavailable") from None


def _scoped_workspace(command: AgentAdminExtensionCommand) -> Workspace:
    workspace = Workspace.objects.filter(pk=_uuid(command.workspace_id, "workspace_id")).first()
    if workspace is None:
        raise AgentAdminExtensionError("The governance command is unavailable")
    return workspace


def _scoped_user(workspace: Workspace, value: Any) -> User:
    user = User.objects.filter(pk=_uuid(value, "user_id"), is_active=True, is_bot=False).first()
    if (
        user is None
        or not WorkspaceMember.objects.filter(
            workspace=workspace, member=user, role__in=[20, 15], is_active=True
        ).exists()
    ):
        raise AgentAdminExtensionError("The governance command is unavailable")
    return user


def _scoped_actor(workspace: Workspace, value: Any) -> AgentActor:
    actor = (
        AgentActor.objects.select_related("active_profile")
        .filter(workspace=workspace, pk=_uuid(value, "actor_id"))
        .first()
    )
    if actor is None or not actor.is_active:
        raise AgentAdminExtensionError("The governance command is unavailable")
    return actor


def _scoped_assignment(workspace: Workspace, value: Any) -> AssignmentContract:
    assignment = AssignmentContract.objects.filter(workspace=workspace, pk=_uuid(value, "assignment_id")).first()
    if assignment is None:
        raise AgentAdminExtensionError("The governance command is unavailable")
    return assignment


def _scoped_outcome(workspace: Workspace, value: Any) -> OutcomeSubmission:
    outcome = (
        OutcomeSubmission.objects.select_related("run")
        .filter(workspace=workspace, pk=_uuid(value, "outcome_id"))
        .first()
    )
    if outcome is None:
        raise AgentAdminExtensionError("The governance command is unavailable")
    return outcome


def _assert_binding(command: AgentAdminExtensionCommand, *, actor_id=None, run_id=None, invocation_id=None) -> None:
    if command.actor_id is not None and (actor_id is None or str(command.actor_id) != str(actor_id)):
        raise AgentAdminExtensionError("The governance command is unavailable")
    if command.run_id is not None and (run_id is None or str(command.run_id) != str(run_id)):
        raise AgentAdminExtensionError("The governance command is unavailable")
    if command.invocation_id is not None and (
        invocation_id is None or str(command.invocation_id) != str(invocation_id)
    ):
        raise AgentAdminExtensionError("The governance command is unavailable")


class PlaneAgentAdministrationExtension:
    """Concrete implementation of the administration extension port."""

    resource_name = RESOURCE_NAME

    def read(self, *, workspace_id: str, resource_id: str) -> Mapping[str, Any] | None:
        workspace = Workspace.objects.filter(pk=_uuid(workspace_id, "workspace_id")).first()
        if workspace is None:
            return None
        return build_governance_readback(workspace, limit=1, resource_id=resource_id)

    @transaction.atomic
    def execute(self, command: AgentAdminExtensionCommand) -> Mapping[str, Any]:
        workspace = _scoped_workspace(command)
        payload = dict(command.payload)
        if command.action == "delegation.lineage.read":
            _assert_binding(command)
            return (
                self.read(
                    workspace_id=str(workspace.id),
                    resource_id=str(payload.get("resource_id") or RESOURCE_ALL),
                )
                or {}
            )
        if command.action == "hr.proposal.read":
            _assert_binding(command)
            return (
                self.read(
                    workspace_id=str(workspace.id),
                    resource_id=str(payload.get("resource_id") or RESOURCE_ALL),
                )
                or {}
            )
        if command.action == "chief_of_staff.provision":
            human = _scoped_user(workspace, payload.get("human_id"))
            proposer = _scoped_actor(workspace, payload.get("proposed_by_id"))
            _assert_binding(command, actor_id=proposer.id)
            proposal = propose_chief_of_staff(
                workspace=workspace,
                human=human,
                proposed_by=proposer,
                idempotency_key=command.idempotency_key,
                rationale=_safe_text(payload.get("rationale"), max_chars=4096),
                created_by=human,
            )
            return {"hr_proposals": [hr_proposal_governance_projection(proposal)]}
        if command.action == "hr.proposal.decide":
            proposal = AgentHRProposal.objects.filter(
                workspace=workspace, pk=_uuid(payload.get("proposal_id"), "proposal_id")
            ).first()
            if proposal is None:
                raise AgentAdminExtensionError("The governance command is unavailable")
            _assert_binding(command, actor_id=proposal.proposed_by_id)
            proposal = decide_hr_proposal(
                proposal,
                human_reviewer=command.authenticated_user,
                approved=bool(payload.get("approved")),
                decision_note=_safe_text(payload.get("decision_note")),
                idempotency_key=command.idempotency_key,
            )
            return {"hr_proposals": [hr_proposal_governance_projection(proposal)]}
        if command.action == "assignment.cancel":
            assignment = _scoped_assignment(workspace, payload.get("assignment_id"))
            _assert_binding(command, actor_id=assignment.assignee_id)
            cancelled = cancel_assignment(assignment, operator=command.authenticated_user)
            return {"assignments": [assignment_governance_projection(cancelled)]}
        if command.action == "evaluator.review":
            outcome = _scoped_outcome(workspace, payload.get("outcome_id"))
            evaluator = _scoped_actor(workspace, payload.get("evaluator_id"))
            if (
                command.invocation_id is not None
                and not RuntimeInvocation.objects.filter(
                    run_id=outcome.run_id, invocation_id=command.invocation_id
                ).exists()
            ):
                raise AgentAdminExtensionError("The governance command is unavailable")
            _assert_binding(command, actor_id=evaluator.id, run_id=outcome.run_id, invocation_id=command.invocation_id)
            reviewed = review_outcome(
                outcome,
                evaluator=evaluator,
                feedback=_safe_text(payload.get("feedback"), max_chars=4096),
                criteria=payload.get("criteria"),
                verdict=payload.get("verdict", "accept"),
                provenance=payload.get("provenance"),
                idempotency_key=command.idempotency_key,
            )
            review = EvaluatorReview.objects.select_related("outcome").get(outcome_id=reviewed.id)
            return {"evaluator_reviews": [evaluator_review_governance_projection(review)]}
        if command.action in {"outcome.accept", "outcome.request_revision"}:
            outcome = _scoped_outcome(workspace, payload.get("outcome_id"))
            if (
                command.invocation_id is not None
                and not RuntimeInvocation.objects.filter(
                    run_id=outcome.run_id, invocation_id=command.invocation_id
                ).exists()
            ):
                raise AgentAdminExtensionError("The governance command is unavailable")
            _assert_binding(
                command,
                actor_id=outcome.evaluator_id,
                run_id=outcome.run_id,
                invocation_id=command.invocation_id,
            )
            target_state = (
                OutcomeState.ACCEPTED if command.action == "outcome.accept" else OutcomeState.REVISION_REQUESTED
            )
            if outcome.state != target_state:
                if command.action == "outcome.accept":
                    outcome = accept_outcome(
                        outcome,
                        human_reviewer=command.authenticated_user,
                        decision_note=_safe_text(payload.get("decision_note")),
                    )
                else:
                    outcome = request_revision(
                        outcome,
                        human_reviewer=command.authenticated_user,
                        decision_note=_safe_text(payload.get("decision_note")),
                    )
            review = EvaluatorReview.objects.filter(outcome=outcome).select_related("outcome").first()
            return {
                "evaluator_reviews": [evaluator_review_governance_projection(review)] if review else [],
            }
        raise AgentAdminExtensionError("The governance command is unavailable")


def plane_agent_admin_extension() -> PlaneAgentAdministrationExtension:
    existing = agent_admin_extension(RESOURCE_NAME)
    if existing is not None:
        return existing.port  # type: ignore[return-value]
    return register_agent_admin_extension(PlaneAgentAdministrationExtension()).port  # type: ignore[return-value]


__all__ = [
    "AGENT_ADMIN_L7_ACTIONS",
    "AgentAdminExtensionCommand",
    "AgentReadbackTooLarge",
    "GovernanceReadback",
    "PlaneAgentAdministrationExtension",
    "assignment_governance_projection",
    "build_governance_readback",
    "evaluator_review_governance_projection",
    "hr_proposal_governance_projection",
    "plane_agent_admin_extension",
]
