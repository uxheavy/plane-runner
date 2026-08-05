# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Convergent, credential-free Agent administration fixture command."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from plane.agent.administration import ensure_fixture_profile, update_actor, validate_credential_ref
from plane.db.models import AgentActor, AgentRole, Project, Workspace


class Command(BaseCommand):
    help = "Create or converge one Plane Agent actor and immutable profile fixture."

    def add_arguments(self, parser):
        parser.add_argument("--workspace-slug", required=True)
        parser.add_argument("--display-name")
        parser.add_argument("--role", choices=[role.value for role in AgentRole], default=None)
        parser.add_argument("--instructions")
        parser.add_argument("--persona", default=None)
        parser.add_argument("--expected-outcome", action="append", dest="expected_outcomes")
        parser.add_argument("--project-id")
        parser.add_argument("--credential-ref")
        parser.add_argument("--fixture", type=Path, help="Path to a JSON fixture; CLI values override fixture values.")

    def handle(self, *args, **options):
        payload = self._fixture_payload(options.get("fixture"))
        for name in (
            "display_name",
            "role",
            "instructions",
            "persona",
            "expected_outcomes",
            "project_id",
            "credential_ref",
        ):
            if options.get(name) is not None:
                payload[name] = options[name]

        display_name = payload.get("display_name")
        instructions = payload.get("instructions")
        if not display_name or not instructions:
            raise CommandError("display_name and instructions are required, directly or in --fixture")

        workspace = Workspace.objects.filter(slug=options["workspace_slug"]).first()
        if workspace is None:
            raise CommandError(f'Workspace "{options["workspace_slug"]}" does not exist')
        project = self._project(workspace, payload.get("project_id"))
        try:
            credential_ref = validate_credential_ref(payload.get("credential_ref"))
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        with transaction.atomic():
            actor, _ = AgentActor.objects.get_or_create(
                workspace=workspace,
                display_name=display_name,
                defaults={
                    "project": project,
                    "credential_ref": credential_ref,
                },
            )
            actor = AgentActor.objects.select_for_update().get(pk=actor.pk)
            if actor.project_id != getattr(project, "id", None):
                raise CommandError("Existing Agent actor has a different project scope")
            if credential_ref is not None and actor.credential_ref != credential_ref:
                actor = update_actor(actor, credential_ref=credential_ref)

            profile_data = {
                "role": payload.get("role") or AgentRole.WORKER,
                "instructions": instructions,
                "display_name": payload.get("profile_display_name") or display_name,
                "persona": payload.get("persona") or "",
                "expected_outcomes": payload.get("expected_outcomes") or [],
                "model_defaults": payload.get("model_defaults") or {},
                "runtime_defaults": payload.get("runtime_defaults") or {},
                "context_refs": payload.get("context_refs") or [],
                "tool_presentation": payload.get("tool_presentation") or {},
                "memory_scopes": payload.get("memory_scopes") or [],
            }
            profile = ensure_fixture_profile(actor, **profile_data)

        self.stdout.write(
            json.dumps(
                {
                    "actor_id": str(actor.id),
                    "profile_id": str(profile.id),
                    "profile_version": profile.version,
                    "credential_configured": bool(actor.credential_ref),
                },
                sort_keys=True,
            )
        )

    @staticmethod
    def _fixture_payload(path):
        if path is None:
            return {}
        try:
            payload = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            raise CommandError(f"Could not read Agent fixture: {path}") from exc
        if not isinstance(payload, dict):
            raise CommandError("Agent fixture must contain one JSON object")
        return payload

    @staticmethod
    def _project(workspace, project_id):
        if project_id is None:
            return None
        try:
            project_uuid = UUID(str(project_id))
        except ValueError as exc:
            raise CommandError("project_id must be a UUID") from exc
        project = Project.objects.filter(pk=project_uuid, workspace=workspace).first()
        if project is None:
            raise CommandError("project_id does not identify a project in the workspace")
        return project
