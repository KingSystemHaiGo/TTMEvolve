"""COS-driven project management control summary.

This module converts already-observed project state plus COS Gate 0 evidence
into a compact project-manager surface: next action, blockers, verification
status, and memory updates due.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


PROJECT_CONTROL_VERSION = "project-control.v1"


def build_project_control(
    *,
    project_state: Dict[str, Any],
    cos_gate: Dict[str, Any],
    runtime_advice: Optional[Dict[str, Any]] = None,
    layer_control: Optional[Dict[str, Any]] = None,
    engineering_control: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a compact project-manager summary from public evidence."""
    project_state = project_state if isinstance(project_state, dict) else {}
    cos_gate = cos_gate if isinstance(cos_gate, dict) else {}
    runtime_advice = runtime_advice if isinstance(runtime_advice, dict) else {}
    layer_control = layer_control if isinstance(layer_control, dict) else {}
    engineering_control = engineering_control if isinstance(engineering_control, dict) else {}

    required_gates = [
        str(item)
        for item in (cos_gate.get("required_gates") or [])
        if item
    ]
    completed_gates = _completed_gates(project_state=project_state, cos_gate=cos_gate)
    pending_gates = [gate for gate in required_gates if gate not in completed_gates]
    blockers = _blockers(
        project_state=project_state,
        cos_gate=cos_gate,
        runtime_advice=runtime_advice,
        layer_control=layer_control,
        engineering_control=engineering_control,
    )
    memory_updates_due = _memory_updates_due(cos_gate=cos_gate)
    verification = _verification(
        project_state=project_state,
        cos_gate=cos_gate,
        blockers=blockers,
        layer_control=layer_control,
        engineering_control=engineering_control,
    )
    status = _status(blockers=blockers, verification=verification, cos_gate=cos_gate)
    next_action = _next_action(
        project_state=project_state,
        cos_gate=cos_gate,
        runtime_advice=runtime_advice,
        blockers=blockers,
        pending_gates=pending_gates,
    )
    current_focus = (
        project_state.get("next_focus")
        or project_state.get("next_action")
        or project_state.get("task")
        or _classification_label(cos_gate)
    )

    return {
        "version": PROJECT_CONTROL_VERSION,
        "status": status,
        "source": "cos_gate_project_state",
        "current_focus": current_focus or "-",
        "next_action": next_action,
        "blockers": blockers,
        "classification": {
            "task_type": cos_gate.get("task_type"),
            "task_type_label": cos_gate.get("task_type_label"),
            "level": cos_gate.get("level"),
            "mode": cos_gate.get("mode"),
            "understanding_status": cos_gate.get("understanding_status"),
            "declaration": cos_gate.get("declaration"),
        },
        "required_gates": required_gates,
        "completed_gates": completed_gates,
        "pending_gates": pending_gates,
        "memory_updates_due": memory_updates_due,
        "verification": verification,
        "layer_control": _layer_control_summary(layer_control),
        "engineering_control": _engineering_control_summary(engineering_control),
        "control_actions": _control_actions(layer_control, engineering_control),
        "truthfulness": cos_gate.get("truthfulness") if isinstance(cos_gate.get("truthfulness"), dict) else {},
        "project_manager": (
            cos_gate.get("project_management")
            if isinstance(cos_gate.get("project_management"), dict)
            else {}
        ),
    }


def _completed_gates(*, project_state: Dict[str, Any], cos_gate: Dict[str, Any]) -> List[str]:
    completed: List[str] = []
    if cos_gate.get("status") in {"ready", "computed"} or cos_gate.get("declaration"):
        completed.append("GATE_0_DECLARE")
    if project_state.get("task") or project_state.get("next_focus") or project_state.get("next_action"):
        completed.append("UNDERSTAND")
    if project_state.get("plan_verdict") == "pass":
        completed.append("PLAN_CHECK")
    return completed


