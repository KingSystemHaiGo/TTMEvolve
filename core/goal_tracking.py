"""Deterministic cross-step goal checklist for ReAct sessions."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional


SIDE_EFFECT_TERMS = (
    "write", "create", "delete", "modify", "save", "build", "publish", "deploy",
    "生成", "创建", "写入", "修改", "删除", "保存", "构建", "发布", "提交",
)


def derive_goal_checklist(
    task: str,
    maker_templates: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    criteria = [
        {
            "id": "task_defined",
            "label": "Task intent is captured",
            "status": "done" if task.strip() else "pending",
            "evidence": ["task"] if task.strip() else [],
            "next_check": "Keep the original user task visible.",
        },
        {
            "id": "valid_action",
            "label": "At least one valid action/tool route is chosen",
            "status": "pending",
            "evidence": [],
            "next_check": "Choose a registered tool with valid params.",
        },
        {
            "id": "step_evidence",
            "label": "Latest step has verifiable evidence",
            "status": "pending",
            "evidence": [],
            "next_check": "Run or inspect a tool result that proves progress.",
        },
        {
            "id": "final_response",
            "label": "Final response/result is produced",
            "status": "pending",
            "evidence": [],
            "next_check": "Finish only after the required outcome is evidenced.",
        },
    ]
    if _needs_side_effect_verification(task):
        criteria.insert(3, {
            "id": "side_effect_state",
            "label": "Side effect or external state is verified",
            "status": "pending",
            "evidence": [],
            "next_check": "Confirm committed=true or run a direct state lookup.",
        })
    criteria.extend(_derive_maker_template_criteria(task, maker_templates or []))
    return criteria


def update_goal_checklist(
    *,
    task: str,
    trajectory: List[Dict[str, Any]],
    output: str = "",
    maker_templates: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    criteria = derive_goal_checklist(task, maker_templates=maker_templates)
    by_id = {item["id"]: item for item in criteria}

    valid_steps = [
        step for step in trajectory
        if isinstance(step.get("action"), dict)
        and step.get("action", {}).get("tool")
        and step.get("observation", {}).get("failure_type") != "tool_validation"
    ]
    validation_failures = [
        step for step in trajectory
        if step.get("observation", {}).get("failure_type") == "tool_validation"
    ]
    if valid_steps:
        _set(by_id["valid_action"], "done", f"step {valid_steps[-1].get('iteration')}")
    elif validation_failures:
        _set(by_id["valid_action"], "fail", f"step {validation_failures[-1].get('iteration')}")

    reports = [
        step.get("plan_validation")
        for step in trajectory
        if isinstance(step.get("plan_validation"), dict)
    ]
    if reports:
        latest = reports[-1]
        verdict = latest.get("verdict")
        status = "done" if verdict == "pass" else ("warn" if verdict == "warn" else "fail")
        _set(
            by_id["step_evidence"],
            status,
            str(latest.get("summary") or latest.get("tool") or "plan_validation"),
            str(latest.get("next_check") or by_id["step_evidence"]["next_check"]),
        )

    if "side_effect_state" in by_id:
        observations = [
            step.get("observation")
            for step in trajectory
            if isinstance(step.get("observation"), dict)
        ]
        committed_values = [
            obs.get("committed")
            for obs in observations
            if "committed" in obs or obs.get("idempotency_key")
        ]
        if any(value is True for value in committed_values):
            _set(by_id["side_effect_state"], "done", "committed=true")
        elif any(value is False for value in committed_values):
            _set(by_id["side_effect_state"], "fail", "committed=false")
        elif any(value is None for value in committed_values):
            _set(by_id["side_effect_state"], "warn", "committed=null")
        elif reports and reports[-1].get("verdict") == "pass":
            _set(by_id["side_effect_state"], "warn", "step passed but commit state is not explicit")

    if output.strip():
        _set(by_id["final_response"], "done", "output")

    _update_maker_template_criteria(criteria, by_id, reports, valid_steps)

    counts = {"done": 0, "pending": 0, "warn": 0, "fail": 0}
    for item in criteria:
        status = item.get("status", "pending")
        if status in counts:
            counts[status] += 1
    overall = "fail" if counts["fail"] else ("warn" if counts["warn"] else ("done" if counts["pending"] == 0 else "active"))
    return {
        "overall": overall,
        "counts": counts,
        "criteria": criteria,
        "next_focus": _next_focus(criteria),
    }


def checklist_context_hint(checklist: Dict[str, Any], *, max_items: int = 3) -> str:
    criteria = [
        {
            "id": item.get("id"),
            "status": item.get("status"),
            "next_check": item.get("next_check"),
        }
        for item in checklist.get("criteria", [])
        if item.get("status") != "done"
    ][:max_items]
    payload = {
        "overall": checklist.get("overall"),
        "next_focus": checklist.get("next_focus"),
        "open_criteria": criteria,
    }
    return "\n[goal_checklist]\n" + json.dumps(payload, ensure_ascii=False) + "\n"


def _needs_side_effect_verification(task: str) -> bool:
    task_l = task.lower()
    return any(term in task_l for term in SIDE_EFFECT_TERMS) or bool(re.search(r"\b(file|asset|project|maker)\b", task_l))


def _derive_maker_template_criteria(task: str, templates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not templates:
        return []
    task_l = task.lower()
    maker_task = _is_maker_task(task_l)
    derived: List[Dict[str, Any]] = []
    for template in templates:
        template_id = str(template.get("id") or "")
        if not _template_applies(template_id, task_l, maker_task):
            continue
        label = str(template.get("label") or template_id)
        acceptance = template.get("acceptance_criteria") if isinstance(template.get("acceptance_criteria"), list) else []
        for index, text in enumerate(acceptance[:2]):
            text_s = str(text)
            status = "pending"
            evidence: List[str] = []
            if template_id == "maker_inspect_project" and index == 0:
                status = "done"
                evidence = ["runtime_contract"]
            derived.append({
                "id": f"maker:{template_id}:{index}",
                "label": text_s,
                "status": status,
                "evidence": evidence,
                "next_check": f"{label}: {text_s}",
                "source": "maker_template",
                "template_id": template_id,
            })
    return derived


def _update_maker_template_criteria(
    criteria: List[Dict[str, Any]],
    by_id: Dict[str, Dict[str, Any]],
    reports: List[Dict[str, Any]],
    valid_steps: List[Dict[str, Any]],
) -> None:
    latest_report = reports[-1] if reports else {}
    report_verdict = latest_report.get("verdict")
    report_status = "done" if report_verdict == "pass" else ("warn" if report_verdict == "warn" else ("fail" if report_verdict == "fail" else "pending"))
    tool_names = [
        str(step.get("action", {}).get("tool") or step.get("observation", {}).get("tool") or "").lower()
        for step in valid_steps
    ]
    side_effect = by_id.get("side_effect_state", {})
    side_effect_status = side_effect.get("status")
    for item in criteria:
        if item.get("source") != "maker_template" or item.get("status") == "done":
            continue
        template_id = item.get("template_id")
        if template_id == "maker_plan_small_change" and report_status != "pending":
            _set(item, report_status, str(latest_report.get("summary") or "plan_validation"))
        elif template_id == "maker_execute_and_verify" and side_effect_status in {"done", "warn", "fail"}:
            _set(item, str(side_effect_status), "side_effect_state")
        elif template_id == "maker_build_or_submit" and any(
            any(term in tool for term in ("build", "publish", "submit", "deploy"))
            for tool in tool_names
        ):
            _set(item, "done", "maker build/submit tool selected")


def _is_maker_task(task_l: str) -> bool:
    return any(term in task_l for term in (
        "maker", "taptap", "game", "preview", "build", "submit", "publish",
        "asset", "script", "scene", "mcp",
        "游戏", "预览", "构建", "提交", "发布", "素材", "脚本",
    ))


def _template_applies(template_id: str, task_l: str, maker_task: bool) -> bool:
    if template_id in {"maker_inspect_project", "maker_plan_small_change"}:
        return maker_task
    if template_id == "maker_execute_and_verify":
        return maker_task and _needs_side_effect_verification(task_l)
    if template_id == "maker_build_or_submit":
        return any(term in task_l for term in ("build", "submit", "publish", "deploy", "构建", "提交", "发布"))
    if template_id == "external_agent_handoff":
        return any(term in task_l for term in ("handoff", "external", "claude", "codex", "opencode", "agent", "交接", "外部"))
    return False


def _set(item: Dict[str, Any], status: str, evidence: str, next_check: str = "") -> None:
    item["status"] = status
    if evidence:
        item.setdefault("evidence", []).append(evidence)
    if next_check:
        item["next_check"] = next_check


def _next_focus(criteria: List[Dict[str, Any]]) -> str:
    for status in ("fail", "warn", "pending"):
        for item in criteria:
            if item.get("status") == status:
                return str(item.get("next_check") or item.get("label") or "")
    return "All checklist items are satisfied."
