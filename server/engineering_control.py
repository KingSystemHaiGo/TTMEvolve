"""Engineering-control signals beyond layer health.

This module turns public runtime evidence into corrective actions for
memory/RAG recall, repeated tool failures, and plan-gate failures. It stays
pure so evidence endpoints can use it without coupling to ReActLoop internals.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


ENGINEERING_CONTROL_VERSION = "engineering-control.v1"

DEFAULT_THRESHOLDS = {
    "memory_miss_watch_events": 1,
    "memory_miss_warn_events": 2,
    "memory_miss_block_events": 5,
    "context_build_warn_ms": 1_500.0,
    "context_build_block_ms": 5_000.0,
    "cold_recall_warn_ms": 1_000.0,
    "cold_recall_block_ms": 3_000.0,
    "tool_failure_warn_count": 2,
    "tool_failure_block_count": 4,
    "same_tool_failure_warn_count": 2,
    "same_tool_failure_block_count": 3,
}

SEVERITY_RANK = {
    "ok": 0,
    "watch": 1,
    "warn": 2,
    "critical": 3,
}


def build_engineering_control_snapshot(
    *,
    session_id: Optional[str] = None,
    layer_control: Optional[Dict[str, Any]] = None,
    memory_recall: Optional[Dict[str, Any]] = None,
    runtime_metrics_summary: Optional[Dict[str, Any]] = None,
    project_state: Optional[Dict[str, Any]] = None,
    cos_gate: Optional[Dict[str, Any]] = None,
    recent_events: Optional[List[Dict[str, Any]]] = None,
    thresholds: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build compact engineering-control signals from public evidence."""
    layer_control = layer_control if isinstance(layer_control, dict) else {}
    memory_recall = memory_recall if isinstance(memory_recall, dict) else {}
    runtime_metrics_summary = runtime_metrics_summary if isinstance(runtime_metrics_summary, dict) else {}
    project_state = project_state if isinstance(project_state, dict) else {}
    cos_gate = cos_gate if isinstance(cos_gate, dict) else {}
    recent_events = recent_events if isinstance(recent_events, list) else []
    merged_thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}

    signals: List[Dict[str, Any]] = []
    actions: List[Dict[str, Any]] = []

    _add_memory_signals(
        signals,
        actions,
        memory_recall=memory_recall,
        thresholds=merged_thresholds,
    )
    tool_failures = summarize_tool_failures(recent_events)
    _add_tool_failure_signals(
        signals,
        actions,
        tool_failures=tool_failures,
        thresholds=merged_thresholds,
    )
    plan_gates = summarize_plan_gate_events(recent_events, project_state=project_state)
    _add_plan_gate_signals(
        signals,
        actions,
        plan_gates=plan_gates,
    )

    status = _status_from_signals(signals)
    decision = {
        "ready": "continue",
        "watch": "continue_with_monitoring",
        "needs_action": "correct_before_claiming_ready",
        "blocked": "pause_side_effects_until_control_signal_is_repaired",
    }[status]
    memory_signal_ids = [
        signal.get("id")
        for signal in signals
        if str(signal.get("domain") or "") == "memory_rag"
    ]
    plan_signal_ids = [
        signal.get("id")
        for signal in signals
        if str(signal.get("domain") or "") == "plan_gate"
    ]
    blocking_signal_ids = [
        signal.get("id")
        for signal in signals
        if signal.get("severity") == "critical"
    ]
    missing_evidence = [
        signal.get("id")
        for signal in signals
        if signal.get("status") == "missing"
    ]

    return {
        "version": ENGINEERING_CONTROL_VERSION,
        "session_id": session_id,
        "status": status,
        "decision": decision,
        "source": "layer_control_memory_recall_runtime_events_project_state",
        "thresholds": merged_thresholds,
        "summary": {
            "layer_control_status": layer_control.get("status") or "missing",
            "memory_recall_status": memory_recall.get("status") or "missing",
            "memory_event_count": int(_number(memory_recall.get("event_count"), 0)),
            "memory_total_hits": _memory_total_hits(memory_recall),
            "tool_failure_count": tool_failures.get("failure_count", 0),
            "latest_tool_failure": tool_failures.get("latest"),
            "plan_verdict": plan_gates.get("latest_verdict")
                or project_state.get("plan_verdict")
                or "missing",
            "cos_gate_mode": cos_gate.get("mode") or cos_gate.get("status") or "missing",
        },
        "signals": signals,
        "corrective_actions": sorted(actions, key=lambda item: item.get("priority", 99)),
        "tool_failures": tool_failures,
        "plan_gates": plan_gates,
        "closure_gate": {
            "can_claim_engineering_control_ready": status == "ready",
            "can_continue_user_task": not blocking_signal_ids,
            "can_claim_memory_rag_optimized": not memory_signal_ids and memory_recall.get("status") in {"ready", "replay"},
            "can_claim_plan_control_ready": not plan_signal_ids,
            "missing_evidence": missing_evidence,
            "blocking_signals": blocking_signal_ids,
            "truthfulness_rule": (
                "do_not_claim_memory_rag_tooling_or_plan_control_ready_unless_"
                "engineering_control_status_is_ready"
            ),
        },
        "control_rule": (
            "plan_failures_and_repeated_tool_failures_block_side_effects_"
            "memory_misses_or_latency_require_correction_before_optimization_claims"
        ),
    }


