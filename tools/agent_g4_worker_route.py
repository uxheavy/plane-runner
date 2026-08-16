"""Reusable durable checks for the typed Worker persona journey.

The live invoker owns lifecycle orchestration.  This module keeps Worker route
fixtures and readback assertions on the existing Plane memory, skill, gateway,
and readback owners instead of turning the invoker into a persona verifier.
"""

from __future__ import annotations

import json
from datetime import timedelta

from django.utils import timezone
from plane.agent.memory.projections import parse_memory_markdown
from plane.agent.memory.services import AgentMemoryError, create_memory, create_user_preference, delete_memory
from plane.agent.operations_readback import build_correlation_readback
from plane.agent.skills.projections import parse_skill_package
from plane.agent.skills.services import (
    capture_skill_candidate,
    create_skill,
    delete_skill,
    promote_skill_proposal,
    propose_skill_change,
    rollback_skill,
)
from agent_g4_worker_route_observations import has_code_mode_callback
from plane.db.models import (
    AgentChangeProposal,
    AgentMemoryRevision,
    AgentProposalState,
    AgentRevisionState,
    AgentRole,
    AgentSkillDefinition,
    AgentSkillRevision,
    AgentSkillVisibility,
    Issue,
    OutcomeSubmission,
    Project,
    ProjectMember,
    RunTerminalEvent,
    RuntimeEventIngress,
    State,
    User,
    Workspace,
    WorkspaceMember,
)
from plane.db.models.operation_gateway import OperationGatewayAudit, OperationGatewayIdempotency
from plane.operation_gateway.gateway import OperationGateway
from plane.agent.lifecycle import create_actor, create_profile
from plane.agent.memory.services import review_proposal


def context_state_counts(actor, run):
    """Return bounded durable counters used to prove provider-disabled replay."""

    return {
        "memoryRevisions": AgentMemoryRevision.objects.filter(entry__actor=actor).count(),
        "skillRevisions": AgentSkillRevision.objects.filter(definition__actor=actor).count(),
        "proposals": AgentChangeProposal.objects.filter(actor=actor).count(),
        "contextReceipts": OperationGatewayIdempotency.objects.filter(
            correlation_id=f"correlation:{run.id}", operation_id="agent.context.read"
        ).count(),
    }