def _blockers(
    *,
    project_state: Dict[str, Any],
    cos_gate: Dict[str, Any],
    runtime_advice: Dict[str, Any],
    layer_control: Dict[str, Any],
    engineering_control: Dict[str, Any],
) -> List[Dict[str, str]]:
    blockers: List[Dict[str, str]] = []
    vague = cos_gate.get("vague_protocol") if isinstance(cos_gate.get("vague_protocol"), dict) else {}
    if vague.get("active"):
        blockers.append({
            "id": "vague_instruction_needs_confirmation",
            "severity": "blocker",
            "detail": "COS vague-instruction protocol requires subtask confirmation before execution.",
        })
    if project_state.get("plan_verdict") == "fail":
        blockers.append({
            "id": "plan_validation_failed",
            "severity": "blocker",
            "detail": "Plan validation failed; side effects should pause until repaired.",
        })
    if project_state.get("goal_overall") == "fail":
        blockers.append({
            "id": "goal_validation_failed",
            "severity": "blocker",
            "detail": "Goal criteria are failing and need repair before continuing.",
        })
    continuation = project_state.get("continuation") if isinstance(project_state.get("continuation"), dict) else {}
    if continuation and continuation.get("resume_ready") is False:
        blockers.append({
            "id": "continuation_not_ready",
            "severity": "warn",
            "detail": "Continuation checkpoint exists but is not resume-ready.",
        })
    if runtime_advice.get("status") == "needs_action" and runtime_advice.get("priority"):
        blockers.append({
            "id": f"runtime_advice_{runtime_advice.get('priority')}",
            "severity": "warn",
            "detail": str(runtime_advice.get("next_action") or "Runtime advice requires attention."),
        })
    if layer_control.get("status") == "blocked":
        blockers.append({
            "id": "layer_control_blocked",
            "severity": "blocker",
            "detail": _layer_control_next_action(layer_control) or "Layer-control signals block completion claims.",
        })
    elif layer_control.get("status") == "needs_action":
        blockers.append({
            "id": "layer_control_needs_action",
            "severity": "warn",
            "detail": _layer_control_next_action(layer_control) or "Layer-control signals require correction.",
        })
    if engineering_control.get("status") == "blocked":
        blockers.append({
            "id": "engineering_control_blocked",
            "severity": "blocker",
            "detail": _engineering_control_next_action(engineering_control)
                or "Engineering-control signals block completion claims.",
        })
    elif engineering_control.get("status") == "needs_action":
        blockers.append({
            "id": "engineering_control_needs_action",
            "severity": "warn",
            "detail": _engineering_control_next_action(engineering_control)
                or "Engineering-control signals require correction.",
        })
    return blockers


def _memory_updates_due(*, cos_gate: Dict[str, Any]) -> List[Dict[str, str]]:
    post = cos_gate.get("post_requirements") if isinstance(cos_gate.get("post_requirements"), dict) else {}
    if post.get("required") is False:
        return []
    files = post.get("files") if isinstance(post.get("files"), list) else []
    gates = [gate for gate in (cos_gate.get("required_gates") or []) if str(gate).startswith("POST")]
    due: List[Dict[str, str]] = []
    for gate, file_path in zip(gates or ["POST_MEM", "POST_SYNC"], files or ["docs/memory-index.md", "docs/sprint-board.md"]):
        due.append({"gate": str(gate), "file": str(file_path)})
    return due


def _verification(
    *,
    project_state: Dict[str, Any],
    cos_gate: Dict[str, Any],
    blockers: List[Dict[str, str]],
    layer_control: Dict[str, Any],
    engineering_control: Dict[str, Any],
) -> Dict[str, Any]:
    truth = cos_gate.get("truthfulness") if isinstance(cos_gate.get("truthfulness"), dict) else {}
    if any(blocker.get("severity") == "blocker" for blocker in blockers):
        status = "blocked"
    elif project_state.get("runtime_status") == "done" and project_state.get("plan_verdict") == "pass":
        status = "ready"
    elif truth.get("requires_evidence", True):
        status = "requires_evidence"
    else:
        status = "instrumented"
    return {
        "status": status,
        "requires_evidence": bool(truth.get("requires_evidence", True)),
        "rule": truth.get("rule") or "Strong claims require test, endpoint, runtime, or file evidence.",
        "evidence_sources": [
            "cos_gate",
            "project_state",
            "runtime_advice",
            *([] if not layer_control else ["layer_control"]),
            *([] if not engineering_control else ["engineering_control"]),
        ],
    }


def _status(
    *,
    blockers: List[Dict[str, str]],
    verification: Dict[str, Any],
    cos_gate: Dict[str, Any],
) -> str:
    if cos_gate.get("understanding_status") == "decompose_vague":
        return "needs_confirmation"
    if any(blocker.get("severity") == "blocker" for blocker in blockers):
        return "blocked"
    if verification.get("status") == "ready":
        return "ready"
    if cos_gate.get("status") in {"ready", "computed"} or cos_gate.get("declaration"):
        return "ready"
    return "needs_action" if blockers else "instrumented"


def _next_action(
    *,
    project_state: Dict[str, Any],
    cos_gate: Dict[str, Any],
    runtime_advice: Dict[str, Any],
    blockers: List[Dict[str, str]],
    pending_gates: List[str],
) -> str:
    if cos_gate.get("understanding_status") == "decompose_vague":
        return "Confirm decomposed vague subtasks before execution."
    hard_blockers = [blocker for blocker in blockers if blocker.get("severity") == "blocker"]
    if hard_blockers:
        return str(hard_blockers[0].get("detail") or "Resolve project blocker.")
    if project_state.get("next_action"):
        return str(project_state.get("next_action"))
    if project_state.get("next_focus"):
        return str(project_state.get("next_focus"))
    if blockers:
        return str(blockers[0].get("detail") or "Resolve project blocker.")
    if runtime_advice.get("status") == "needs_action" and runtime_advice.get("next_action"):
        return str(runtime_advice.get("next_action"))
    if pending_gates:
        return f"Execute COS gate: {pending_gates[0]}."
    return "Wait for project-state evidence before selecting the next action."