def summarize_tool_failures(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Summarize failed observation events without reading private trajectory."""
    failures: List[Dict[str, Any]] = []
    by_tool: Dict[str, int] = {}
    by_failure_type: Dict[str, int] = {}
    for event in events:
        if not isinstance(event, dict) or event.get("type") != "observation":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        observation = payload.get("observation") if isinstance(payload.get("observation"), dict) else {}
        if not observation:
            continue
        ok = observation.get("ok")
        failure_type = (
            observation.get("failure_type")
            or observation.get("error_type")
            or ("tool_failed" if ok is False else None)
        )
        if ok is not False and not failure_type:
            continue
        tool = str(payload.get("tool") or observation.get("tool") or "unknown")
        failure_key = str(failure_type or "tool_failed")
        item = {
            "tool": tool,
            "failure_type": failure_key,
            "error": observation.get("error"),
            "iteration": payload.get("iteration"),
            "timestamp": event.get("created_at") or (event.get("meta") or {}).get("timestamp")
                if isinstance(event.get("meta"), dict)
                else event.get("created_at"),
        }
        failures.append(item)
        by_tool[tool] = by_tool.get(tool, 0) + 1
        by_failure_type[failure_key] = by_failure_type.get(failure_key, 0) + 1

    repeated_tool = _max_key(by_tool)
    repeated_failure_type = _max_key(by_failure_type)
    return {
        "failure_count": len(failures),
        "by_tool": by_tool,
        "by_failure_type": by_failure_type,
        "most_failed_tool": repeated_tool,
        "most_common_failure_type": repeated_failure_type,
        "latest": failures[-1] if failures else {},
        "history": failures[-8:],
    }


def summarize_plan_gate_events(
    events: List[Dict[str, Any]],
    *,
    project_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Summarize plan-validation verdicts from session events."""
    project_state = project_state if isinstance(project_state, dict) else {}
    verdicts: List[Dict[str, Any]] = []
    counts: Dict[str, int] = {}
    for event in events:
        if not isinstance(event, dict) or event.get("type") != "plan_validation":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        verdict = str(payload.get("verdict") or "").strip()
        if not verdict:
            continue
        item = {
            "verdict": verdict,
            "summary": payload.get("summary"),
            "issues_count": len(payload.get("issues") or []) if isinstance(payload.get("issues"), list) else payload.get("issues_count"),
            "timestamp": event.get("created_at") or (event.get("meta") or {}).get("timestamp")
                if isinstance(event.get("meta"), dict)
                else event.get("created_at"),
        }
        verdicts.append(item)
        counts[verdict] = counts.get(verdict, 0) + 1

    latest_verdict = verdicts[-1].get("verdict") if verdicts else project_state.get("plan_verdict")
    if latest_verdict:
        counts[str(latest_verdict)] = max(counts.get(str(latest_verdict), 0), 1)
    goal_overall = project_state.get("goal_overall")
    return {
        "event_count": len(verdicts),
        "counts": counts,
        "latest_verdict": latest_verdict,
        "latest": verdicts[-1] if verdicts else {},
        "goal_overall": goal_overall,
        "history": verdicts[-8:],
    }


def _add_memory_signals(
    signals: List[Dict[str, Any]],
    actions: List[Dict[str, Any]],
    *,
    memory_recall: Dict[str, Any],
    thresholds: Dict[str, Any],
) -> None:
    status = str(memory_recall.get("status") or "missing")
    if status == "error":
        _add_signal(
            signals,
            actions,
            signal_id="memory_recall_observer_error",
            domain="memory_rag",
            severity="warn",
            status="fail",
            owner_layer="runtime",
            metric="memory_recall.status",
            observed=status,
            threshold="ready_or_replay",
            action="fix_memory_recall_observer_before_claiming_rag_evidence",
            reason="Memory/RAG observer returned an error.",
            evidence=[{"path": "memory_recall.error", "value": memory_recall.get("error")}],
        )
        return
    if status not in {"ready", "replay", "not_requested"}:
        _add_signal(
            signals,
            actions,
            signal_id="memory_recall_sample_missing",
            domain="memory_rag",
            severity="watch",
            status="missing",
            owner_layer="runtime",
            metric="memory_recall.status",
            observed=status,
            threshold="one_context_budget_sample",
            action="emit_context_budget_or_pull_runtime_metrics_before_memory_claims",
            reason="No memory/RAG recall sample is available for this session.",
            evidence=[{"path": "memory_recall.status", "value": status}],
        )
        return

    event_count = int(_number(memory_recall.get("event_count"), 0))
    total_hits = _memory_total_hits(memory_recall)
    if event_count >= int(_number(thresholds.get("memory_miss_block_events"), 5)) and total_hits <= 0:
        severity = "critical"
        action = "rebuild_or_reseed_memory_index_before_continuing_long_task"
        reason = "Repeated memory/RAG samples produced zero recall hits."
    elif event_count >= int(_number(thresholds.get("memory_miss_warn_events"), 2)) and total_hits <= 0:
        severity = "warn"
        action = "inspect_memory_profiles_and_rag_index_before_optimization_claims"
        reason = "Memory/RAG recall has repeated zero-hit samples."
    elif event_count >= int(_number(thresholds.get("memory_miss_watch_events"), 1)) and total_hits <= 0:
        severity = "watch"
        action = "monitor_next_memory_recall_sample_for_hits"
        reason = "Latest memory/RAG recall has no hits yet."
    else:
        severity = ""
        action = ""
        reason = ""
    if severity:
        _add_signal(
            signals,
            actions,
            signal_id="memory_recall_zero_hits",
            domain="memory_rag",
            severity=severity,
            status="miss",
            owner_layer="runtime",
            metric="memory_recall.totals.total_hits",
            observed=total_hits,
            threshold=">0",
            action=action,
            reason=reason,
            evidence=[
                {"path": "memory_recall.event_count", "value": event_count},
                {"path": "memory_recall.totals", "value": memory_recall.get("totals")},
            ],
        )

    latency = memory_recall.get("max_latency") if isinstance(memory_recall.get("max_latency"), dict) else {}
    _add_latency_signal(
        signals,
        actions,
        signal_id="memory_context_build_latency",
        owner_layer="runtime",
        metric="memory_recall.max_latency.context_build_ms",
        observed=_number(latency.get("context_build_ms"), 0),
        warn_threshold=_number(thresholds.get("context_build_warn_ms"), 1_500.0),
        block_threshold=_number(thresholds.get("context_build_block_ms"), 5_000.0),
        action_warn="profile_memory_context_builder_and_trim_context_sources",
        action_block="stop_long_task_and_fix_context_builder_latency",
        reason_warn="Memory context build latency reached the warning threshold.",
        reason_block="Memory context build latency reached the block threshold.",
    )
    _add_latency_signal(
        signals,
        actions,
        signal_id="cold_recall_latency",
        owner_layer="runtime",
        metric="memory_recall.max_latency.cold_recall_ms",
        observed=_number(latency.get("cold_recall_ms"), 0),
        warn_threshold=_number(thresholds.get("cold_recall_warn_ms"), 1_000.0),
        block_threshold=_number(thresholds.get("cold_recall_block_ms"), 3_000.0),
        action_warn="profile_cold_memory_recall_and_index_filters",
        action_block="fix_cold_memory_recall_latency_before_large_context_runs",
        reason_warn="Cold-memory recall latency reached the warning threshold.",
        reason_block="Cold-memory recall latency reached the block threshold.",
    )


def _add_tool_failure_signals(
    signals: List[Dict[str, Any]],
    actions: List[Dict[str, Any]],
    *,
    tool_failures: Dict[str, Any],
    thresholds: Dict[str, Any],
) -> None:
    failure_count = int(_number(tool_failures.get("failure_count"), 0))
    warn_count = int(_number(thresholds.get("tool_failure_warn_count"), 2))
    block_count = int(_number(thresholds.get("tool_failure_block_count"), 4))
    if failure_count >= block_count:
        _add_signal(
            signals,
            actions,
            signal_id="repeated_tool_failures_block",
            domain="tooling",
            severity="critical",
            status="fail",
            owner_layer="core_runtime",
            metric="tool_failures.failure_count",
            observed=failure_count,
            threshold=block_count,
            action="pause_side_effects_and_fix_repeated_tool_failure_pattern",
            reason="Repeated tool failures reached the block threshold.",
            evidence=[{"path": "tool_failures", "value": _compact_tool_failure_summary(tool_failures)}],
        )
    elif failure_count >= warn_count:
        _add_signal(
            signals,
            actions,
            signal_id="repeated_tool_failures_warn",
            domain="tooling",
            severity="warn",
            status="warn",
            owner_layer="core_runtime",
            metric="tool_failures.failure_count",
            observed=failure_count,
            threshold=warn_count,
            action="inspect_latest_tool_failure_before_retrying",
            reason="Repeated tool failures were observed.",
            evidence=[{"path": "tool_failures", "value": _compact_tool_failure_summary(tool_failures)}],
        )

    most_failed = tool_failures.get("most_failed_tool") if isinstance(tool_failures.get("most_failed_tool"), dict) else {}
    same_tool_count = int(_number(most_failed.get("count"), 0))
    same_warn = int(_number(thresholds.get("same_tool_failure_warn_count"), 2))
    same_block = int(_number(thresholds.get("same_tool_failure_block_count"), 3))
    if same_tool_count >= same_block:
        severity = "critical"
        action = "stop_repeating_same_tool_and_change_params_or_tool"
        reason = "The same tool failed repeatedly."
    elif same_tool_count >= same_warn:
        severity = "warn"
        action = "change_same_tool_params_or_select_alternative_tool_before_retry"
        reason = "The same tool failed more than once."
    else:
        return
    _add_signal(
        signals,
        actions,
        signal_id="same_tool_repeated_failure",
        domain="tooling",
        severity=severity,
        status="fail",
        owner_layer="agent",
        metric="tool_failures.by_tool",
        observed=same_tool_count,
        threshold=same_block if severity == "critical" else same_warn,
        action=action,
        reason=reason,
        evidence=[{"path": "tool_failures.most_failed_tool", "value": most_failed}],
    )


def _add_plan_gate_signals(
    signals: List[Dict[str, Any]],
    actions: List[Dict[str, Any]],
    *,
    plan_gates: Dict[str, Any],
) -> None:
    verdict = str(plan_gates.get("latest_verdict") or "")
    goal_overall = str(plan_gates.get("goal_overall") or "")
    if verdict == "fail":
        _add_signal(
            signals,
            actions,
            signal_id="plan_gate_failed",
            domain="plan_gate",
            severity="critical",
            status="fail",
            owner_layer="agent",
            metric="plan_gates.latest_verdict",
            observed=verdict,
            threshold="pass_or_warn",
            action="repair_failed_plan_gate_before_more_side_effects",
            reason="Plan validation failed.",
            evidence=[{"path": "plan_gates.latest", "value": plan_gates.get("latest")}],
        )
    elif verdict == "warn":
        _add_signal(
            signals,
            actions,
            signal_id="plan_gate_warn",
            domain="plan_gate",
            severity="warn",
            status="warn",
            owner_layer="agent",
            metric="plan_gates.latest_verdict",
            observed=verdict,
            threshold="pass",
            action="resolve_plan_warning_before_claiming_project_ready",
            reason="Plan validation reported a warning.",
            evidence=[{"path": "plan_gates.latest", "value": plan_gates.get("latest")}],
        )
    if goal_overall == "fail":
        _add_signal(
            signals,
            actions,
            signal_id="goal_gate_failed",
            domain="plan_gate",
            severity="critical",
            status="fail",
            owner_layer="agent",
            metric="project_state.goal_overall",
            observed=goal_overall,
            threshold="done_or_active",
            action="repair_failed_goal_criteria_before_completion_claim",
            reason="Goal checklist reported failing criteria.",
            evidence=[{"path": "project_state.goal_overall", "value": goal_overall}],
        )


def _add_latency_signal(
    signals: List[Dict[str, Any]],
    actions: List[Dict[str, Any]],
    *,
    signal_id: str,
    owner_layer: str,
    metric: str,
    observed: float,
    warn_threshold: float,
    block_threshold: float,
    action_warn: str,
    action_block: str,
    reason_warn: str,
    reason_block: str,
) -> None:
    if observed <= 0:
        return
    if observed >= block_threshold:
        severity = "critical"
        threshold = block_threshold
        action = action_block
        reason = reason_block
    elif observed >= warn_threshold:
        severity = "warn"
        threshold = warn_threshold
        action = action_warn
        reason = reason_warn
    else:
        return
    _add_signal(
        signals,
        actions,
        signal_id=signal_id,
        domain="memory_rag",
        severity=severity,
        status="slow",
        owner_layer=owner_layer,
        metric=metric,
        observed=observed,
        threshold=threshold,
        action=action,
        reason=reason,
        evidence=[{"path": metric, "value": observed}],
    )


def _add_signal(
    signals: List[Dict[str, Any]],
    actions: List[Dict[str, Any]],
    *,
    signal_id: str,
    domain: str,
    severity: str,
    status: str,
    owner_layer: Any,
    metric: str,
    observed: Any,
    threshold: Any,
    action: str,
    reason: str,
    evidence: List[Dict[str, Any]],
) -> None:
    signal = {
        "id": signal_id,
        "domain": domain,
        "severity": severity,
        "status": status,
        "owner_layer": owner_layer,
        "metric": metric,
        "observed": observed,
        "threshold": threshold,
        "action": action,
        "reason": reason,
        "evidence": evidence,
    }
    signals.append(signal)
    actions.append({
        "id": action,
        "source": "engineering_control",
        "signal_id": signal_id,
        "priority": _priority_for_severity(severity),
        "owner_layer": owner_layer,
        "domain": domain,
        "reason": reason,
        "evidence": evidence,
    })


def _status_from_signals(signals: List[Dict[str, Any]]) -> str:
    worst = 0
    for signal in signals:
        worst = max(worst, SEVERITY_RANK.get(str(signal.get("severity")), 0))
    if worst >= SEVERITY_RANK["critical"]:
        return "blocked"
    if worst >= SEVERITY_RANK["warn"]:
        return "needs_action"
    if worst >= SEVERITY_RANK["watch"]:
        return "watch"
    return "ready"


def _priority_for_severity(severity: str) -> int:
    if severity == "critical":
        return 0
    if severity == "warn":
        return 1
    if severity == "watch":
        return 2
    return 3


def _memory_total_hits(memory_recall: Dict[str, Any]) -> float:
    totals = memory_recall.get("totals") if isinstance(memory_recall.get("totals"), dict) else {}
    return _number(totals.get("agents_md_hits"), 0) + _number(totals.get("cold_recall_hits"), 0)


def _compact_tool_failure_summary(tool_failures: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "failure_count": tool_failures.get("failure_count", 0),
        "most_failed_tool": tool_failures.get("most_failed_tool"),
        "most_common_failure_type": tool_failures.get("most_common_failure_type"),
        "latest": tool_failures.get("latest"),
    }


def _max_key(counts: Dict[str, int]) -> Dict[str, Any]:
    if not counts:
        return {}
    key = max(counts, key=lambda item: counts[item])
    return {"key": key, "count": counts[key]}


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default
