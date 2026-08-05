from uuid import uuid4

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


MIGRATION_0131 = ("db", "0131_agentmemoryentry_agentmemoryrevision_agentschedule_and_more")
MIGRATION_0132 = ("db", "0132_governed_context_scope_and_rollback_guards")


@pytest.fixture
def migration_context(django_db_setup, django_db_blocker):
    """Provide an actual migration-backed PostgreSQL database without pytest flush."""

    del django_db_setup
    with django_db_blocker.unblock():
        applied = MigrationExecutor(connection).recorder.applied_migrations()
        if MIGRATION_0132 not in applied:
            pytest.skip("requires a migration-backed database at migration 0132")
        context = {}
        try:
            yield context
        finally:
            if context.get("workspace_id"):
                _cleanup_seed(context["workspace_id"])
            _migrate(MIGRATION_0132)


def _migrate(target):
    try:
        MigrationExecutor(connection).migrate([target])
    finally:
        connection.close()


def _historical_apps(target):
    return MigrationExecutor(connection).loader.project_state([target]).apps


def _seed_bundle(target, *, include_unsupported=False):
    apps = _historical_apps(target)
    User = apps.get_model("db", "User")
    Workspace = apps.get_model("db", "Workspace")
    Project = apps.get_model("db", "Project")
    AgentActor = apps.get_model("db", "AgentActor")
    Skill = apps.get_model("db", "AgentSkillDefinition")
    Revision = apps.get_model("db", "AgentSkillRevision")
    Proposal = apps.get_model("db", "AgentChangeProposal")

    suffix = uuid4().hex[:12]
    user = User.objects.create(
        username=f"migration-{suffix}",
        email=f"migration-{suffix}@example.com",
    )
    workspace = Workspace.objects.create(
        name=f"Migration Workspace {suffix}",
        slug=f"migration-{suffix}",
        owner=user,
    )
    project = Project.objects.create(
        name=f"Migration Project {suffix}",
        identifier=f"M{suffix[:5]}".upper(),
        workspace=workspace,
    )
    actor = AgentActor.objects.create(
        workspace=workspace,
        project=project,
        display_name=f"Migration Agent {suffix}",
    )

    def create_skill(key, visibility, *, subject_user=None, proposal_visibility=None):
        skill_kwargs = {
            "workspace": workspace,
            "project": project,
            "actor": actor,
            "key": key,
            "display_name": key,
            "description": "",
            "visibility": visibility,
            "subject_user": subject_user,
            "retention_expires_at": None,
            "deletion_reason": "",
            "deleted_by": None,
            "created_by": user,
            "updated_by": None,
        }
        if target == MIGRATION_0132 and visibility == "workspace":
            skill_kwargs["shared_scope_id"] = workspace.pk
        skill = Skill.objects.create(**skill_kwargs)
        revision = Revision.objects.create(
            workspace=workspace,
            project=project,
            definition=skill,
            revision=1,
            predecessor=None,
            state="candidate" if proposal_visibility else "active",
            package_files={"SKILL.md": f"# {key}"},
            package_digest="skill:" + "0" * 64,
            provenance="gardener" if proposal_visibility else "human",
            provenance_ref=f"migration:{suffix}:{key}",
            source_actor=None,
            source_run=None,
            rationale="migration seed",
            created_by=user,
            updated_by=None,
        )
        proposal = None
        if proposal_visibility:
            proposal_kwargs = {
                "workspace": workspace,
                "project": project,
                "kind": "skill",
                "actor": actor,
                "skill_revision": revision,
                "memory_revision": None,
                "state": "proposed",
                "rationale": f"Proposal for {key}",
                "requested_visibility": proposal_visibility,
                "proposed_by": actor,
                "reviewed_by": None,
                "reviewed_at": None,
                "review_note": "",
                "applied_revision_ref": "",
                "idempotency_key": None,
                "command_fingerprint": None,
                "created_by": user,
                "updated_by": None,
            }
            if target == MIGRATION_0132 and proposal_visibility == "workspace":
                proposal_kwargs["requested_scope_id"] = workspace.pk
            proposal = Proposal.objects.create(**proposal_kwargs)
        return skill, revision, proposal

    workspace_skill, _, workspace_proposal = create_skill(
        "workspace-skill", "workspace", proposal_visibility="workspace"
    )
    private_skill, _, private_proposal = create_skill(
        "private-skill", "agent_private", proposal_visibility="agent_private"
    )
    subject_skill, _, subject_proposal = create_skill(
        "subject-skill", "subject_user", subject_user=user, proposal_visibility="subject_user"
    )
    unsupported = []
    if include_unsupported:
        for visibility in ("template", "organization"):
            unsupported.append(
                create_skill(
                    f"{visibility}-skill",
                    visibility,
                    proposal_visibility=visibility,
                )
            )

    return {
        "apps": apps,
        "workspace_id": workspace.pk,
        "workspace_skill_id": workspace_skill.pk,
        "workspace_proposal_id": workspace_proposal.pk,
        "private_skill_id": private_skill.pk,
        "private_proposal_id": private_proposal.pk,
        "subject_skill_id": subject_skill.pk,
        "subject_proposal_id": subject_proposal.pk,
        "unsupported": unsupported,
    }


