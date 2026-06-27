"""Plan First phase helpers for ReActLoop.

This module owns plan drafting, deterministic review, approval handling, and
the no-approval result shape. ReActLoop keeps orchestration state and event
ordering, but no longer needs to know the details of plan prompt parsing or
review policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from core.plan_format import empty_plan, normalize_plan, plan_progress
from core.plan_prompt import build_plan_prompt, extract_plan_from_llm_text
from core.plan_review import review_plan


EmitFn = Callable[[str, str, Dict[str, Any]], None]
PlanApprovalProvider = Callable[[Dict[str, Any]], bool]
DraftPlanFn = Callable[[str], Dict[str, Any]]


@dataclass
class PlanFirstResult:
    plan: Dict[str, Any]
    review: Dict[str, Any]
    approved: bool
    reason: str = "not_approved"


def run_plan_first_phase(
    *,
    llm: Any,
    tools: Any,
    task: str,
    context: str,
    session_id: str,
    emit: EmitFn,
    approval_provider: Optional[PlanApprovalProvider] = None,
    draft_plan: Optional[DraftPlanFn] = None,
) -> PlanFirstResult:
    """Generate, review, and optionally approve a structured plan."""
    emit(session_id, "plan_first_phase", {"phase": "drafting", "task": task})
    plan = draft_plan(task) if callable(draft_plan) else draft_plan_from_llm(
        llm=llm,
        tools=tools,
        task=task,
        context=context,
        session_id=session_id,
        emit=emit,
    )
    review = review_plan(plan, known_tools=known_tool_names(tools))
    emit(session_id, "plan_draft", {
        "plan": plan,
        "review": review,
        "progress": plan_progress(plan),
    })

    if review.get("verdict") == "fail":
        emit(session_id, "plan_first_phase", {
            "phase": "auto_rejected",
            "review": review,
        })
        return PlanFirstResult(plan=plan, review=review, approved=False)

    if not callable(approval_provider):
        if review.get("verdict") == "pass":
            plan["approved"] = True
            plan["status"] = "approved"
            return PlanFirstResult(plan=plan, review=review, approved=True, reason="")
        return PlanFirstResult(plan=plan, review=review, approved=False)

    try:
        approved = bool(approval_provider(plan))
    except Exception as exc:
        emit(session_id, "plan_approval_error", {"error": str(exc)})
        approved = False

    if not approved:
        return PlanFirstResult(plan=plan, review=review, approved=False)
    plan["approved"] = True
    plan["status"] = "approved"
    return PlanFirstResult(plan=plan, review=review, approved=True, reason="")


def draft_plan_from_llm(
    *,
    llm: Any,
    tools: Any,
    task: str,
    context: str,
    session_id: str,
    emit: EmitFn,
) -> Dict[str, Any]:
    """Ask the LLM for JSON and normalize it into the public plan schema."""
    names = sorted(known_tool_names(tools))
    prompt = build_plan_prompt(
        task=task,
        context=context,
        runtime_hints={
            "session_id": session_id,
            "tools_available": len(names),
        },
        tool_list=names,
    )
    try:
        response = llm.generate(prompt=prompt, max_tokens=800)
        text = response.text if hasattr(response, "text") else str(response)
    except Exception as exc:
        emit(session_id, "plan_draft_error", {"error": str(exc)})
        return empty_plan(task=task)

    parsed = extract_plan_from_llm_text(text or "")
    if parsed is None:
        emit(session_id, "plan_draft_parse_failed", {
            "raw_excerpt": (text or "")[:200],
        })
        return empty_plan(task=task)
    return normalize_plan(parsed, task=task)


def known_tool_names(tools: Any) -> List[str]:
    names: List[str] = []
    try:
        tool_list = tools.list_tools()
    except Exception:
        return []
    for tool in tool_list:
        if isinstance(tool, dict):
            name = tool.get("name")
        else:
            name = getattr(tool, "name", None)
        if isinstance(name, str) and name:
            names.append(name)
    return names


def build_plan_first_result(
    *,
    session_id: str,
    task: str,
    plan: Dict[str, Any],
    review: Dict[str, Any],
    reason: str = "not_approved",
) -> Dict[str, Any]:
    """Return the stable result shape used when planning stops execution."""
    return {
        "session_id": session_id,
        "task": task,
        "trajectory": [],
        "output": "",
        "done": False,
        "plan": plan,
        "plan_review": review,
        "plan_progress": plan_progress(plan),
        "plan_first_phase": reason,
    }
