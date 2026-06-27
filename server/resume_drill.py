"""Durable long-task resume drill evidence.

This module verifies what can be recovered from persisted session evidence.
It deliberately does not read live ReActLoop state, private queues, or raw SSE
streams, so callers can use it as a restart-style store replay check.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


RESUME_DRILL_VERSION = "resume-drill.v1"


def build_resume_drill_report(
    *,
    session_id: str,
    stored_session: Optional[Dict[str, Any]] = None,
    context_history: Optional[List[Dict[str, Any]]] = None,
    event_history: Optional[List[Dict[str, Any]]] = None,
    live_session_present: bool = False,
) -> Dict[str, Any]:
    """Build a compact durable-handoff recovery report from store evidence."""
    stored_session = stored_session if isinstance(stored_session, dict) else {}
    context_history = context_history if isinstance(context_history, list) else []
    event_history = event_history if isinstance(event_history, list) else []
    latest_context = context_history[-1] if context_history else {}
    checkpoint = _checkpoint_from_context(latest_context)
    snapshot = (
        latest_context.get("snapshot")
        if isinstance(latest_context.get("snapshot"), dict)
        else {}
    )
    task = (
        stored_session.get("task")
        or snapshot.get("task")
        or checkpoint.get("task")
        or ""
    )
    open_plan_steps = _list_of_dicts(checkpoint.get("open_plan_steps"))[:6]
    artifacts = _list_of_dicts(checkpoint.get("artifact_refs"))[:6]
    compression = (
        checkpoint.get("compression")
        if isinstance(checkpoint.get("compression"), dict)
        else {}
    )
    resume_limits = (
        checkpoint.get("resume_limits")
        if isinstance(checkpoint.get("resume_limits"), dict)
        else {}
    )
    recovered = {
        "session_id": session_id,
        "session_status": stored_session.get("status"),
        "task": task,
        "checkpoint_version": checkpoint.get("version"),
        "context_revision": checkpoint.get("context_revision") or latest_context.get("revision"),
        "context_signature": latest_context.get("signature"),
        "checkpoint_timestamp": latest_context.get("timestamp"),
        "resume_mode": checkpoint.get("resume_mode"),
        "workspace_profile": (
            checkpoint.get("workspace_profile")
            or latest_context.get("workspace_profile")
            or "general"
        ),
        "goal_overall": checkpoint.get("goal_overall") or latest_context.get("goal_overall"),
        "goal_next_focus": checkpoint.get("goal_next_focus"),
        "open_plan_steps": open_plan_steps,
        "open_plan_count": len(open_plan_steps),
        "last_tool": checkpoint.get("last_tool") or latest_context.get("last_tool"),
        "last_ok": checkpoint.get("last_ok"),
        "plan_verdict": checkpoint.get("plan_verdict") or latest_context.get("plan_verdict"),
        "last_result": {
            "tool": checkpoint.get("last_tool") or latest_context.get("last_tool"),
            "ok": checkpoint.get("last_ok"),
            "plan_verdict": checkpoint.get("plan_verdict") or latest_context.get("plan_verdict"),
        },
        "artifact_refs": artifacts,
        "artifact_count": checkpoint.get("artifact_count") or latest_context.get("artifact_count") or len(artifacts),
        "compression": {
            "needed": bool(compression.get("needed")),
            "version": compression.get("version"),
            "compressed_step_count": compression.get("compressed_step_count", 0),
            "skipped_step_count": compression.get("skipped_step_count", 0),
            "summary": str(compression.get("summary") or "")[:800],
        },
        "event_counts": _event_counts(event_history),
    }
    missing_required = _missing_required_fields(
        stored_session=stored_session,
        latest_context=latest_context,
        checkpoint=checkpoint,
        recovered=recovered,
    )
    missing_recommended = _missing_recommended_fields(recovered=recovered)
    missing_fields = missing_required + [
        field for field in missing_recommended if field not in missing_required
    ]
    status = _status(checkpoint=checkpoint, latest_context=latest_context, missing_required=missing_required)
    capability_levels = _capability_levels(status=status, missing_fields=missing_fields)

    return {
        "version": RESUME_DRILL_VERSION,
        "session_id": session_id,
        "status": status,
        "source": "session_store_replay",
        "drill": {
            "kind": "durable_store_replay",
            "uses_live_runtime_state": False,
            "live_session_present": bool(live_session_present),
            "context_sync_count": len(context_history),
            "event_count": len(event_history),
        },
        "capability_levels": capability_levels,
        "recovered": recovered,
        "missing_fields": missing_fields,
        "missing_required_fields": missing_required,
        "missing_recommended_fields": missing_recommended,
        "resume_limits": {
            "process_resurrection": bool(resume_limits.get("process_resurrection")),
            "requires_runtime_replay": bool(resume_limits.get("requires_runtime_replay")),
            "raw_sse_replay_required": bool(resume_limits.get("raw_sse_replay_required")),
            "warm_process_resume_proven": False,
            "hot_tool_call_resume_proven": False,
        },
        "closure_gate": {
            "can_claim_long_task_durable_handoff": status == "ready",
            "can_claim_warm_process_resume": False,
            "can_claim_hot_tool_call_resume": False,
            "missing_evidence": missing_fields,
            "truthfulness_rule": (
                "claim_only_durable_handoff_when_resume_drill_status_is_ready; "
                "never_claim_warm_or_hot_resume_without_separate_runtime_drill"
            ),
        },
        "next_action": _next_action(
            status=status,
            recovered=recovered,
            missing_required=missing_required,
            missing_recommended=missing_recommended,
        ),
    }


def _checkpoint_from_context(latest_context: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(latest_context, dict):
        return {}
    checkpoint = latest_context.get("continuation_checkpoint")
    if isinstance(checkpoint, dict):
        return checkpoint
    snapshot = latest_context.get("snapshot") if isinstance(latest_context.get("snapshot"), dict) else {}
    checkpoint = snapshot.get("continuation_checkpoint")
    return checkpoint if isinstance(checkpoint, dict) else {}


def _missing_required_fields(
    *,
    stored_session: Dict[str, Any],
    latest_context: Dict[str, Any],
    checkpoint: Dict[str, Any],
    recovered: Dict[str, Any],
) -> List[str]:
    missing: List[str] = []
    if not stored_session and not recovered.get("task"):
        missing.append("session_record")
    if not latest_context:
        missing.append("context_sync")
    if not checkpoint:
        missing.append("continuation_checkpoint")
        return missing
    if checkpoint.get("version") != "continuation-checkpoint.v1":
        missing.append("checkpoint.version")
    if checkpoint.get("resume_ready") is not True:
        missing.append("checkpoint.resume_ready")
    if not checkpoint.get("resume_mode"):
        missing.append("checkpoint.resume_mode")
    if recovered.get("context_revision") is None:
        missing.append("context_revision")
    if not recovered.get("task"):
        missing.append("task")
    if not recovered.get("goal_next_focus") and not recovered.get("open_plan_steps"):
        missing.append("goal_next_focus_or_open_plan_steps")
    if not recovered.get("open_plan_steps"):
        missing.append("open_plan_steps")
    last_result = recovered.get("last_result") if isinstance(recovered.get("last_result"), dict) else {}
    if (
        last_result.get("tool") is None
        and last_result.get("ok") is None
        and last_result.get("plan_verdict") is None
    ):
        missing.append("last_result")
    if not recovered.get("artifact_refs"):
        missing.append("artifact_refs")
    return missing


def _missing_recommended_fields(*, recovered: Dict[str, Any]) -> List[str]:
    missing: List[str] = []
    compression = recovered.get("compression") if isinstance(recovered.get("compression"), dict) else {}
    if not compression.get("summary"):
        missing.append("compression.summary")
    return missing


def _status(
    *,
    checkpoint: Dict[str, Any],
    latest_context: Dict[str, Any],
    missing_required: List[str],
) -> str:
    if not latest_context:
        return "missing"
    if checkpoint and checkpoint.get("resume_ready") is False:
        return "failed"
    if missing_required:
        return "partial"
    return "ready"


def _capability_levels(*, status: str, missing_fields: List[str]) -> Dict[str, Dict[str, Any]]:
    durable_status = "ready" if status == "ready" else status
    return {
        "durable_handoff": {
            "status": durable_status,
            "evidence": ["session_store", "context_sync", "continuation_checkpoint"],
            "missing_evidence": missing_fields,
            "claim": (
                "Persisted checkpoint can restore task, plan, last result, artifacts, and next action."
                if status == "ready"
                else "Durable handoff is not ready; missing evidence must be emitted first."
            ),
        },
        "warm_process": {
            "status": "unproven",
            "evidence": [],
            "missing_evidence": ["separate_warm_process_resume_drill"],
            "claim": "Not claimed by this store replay drill.",
        },
        "hot_tool_call": {
            "status": "unproven",
            "evidence": [],
            "missing_evidence": ["separate_in_process_tool_call_resurrection_drill"],
            "claim": "Not claimed by this store replay drill.",
        },
    }


def _next_action(
    *,
    status: str,
    recovered: Dict[str, Any],
    missing_required: List[str],
    missing_recommended: List[str],
) -> str:
    if status == "missing":
        return "Start or resume the session until a context_sync continuation checkpoint is persisted."
    if status == "failed":
        return "Emit a new continuation checkpoint with resume_ready=true after repairing the failed state."
    if status == "partial":
        return "Emit a new context_sync checkpoint with required fields: " + ", ".join(missing_required)
    open_steps = recovered.get("open_plan_steps") if isinstance(recovered.get("open_plan_steps"), list) else []
    if open_steps and isinstance(open_steps[0], dict):
        title = open_steps[0].get("title") or open_steps[0].get("id") or "next open plan step"
        if missing_recommended:
            return f"Continue with open plan step: {title}; also improve recommended evidence: {', '.join(missing_recommended)}."
        return f"Continue with open plan step: {title}."
    return str(recovered.get("goal_next_focus") or "Continue from recovered goal focus.")


def _event_counts(events: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("type") or "unknown")
        counts[event_type] = counts.get(event_type, 0) + 1
    return counts


def _list_of_dicts(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