def _scope_snapshot(target, workspace_id):
    apps = _historical_apps(target)
    Skill = apps.get_model("db", "AgentSkillDefinition")
    Proposal = apps.get_model("db", "AgentChangeProposal")
    skills = tuple(
        Skill.objects.filter(workspace_id=workspace_id)
        .order_by("key")
        .values_list("key", "visibility", "subject_user_id", *(["shared_scope_id"] if target == MIGRATION_0132 else []))
    )
    proposals = tuple(
        Proposal.objects.filter(workspace_id=workspace_id)
        .order_by("rationale")
        .values_list(
            "rationale",
            "requested_visibility",
            *(["requested_scope_id"] if target == MIGRATION_0132 else []),
        )
    )
    return skills, proposals


def _cleanup_seed(workspace_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT owner_id FROM workspaces WHERE id = %s", [workspace_id])
        owner = cursor.fetchone()
        cursor.execute("DELETE FROM agent_change_proposals WHERE workspace_id = %s", [workspace_id])
        cursor.execute("ALTER TABLE agent_skill_revisions DISABLE TRIGGER ALL")
        try:
            cursor.execute("DELETE FROM agent_skill_revisions WHERE workspace_id = %s", [workspace_id])
        finally:
            cursor.execute("ALTER TABLE agent_skill_revisions ENABLE TRIGGER ALL")
        cursor.execute("DELETE FROM agent_skill_definitions WHERE workspace_id = %s", [workspace_id])
        cursor.execute("DELETE FROM agent_actors WHERE workspace_id = %s", [workspace_id])
        cursor.execute("DELETE FROM projects WHERE workspace_id = %s", [workspace_id])
        cursor.execute("DELETE FROM workspaces WHERE id = %s", [workspace_id])
        if owner:
            cursor.execute("DELETE FROM users WHERE id = %s", [owner[0]])


def _catalog_names():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT conname FROM pg_constraint WHERE conrelid = 'agent_skill_definitions'::regclass ORDER BY conname"
        )
        constraints = tuple(row[0] for row in cursor.fetchall())
        cursor.execute(
            "SELECT indexname FROM pg_indexes "
            "WHERE tablename IN ('agent_skill_definitions', 'agent_memory_revisions', 'agent_skill_revisions') "
            "AND indexname IN ('agent_skill_unique_shared_key', 'agent_memory_revision_unique_rollback_target', "
            "'agent_skill_revision_unique_rollback_target') ORDER BY indexname"
        )
        indexes = tuple(row[0] for row in cursor.fetchall())
        cursor.execute(
            "SELECT tgname FROM pg_trigger "
            "WHERE tgrelid IN ('agent_memory_revisions'::regclass, 'agent_skill_revisions'::regclass) "
            "AND NOT tgisinternal ORDER BY tgname"
        )
        triggers = tuple(row[0] for row in cursor.fetchall())
    return constraints, indexes, triggers