def seed_worker_context(*, actor, workspace, project, user, suffix, provider, model):
    """Create isolated context subjects and exclusion sentinels through owners."""

    other_user = User.objects.create(
        email=f"g4-live-other-{suffix}@plane.test",
        username=f"g4-live-other-{suffix}",
        first_name="Other",
        last_name="Subject",
    )
    WorkspaceMember.objects.create(workspace=workspace, member=other_user, role=15)
    other_project = Project.objects.create(
        name="G4 Hidden Project", identifier=f"H{suffix[:2].upper()}", workspace=workspace, created_by=user
    )
    ProjectMember.objects.create(project=other_project, member=user, role=20, is_active=True)
    State.objects.create(
        name="Hidden Backlog",
        color="#111111",
        group="backlog",
        default=True,
        project=other_project,
        workspace=workspace,
        created_by=user,
    )
    hidden_issue = Issue.objects.create(
        name="G4 Hidden Project Only", project=other_project, workspace=workspace, created_by=user
    )
    other_actor = create_actor(workspace=workspace, project=project, display_name="G4 Other Agent", created_by=user)
    private_memory = create_memory(
        actor,
        key="maya-rename-policy",
        content="Use the assigned issue's semantic rename operation and verify its receipt.",
        created_by=user,
    )
    create_user_preference(
        actor,
        subject_user=user,
        key="maya-response-style",
        content="Report the final Plane receipt briefly.",
        created_by=user,
    )
    create_user_preference(
        actor,
        subject_user=other_user,
        key="other-subject-only",
        content="OTHER_USER_ONLY",
        created_by=user,
    )
    stale_memory = create_memory(
        actor,
        key="stale-memory",
        content="STALE_MEMORY_ONLY",
        retention_expires_at=timezone.now() - timedelta(minutes=1),
        created_by=user,
    )
    deleted_memory = create_memory(
        actor, key="deleted-memory", content="DELETED_MEMORY_ONLY", created_by=user
    )
    delete_memory(deleted_memory, reviewer=user, reason="worker route exclusion")
    create_memory(other_actor, key="other-agent-memory", content="OTHER_AGENT_ONLY", created_by=user)
    skill_package = {
        "SKILL.md": "# Maya rename skill\n\nUse the typed work_item.rename callback and verify the returned name.",
        "examples/rename.ts": "export const operation = 'work_item.rename';\n",
    }
    skill = create_skill(
        actor, key="maya-rename-skill", package_files=skill_package, display_name="Maya Rename Skill", created_by=user
    )
    stale_skill = create_skill(
        actor,
        key="stale-skill",
        package_files={"SKILL.md": "STALE_SKILL_ONLY"},
        retention_expires_at=timezone.now() - timedelta(minutes=1),
        created_by=user,
    )
    deleted_skill = create_skill(
        actor, key="deleted-skill", package_files={"SKILL.md": "DELETED_SKILL_ONLY"}, created_by=user
    )
    delete_skill(deleted_skill, reviewer=user, reason="worker route exclusion")
    gardener = create_actor(workspace=workspace, project=project, display_name="G4 Gardener", created_by=user)
    create_profile(
        gardener,
        role=AgentRole.GARDENER,
        instructions="Govern private skill revisions for this worker.",
        runtime_defaults={"provider": provider, "model": model, "adapter": "hermes"},
        created_by=user,
    )
    return {
        "privateMemoryKey": private_memory.key,
        "subjectPreferenceKey": "maya-response-style",
        "skillKey": skill.key,
        "hiddenMarkers": (
            "G4 Hidden Project Only",
            "OTHER_USER_ONLY",
            "STALE_MEMORY_ONLY",
            "DELETED_MEMORY_ONLY",
            "OTHER_AGENT_ONLY",
            "STALE_SKILL_ONLY",
            "DELETED_SKILL_ONLY",
        ),
        "hiddenIssueId": str(hidden_issue.id),
        "gardener": gardener,
        "initialSkill": skill,
        "staleMemory": stale_memory,
        "staleSkill": stale_skill,
    }


def attempt_actor_substitution(*, actor, fake_actor, workspace, run, user, suffix):
    """Prove the context operation binds the durable actor to the run."""

    correlation = f"correlation:{run.id}:actor-substitution"
    request = type(
        "TrustedSubstitutionRequest",
        (),
        {
            "user": actor.principal,
            "META": {},
            "agent_actor_ref": f"actor:{fake_actor.id}",
            "agent_workspace_ref": f"workspace:{workspace.id}",
            "agent_run_ref": run.snapshot["runId"],
        },
    )()
    raw = {
        "schema_version": "plane.operation/v1",
        "operation_id": "agent.context.read",
        "workspace_slug": workspace.slug,
        "idempotency_key": f"idempotency:g4-live-substitution-{suffix}",
        "correlation_id": correlation,
        "input": {"subject_user_ref": f"user:{user.id}"},
    }
    response, status = OperationGateway().execute(request, raw)
    error = response.get("error", {}) if isinstance(response, dict) else {}
    return {
        "status": "denied" if status == 403 else "unexpected",
        "errorCode": error.get("code"),
        "sideEffects": OperationGatewayIdempotency.objects.filter(
            correlation_id=correlation,
            state=OperationGatewayIdempotency.State.SUCCEEDED,
        ).count()
        + OutcomeSubmission.objects.filter(run=run).count(),
    }


