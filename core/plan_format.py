"""Structured plan format for Plan First mode.

A plan is a list of steps the Agent should execute before it actually runs any
tool. Each step carries the tool name, parameters, the expected evidence, and
optional dependencies on other steps. The format is intentionally small enough
to be produced by a single LLM call but rich enough for the UI to render as
editable cards.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


PLAN_FORMAT_VERSION = "plan-format.v1"


def empty_plan(task: str = "") -> Dict[str, Any]:
    """Return an empty plan scaffold for the given task."""
    return {
        "version": PLAN_FORMAT_VERSION,
        "task": task,
        "summary": "",
        "assumptions": [],
        "steps": [],
        "status": "draft",
        "approved": False,
    }


def normalize_plan(plan: Optional[Dict[str, Any]], task: str = "") -> Dict[str, Any]:
    """Coerce arbitrary LLM output into a valid plan shape.

    Never raises: missing fields are filled with defaults, malformed steps are
    filtered out so downstream code can always trust the structure.
    """
    base = empty_plan(task)
    if not isinstance(plan, dict):
        return base
    base["summary"] = str(plan.get("summary") or "")
    base["assumptions"] = [str(item) for item in plan.get("assumptions") or []]
    base["status"] = str(plan.get("status") or "draft")
    base["approved"] = bool(plan.get("approved"))
    raw_steps = plan.get("steps") or []
    if not isinstance(raw_steps, list):
        return base
    normalized_steps: List[Dict[str, Any]] = []
    for index, raw in enumerate(raw_steps):
        step = _normalize_step(raw, index)
        if step is not None:
            normalized_steps.append(step)
    base["steps"] = normalized_steps
    return base


def _normalize_step(raw: Any, index: int) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    tool = str(raw.get("tool") or "").strip()
    if not tool:
        return None
    params = raw.get("params") if isinstance(raw.get("params"), dict) else {}
    expected = [str(item) for item in raw.get("expected_evidence") or []]
    step_id = str(raw.get("id") or f"step-{index + 1}")
    depends_on = [str(item) for item in raw.get("depends_on") or []]
    return {
        "id": step_id,
        "tool": tool,
        "params": params,
        "intent": str(raw.get("intent") or ""),
        "expected_evidence": expected,
        "depends_on": depends_on,
        "status": "pending",
        "notes": str(raw.get("notes") or ""),
    }


def plan_to_context_block(plan: Dict[str, Any], max_steps: int = 8) -> str:
    """Render an approved plan as a compact context hint for the ReAct loop."""
    steps = plan.get("steps") or []
    if not isinstance(steps, list) or not steps:
        return ""
    visible = steps[:max_steps]
    payload = {
        "plan_id": plan.get("version", PLAN_FORMAT_VERSION),
        "task": plan.get("task"),
        "summary": plan.get("summary"),
        "steps": [
            {
                "id": step.get("id"),
                "tool": step.get("tool"),
                "intent": step.get("intent"),
                "expected_evidence": step.get("expected_evidence", []),
                "depends_on": step.get("depends_on", []),
                "status": step.get("status", "pending"),
            }
            for step in visible
        ],
    }
    return (
        "\n[approved_plan]\n"
        + json.dumps(payload, ensure_ascii=False)
        + "\nFollow the approved plan step by step. Mark the current step "
        "before executing it and update its status after verification.\n"
    )


def plan_progress(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Summarize step statuses for the UI progress card."""
    steps = plan.get("steps") or []
    if not isinstance(steps, list):
        steps = []
    counts = {"pending": 0, "in_progress": 0, "done": 0, "skipped": 0, "failed": 0}
    for step in steps:
        status = str(step.get("status") or "pending")
        if status not in counts:
            status = "pending"
        counts[status] += 1
    overall = "draft"
    if plan.get("approved") and counts["pending"] == 0 and counts["in_progress"] == 0:
        overall = "completed" if counts["failed"] == 0 else "needs_recovery"
    elif plan.get("approved"):
        overall = "executing"
    return {
        "overall": overall,
        "counts": counts,
        "current_step": _first_open_step_id(steps),
        "total_steps": len(steps),
    }


def _first_open_step_id(steps: List[Dict[str, Any]]) -> Optional[str]:
    for step in steps:
        if str(step.get("status") or "pending") in {"pending", "in_progress"}:
            return step.get("id")
    return None


def update_step_status(
    plan: Dict[str, Any],
    step_id: str,
    status: str,
    note: str = "",
) -> Dict[str, Any]:
    """Return a new plan with the given step status updated.

    Status must be one of: pending, in_progress, done, skipped, failed.
    """
    if status not in {"pending", "in_progress", "done", "skipped", "failed"}:
        return plan
    for step in plan.get("steps") or []:
        if step.get("id") == step_id:
            step["status"] = status
            if note:
                existing = step.get("notes") or ""
                step["notes"] = f"{existing}\n{note}".strip() if existing else note
            break
    return plan