from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from django.core.exceptions import ValidationError
from django.db import close_old_connections

from plane.agent.lifecycle import (
    InvalidTransitionError,
    RecoveryIntentRequiredError,
    create_actor,
    create_profile,
    create_run,
    record_invocation,
    transition_run,
)
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
    project_memory_markdown,
    review_proposal,
    rollback_memory,
)
from plane.agent.schedules import (
    AgentScheduleError,
    cancel_schedule,
    create_schedule,
    fire_due_schedules,
    fire_schedule,
    next_schedule_fire,
    parse_cron_expression,
    pause_schedule,
    resume_schedule,
)
from plane.agent.skills import (
    capture_skill_candidate,
    create_skill,
    delete_skill,
    parse_skill_package,
    project_skill_package,
    propose_skill_change,
    rollback_skill,
    skill_package_digest,
)
from plane.db.models import (
    AgentChangeProposal,
    AgentProposalState,
    AgentProvenanceKind,
    AgentRevisionState,
    AgentRole,
    AgentScheduleFire,
    AgentScheduleFireState,
    AgentScheduleState,
    AgentSkillDefinition,
    AgentSkillVisibility,
    AssignmentContract,
    Project,
    RecoveryIntent,
    RunState,
    User,
    Workspace,
    WorkspaceMember,
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

    def can_read_shared_skills(self, *, actor, visibility, scope_id):
        return visibility == AgentSkillVisibility.WORKSPACE and scope_id == str(actor.workspace_id)


@pytest.mark.django_db
def test_context_projection_keeps_agent_memory_and_subject_user_preferences_separate(
    actor, profile, gardener, create_user
):
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
    shared_proposal = propose_skill_change(
        actor,
        key="shared-release-check",
        package_files={"SKILL.md": "# Shared release\n"},
        gardener=gardener,
        rationale="Share the reviewed release check with this workspace.",
        requested_visibility=AgentSkillVisibility.WORKSPACE,
        requested_scope_id=actor.workspace_id,
    )
    review_proposal(shared_proposal, reviewer=user, approve=True)
    promote_proposal(shared_proposal)
    shared_skill = actor.skill_definitions.get(key="shared-release-check")

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
def test_context_projection_excludes_expired_memory_and_skill_roots(actor, profile, create_user):
    expired_memory = create_memory(
        actor,
        key="expired-projection-memory",
        content="EXPIRED_PROJECTION_MEMORY",
        retention_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    expired_skill = create_skill(
        actor,
        key="expired-projection-skill",
        package_files={"SKILL.md": "EXPIRED_PROJECTION_SKILL"},
        retention_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )

    projection = assemble_agent_context(actor, subject_user=create_user, authorization=AllowSubject())

    assert expired_memory.key not in {entry.key for entry in parse_memory_markdown(projection.memory_markdown)}
    assert expired_skill.key not in projection.skill_packages


@pytest.mark.django_db
def test_memory_projection_parser_is_fail_closed_and_unicode_lossless(actor, profile):
    content = 'café🙂\n<!-- plane-memory-entry:v1 {"nested":true} -->\n終\n'
    entry = create_memory(actor, key="unicode", content=content)
    revision = entry.revisions.get(revision=1)
    projection = project_memory_markdown([(entry, revision)])
    assert parse_memory_markdown(projection)[0].content == content

    header = projection.split("## unicode", 1)[0]

    adversarial_inputs = {
        "prefixed": "prefix\n" + projection,
        "appended": projection + "trailing garbage",
        "header_only_garbage": header + "unmarked garbage",
        "malformed_metadata": projection.replace('"key":"unicode"', '"key":', 1),
        "duplicate_metadata": projection.replace('"key":"unicode"', '"key":"unicode","key":"duplicate"'),
        "wrong_metadata_type": projection.replace(
            f'"contentChars":{len(content)}', f'"contentChars":"{len(content)}"', 1
        ),
        "length_mismatch": projection.replace(
            f'"contentBytes":{len(content.encode("utf-8"))}', '"contentBytes":999999', 1
        ),
        "digest_mismatch": projection.replace(
            f'"contentDigest":"{revision.content_digest}"', f'"contentDigest":"content:{"0" * 64}"', 1
        ),
    }
    for name, malformed in adversarial_inputs.items():
        with pytest.raises(ValueError, match="Plane|projection|metadata|content|digest|entry"):
            parse_memory_markdown(malformed), name

    second = create_memory(actor, key="zulu", content="later")
    second_projection = project_memory_markdown([(entry, revision), (second, second.revisions.get(revision=1))])
    first_end = second_projection.index("<!-- plane-memory-entry-end -->") + len("<!-- plane-memory-entry-end -->")
    with pytest.raises(ValueError, match="unexpected|ordered|separator"):
        parse_memory_markdown(second_projection[:first_end] + "\ncorrupt\n\n" + second_projection[first_end + 2 :])

    first_start = second_projection.index("## unicode\n")
    second_start = second_projection.index("## zulu\n")
    reordered = (
        second_projection[:first_start] + second_projection[second_start:] + second_projection[first_start:second_start]
    )
    with pytest.raises(ValueError, match="ordered|duplicate|key"):
        parse_memory_markdown(reordered)


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
        requested_scope_id=actor.workspace_id,
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
def test_shared_skill_requires_reviewed_real_scope_and_never_leaks(actor, profile, gardener, create_user):
    with pytest.raises(AgentMemoryError, match="Direct skill creation"):
        create_skill(
            actor,
            key="direct-shared",
            package_files={"SKILL.md": "# Direct\n"},
            visibility=AgentSkillVisibility.WORKSPACE,
            provenance=AgentProvenanceKind.HUMAN,
        )
    assert AgentSkillDefinition.objects.filter(key="direct-shared").count() == 0

    for unsupported in (AgentSkillVisibility.TEMPLATE, AgentSkillVisibility.ORGANIZATION):
        with pytest.raises(AgentMemoryError, match="Direct skill creation"):
            create_skill(
                actor,
                key=f"direct-{unsupported}",
                package_files={"SKILL.md": "# Direct unsupported\n"},
                visibility=unsupported,
                provenance=AgentProvenanceKind.HUMAN,
            )

    for requested_scope in (None, uuid4()):
        with pytest.raises(AgentMemoryError, match="scope"):
            propose_skill_change(
                actor,
                key=f"invalid-scope-{uuid4().hex}",
                package_files={"SKILL.md": "# Invalid scope\n"},
                gardener=gardener,
                rationale="The scope must be real and explicit.",
                requested_visibility=AgentSkillVisibility.WORKSPACE,
                requested_scope_id=requested_scope,
            )
    for unsupported in (AgentSkillVisibility.TEMPLATE, AgentSkillVisibility.ORGANIZATION):
        with pytest.raises(AgentMemoryError, match="Unsupported shared skill scope"):
            propose_skill_change(
                actor,
                key=f"unsupported-{unsupported}",
                package_files={"SKILL.md": "# Unsupported scope\n"},
                gardener=gardener,
                rationale="Plane has no authoritative owner for this scope.",
                requested_visibility=unsupported,
            )
    assert not AgentChangeProposal.objects.filter(actor=actor).exists()

    proposal = propose_skill_change(
        actor,
        key="reviewed-shared",
        package_files={"SKILL.md": "# Reviewed shared\n"},
        gardener=gardener,
        rationale="Promote only after a real human review.",
        requested_visibility=AgentSkillVisibility.WORKSPACE,
        requested_scope_id=actor.workspace_id,
        idempotency_key="shared-skill-review",
    )
    with pytest.raises(AgentMemoryError, match="human-approved"):
        promote_proposal(proposal)
    assert proposal.__class__.objects.get(pk=proposal.pk).state == AgentProposalState.PROPOSED
    with pytest.raises(AgentMemoryError, match="authorized|human"):
        review_proposal(proposal, reviewer=gardener, approve=True)
    assert proposal.__class__.objects.get(pk=proposal.pk).state == AgentProposalState.PROPOSED
    review_proposal(proposal, reviewer=create_user, approve=True)

    def promote_shared_concurrently():
        close_old_connections()
        try:
            return promote_proposal(proposal)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = list(executor.map(lambda _: promote_shared_concurrently(), range(2)))
    assert first.id == second.id
    definition = AgentSkillDefinition.objects.get(key="reviewed-shared")
    assert definition.visibility == AgentSkillVisibility.WORKSPACE
    assert definition.shared_scope_id == actor.workspace_id

    class WorkspaceOnlyAllow:
        def can_read_user_preferences(self, *, actor, subject_user_id):
            return False

        def can_read_shared_skills(self, *, actor, visibility, scope_id):
            return visibility == AgentSkillVisibility.WORKSPACE and scope_id == str(actor.workspace_id)

    assert "reviewed-shared" in assemble_agent_context(actor, authorization=WorkspaceOnlyAllow()).skill_packages

    other_owner = User.objects.create(
        username=f"other-owner-{uuid4().hex}", email=f"other-owner-{uuid4().hex}@plane.so"
    )
    other_workspace = Workspace.objects.create(
        name="Other shared workspace",
        owner=other_owner,
        slug=f"other-shared-{uuid4().hex[:12]}",
    )
    WorkspaceMember.objects.create(workspace=other_workspace, member=other_owner, role=20)
    other_project = Project.objects.create(
        workspace=other_workspace,
        name="Other shared project",
        identifier="OSH",
    )
    other_actor = create_actor(workspace=other_workspace, project=other_project, display_name="Other shared actor")
    create_profile(other_actor, role=AgentRole.WORKER, instructions="Other scope.")
    assert (
        "reviewed-shared" not in assemble_agent_context(other_actor, authorization=WorkspaceOnlyAllow()).skill_packages
    )


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


@pytest.mark.django_db(transaction=True)
def test_deleted_memory_and_skill_roots_restore_idempotently_with_governance(actor, profile, create_user):
    memory = create_memory(actor, key="restore-memory", content="Restore me.")
    memory_revision = memory.revisions.get(revision=1)
    delete_memory(memory, reviewer=create_user, reason="temporary removal")
    unauthorized = User.objects.create(
        username=f"unauthorized-{uuid4().hex}", email=f"unauthorized-{uuid4().hex}@plane.so"
    )
    with pytest.raises(AgentMemoryError, match="authorized|human"):
        rollback_memory(
            memory,
            to_revision=memory_revision,
            reviewer=unauthorized,
            rationale="Unauthorized restore.",
        )
    assert memory.__class__.all_objects.get(pk=memory.pk).deleted_at is not None

    restored = rollback_memory(
        memory,
        to_revision=memory_revision,
        reviewer=create_user,
        rationale="Restore the approved memory.",
    )
    repeated = rollback_memory(
        memory,
        to_revision=memory_revision,
        reviewer=create_user,
        rationale="Replay the approved restore.",
    )
    assert repeated.id == restored.id
    assert memory.__class__.objects.get(pk=memory.pk).deleted_at is None

    concurrent_memory = create_memory(actor, key="concurrent-restore", content="Concurrent restore.")
    concurrent_revision = concurrent_memory.revisions.get(revision=1)
    delete_memory(concurrent_memory, reviewer=create_user, reason="concurrent removal")

    def restore_memory_concurrently():
        close_old_connections()
        try:
            return rollback_memory(
                concurrent_memory,
                to_revision=concurrent_revision,
                reviewer=create_user,
                rationale="Concurrent approved restore.",
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = list(executor.map(lambda _: restore_memory_concurrently(), range(2)))
    assert first.id == second.id
    assert concurrent_memory.__class__.all_objects.get(pk=concurrent_memory.pk).deleted_at is None

    wrong_root = create_memory(actor, key="wrong-root", content="Wrong root.")
    delete_memory(wrong_root, reviewer=create_user, reason="wrong-root removal")
    with pytest.raises(AgentMemoryError, match="another memory entry"):
        rollback_memory(
            wrong_root,
            to_revision=memory_revision,
            reviewer=create_user,
            rationale="Wrong root target.",
        )
    assert wrong_root.__class__.all_objects.get(pk=wrong_root.pk).deleted_at is not None

    expired = create_memory(
        actor,
        key="expired-restore",
        content="Expired retention.",
        retention_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    expired_revision = expired.revisions.get(revision=1)
    delete_memory(expired, retention=True, reason="retention policy expired")
    with pytest.raises(AgentMemoryError, match="retention has expired"):
        rollback_memory(
            expired,
            to_revision=expired_revision,
            reviewer=create_user,
            rationale="Expired restore.",
        )
    assert expired.__class__.all_objects.get(pk=expired.pk).deleted_at is not None

    skill = create_skill(actor, key="restore-skill", package_files={"SKILL.md": "# Restore\n"})
    skill_revision = skill.revisions.get(revision=1)
    delete_skill(skill, reviewer=create_user, reason="temporary removal")
    with pytest.raises(AgentMemoryError, match="authorized|human"):
        rollback_skill(
            skill,
            to_revision=skill_revision,
            reviewer=unauthorized,
            rationale="Unauthorized skill restore.",
        )
    restored_skill = rollback_skill(
        skill,
        to_revision=skill_revision,
        reviewer=create_user,
        rationale="Restore the approved skill.",
    )
    repeated_skill = rollback_skill(
        skill,
        to_revision=skill_revision,
        reviewer=create_user,
        rationale="Replay the approved skill restore.",
    )
    assert repeated_skill.id == restored_skill.id
    assert skill.__class__.objects.get(pk=skill.pk).deleted_at is None

    expired_skill = create_skill(
        actor,
        key="expired-skill-restore",
        package_files={"SKILL.md": "# Expired\n"},
        retention_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    expired_skill_revision = expired_skill.revisions.get(revision=1)
    delete_skill(expired_skill, retention=True, reason="retention policy expired")
    with pytest.raises(AgentMemoryError, match="retention has expired"):
        rollback_skill(
            expired_skill,
            to_revision=expired_skill_revision,
            reviewer=create_user,
            rationale="Expired skill restore.",
        )
    assert expired_skill.__class__.all_objects.get(pk=expired_skill.pk).deleted_at is not None


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

    paused = pause_schedule(schedule)
    with pytest.raises(AgentScheduleError, match="paused"):
        fire_schedule(schedule, scheduled_for=schedule.next_fire_at, now=start)
    assert paused.__class__.objects.get(pk=schedule.pk).fires.count() == 1
    resumed = resume_schedule(paused)
    retried = fire_schedule(schedule, scheduled_for=resumed.next_fire_at, now=start + timedelta(seconds=1))
    assert retried.state == AgentScheduleFireState.CREATED
    assert retried.assignment is not None


@pytest.mark.django_db
def test_schedule_control_state_is_idempotent_and_blocks_new_fires(actor, profile, create_user):
    start = datetime(2026, 8, 5, 15, 0, tzinfo=timezone.utc)
    schedule = create_schedule(
        actor,
        name="Controllable schedule",
        cron_expression="*/5 * * * *",
        timezone_name="UTC",
        target_ref="issue:control",
        objective="Honor Plane schedule control state.",
        starts_at=start,
    )
    scheduled_for = schedule.next_fire_at

    paused = pause_schedule(schedule)
    assert pause_schedule(paused).id == paused.id
    paused.refresh_from_db()
    assert paused.state == AgentScheduleState.PAUSED
    assert paused.next_fire_at == scheduled_for
    assert fire_due_schedules(now=scheduled_for + timedelta(minutes=1)) == []
    with pytest.raises(AgentScheduleError, match="paused"):
        fire_schedule(paused, scheduled_for=scheduled_for, created_by=create_user)
    assert paused.fires.count() == 0

    resumed = resume_schedule(paused)
    assert resume_schedule(resumed).id == resumed.id
    fire = fire_schedule(resumed, scheduled_for=scheduled_for, created_by=create_user)
    assert fire.state == AgentScheduleFireState.CREATED

    cancelled = cancel_schedule(resumed)
    assert cancel_schedule(cancelled).id == cancelled.id
    cancelled.refresh_from_db()
    assert cancelled.state == AgentScheduleState.DISABLED
    assert cancelled.next_fire_at is None
    with pytest.raises(AgentScheduleError, match="disabled"):
        fire_schedule(cancelled, scheduled_for=scheduled_for + timedelta(minutes=5), created_by=create_user)
    assert cancelled.fires.count() == 1
    with pytest.raises(AgentScheduleError, match="terminal"):
        resume_schedule(cancelled)


def test_standard_cron_weekday_dom_dow_and_dst_semantics():
    _, _, _, _, sunday_zero = parse_cron_expression("0 0 * * 0")
    _, _, _, _, sunday_seven = parse_cron_expression("0 0 * * 7")
    assert sunday_zero == sunday_seven == {0}
    assert next_schedule_fire(
        "0 0 * * 0",
        "UTC",
        datetime(2026, 8, 3, 0, 0, tzinfo=timezone.utc),
    ) == datetime(2026, 8, 9, 0, 0, tzinfo=timezone.utc)
    assert next_schedule_fire(
        "0 0 1 * 1",
        "UTC",
        datetime(2026, 8, 2, 0, 0, tzinfo=timezone.utc),
    ) == datetime(2026, 8, 3, 0, 0, tzinfo=timezone.utc)
    assert next_schedule_fire(
        "0 0 1 * 1",
        "UTC",
        datetime(2026, 8, 3, 0, 0, tzinfo=timezone.utc),
    ) == datetime(2026, 8, 10, 0, 0, tzinfo=timezone.utc)

    spring_forward = next_schedule_fire(
        "30 2 * * *",
        "America/Los_Angeles",
        datetime(2026, 3, 8, 0, 0, tzinfo=timezone.utc),
    )
    assert spring_forward == datetime(2026, 3, 9, 9, 30, tzinfo=timezone.utc)

    fall_back_first = next_schedule_fire(
        "30 1 * * *",
        "America/Los_Angeles",
        datetime(2026, 11, 1, 8, 0, tzinfo=timezone.utc),
    )
    fall_back_after_first = next_schedule_fire(
        "30 1 * * *",
        "America/Los_Angeles",
        datetime(2026, 11, 1, 8, 31, tzinfo=timezone.utc),
    )
    assert fall_back_first == datetime(2026, 11, 1, 8, 30, tzinfo=timezone.utc)
    assert fall_back_after_first == datetime(2026, 11, 2, 9, 30, tzinfo=timezone.utc)


@pytest.mark.django_db(transaction=True)
def test_schedule_fire_concurrency_and_retry_exhaustion(actor, profile, create_user):
    start = datetime(2026, 8, 5, 15, 0, tzinfo=timezone.utc)
    schedule = create_schedule(
        actor,
        name="Concurrent schedule",
        cron_expression="*/5 * * * *",
        timezone_name="UTC",
        target_ref="issue:concurrent",
        objective="Run once.",
        retry_policy={"maxAttempts": 2, "backoffSeconds": 0},
        starts_at=start,
    )
    scheduled_for = schedule.next_fire_at

    def fire_concurrently():
        close_old_connections()
        try:
            return fire_schedule(schedule, scheduled_for=scheduled_for, created_by=create_user)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = list(executor.map(lambda _: fire_concurrently(), range(2)))
    assert first.id == second.id
    assert first.assignment_id is not None
    assert schedule.__class__.objects.get(pk=schedule.pk).fires.count() == 1

    schedule.refresh_from_db()
    actor.is_active = False
    actor.save(update_fields=["is_active", "updated_at"])
    failed = fire_schedule(schedule, scheduled_for=schedule.next_fire_at, now=start)
    assert failed.state == AgentScheduleFireState.FAILED
    failed_again = fire_schedule(
        schedule,
        scheduled_for=schedule.next_fire_at,
        now=start + timedelta(seconds=1),
    )
    assert failed_again.state == AgentScheduleFireState.EXHAUSTED
    assert failed_again.assignment_id is None


@pytest.mark.django_db
def test_schedule_fire_enters_normal_lifecycle_and_requires_explicit_unknown_recovery(actor, profile, create_user):
    start = datetime(2026, 8, 5, 15, 0, tzinfo=timezone.utc)
    schedule = create_schedule(
        actor,
        name="Recovery schedule",
        cron_expression="*/5 * * * *",
        timezone_name="UTC",
        target_ref="issue:recovery",
        objective="Recover through the Plane run lifecycle.",
        starts_at=start,
    )
    fire = fire_schedule(schedule, scheduled_for=schedule.next_fire_at, created_by=create_user)
    replay = fire_schedule(schedule, scheduled_for=schedule.next_fire_at, created_by=create_user)
    assignment = fire.assignment
    assert replay.id == fire.id
    assert assignment is not None
    assert AgentScheduleFire.objects.filter(schedule=schedule).count() == 1
    assert AssignmentContract.objects.filter(assignee=actor).count() == 1

    run = create_run(
        assignment,
        profile,
        idempotency_key="idempotency:schedule-recovery-run",
        created_by=create_user,
    )
    invocation = record_invocation(run, idempotency_key="idempotency:schedule-recovery-invocation")
    unknown = transition_run(run, RunState.OUTCOME_UNKNOWN)

    with pytest.raises(RecoveryIntentRequiredError):
        create_run(assignment, profile)
    with pytest.raises(RecoveryIntentRequiredError):
        create_run(assignment, profile, recovery_of=unknown)

    recovered = create_run(
        assignment,
        profile,
        recovery_of=unknown,
        recovery_intent=RecoveryIntent.RECONCILE,
        idempotency_key="idempotency:schedule-reconciled-run",
        created_by=create_user,
    )
    assert recovered.id != run.id
    assert recovered.recovery_of_id == unknown.id
    assert recovered.lineage_of_id == unknown.id
    with pytest.raises(InvalidTransitionError):
        record_invocation(unknown, idempotency_key="idempotency:schedule-blind-replay")
    assert invocation.run_id == run.id
    assert AssignmentContract.objects.filter(assignee=actor).count() == 1
    assert AgentScheduleFire.objects.filter(schedule=schedule).count() == 1