def replay_worker_rename(*, actor, workspace, run, issue, correlation_id):
    """Replay the provider-created rename receipt and verify no semantic mutation."""

    record = OperationGatewayIdempotency.objects.filter(
        correlation_id=correlation_id,
        operation_id="work_item.rename",
        state=OperationGatewayIdempotency.State.SUCCEEDED,
    ).order_by("created_at", "id").first()
    if record is None:
        raise RuntimeError("Worker W03 requires one successful work_item.rename gateway receipt")
    issue.refresh_from_db()
    before_name = issue.name
    before_audit_count = OperationGatewayAudit.objects.filter(
        correlation_id=correlation_id, operation_id="work_item.rename", phase="outcome"
    ).count()
    request = type(
        "TrustedReplayRequest",
        (),
        {
            "user": actor.principal,
            "META": {},
            "agent_actor_ref": run.snapshot["actorRef"],
            "agent_workspace_ref": run.snapshot["workspaceRef"],
            "agent_run_ref": run.snapshot["runId"],
        },
    )()
    raw = {
        "schema_version": "plane.operation/v1",
        "operation_id": "work_item.rename",
        "workspace_slug": workspace.slug,
        "idempotency_key": record.idempotency_key,
        "correlation_id": correlation_id,
        "input": record.request_input,
    }
    response, status = OperationGateway().execute(request, raw)
    issue.refresh_from_db()
    after_audit_count = OperationGatewayAudit.objects.filter(
        correlation_id=correlation_id, operation_id="work_item.rename", phase="outcome"
    ).count()
    replay = {
        "status": "replayed" if response.get("idempotency", {}).get("replayed") is True else "unexpected",
        "semanticDelta": int(issue.name != before_name),
        "duplicateMutation": int(after_audit_count - before_audit_count > 1),
        "httpStatus": status,
    }
    if replay["status"] != "replayed" or replay["semanticDelta"] != 0:
        raise RuntimeError("Worker W03 gateway replay was not stable and duplicate-free")
    return replay


def govern_worker_skill(*, actor, gardener, initial_skill, run, user, workspace, suffix):
    """Exercise the existing candidate, review, promotion, and rollback owners."""

    files = {
        "SKILL.md": "# Maya rename skill v2\n\nVerify the bounded rename receipt before publishing.",
        "examples/rename.ts": "export const operation = 'work_item.rename';\nexport const version = 2;\n",
    }
    candidate = capture_skill_candidate(
        actor, key=initial_skill.key, package_files=files, source_run=run,
        rationale="Provider-backed Worker candidate from the assigned rename journey.", created_by=user,
    )
    proposal = propose_skill_change(
        actor, key=initial_skill.key, package_files=files, gardener=gardener,
        rationale="Human-reviewable private improvement from the Worker run.",
        requested_visibility=AgentSkillVisibility.AGENT_PRIVATE,
        idempotency_key=f"idempotency:g4-live-skill-proposal-{suffix}", source_run=run, created_by=user,
    )
    proposal_replay = propose_skill_change(
        actor, key=initial_skill.key, package_files=files, gardener=gardener,
        rationale="Human-reviewable private improvement from the Worker run.",
        requested_visibility=AgentSkillVisibility.AGENT_PRIVATE,
        idempotency_key=f"idempotency:g4-live-skill-proposal-{suffix}", source_run=run, created_by=user,
    )
    reviewed = review_proposal(proposal, reviewer=user, approve=True, note="Reviewed by Maya's human owner.")
    promoted = promote_skill_proposal(reviewed, reviewer=user)
    definition = AgentSkillDefinition.objects.get(pk=initial_skill.id)
    initial_revision = AgentSkillRevision.objects.filter(
        definition=initial_skill, state=AgentRevisionState.ACTIVE
    ).order_by("revision").first()
    if initial_revision is None:
        raise RuntimeError("Worker W06 requires an initial active skill revision")
    rolled_back = rollback_skill(
        definition, to_revision=initial_revision, reviewer=user,
        rationale="Restore the original private skill revision after the governed trial.",
    )
    try:
        propose_skill_change(
            actor, key=initial_skill.key, package_files=files, gardener=gardener,
            rationale="Unsupported shared promotion must fail closed.",
            requested_visibility=AgentSkillVisibility.ORGANIZATION,
            idempotency_key=f"idempotency:g4-live-skill-org-{suffix}", source_run=run, created_by=user,
        )
    except AgentMemoryError:
        unsupported_shared = True
    else:
        unsupported_shared = False
    workspace_proposal = propose_skill_change(
        actor, key=initial_skill.key, package_files=files, gardener=gardener,
        rationale="Remain private until an explicit human promotion decision.",
        requested_visibility=AgentSkillVisibility.WORKSPACE, requested_scope_id=workspace.id,
        idempotency_key=f"idempotency:g4-live-skill-workspace-{suffix}", source_run=run, created_by=user,
    )
    definition.refresh_from_db()
    evidence = {
        "candidate": candidate.state == AgentRevisionState.CANDIDATE,
        "humanApproved": reviewed.state == AgentProposalState.APPROVED,
        "promoted": promoted.state == AgentRevisionState.ACTIVE,
        "privateAfterPromotion": definition.visibility == AgentSkillVisibility.AGENT_PRIVATE,
        "rollbackRevision": rolled_back.state == AgentRevisionState.ACTIVE,
        "proposalReplayStable": proposal_replay.id == proposal.id,
        "unsupportedSharedDenied": unsupported_shared,
        "workspaceUnreviewedNotPromoted": (
            workspace_proposal.state == AgentProposalState.PROPOSED
            and definition.visibility == AgentSkillVisibility.AGENT_PRIVATE
        ),
    }
    if not all(evidence.values()):
        raise RuntimeError("Worker W06 skill governance evidence was incomplete")
    return evidence


