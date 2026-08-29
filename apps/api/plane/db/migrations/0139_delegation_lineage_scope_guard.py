from django.db import migrations


FORWARD_SQL = r"""
CREATE OR REPLACE FUNCTION agent_guard_scope() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    referenced_workspace uuid;
    referenced_project uuid;
    referenced_actor uuid;
    referenced_assignment uuid;
    referenced_run uuid;
BEGIN
    IF NEW.project_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM projects p WHERE p.id = NEW.project_id AND p.workspace_id = NEW.workspace_id
    ) THEN
        RAISE EXCEPTION 'Agent record project is outside its workspace' USING ERRCODE = 'check_violation';
    END IF;

    IF TG_TABLE_NAME = 'agent_profile_versions' THEN
        SELECT workspace_id, project_id INTO referenced_workspace, referenced_project
        FROM agent_actors WHERE id = NEW.actor_id;
        IF (referenced_workspace, referenced_project) IS DISTINCT FROM (NEW.workspace_id, NEW.project_id) THEN
            RAISE EXCEPTION 'Profile version must use its actor scope' USING ERRCODE = 'check_violation';
        END IF;
    ELSIF TG_TABLE_NAME = 'agent_assignment_contracts' THEN
        SELECT workspace_id, project_id INTO referenced_workspace, referenced_project
        FROM agent_actors WHERE id = NEW.assignee_id;
        IF referenced_workspace IS DISTINCT FROM NEW.workspace_id OR
           (referenced_project IS NOT NULL AND referenced_project IS DISTINCT FROM NEW.project_id) THEN
            RAISE EXCEPTION 'Assignment must use its assignee scope' USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.lineage_of_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM agent_assignment_contracts a
            WHERE a.id = NEW.lineage_of_id AND a.workspace_id = NEW.workspace_id
              AND a.project_id IS NOT DISTINCT FROM NEW.project_id
        ) THEN
            RAISE EXCEPTION 'Assignment lineage must remain in the same Plane scope' USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.root_assignment_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM agent_assignment_contracts a
            WHERE a.id = NEW.root_assignment_id AND a.workspace_id = NEW.workspace_id
              AND a.project_id IS NOT DISTINCT FROM NEW.project_id
        ) THEN
            RAISE EXCEPTION 'Assignment root lineage must remain in the same Plane scope'
                USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.delegated_by_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM agent_actors a
            WHERE a.id = NEW.delegated_by_id AND a.workspace_id = NEW.workspace_id
              AND (a.project_id IS NULL OR a.project_id IS NOT DISTINCT FROM NEW.project_id)
        ) THEN
            RAISE EXCEPTION 'Assignment delegator is outside the assignment scope'
                USING ERRCODE = 'check_violation';
        END IF;
    ELSIF TG_TABLE_NAME = 'agent_run_attempts' THEN
        SELECT workspace_id, project_id, assignee_id INTO referenced_workspace, referenced_project, referenced_actor
        FROM agent_assignment_contracts WHERE id = NEW.assignment_id;
        IF (referenced_workspace, referenced_project) IS DISTINCT FROM (NEW.workspace_id, NEW.project_id)
           OR referenced_actor IS DISTINCT FROM NEW.actor_id THEN
            RAISE EXCEPTION 'Run must use its assignment scope and assignee' USING ERRCODE = 'check_violation';
        END IF;
        SELECT workspace_id, project_id, actor_id INTO referenced_workspace, referenced_project, referenced_actor
        FROM agent_profile_versions WHERE id = NEW.profile_version_id;
        IF (referenced_workspace, referenced_project) IS DISTINCT FROM (NEW.workspace_id, NEW.project_id)
           OR referenced_actor IS DISTINCT FROM NEW.actor_id THEN
            RAISE EXCEPTION 'Run must use its actor profile scope' USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.lineage_of_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM agent_run_attempts r
            WHERE r.id = NEW.lineage_of_id AND r.assignment_id = NEW.assignment_id
              AND r.workspace_id = NEW.workspace_id AND r.project_id IS NOT DISTINCT FROM NEW.project_id
        ) THEN
            RAISE EXCEPTION 'Run lineage must remain on the same assignment and scope'
                USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.recovery_of_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM agent_run_attempts r
            WHERE r.id = NEW.recovery_of_id AND r.assignment_id = NEW.assignment_id
              AND r.workspace_id = NEW.workspace_id AND r.project_id IS NOT DISTINCT FROM NEW.project_id
              AND r.state = 'outcome_unknown'
        ) THEN
            RAISE EXCEPTION 'Run recovery must name an outcome-unknown run on the same assignment'
                USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.recovery_intent IS NOT NULL AND NEW.recovery_of_id IS NULL THEN
            RAISE EXCEPTION 'Run recovery intent requires a recovery source' USING ERRCODE = 'check_violation';
        END IF;
    ELSIF TG_TABLE_NAME IN ('agent_run_input_events', 'agent_runtime_invocations', 'agent_outcome_submissions') THEN
        IF TG_TABLE_NAME = 'agent_run_input_events' OR TG_TABLE_NAME = 'agent_runtime_invocations' THEN
            referenced_run := NEW.run_id;
        ELSE
            referenced_run := NEW.run_id;
        END IF;
        SELECT workspace_id, project_id INTO referenced_workspace, referenced_project
        FROM agent_run_attempts WHERE id = referenced_run;
        IF (referenced_workspace, referenced_project) IS DISTINCT FROM (NEW.workspace_id, NEW.project_id) THEN
            RAISE EXCEPTION 'Agent child record must use its run scope' USING ERRCODE = 'check_violation';
        END IF;
        IF TG_TABLE_NAME = 'agent_outcome_submissions' THEN
            IF NEW.evaluator_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM agent_actors a
                WHERE a.id = NEW.evaluator_id AND a.workspace_id = NEW.workspace_id
                  AND (a.project_id IS NULL OR a.project_id IS NOT DISTINCT FROM NEW.project_id)
            ) THEN
                RAISE EXCEPTION 'Outcome evaluator is outside the outcome scope' USING ERRCODE = 'check_violation';
            END IF;
        END IF;
    ELSIF TG_TABLE_NAME = 'agent_run_terminal_events' THEN
        SELECT workspace_id, project_id, run_id INTO referenced_workspace, referenced_project, referenced_run
        FROM agent_runtime_invocations WHERE id = NEW.invocation_id;
        IF referenced_run IS DISTINCT FROM NEW.run_id
           OR (referenced_workspace, referenced_project) IS DISTINCT FROM (NEW.workspace_id, NEW.project_id)
           OR NOT EXISTS (
               SELECT 1 FROM agent_run_attempts r
               WHERE r.id = NEW.run_id
                 AND (r.workspace_id, r.project_id) IS NOT DISTINCT FROM (NEW.workspace_id, NEW.project_id)
           ) THEN
            RAISE EXCEPTION 'Terminal event must bind one invocation and its run scope'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
"""


