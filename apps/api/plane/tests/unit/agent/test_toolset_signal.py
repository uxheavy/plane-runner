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
