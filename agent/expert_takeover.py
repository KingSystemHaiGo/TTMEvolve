"""Expert takeover runner used by rescue orchestration."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


EmitFn = Callable[[str, str, Dict[str, Any]], None]
ExecuteActionFn = Callable[[str, Optional[str], Dict[str, Any]], Dict[str, Any]]
ContextProvider = Callable[[], str]
ToolsDescriptionProvider = Callable[[], str]
AppendContextFn = Callable[[str], None]
OnStepFn = Callable[[Dict[str, Any], List[Dict[str, Any]]], None]


@dataclass
class ExpertTakeoverResult:
    steps_executed: int = 0
    stopped_on_done: bool = False


def run_expert_takeover(
    *,
    expert_llm: Any,
    steps: int,
    task: str,
    session_id: str,
    trajectory: List[Dict[str, Any]],
    context: ContextProvider,
    tools_description: ToolsDescriptionProvider,
    emit: EmitFn,
    execute_action: ExecuteActionFn,
    append_context: AppendContextFn,
    on_step: Optional[OnStepFn] = None,
) -> ExpertTakeoverResult:
    """Run a bounded expert-controlled ReAct loop."""
    result = ExpertTakeoverResult()
    for _ in range(max(0, int(steps or 0))):
        iteration = len(trajectory)
        step = {
            "iteration": iteration,
            "timestamp": time.time(),
            "source": "expert",
        }

        thought = expert_llm.think(
            task=task,
            context=context(),
            trajectory=trajectory,
            tools_description=tools_description(),
        )
        step["thought"] = thought
        emit(session_id, "thought", {"iteration": iteration, "thought": thought, "source": "expert"})

        action = expert_llm.choose_action(
            task=task,
            thought=thought,
            tools_description=tools_description(),
        )
        step["action"] = action
        emit(session_id, "action", {"iteration": iteration, "action": action, "source": "expert"})

        result.steps_executed += 1
        if action.get("done"):
            step["output"] = action.get("output", "")
            step["done"] = True
            trajectory.append(step)
            emit(session_id, "output", {"output": step["output"], "source": "expert"})
            result.stopped_on_done = True
            return result

        tool_name = action.get("tool")
        params = action.get("params", {})
        emit(session_id, "tool_call", {"tool": tool_name, "params": params, "source": "expert"})
        observation = execute_action(session_id, tool_name, params)
        step["observation"] = observation
        trajectory.append(step)
        emit(session_id, "observation", {
            "iteration": iteration,
            "tool": tool_name,
            "observation": observation,
            "source": "expert",
        })

        if not observation.get("ok"):
            error_msg = f"\n[错误] {tool_name} 失败: {observation.get('error')}"
            append_context(error_msg)
            emit(session_id, "error", {"iteration": iteration, "message": error_msg, "source": "expert"})

        if on_step:
            on_step(step, trajectory)
    return result