def _layer_control_summary(layer_control: Dict[str, Any]) -> Dict[str, Any]:
    if not layer_control:
        return {"status": "missing", "decision": "not_available", "signal_count": 0, "action_count": 0}
    closure = layer_control.get("closure_gate") if isinstance(layer_control.get("closure_gate"), dict) else {}
    actions = layer_control.get("corrective_actions") if isinstance(layer_control.get("corrective_actions"), list) else []
    signals = layer_control.get("signals") if isinstance(layer_control.get("signals"), list) else []
    top_action = actions[0] if actions and isinstance(actions[0], dict) else {}
    return {
        "status": layer_control.get("status"),
        "decision": layer_control.get("decision"),
        "signal_count": len(signals),
        "action_count": len(actions),
        "can_claim_layer_independence": closure.get("can_claim_layer_independence"),
        "can_continue_user_task": closure.get("can_continue_user_task"),
        "top_action": {
            "id": top_action.get("id"),
            "priority": top_action.get("priority"),
            "owner_layer": top_action.get("owner_layer"),
            "reason": top_action.get("reason"),
        } if top_action else {},
    }


def _engineering_control_summary(engineering_control: Dict[str, Any]) -> Dict[str, Any]:
    if not engineering_control:
        return {"status": "missing", "decision": "not_available", "signal_count": 0, "action_count": 0}
    closure = (
        engineering_control.get("closure_gate")
        if isinstance(engineering_control.get("closure_gate"), dict)
        else {}
    )
    summary = (
        engineering_control.get("summary")
        if isinstance(engineering_control.get("summary"), dict)
        else {}
    )
    actions = (
        engineering_control.get("corrective_actions")
        if isinstance(engineering_control.get("corrective_actions"), list)
        else []
    )
    signals = (
        engineering_control.get("signals")
        if isinstance(engineering_control.get("signals"), list)
        else []
    )
    top_action = actions[0] if actions and isinstance(actions[0], dict) else {}
    return {
        "status": engineering_control.get("status"),
        "decision": engineering_control.get("decision"),
        "signal_count": len(signals),
        "action_count": len(actions),
        "memory_total_hits": summary.get("memory_total_hits"),
        "tool_failure_count": summary.get("tool_failure_count"),
        "plan_verdict": summary.get("plan_verdict"),
        "can_claim_engineering_control_ready": closure.get("can_claim_engineering_control_ready"),
        "can_continue_user_task": closure.get("can_continue_user_task"),
        "can_claim_memory_rag_optimized": closure.get("can_claim_memory_rag_optimized"),
        "top_action": {
            "id": top_action.get("id"),
            "priority": top_action.get("priority"),
            "owner_layer": top_action.get("owner_layer"),
            "domain": top_action.get("domain"),
            "reason": top_action.get("reason"),
        } if top_action else {},
    }


def _control_actions(
    layer_control: Dict[str, Any],
    engineering_control: Dict[str, Any],
) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    actions = layer_control.get("corrective_actions") if isinstance(layer_control.get("corrective_actions"), list) else []
    for action in actions:
        if not isinstance(action, dict):
            continue
        merged.append({
            "id": action.get("id"),
            "source": action.get("source") or "layer_control",
            "priority": action.get("priority"),
            "owner_layer": action.get("owner_layer"),
            "domain": action.get("domain") or "layer",
            "reason": action.get("reason"),
        })
    engineering_actions = (
        engineering_control.get("corrective_actions")
        if isinstance(engineering_control.get("corrective_actions"), list)
        else []
    )
    for action in engineering_actions:
        if not isinstance(action, dict):
            continue
        merged.append({
            "id": action.get("id"),
            "source": action.get("source") or "engineering_control",
            "priority": action.get("priority"),
            "owner_layer": action.get("owner_layer"),
            "domain": action.get("domain"),
            "reason": action.get("reason"),
        })
    return sorted(merged, key=lambda item: item.get("priority", 99))[:3]


def _layer_control_next_action(layer_control: Dict[str, Any]) -> str:
    actions = layer_control.get("corrective_actions") if isinstance(layer_control.get("corrective_actions"), list) else []
    if not actions or not isinstance(actions[0], dict):
        return ""
    action = actions[0]
    action_id = action.get("id") or "correct_layer_control_signal"
    reason = action.get("reason")
    return f"{action_id}: {reason}" if reason else str(action_id)


def _engineering_control_next_action(engineering_control: Dict[str, Any]) -> str:
    actions = (
        engineering_control.get("corrective_actions")
        if isinstance(engineering_control.get("corrective_actions"), list)
        else []
    )
    if not actions or not isinstance(actions[0], dict):
        return ""
    action = actions[0]
    action_id = action.get("id") or "correct_engineering_control_signal"
    reason = action.get("reason")
    return f"{action_id}: {reason}" if reason else str(action_id)


def _classification_label(cos_gate: Dict[str, Any]) -> str:
    label = cos_gate.get("task_type_label") or cos_gate.get("task_type")
    level = cos_gate.get("level")
    if label and level:
        return f"{label} [{level}]"
    return str(label or "")