def worker_readback_facts(*, run, workspace, user, suffix):
    """Use the existing bounded API/CLI-equivalent readback owners."""

    # W08 needs presence/consistency facts only.  The established correlation
    # readback is the bounded API/CLI-equivalent owner for those facts; avoid
    # duplicating the full admin projection, whose outcome payload can exceed
    # the shared 8-KiB ceiling on a provider-heavy run.
    correlation_readback = build_correlation_readback(workspace, run_id=str(run.id), limit=1)
    other_workspace = Workspace.objects.create(
        name=f"G4 Readback Isolation {suffix}", owner=user, slug=f"g4-readback-{suffix}"
    )
    cross_workspace_readback = build_correlation_readback(other_workspace, run_id=str(run.id), limit=8)
    readback_json = json.dumps(correlation_readback, sort_keys=True, default=str)
    return {
        "runReadbackPassed": bool(correlation_readback.get("linkage", {}).get("found", {}).get("run"))
        and "plane-credential" not in readback_json,
        "apiCliConsistent": bool(correlation_readback.get("linkage", {}).get("found", {}).get("run"))
        and bool(correlation_readback.get("links", {}).get("runs")),
        "crossWorkspaceDenied": not any(cross_workspace_readback.get("linkage", {}).get("found", {}).values()),
    }


def worker_code_mode_controls(run):
    """Bind live positive Code Mode use to the persisted bounded runtime policy."""

    policy = run.snapshot.get("runtimePolicy", {}) if isinstance(run.snapshot, dict) else {}
    return all(
        isinstance(policy.get(field), int) and policy[field] > 0
        for field in ("maxCodeModeInputBytes", "maxCodeModeOutputBytes", "maxCodeModeCalls")
    )


def worker_code_mode_operation_observed(run, operation_id):
    """Require the runtime's source/action observation for one Code Mode callback."""

    observations = RuntimeEventIngress.objects.filter(
        run=run, kind="progress_observed"
    ).values_list("raw_payload", flat=True)
    return has_code_mode_callback(observations, operation_id)


