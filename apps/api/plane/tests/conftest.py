# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest
from django.core.management import call_command
from django.db import connection, connections
from django.test.testcases import TransactionTestCase
from rest_framework.test import APIClient
from pytest_django.fixtures import django_db_setup

from plane.db.models import (
    Issue,
    Project,
    ProjectMember,
    State,
    User,
    Workspace,
    WorkspaceMember,
)
from plane.db.models.api import APIToken


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup):  # noqa: F811
    """Set up the Django database for the test session"""
    pass


@pytest.fixture(scope="session", autouse=True)
def clear_migration_metadata_before_django_flush(django_db_setup):
    """Clear the reverse-migration metadata table before Django flushes fixtures.

    Migration 0135 keeps this unmanaged table at the head so a reverse can
    restore legacy input sequences. Django's flush planner cannot see it, so
    PostgreSQL rejects the parent-table TRUNCATE while the metadata rows still
    reference ``agent_run_input_events``. This is test isolation only; the
    migration-owned immutability and audit triggers remain intact during tests.
    """

    original_fixture_teardown = TransactionTestCase._fixture_teardown

    def fixture_teardown(test_case):
        if "agent_run_input_sequence_legacy_metadata" not in connection.introspection.table_names():
            return original_fixture_teardown(test_case)
        with connection.cursor() as cursor:
            # The migrated test schema intentionally keeps append-only
            # truncate guards. Disable triggers only for fixture cleanup after
            # assertions have completed; production and test-body assertions
            # still exercise the guards unchanged.
            cursor.execute("SET session_replication_role = replica")
        try:
            for db_name in test_case._databases_names(include_mirrors=False):
                inhibit_post_migrate = (
                    test_case.available_apps is not None
                    or (
                        test_case.serialized_rollback
                        and hasattr(connections[db_name], "_test_serialized_contents")
                    )
                )
                call_command(
                    "flush",
                    verbosity=0,
                    interactive=False,
                    database=db_name,
                    reset_sequences=False,
                    allow_cascade=True,
                    inhibit_post_migrate=inhibit_post_migrate,
                )
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SET session_replication_role = origin")

    TransactionTestCase._fixture_teardown = fixture_teardown
    try:
        yield
    finally:
        TransactionTestCase._fixture_teardown = original_fixture_teardown


@pytest.fixture
def api_client():
    """Return an unauthenticated API client"""
    return APIClient()


@pytest.fixture
def user_data():
    """Return standard user data for tests"""
    return {
        "email": "test@plane.so",
        "password": "test-password",
        "first_name": "Test",
        "last_name": "User",
    }


@pytest.fixture
def create_user(db, user_data):
    """Create and return a user instance"""
    user = User.objects.create(
        email=user_data["email"],
        username=user_data["email"],
        first_name=user_data["first_name"],
        last_name=user_data["last_name"],
    )
    user.set_password(user_data["password"])
    user.save()
    return user


@pytest.fixture
def api_token(db, create_user):
    """Create and return an API token for testing the external API"""
    token = APIToken.objects.create(
        user=create_user,
        label="Test API Token",
        token="test-api-token-12345",
    )
    return token


@pytest.fixture
def api_key_client(api_client, api_token):
    """Return an API key authenticated client for external API testing"""
    api_client.credentials(HTTP_X_API_KEY=api_token.token)
    return api_client


@pytest.fixture
def session_client(api_client, create_user):
    """Return a session authenticated API client for app API testing, which is what plane.app uses"""
    api_client.force_authenticate(user=create_user)
    return api_client


@pytest.fixture
def create_bot_user(db):
    """Create and return a bot user instance"""
    from uuid import uuid4

    unique_id = uuid4().hex[:8]
    user = User.objects.create(
        email=f"bot-{unique_id}@plane.so",
        username=f"bot_user_{unique_id}",
        first_name="Bot",
        last_name="User",
        is_bot=True,
    )
    user.set_password("bot@123")
    user.save()
    return user


@pytest.fixture
def api_token_data():
    """Return sample API token data for testing"""
    from django.utils import timezone
    from datetime import timedelta

    return {
        "label": "Test API Token",
        "description": "Test description for API token",
        "expired_at": (timezone.now() + timedelta(days=30)).isoformat(),
    }


@pytest.fixture
def create_api_token_for_user(db, create_user):
    """Create and return an API token for a specific user"""
    return APIToken.objects.create(
        label="Test Token",
        description="Test token description",
        user=create_user,
        user_type=0,
    )


@pytest.fixture
def plane_server(live_server):
    """
    Renamed version of live_server fixture to avoid name clashes.
    Returns a live Django server for testing HTTP requests.
    """
    return live_server


@pytest.fixture
def workspace(create_user):
    """
    Create a new workspace and return the
    corresponding Workspace model instance.
    """
    # Create the workspace using the model
    created_workspace = Workspace.objects.create(
        name="Test Workspace",
        owner=create_user,
        slug="test-workspace",
    )

    WorkspaceMember.objects.create(workspace=created_workspace, member=create_user, role=20)

    return created_workspace


@pytest.fixture
def gateway_project(db, workspace, create_user):
    """Create the shared project fixture used by the agent gateway contracts."""
    project = Project.objects.create(
        name="Gateway Project",
        identifier="AGW",
        workspace=workspace,
        created_by=create_user,
    )
    ProjectMember.objects.create(project=project, member=create_user, role=20, is_active=True)
    State.objects.create(
        name="Backlog",
        color="#000000",
        group="backlog",
        default=True,
        project=project,
        workspace=workspace,
        created_by=create_user,
    )
    return project


@pytest.fixture
def gateway_issue(db, gateway_project, workspace, create_user):
    """Create the shared issue fixture used by the agent gateway contracts."""
    return Issue.objects.create(
        name="Gateway Issue",
        project=gateway_project,
        workspace=workspace,
        created_by=create_user,
    )