def test_0131_workspace_rows_backfill_before_new_constraints(migration_context):
    context = migration_context
    _migrate(MIGRATION_0131)
    context.update(_seed_bundle(MIGRATION_0131))
    before = _scope_snapshot(MIGRATION_0131, context["workspace_id"])

    _migrate(MIGRATION_0132)

    after = _scope_snapshot(MIGRATION_0132, context["workspace_id"])
    assert any(row[0] == "workspace-skill" and row[3] == context["workspace_id"] for row in after[0])
    assert any(row[1] == "workspace" and row[2] == context["workspace_id"] for row in after[1])
    assert any(row[0] == "private-skill" and row[3] is None for row in after[0])
    assert any(row[0] == "subject-skill" and row[3] is None for row in after[0])
    assert any(row[0] == "private-skill" and row[1] == "agent_private" for row in before[0])


def test_0132_round_trip_reconstructs_supported_scopes_and_keeps_private_subject(migration_context):
    context = migration_context
    context.update(_seed_bundle(MIGRATION_0132))
    before = _scope_snapshot(MIGRATION_0132, context["workspace_id"])
    catalog_before = _catalog_names()

    _migrate(MIGRATION_0131)
    _migrate(MIGRATION_0132)

    assert _scope_snapshot(MIGRATION_0132, context["workspace_id"]) == before
    assert _catalog_names() == catalog_before


def test_0132_preflight_rejects_mixed_unsupported_rows_without_mutation_and_retries(
    migration_context,
):
    context = migration_context
    _migrate(MIGRATION_0131)
    context.update(_seed_bundle(MIGRATION_0131, include_unsupported=True))
    before = _scope_snapshot(MIGRATION_0131, context["workspace_id"])

    with pytest.raises(RuntimeError, match="unsupported template/organization"):
        _migrate(MIGRATION_0132)

    assert MIGRATION_0132 not in MigrationExecutor(connection).recorder.applied_migrations()
    assert _scope_snapshot(MIGRATION_0131, context["workspace_id"]) == before
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid = 'agent_skill_definitions'::regclass "
            "AND conname = 'agent_skill_visibility_subject_binding'"
        )
        assert cursor.fetchone() is not None
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'agent_skill_definitions' AND column_name = 'shared_scope_id'"
        )
        assert cursor.fetchone() is None

    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE agent_skill_definitions SET visibility = 'agent_private' "
            "WHERE workspace_id = %s AND visibility IN ('template', 'organization')",
            [context["workspace_id"]],
        )
        cursor.execute(
            "UPDATE agent_change_proposals SET requested_visibility = 'agent_private' "
            "WHERE workspace_id = %s AND requested_visibility IN ('template', 'organization')",
            [context["workspace_id"]],
        )

    _migrate(MIGRATION_0132)
    skills, proposals = _scope_snapshot(MIGRATION_0132, context["workspace_id"])
    assert any(row[0] == "workspace-skill" and row[3] == context["workspace_id"] for row in skills)
    assert all(row[3] is None for row in skills if row[1] != "workspace")
    assert all(row[2] is None for row in proposals if row[1] != "workspace")


def test_0132_preserves_revision_guards_and_scope_catalog(migration_context):
    context = migration_context
    _migrate(MIGRATION_0131)
    context.update(_seed_bundle(MIGRATION_0131))
    _migrate(MIGRATION_0132)
    constraints, indexes, triggers = _catalog_names()

    assert "agent_skill_visibility_scope_binding" in constraints
    assert "agent_skill_visibility_subject_binding" not in constraints
    assert indexes == (
        "agent_memory_revision_unique_rollback_target",
        "agent_skill_revision_unique_rollback_target",
        "agent_skill_unique_shared_key",
    )
    assert triggers == (
        "agent_memory_revision_immutable",
        "agent_memory_revision_immutable_truncate",
        "agent_skill_revision_immutable",
        "agent_skill_revision_immutable_truncate",
    )
