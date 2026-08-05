from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from django.core.exceptions import ValidationError
from django.db import close_old_connections

from plane.agent.lifecycle import create_actor, create_profile
from plane.agent.memory import (
    AgentMemoryError,
    apply_memory_retention,
    assemble_agent_context,
    capture_memory_candidate,
    create_memory,
    create_user_preference,
    delete_memory,
    parse_memory_markdown,
    promote_proposal,
    propose_memory_change,
    project_user_markdown,
    review_proposal,
    rollback_memory,
)
from plane.agent.schedules import create_schedule, fire_schedule
from plane.agent.skills import (
    capture_skill_candidate,
    create_skill,
    parse_skill_package,
    project_skill_package,
    propose_skill_change,
    rollback_skill,
    skill_package_digest,
)
from plane.db.models import (
    AgentProposalState,
    AgentProvenanceKind,
    AgentRevisionState,
    AgentRole,
    AgentScheduleFireState,
    AgentScheduleState,
    AgentSkillVisibility,
    Project,
    User,
)


@pytest.fixture
def project(workspace):
    return Project.objects.create(workspace=workspace, name="Context project", identifier="CTX")


@pytest.fixture
def actor(workspace, project):
    return create_actor(workspace=workspace, project=project, display_name="Context worker")


@pytest.fixture
def profile(actor):
    return create_profile(actor, role=AgentRole.WORKER, instructions="Use only authorized Plane context.")


@pytest.fixture
def gardener(workspace, project):
    gardener = create_actor(workspace=workspace, project=project, display_name="Context gardener")
    create_profile(gardener, role=AgentRole.GARDENER, instructions="Curate one target Agent at a time.")
    return gardener


class AllowSubject:
    def can_read_user_preferences(self, *, actor, subject_user_id):
        return True

    def can_read_shared_skills(self, *, actor, visibility):
        return visibility == AgentSkillVisibility.WORKSPACE


@pytest.mark.django_db
def test_context_projection_keeps_agent_memory_and_subject_user_preferences_separate(actor, profile, create_user):
    user = create_user
    other_user = User.objects.create(username="other-context-user", email="other-context-user@plane.so")
    memory_content = 'Prefer short updates.\n<!-- plane-memory-entry:v1 {"fake":1} -->\n'
    memory = create_memory(actor, key="working-style", content=memory_content)
    preference = create_user_preference(actor, subject_user=user, key="tone", content="Use direct language.")
    skill = create_skill(actor, key="release-check", package_files={"SKILL.md": "# Release\nCheck evidence.\n"})
    user_skill = create_skill(
        actor,
        key="user-release-check",
        package_files={"SKILL.md": "# User release\n"},
        visibility=AgentSkillVisibility.SUBJECT_USER,
        subject_user=user,
    )
    shared_skill = create_skill(
        actor,
        key="shared-release-check",
        package_files={"SKILL.md": "# Shared release\n"},
        visibility=AgentSkillVisibility.WORKSPACE,
    )

    denied = assemble_agent_context(actor, subject_user=user)
    assert parse_memory_markdown(denied.memory_markdown)[0].content == memory_content
    assert denied.user_markdown == project_user_markdown([])
    assert "Use direct language." not in denied.memory_markdown
    assert denied.skill_packages["release-check"] == {"SKILL.md": "# Release\nCheck evidence.\n"}
    assert "user-release-check" not in denied.skill_packages
    assert "shared-release-check" not in denied.skill_packages

    allowed = assemble_agent_context(actor, subject_user=user, authorization=AllowSubject())
    assert parse_memory_markdown(allowed.memory_markdown)[0].entry_ref == f"memory-entry:{memory.id}"
    assert parse_memory_markdown(allowed.user_markdown)[0].entry_ref == f"memory-entry:{preference.id}"
    assert "Use direct language." not in allowed.memory_markdown
    assert (
        project_skill_package(skill.revisions.get(state=AgentRevisionState.ACTIVE))
        == allowed.skill_packages["release-check"]
    )
    assert allowed.skill_packages["user-release-check"] == project_skill_package(
        user_skill.revisions.get(state=AgentRevisionState.ACTIVE)
    )
    assert allowed.skill_packages["shared-release-check"] == project_skill_package(
        shared_skill.revisions.get(state=AgentRevisionState.ACTIVE)
    )

    other_subject = assemble_agent_context(actor, subject_user=other_user, authorization=AllowSubject())
    assert "user-release-check" not in other_subject.skill_packages

    other_actor = create_actor(workspace=actor.workspace, project=actor.project, display_name="Other context worker")
    create_memory(other_actor, key="other-agent-fact", content="Only the other Agent may see this.")
    other_context = assemble_agent_context(other_actor, authorization=AllowSubject())
    assert "Only the other Agent may see this." in other_context.memory_markdown
    assert memory_content not in other_context.memory_markdown
    assert other_context.skill_packages["shared-release-check"] == allowed.skill_packages["shared-release-check"]


