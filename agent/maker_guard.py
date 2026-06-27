"""Maker authority first-action guard for the ReAct loop."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional


MAKER_AUTHORITY_KEYWORDS = (
    "maker",
    "taptap",
    "tap maker",
    "tapmaker",
    "游戏",
    "关卡",
    "构建",
    "预览",
    "发布",
    "素材",
    "场景",
    "精灵",
    "脚本",
    "地图",
    "practice",
    "build",
    "preview",
    "asset",
    "scene",
)

LOCAL_SIDE_EFFECT_WORDS = (
    "write",
    "delete",
    "move",
    "rename",
    "create",
    "save",
    "patch",
    "apply",
    "build",
    "submit",
    "publish",
)

LOCAL_SIDE_EFFECT_PARAM_KEYS = {
    "content",
    "patch",
    "diff",
    "destination",
    "new_path",
    "target_path",
}

AUTHORITY_TOOLS = (
    "maker_briefing",
    "runtime_contract",
    "query_skills",
)


def maker_first_action_guard(
    *,
    iteration: int,
    task: str,
    briefing: Dict[str, Any],
    runtime_contract: Dict[str, Any],
    tool_name: Optional[str],
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Decide whether the first action is aligned with Maker authority."""
    briefing = briefing if isinstance(briefing, dict) else {}
    if iteration != 0 or not briefing or not tool_name:
        return {"decision": "skip", "iteration": iteration}
    if not task_needs_maker_authority(task):
        return {
            "decision": "skip",
            "iteration": iteration,
            "tool": tool_name,
            "reason": "Task does not require Maker authority before local actions.",
            "authority": briefing.get("authority"),
        }
    if not briefing.get("connected"):
        return {
            "decision": "pass",
            "iteration": iteration,
            "tool": tool_name,
            "reason": "MakerMCP is disconnected; local diagnostics are allowed.",
            "authority": briefing.get("authority"),
            "recommended_first_action": briefing.get("recommended_first_action"),
        }

    selected_template = briefing.get("selected_template")
    if not isinstance(selected_template, dict):
        selected_template = {}

    suggested_tools = [
        str(item)
        for item in briefing.get("suggested_tools", [])
        if item
    ] if isinstance(briefing.get("suggested_tools"), list) else []

    maker = runtime_contract.get("maker_mcp") if isinstance(runtime_contract, dict) else {}
    top_tools = [
        str(item.get("name"))
        for item in (maker.get("top_tools", []) if isinstance(maker, dict) else [])
        if isinstance(item, dict) and item.get("name")
    ]
    allowed_tools = sorted(set(suggested_tools + top_tools + list(AUTHORITY_TOOLS)))
    if not allowed_tools:
        return {
            "decision": "pass",
            "iteration": iteration,
            "tool": tool_name,
            "reason": "No Maker authority tools are known yet; current diagnostic action is allowed.",
            "authority": briefing.get("authority"),
            "recommended_first_action": briefing.get("recommended_first_action"),
        }
    if tool_name in allowed_tools or tool_name.startswith("maker_") or tool_name.startswith("mcp_"):
        return {
            "decision": "pass",
            "iteration": iteration,
            "tool": tool_name,
            "reason": "First action matches Maker briefing authority.",
            "authority": briefing.get("authority"),
            "selected_template": selected_template,
            "allowed_tools": allowed_tools[:8],
            "recommended_first_action": briefing.get("recommended_first_action"),
        }

    if looks_like_local_side_effect(tool_name, params):
        return {
            "decision": "block",
            "iteration": iteration,
            "tool": tool_name,
            "reason": (
                "First action would make a local side effect before using the Maker briefing "
                "authority. Use a MakerMCP/status/briefing action first, or explain why local "
                "files are the authority for this task."
            ),
            "authority": briefing.get("authority"),
            "selected_template": selected_template,
            "allowed_tools": allowed_tools[:8],
            "suggested_tools": suggested_tools[:4],
            "recommended_first_action": briefing.get("recommended_first_action"),
            "recommended_endpoint": briefing.get("recommended_endpoint"),
        }

    return {
        "decision": "warn",
        "iteration": iteration,
        "tool": tool_name,
        "reason": "First action does not directly match Maker briefing, but appears diagnostic.",
        "authority": briefing.get("authority"),
        "selected_template": selected_template,
        "allowed_tools": allowed_tools[:8],
        "suggested_tools": suggested_tools[:4],
        "recommended_first_action": briefing.get("recommended_first_action"),
        "recommended_endpoint": briefing.get("recommended_endpoint"),
    }


def looks_like_local_side_effect(tool_name: Optional[str], params: Dict[str, Any]) -> bool:
    name = (tool_name or "").lower()
    if any(word in name for word in LOCAL_SIDE_EFFECT_WORDS):
        return True
    if not isinstance(params, dict):
        return False
    return any(key in params for key in LOCAL_SIDE_EFFECT_PARAM_KEYS)


def task_needs_maker_authority(task: str) -> bool:
    text = (task or "").lower()
    return any(keyword in text for keyword in MAKER_AUTHORITY_KEYWORDS)


def maker_guard_observation(tool_name: Optional[str], guard: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ok": False,
        "valid": False,
        "failure_type": "maker_briefing_guard",
        "tool": tool_name,
        "decision": guard.get("decision"),
        "reason": guard.get("reason"),
        "authority": guard.get("authority"),
        "allowed_tools": guard.get("allowed_tools", []),
        "suggested_tools": guard.get("suggested_tools", []),
        "recommended_first_action": guard.get("recommended_first_action"),
        "recommended_endpoint": guard.get("recommended_endpoint"),
        "suggested_fix": (
            "Follow maker_briefing first: choose one suggested MakerMCP/status tool, "
            "or call maker_briefing/runtime_contract before making local side effects."
        ),
    }


def maker_guard_context_hint(guard: Dict[str, Any]) -> str:
    payload = {
        "failure_type": "maker_briefing_guard",
        "decision": guard.get("decision"),
        "reason": guard.get("reason"),
        "authority": guard.get("authority"),
        "allowed_tools": guard.get("allowed_tools", []),
        "suggested_tools": guard.get("suggested_tools", []),
        "recommended_first_action": guard.get("recommended_first_action"),
        "recommended_endpoint": guard.get("recommended_endpoint"),
    }
    return (
        "\n[maker_briefing_guard]\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n"
        "Before local side effects, follow the Maker briefing authority or fetch the compact briefing/contract again.\n"
    )
