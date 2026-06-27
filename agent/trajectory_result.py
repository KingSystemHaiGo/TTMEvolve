"""Trajectory recording and final result helpers for ReActLoop."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from core.plan_format import plan_progress
from core.plan_validation import summarize_plan_validation


EmitFn = Callable[[str, str, Dict[str, Any]], None]
ValidateStepFn = Callable[[Dict[str, Any]], Dict[str, Any]]
RefreshGoalFn = Callable[..., None]
SyncFn = Callable[..., None]


def record_output_step(
    *,
    trajectory: List[Dict[str, Any]],
    step: Dict[str, Any],
    iteration: int,
    session_id: str,
    emit: EmitFn,
    refresh_goal: RefreshGoalFn,
    emit_context_sync: SyncFn,
    output: Optional[str] = None,
) -> None:
    """Append a completed output step and emit the public completion events."""
    output_text = step.get("output", "") if output is None else output
    trajectory.append(step)
    emit(session_id, "output", {"output": output_text})
    refresh_goal(output=output_text)
    emit_context_sync(iteration=iteration, reason="output")


def record_observation_step(
    *,
    trajectory: List[Dict[str, Any]],
    step: Dict[str, Any],
    iteration: int,
    session_id: str,
    tool_name: str,
    observation: Dict[str, Any],
    emit: EmitFn,
    validate_step: ValidateStepFn,
    refresh_goal: RefreshGoalFn,
    emit_skill_sync: SyncFn,
    emit_context_sync: SyncFn,
    reason: str = "plan_validation",
) -> Dict[str, Any]:
    """Append an observed action step and emit validation/progress events."""
    step["observation"] = observation
    plan_validation = validate_step(step)
    step["plan_validation"] = plan_validation
    trajectory.append(step)
    emit(session_id, "observation", {
        "iteration": iteration,
        "tool": tool_name,
        "observation": observation,
    })
    emit(session_id, "plan_validation", plan_validation)
    refresh_goal()
    emit_skill_sync(iteration=iteration, reason=reason)
    emit_context_sync(iteration=iteration, reason=reason)
    return plan_validation


def latest_output_from_trajectory(trajectory: List[Dict[str, Any]]) -> str:
    """Return the last user-facing output in a trajectory."""
    for step in reversed(trajectory):
        if step.get("done") or "output" in step:
            return step.get("output", "")
    return ""


def build_react_result(
    *,
    session_id: str,
    task: str,
    trajectory: List[Dict[str, Any]],
    goal_checklist: Dict[str, Any],
    plan: Dict[str, Any],
    plan_review: Dict[str, Any],
    include_plan: bool,
) -> Dict[str, Any]:
    """Build the stable public ReAct result shape."""
    result = {
        "session_id": session_id,
        "task": task,
        "trajectory": trajectory,
        "output": latest_output_from_trajectory(trajectory),
        "iteration_count": len(trajectory),
        "plan_validation": summarize_plan_validation(trajectory),
        "goal_checklist": goal_checklist,
    }
    if include_plan:
        result["plan"] = plan
        result["plan_review"] = plan_review
        result["plan_progress"] = plan_progress(plan)
    return result


def summarize_react_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Return the compact result summary emitted in session status."""
    return {
        "iteration_count": result.get("iteration_count", 0),
        "output_length": len(result.get("output", "")),
    }
