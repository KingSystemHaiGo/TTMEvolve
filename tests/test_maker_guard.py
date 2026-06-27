from __future__ import annotations

import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent.maker_guard import (
    looks_like_local_side_effect,
    maker_first_action_guard,
    maker_guard_context_hint,
    maker_guard_observation,
    task_needs_maker_authority,
)


def _briefing(**overrides):
    data = {
        "connected": True,
        "authority": "maker_mcp",
        "selected_template": {"id": "maker_build_or_submit"},
        "suggested_tools": ["maker_build"],
        "recommended_first_action": "Use maker_build first.",
        "recommended_endpoint": "/mcp/tools",
    }
    data.update(overrides)
    return data


def _contract():
    return {
        "maker_mcp": {
            "top_tools": [
                {"name": "maker_query_project"},
                {"name": "maker_build"},
            ],
        },
    }


def test_task_needs_maker_authority_for_maker_terms_only():
    assert task_needs_maker_authority("build and preview Maker project") is True
    assert task_needs_maker_authority("构建游戏关卡") is True
    assert task_needs_maker_authority("read the local README") is False


def test_local_side_effect_detection_uses_tool_name_and_params():
    assert looks_like_local_side_effect("write_file", {"path": "main.lua"}) is True
    assert looks_like_local_side_effect("project_status", {"content": "x"}) is True
    assert looks_like_local_side_effect("project_status", {"path": "main.lua"}) is False


def test_maker_guard_skips_non_maker_tasks():
    guard = maker_first_action_guard(
        iteration=0,
        task="read the local README",
        briefing=_briefing(),
        runtime_contract=_contract(),
        tool_name="write_file",
        params={"content": "x"},
    )

    assert guard["decision"] == "skip"
    assert guard["reason"] == "Task does not require Maker authority before local actions."


def test_maker_guard_passes_disconnected_maker_for_local_diagnostics():
    guard = maker_first_action_guard(
        iteration=0,
        task="build Maker project",
        briefing=_briefing(connected=False, authority="local_files"),
        runtime_contract=_contract(),
        tool_name="project_status",
        params={},
    )

    assert guard["decision"] == "pass"
    assert guard["authority"] == "local_files"
    assert "disconnected" in guard["reason"]


def test_maker_guard_passes_known_authority_tools():
    for tool_name in ["maker_build", "maker_query_project", "runtime_contract", "mcp_status"]:
        guard = maker_first_action_guard(
            iteration=0,
            task="build Maker project",
            briefing=_briefing(),
            runtime_contract=_contract(),
            tool_name=tool_name,
            params={},
        )
        assert guard["decision"] == "pass"
        assert guard["tool"] == tool_name


def test_maker_guard_blocks_first_local_side_effect():
    guard = maker_first_action_guard(
        iteration=0,
        task="build Maker project",
        briefing=_briefing(),
        runtime_contract=_contract(),
        tool_name="write_file",
        params={"path": "main.lua", "content": "print('hi')"},
    )

    assert guard["decision"] == "block"
    assert guard["tool"] == "write_file"
    assert "maker_build" in guard["allowed_tools"]
    assert guard["suggested_tools"] == ["maker_build"]
    assert guard["recommended_endpoint"] == "/mcp/tools"


def test_maker_guard_warns_for_non_side_effect_diagnostics():
    guard = maker_first_action_guard(
        iteration=0,
        task="build Maker project",
        briefing=_briefing(),
        runtime_contract=_contract(),
        tool_name="project_status",
        params={},
    )

    assert guard["decision"] == "warn"
    assert "diagnostic" in guard["reason"]


def test_maker_guard_observation_and_context_hint_are_machine_readable():
    guard = maker_first_action_guard(
        iteration=0,
        task="build Maker project",
        briefing=_briefing(),
        runtime_contract=_contract(),
        tool_name="write_file",
        params={"content": "x"},
    )

    observation = maker_guard_observation("write_file", guard)
    hint = maker_guard_context_hint(guard)
    payload = json.loads(hint.split("\n")[2])

    assert observation["failure_type"] == "maker_briefing_guard"
    assert observation["suggested_fix"]
    assert payload["failure_type"] == "maker_briefing_guard"
    assert payload["decision"] == "block"