@pytest.mark.django_db
def test_candidate_promotion_rollback_and_skill_package_round_trip(actor, profile, gardener, create_user):
    memory = create_memory(actor, key="preference", content="Original")
    original_revision = memory.revisions.get(revision=1)
    original_revision.content = "Tampered"
    with pytest.raises(ValidationError):
        original_revision.save()
    with pytest.raises(ValidationError):
        original_revision.delete()

    candidate = capture_memory_candidate(actor, key="learning", content="Observed candidate")
    assert candidate.state == AgentRevisionState.CANDIDATE
    assert candidate.provenance == AgentProvenanceKind.AGENT_LEARNING
    assert "Observed candidate" not in assemble_agent_context(actor).memory_markdown

    skill_candidate = capture_skill_candidate(
        actor,
        key="learned-release",
        package_files={"SKILL.md": "# Learned release\n"},
    )
    assert skill_candidate.state == AgentRevisionState.CANDIDATE
    assert skill_candidate.provenance == AgentProvenanceKind.AGENT_LEARNING
    assert "learned-release" not in assemble_agent_context(actor).skill_packages
    with pytest.raises(AgentMemoryError):
        create_skill(
            actor,
            key="unapproved-shared",
            package_files={"SKILL.md": "# Not promoted\n"},
            visibility=AgentSkillVisibility.WORKSPACE,
            provenance=AgentProvenanceKind.AGENT_LEARNING,
        )

    proposal = propose_memory_change(
        actor,
        key="preference",
        content="Promoted guidance",
        gardener=gardener,
        rationale="The gardener found a repeatable pattern.",
        idempotency_key="proposal:memory:one",
    )
    review_proposal(proposal, reviewer=create_user, approve=True, note="Approved for this Agent.")
    promoted = promote_proposal(proposal)
    assert proposal.__class__.objects.get(pk=proposal.pk).state == AgentProposalState.APPLIED
    assert promoted.predecessor_id == memory.revisions.get(revision=1).id
    assert promoted.content == "Promoted guidance"

    rolled_back = rollback_memory(
        memory,
        to_revision=memory.revisions.get(revision=1),
        reviewer=create_user,
        rationale="Restore the previously accepted guidance.",
    )
    assert rolled_back.content == "Original"
    assert memory.revisions.count() == 4
    assert memory.revisions.get(revision=2).content == "Promoted guidance"

    skill = create_skill(actor, key="release", package_files={"SKILL.md": "# v1\n", "references/a.txt": "a\n"})
    first_revision = skill.revisions.get(revision=1)
    assert parse_skill_package(project_skill_package(first_revision)) == first_revision.package_files
    assert skill_package_digest(first_revision.package_files) == first_revision.package_digest
    skill_proposal = propose_skill_change(
        actor,
        key="release",
        package_files={"SKILL.md": "# v2\n", "scripts/check.py": "print('ok')\n"},
        gardener=gardener,
        rationale="Add the deterministic check script.",
        requested_visibility=AgentSkillVisibility.WORKSPACE,
        idempotency_key="proposal:skill:one",
    )
    review_proposal(skill_proposal, reviewer=create_user, approve=True)
    skill_revision = promote_proposal(skill_proposal)
    skill.refresh_from_db()
    assert skill.visibility == AgentSkillVisibility.WORKSPACE
    assert skill_revision.package_files["scripts/check.py"] == "print('ok')\n"
    rolled_skill = rollback_skill(
        skill,
        to_revision=first_revision,
        reviewer=create_user,
        rationale="Restore the prior package.",
    )
    assert rolled_skill.package_files == first_revision.package_files


@pytest.mark.django_db(transaction=True)
def test_gardener_proposal_is_concurrent_and_idempotent(actor, profile, gardener, create_user):
    def propose():
        close_old_connections()
        try:
            return propose_memory_change(
                actor,
                key="concurrent",
                content="Same candidate",
                gardener=gardener,
                rationale="One deterministic proposal.",
                idempotency_key="proposal:concurrent",
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = list(executor.map(lambda _: propose(), range(2)))
    assert first.id == second.id
    assert first.__class__.objects.filter(idempotency_key="proposal:concurrent").count() == 1


@pytest.mark.django_db
def test_retention_and_deletion_require_governance_and_keep_revisions(actor, profile, create_user):
    entry = create_memory(
        actor,
        key="expires",
        content="Keep until the deadline.",
        retention_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    with pytest.raises(AgentMemoryError):
        delete_memory(entry, reason="missing reviewer")
    with pytest.raises(ValidationError):
        entry.delete()
    assert apply_memory_retention(now=datetime.now(timezone.utc)) == 1
    assert entry.__class__.objects.filter(pk=entry.pk).count() == 0
    assert entry.__class__.all_objects.get(pk=entry.pk).revisions.count() == 1


@pytest.mark.django_db
def test_schedule_timezone_idempotency_normal_assignment_and_retry(actor, profile, create_user):
    start = datetime(2026, 8, 5, 15, 0, tzinfo=timezone.utc)
    schedule = create_schedule(
        actor,
        name="Morning check",
        cron_expression="0 9 * * *",
        timezone_name="America/Los_Angeles",
        target_ref="issue:123",
        objective="Run the morning check.",
        retry_policy={"maxAttempts": 2, "backoffSeconds": 0},
        starts_at=start,
    )
    assert schedule.next_fire_at == datetime(2026, 8, 5, 16, 0, tzinfo=timezone.utc)
    fire = fire_schedule(schedule, scheduled_for=schedule.next_fire_at, created_by=create_user)
    repeated = fire_schedule(schedule, scheduled_for=schedule.next_fire_at, created_by=create_user)
    assert fire.state == AgentScheduleFireState.CREATED
    assert repeated.id == fire.id
    assert fire.assignment.state == "ready"
    schedule.refresh_from_db()
    assert schedule.next_fire_at == datetime(2026, 8, 6, 16, 0, tzinfo=timezone.utc)

    schedule.state = AgentScheduleState.PAUSED
    schedule.save()
    failed = fire_schedule(schedule, scheduled_for=schedule.next_fire_at, now=start)
    assert failed.state == AgentScheduleFireState.FAILED
    schedule.state = AgentScheduleState.ENABLED
    schedule.save()
    retried = fire_schedule(schedule, scheduled_for=schedule.next_fire_at, now=start + timedelta(seconds=1))
    assert retried.state == AgentScheduleFireState.CREATED
    assert retried.assignment is not None