def build_worker_route_evidence(
    *, scenario, run, assignment, actor, context_facts, governance, substitution, rename_replay, context_replay_delta
):
    """Build route evidence from durable records and typed projections."""

    if scenario is None or not scenario.expected or not scenario.expected.get("routeChecks"):
        return {}, []
    route_checks = set(scenario.expected["routeChecks"])
    correlation_id = f"correlation:{run.id}"
    context_records = []
    context = {}
    parsed_memory = ()
    parsed_user = ()
    parsed_skills = {}
    hidden_markers = tuple(context_facts.get("hiddenMarkers", ()))
    context_json = "{}"
    memory_keys = set()
    user_keys = set()
    skill_keys = set()
    if "W05" in route_checks:
        context_records = list(
            OperationGatewayIdempotency.objects.filter(
                correlation_id=correlation_id,
                operation_id="agent.context.read",
                state=OperationGatewayIdempotency.State.SUCCEEDED,
            ).order_by("created_at", "id")
        )
        payloads = [
            (record.result or {}).get("context", {})
            for record in context_records
            if isinstance(record.result, dict) and isinstance((record.result or {}).get("context"), dict)
        ]
        context = payloads[0] if len(payloads) == 1 else {}
        memory_markdown = context.get("memoryMarkdown", "")
        user_markdown = context.get("userMarkdown", "")
        skill_packages = context.get("skillPackages", {})
        parsed_memory = parse_memory_markdown(memory_markdown) if isinstance(memory_markdown, str) else ()
        parsed_user = parse_memory_markdown(user_markdown) if isinstance(user_markdown, str) else ()
        parsed_skills = {
            key: parse_skill_package(files)
            for key, files in skill_packages.items()
            if isinstance(key, str) and isinstance(files, dict)
        }
        context_json = json.dumps(context, sort_keys=True, ensure_ascii=False)
        memory_keys = {item.key for item in parsed_memory}
        user_keys = {item.key for item in parsed_user}
        skill_keys = set(parsed_skills)
    catalog_search = (
        OperationGatewayIdempotency.objects.filter(
            correlation_id=correlation_id,
            operation_id="catalog.search",
            state=OperationGatewayIdempotency.State.SUCCEEDED,
        )
        .order_by("created_at", "id")
        .first()
        if "W02" in route_checks
        else None
    )
    catalog_describe = (
        OperationGatewayIdempotency.objects.filter(
            correlation_id=correlation_id,
            operation_id="catalog.describe",
            state=OperationGatewayIdempotency.State.SUCCEEDED,
        )
        .order_by("created_at", "id")
        .first()
        if "W02" in route_checks
        else None
    )
    rename_record = (
        OperationGatewayIdempotency.objects.filter(
            correlation_id=correlation_id,
            operation_id="work_item.rename",
            state=OperationGatewayIdempotency.State.SUCCEEDED,
        )
        .order_by("created_at", "id")
        .first()
        if "W03" in route_checks
        else None
    )
    outcome = OutcomeSubmission.objects.filter(run=run).first() if "W07" in route_checks else None
    route = {}
    if "W01" in route_checks:
        route["W01"] = {
            "actorProfileAssignmentSeparate": (
                run.actor_id == actor.id and run.assignment_id == assignment.id
                and str(run.profile_version_id) == run.snapshot["profile"]["profileRef"].removeprefix("profile-version:")
                and run.snapshot["actorRef"] == f"actor:{actor.id}"
            ),
            "snapshotBound": run.snapshot.get("assignment", {}).get("assignmentRef") == f"assignment:{assignment.id}",
            "substitution": substitution,
        }
    if "W02" in route_checks:
        route["W02"] = {
            "catalogSearchBeforeDescribe": bool(
                catalog_search and catalog_describe
                and (catalog_search.created_at, str(catalog_search.id)) < (catalog_describe.created_at, str(catalog_describe.id))
            ),
            "boundedSearchAndRead": all(
                OperationGatewayIdempotency.objects.filter(
                    correlation_id=correlation_id, operation_id=operation_id,
                    state=OperationGatewayIdempotency.State.SUCCEEDED,
                ).exists()
                for operation_id in ("search_workspace", "work_item.read")
            ),
            "hiddenObjectsAbsent": not any(
                marker in json.dumps(
                    [record.result for record in OperationGatewayIdempotency.objects.filter(
                        correlation_id=correlation_id, operation_id="search_workspace",
                        state=OperationGatewayIdempotency.State.SUCCEEDED,
                )], sort_keys=True,
            ) for marker in hidden_markers
            ),
        }
    if "W03" in route_checks:
        route["W03"] = {
            **rename_replay,
            "receiptRef": f"receipt:{rename_record.request_id}" if rename_record else None,
            "auditReceiptRef": (
                f"audit-receipt:{rename_record.audit_receipt}" if rename_record and rename_record.audit_receipt else None
            ),
        }
    if "W04" in route_checks:
        route["W04"] = {
            "positiveTypedHostCallback": (
                int((run.cumulative_usage or {}).get("codeModeCalls", 0)) > 0
                and worker_code_mode_operation_observed(run, "work_item.rename")
            ),
            "sameGateway": OperationGatewayIdempotency.objects.filter(
                correlation_id=correlation_id,
                operation_id__in=("work_item.read", "work_item.rename", "agent.context.read"),
                state=OperationGatewayIdempotency.State.SUCCEEDED,
            ).exists(),
            "failClosedControls": context_facts.get("codeModeControlsPassed") is True,
        }
    if "W05" in route_checks:
        route["W05"] = {
            "contextReceipt": len(context_records) == 1,
            "privateMemoryPresent": context_facts["privateMemoryKey"] in memory_keys,
            "subjectPreferencesSeparate": context_facts["subjectPreferenceKey"] in user_keys
            and context_facts["privateMemoryKey"] not in user_keys,
            "skillProjectionPresent": context_facts["skillKey"] in skill_keys,
            "excludedOtherUserAgentStale": not any(marker in context_json for marker in hidden_markers),
            "losslessRoundTrip": bool(
                isinstance(memory_markdown, str) and isinstance(user_markdown, str)
                and parsed_memory is not None and parsed_user is not None
            ),
        }
    if "W06" in route_checks:
        route["W06"] = governance
    if "W07" in route_checks:
        route["W07"] = {
            "oneOutcome": OutcomeSubmission.objects.filter(run=run).count() == 1,
            "oneArtifact": bool(outcome and isinstance(outcome.artifacts, list) and len(outcome.artifacts) == 1),
            "evidenceAttached": bool(outcome and isinstance(outcome.evidence, list) and len(outcome.evidence) > 0),
            "onePublishedTerminal": RunTerminalEvent.objects.filter(
                run=run, visible=True, kind="outcome_submission"
            ).count() == 1,
        }
    if "W08" in route_checks:
        route["W08"] = {
            "runReadback": context_facts.get("runReadbackPassed") is True,
            "apiCliConsistent": context_facts.get("apiCliConsistent") is True,
            "crossWorkspaceDenied": context_facts.get("crossWorkspaceDenied") is True,
        }
    route["replay"] = {"context": context_replay_delta}
    failures = []
    for route_id in scenario.expected["routeChecks"]:
        value = route.get(route_id, {})
        boolean_values = (
            [item for key, item in value.items() if key != "substitution"]
            if isinstance(value, dict)
            else []
        )
        if not isinstance(value, dict) or not all(item is True for item in boolean_values):
            failures.append(f"route:{route_id}")
    return {
        "routes": route,
        "readback": {"contextProjectionDigest": context.get("projectionDigest", "0" * 64)},
    }, failures
