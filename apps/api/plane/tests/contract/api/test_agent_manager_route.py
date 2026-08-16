from __future__ import annotations

import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest

from plane.agent.lifecycle import create_actor, create_profile
from plane.db.models import AgentRole


_ROUTE_PATH = Path(__file__).resolve().parents[6] / "tools" / "agent_g4_manager_route.py"
_ROUTE_SPEC = importlib.util.spec_from_file_location("agent_g4_manager_route", _ROUTE_PATH)
assert _ROUTE_SPEC is not None and _ROUTE_SPEC.loader is not None
_ROUTE = importlib.util.module_from_spec(_ROUTE_SPEC)
_ROUTE_SPEC.loader.exec_module(_ROUTE)


@pytest.mark.django_db(transaction=True)
def test_manager_route_uses_persisted_worker_profile_for_every_run(workspace, gateway_project, create_user):
    manager = create_actor(
        workspace=workspace,
        project=gateway_project,
        display_name="Manager route delegator",
        created_by=create_user,
    )
    create_profile(
        manager,
        role=AgentRole.DELEGATOR,
        instructions="Coordinate bounded synthetic work.",
        created_by=create_user,
    )
    worker = create_actor(
        workspace=workspace,
        project=gateway_project,
        display_name="Manager route worker",
        created_by=create_user,
    )
    create_profile(
        worker,
        role=AgentRole.WORKER,
        instructions="Complete bounded work.",
        created_by=create_user,
    )
    evaluator = create_actor(
        workspace=workspace,
        project=gateway_project,
        display_name="Manager route evaluator",
        created_by=create_user,
    )
    create_profile(
        evaluator,
        role=AgentRole.EVALUATOR,
        instructions="Review bounded outcomes.",
        created_by=create_user,
    )
    hr = create_actor(
        workspace=workspace,
        display_name="Manager route HR",
        created_by=create_user,
    )
    create_profile(
        hr,
        role=AgentRole.HR,
        instructions="Propose bounded governance changes.",
        created_by=create_user,
    )

    evidence, failures = _ROUTE.build_manager_route_evidence(
        workspace=workspace,
        project=gateway_project,
        manager=manager,
        worker=worker,
        evaluator=evaluator,
        hr=hr,
        human_admin=create_user,
        suffix=uuid4().hex[:8],
    )

    assert failures == [], (
        "event=agent.manager.route actor=delegator operation=exercise_manager_journey "
        f"expected=M01-M08 provider-free route evidence actual={failures} "
        "risk=manager-readiness false negative suggestion=inspect the shared route fixture and lifecycle profile binding"
    )
    assert all(
        value is True
        for route_id, route in evidence["routes"].items()
        if route_id != "replay"
        for value in route.values()
    )
    assert evidence["routes"]["replay"] == {"stateMutations": 0}
