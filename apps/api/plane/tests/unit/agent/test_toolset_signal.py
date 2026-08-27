# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from types import SimpleNamespace

import pytest

from plane.agent.tools.disclosure import compose_tool_catalog


def _profile(**presentation):
    return SimpleNamespace(role="worker", tool_presentation=presentation)


def _assignment():
    return SimpleNamespace(target_ref="target:issue-1", objective="Rename the assigned work item")


def test_model_toolset_is_typed_presentation_only_and_bounded():
    standard = compose_tool_catalog(_profile(model_toolset="standard"), _assignment())
    code_mode = compose_tool_catalog(_profile(model_toolset="code_mode_only"), _assignment())

    assert standard["modelToolset"] == "standard"
    assert code_mode["modelToolset"] == "code_mode_only"
    assert "operation:work_item.rename" not in [entry["operationRef"] for entry in code_mode["eagerOperations"]]
    with pytest.raises(ValueError, match="model_toolset"):
        compose_tool_catalog(_profile(model_toolset="native_mutation"), _assignment())


def test_standard_route_is_plane_owned_and_bounded():
    route = {
        "schemaVersion": "plane.standard-route/v1",
        "steps": [{"operationRef": "operation:search_workspace"}],
    }
    catalog = compose_tool_catalog(_profile(model_toolset="standard", standard_route=route), _assignment())
    assert catalog["standardRoute"]["schemaVersion"] == "plane.standard-route/v1"
    assert catalog["standardRoute"]["steps"] == route["steps"]

    with pytest.raises(ValueError, match="standardRoute"):
        compose_tool_catalog(
            _profile(standard_route={"schemaVersion": "plane.standard-route/v1", "steps": []}),
            _assignment(),
        )
    with pytest.raises(ValueError, match="standardRoute"):
        compose_tool_catalog(
            _profile(
                standard_route={
                    "schemaVersion": "plane.standard-route/v1",
                    "steps": [{"operationRef": "operation:search_workspace"}] * 8,
                }
            ),
            _assignment(),
        )
    with pytest.raises(ValueError, match="standardRoute"):
        compose_tool_catalog(
            _profile(
                standard_route={
                    "schemaVersion": "plane.standard-route/v1",
                    "steps": [{"operationRef": "operation:search_workspace", "unexpected": True}],
                }
            ),
            _assignment(),
        )
    with pytest.raises(ValueError, match="disclosed"):
        compose_tool_catalog(
            _profile(
                standard_route={
                    "schemaVersion": "plane.standard-route/v1",
                    "steps": [{"operationRef": "operation:agent.context.read"}],
                }
            ),
            _assignment(),
        )
    with pytest.raises(ValueError, match="prepared work_item.read"):
        compose_tool_catalog(
            _profile(
                standard_route={
                    "schemaVersion": "plane.standard-route/v1",
                    "steps": [{"operationRef": "operation:search_workspace", "optional": True}],
                }
            ),
            _assignment(),
        )
    with pytest.raises(ValueError, match="standard model toolset"):
        compose_tool_catalog(_profile(model_toolset="code_mode_only", standard_route=route), _assignment())