REVERSE_SQL = r"""
CREATE OR REPLACE FUNCTION agent_guard_scope() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    referenced_workspace uuid;
    referenced_project uuid;
    referenced_actor uuid;
    referenced_assignment uuid;
    referenced_run uuid;
BEGIN
    IF NEW.project_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM projects p WHERE p.id = NEW.project_id AND p.workspace_id = NEW.workspace_id
    ) THEN
        RAISE EXCEPTION 'Agent record project is outside its workspace' USING ERRCODE = 'check_violation';
    END IF;

    IF TG_TABLE_NAME = 'agent_profile_versions' THEN
        SELECT workspace_id, project_id INTO referenced_workspace, referenced_project
        FROM agent_actors WHERE id = NEW.actor_id;
        IF (referenced_workspace, referenced_project) IS DISTINCT FROM (NEW.workspace_id, NEW.project_id) THEN
            RAISE EXCEPTION 'Profile version must use its actor scope' USING ERRCODE = 'check_violation';
        END IF;
    ELSIF TG_TABLE_NAME = 'agent_assignment_contracts' THEN
        SELECT workspace_id, project_id INTO referenced_workspace, referenced_project
        FROM agent_actors WHERE id = NEW.assignee_id;
        IF referenced_workspace IS DISTINCT FROM NEW.workspace_id OR
           (referenced_project IS NOT NULL AND referenced_project IS DISTINCT FROM NEW.project_id) THEN
            RAISE EXCEPTION 'Assignment must use its assignee scope' USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.lineage_of_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM agent_assignment_contracts a
            WHERE a.id = NEW.lineage_of_id AND a.workspace_id = NEW.workspace_id
              AND a.project_id IS NOT DISTINCT FROM NEW.project_id AND a.assignee_id = NEW.assignee_id
        ) THEN
            RAISE EXCEPTION 'Assignment lineage must use the same actor and scope' USING ERRCODE = 'check_violation';
        END IF;
    ELSIF TG_TABLE_NAME = 'agent_run_attempts' THEN
        SELECT workspace_id, project_id, assignee_id INTO referenced_workspace, referenced_project, referenced_actor
        FROM agent_assignment_contracts WHERE id = NEW.assignment_id;
        IF (referenced_workspace, referenced_project) IS DISTINCT FROM (NEW.workspace_id, NEW.project_id)
           OR referenced_actor IS DISTINCT FROM NEW.actor_id THEN
            RAISE EXCEPTION 'Run must use its assignment scope and assignee' USING ERRCODE = 'check_violation';
        END IF;
        SELECT workspace_id, project_id, actor_id INTO referenced_workspace, referenced_project, referenced_actor
        FROM agent_profile_versions WHERE id = NEW.profile_version_id;
        IF (referenced_workspace, referenced_project) IS DISTINCT FROM (NEW.workspace_id, NEW.project_id)
           OR referenced_actor IS DISTINCT FROM NEW.actor_id THEN
            RAISE EXCEPTION 'Run must use its actor profile scope' USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.lineage_of_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM agent_run_attempts r
            WHERE r.id = NEW.lineage_of_id AND r.assignment_id = NEW.assignment_id
              AND r.workspace_id = NEW.workspace_id AND r.project_id IS NOT DISTINCT FROM NEW.project_id
        ) THEN
            RAISE EXCEPTION 'Run lineage must remain on the same assignment and scope'
                USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.recovery_of_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM agent_run_attempts r
            WHERE r.id = NEW.recovery_of_id AND r.assignment_id = NEW.assignment_id
              AND r.workspace_id = NEW.workspace_id AND r.project_id IS NOT DISTINCT FROM NEW.project_id
              AND r.state = 'outcome_unknown'
        ) THEN
            RAISE EXCEPTION 'Run recovery must name an outcome-unknown run on the same assignment'
                USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.recovery_intent IS NOT NULL AND NEW.recovery_of_id IS NULL THEN
            RAISE EXCEPTION 'Run recovery intent requires a recovery source' USING ERRCODE = 'check_violation';
        END IF;
    ELSIF TG_TABLE_NAME IN ('agent_run_input_events', 'agent_runtime_invocations', 'agent_outcome_submissions') THEN
        IF TG_TABLE_NAME = 'agent_run_input_events' OR TG_TABLE_NAME = 'agent_runtime_invocations' THEN
            referenced_run := NEW.run_id;
        ELSE
            referenced_run := NEW.run_id;
        END IF;
        SELECT workspace_id, project_id INTO referenced_workspace, referenced_project
        FROM agent_run_attempts WHERE id = referenced_run;
        IF (referenced_workspace, referenced_project) IS DISTINCT FROM (NEW.workspace_id, NEW.project_id) THEN
            RAISE EXCEPTION 'Agent child record must use its run scope' USING ERRCODE = 'check_violation';
        END IF;
        IF TG_TABLE_NAME = 'agent_outcome_submissions' THEN
            IF NEW.evaluator_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM agent_actors a
                WHERE a.id = NEW.evaluator_id AND a.workspace_id = NEW.workspace_id
                  AND (a.project_id IS NULL OR a.project_id IS NOT DISTINCT FROM NEW.project_id)
            ) THEN
                RAISE EXCEPTION 'Outcome evaluator is outside the outcome scope' USING ERRCODE = 'check_violation';
            END IF;
        END IF;
    ELSIF TG_TABLE_NAME = 'agent_run_terminal_events' THEN
        SELECT workspace_id, project_id, run_id INTO referenced_workspace, referenced_project, referenced_run
        FROM agent_runtime_invocations WHERE id = NEW.invocation_id;
        IF referenced_run IS DISTINCT FROM NEW.run_id
           OR (referenced_workspace, referenced_project) IS DISTINCT FROM (NEW.workspace_id, NEW.project_id)
           OR NOT EXISTS (
               SELECT 1 FROM agent_run_attempts r
               WHERE r.id = NEW.run_id
                 AND (r.workspace_id, r.project_id) IS NOT DISTINCT FROM (NEW.workspace_id, NEW.project_id)
           ) THEN
            RAISE EXCEPTION 'Terminal event must bind one invocation and its run scope'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("db", "0138_agentactor_chief_of_staff_for_and_more"),
    ]

    operations = [
        migrations.RunSQL(FORWARD_SQL, REVERSE_SQL),
    ]
