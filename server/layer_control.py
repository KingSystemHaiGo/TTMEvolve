"""Engineering-control signals derived from layer health evidence."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


LAYER_CONTROL_VERSION = "layer-control.v1"

DEFAULT_THRESHOLDS = {
    "max_latency_warn_ms": 30_000.0,
    "max_latency_block_ms": 60_000.0,
    "learning_queue_warn_depth": 1,
    "learning_queue_block_depth": 3,
    "observer_error_warn_count": 1,
    "observer_error_block_count": 3,
}

SEVERITY_RANK = {
    "ok": 0,
    "watch": 1,
    "warn": 2,
    "critical": 3,
}


def build_layer_control_snapshot(
    *,
    layer_health: Optional[Dict[str, Any]],
    thresholds: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Convert layer-health facts into control signals and corrective actions."""
    layer_health = layer_health if isinstance(layer_health, dict) else {}
    merged_thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    session_id = layer_health.get("session_id")
    summary = layer_health.get("summary") if isinstance(layer_health.get("summary"), dict) else {}
    layers = layer_health.get("layers") if isinstance(layer_health.get("layers"), dict) else {}
    contract = (
        layer_health.get("communication_contract")
        if isinstance(layer_health.get("communication_contract"), dict)
        else {}
    )

    signals: List[Dict[str, Any]] = []
    actions: List[Dict[str, Any]] = []

    for layer_name in summary.get("failed_layers") or []:
        layer = layers.get(layer_name) if isinstance(layers.get(layer_name), dict) else {}
        _add_signal(
            signals,
            actions,
            signal_id=f"{layer_name}_layer_failed",
            severity="critical",
            status="fail",
            owner_layer=layer_name,
            metric="layer.health",
            observed=layer.get("health") or "error",
            threshold="no_failed_layers",
            action="block_completion_and_surface_error",
            reason=f"{layer_name} layer reported failure.",
            evidence=[_layer_evidence(layer_name, layer)],
        )

    for layer_name in summary.get("missing_layers") or []:
        layer = layers.get(layer_name) if isinstance(layers.get(layer_name), dict) else {}
        severity = "warn" if layer_health.get("status") != "missing" else "watch"
        _add_signal(
            signals,
            actions,
            signal_id=f"{layer_name}_layer_missing",
            severity=severity,
            status="missing",
            owner_layer=layer_name,
            metric="layer.event",
            observed=layer.get("event") or "missing",
            threshold="one_recent_layer_event",
            action="emit_layer_event_or_mark_unobserved",
            reason=f"{layer_name} has no recent layer event evidence.",
            evidence=[_layer_evidence(layer_name, layer)],
        )

    latency_ms = _number(summary.get("max_latency_ms"), 0.0)
    latency_warn = _number(merged_thresholds.get("max_latency_warn_ms"), 30_000.0)
    latency_block = _number(merged_thresholds.get("max_latency_block_ms"), latency_warn * 2)
    if latency_ms >= latency_block:
        _add_signal(
            signals,
            actions,
            signal_id="layer_latency_block",
            severity="critical",
            status="fail",
            owner_layer="runtime",
            metric="summary.max_latency_ms",
            observed=latency_ms,
            threshold=latency_block,
            action="stop_claiming_responsive_and_profile_slowest_phase",
            reason="Layer latency reached the block threshold.",
            evidence=[{"path": "layer_health.summary.max_latency_ms", "value": latency_ms}],
        )
    elif latency_ms >= latency_warn:
        _add_signal(
            signals,
            actions,
            signal_id="layer_latency_warn",
            severity="warn",
            status="warn",
            owner_layer="runtime",
            metric="summary.max_latency_ms",
            observed=latency_ms,
            threshold=latency_warn,
            action="profile_slowest_layer_before_next_large_task",
            reason="Layer latency reached the warning threshold.",
            evidence=[{"path": "layer_health.summary.max_latency_ms", "value": latency_ms}],
        )

    queue_depth = int(_number(summary.get("learning_queue_depth"), 0.0))
    queue_warn = int(_number(merged_thresholds.get("learning_queue_warn_depth"), 1))
    queue_block = int(_number(merged_thresholds.get("learning_queue_block_depth"), 3))
    if queue_depth >= queue_block:
        _add_signal(
            signals,
            actions,
            signal_id="learning_queue_block",
            severity="critical",
            status="fail",
            owner_layer="learning",
            metric="summary.learning_queue_depth",
            observed=queue_depth,
            threshold=queue_block,
            action="drain_or_cancel_learning_jobs_before_more_background_work",
            reason="Learning queue depth reached the block threshold.",
            evidence=[{"path": "layer_health.summary.learning_queue_depth", "value": queue_depth}],
        )
    elif queue_depth >= queue_warn:
        _add_signal(
            signals,
            actions,
            signal_id="learning_queue_watch",
            severity="watch",
            status="watch",
            owner_layer="learning",
            metric="summary.learning_queue_depth",
            observed=queue_depth,
            threshold=queue_warn,
            action="monitor_learning_queue_until_it_returns_to_zero",
            reason="Learning work is still queued or running.",
            evidence=[{"path": "layer_health.summary.learning_queue_depth", "value": queue_depth}],
        )

    observer_errors = int(_number(summary.get("observer_error_count"), 0.0))
    observer_warn = int(_number(merged_thresholds.get("observer_error_warn_count"), 1))
    observer_block = int(_number(merged_thresholds.get("observer_error_block_count"), 3))
    if observer_errors >= observer_block:
        _add_signal(
            signals,
            actions,
            signal_id="observer_errors_block",
            severity="critical",
            status="fail",
            owner_layer="runtime",
            metric="summary.observer_error_count",
            observed=observer_errors,
            threshold=observer_block,
            action="fix_runtime_event_bus_observers_before_trusting_evidence",
            reason="Observer failures reached the block threshold.",
            evidence=[{"path": "layer_health.summary.observer_error_count", "value": observer_errors}],
        )
    elif observer_errors >= observer_warn:
        _add_signal(
            signals,
            actions,
            signal_id="observer_errors_warn",
            severity="warn",
            status="warn",
            owner_layer="runtime",
            metric="summary.observer_error_count",
            observed=observer_errors,
            threshold=observer_warn,
            action="inspect_last_observer_error_and_retry_observer_path",
            reason="RuntimeEventBus observer errors were observed.",
            evidence=[{"path": "layer_health.summary.observer_error_count", "value": observer_errors}],
        )

    missing_routes = _missing_expected_routes(contract)
    for route in missing_routes:
        severity = _missing_route_severity(str(layer_health.get("status") or "missing"))
        _add_signal(
            signals,
            actions,
            signal_id=f"missing_route_{route.get('route', '').replace('->', '_to_')}",
            severity=severity,
            status="missing",
            owner_layer=route.get("from") or "runtime",
            metric="communication_contract.expected_routes",
            observed=False,
            threshold=route.get("route"),
            action="capture_or_emit_missing_layer_route_evidence",
            reason=f"Expected route {route.get('route')} was not observed in recent layer events.",
            evidence=[{"path": "layer_health.communication_contract.expected_routes", "route": route.get("route")}],
        )

    status = _status_from_signals(signals)
    decision = {
        "ready": "continue",
        "watch": "continue_with_monitoring",
        "needs_action": "correct_before_claiming_ready",
        "blocked": "block_completion_claims",
    }[status]
    missing_evidence = [
        signal.get("id")
        for signal in signals
        if signal.get("status") == "missing"
    ]

    return {
        "version": LAYER_CONTROL_VERSION,
        "session_id": session_id,
        "status": status,
        "decision": decision,
        "source": "layer_health",
        "thresholds": merged_thresholds,
        "signals": signals,
        "corrective_actions": sorted(actions, key=lambda item: item.get("priority", 99)),
        "closure_gate": {
            "can_claim_layer_independence": status == "ready",
            "can_continue_user_task": status != "blocked",
            "missing_evidence": missing_evidence,
            "truthfulness_rule": "do_not_claim_layer_independence_ready_unless_layer_control_status_is_ready",
        },
        "control_rule": (
            "critical_signals_block_claims_warn_signals_require_correction_"
            "watch_signals_allow_progress_with_monitoring"
        ),
    }


def _add_signal(
    signals: List[Dict[str, Any]],
    actions: List[Dict[str, Any]],
    *,
    signal_id: str,
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
        "priority": _priority_for_severity(severity),
        "owner_layer": owner_layer,
        "reason": reason,
        "evidence": evidence,
    })


def _missing_expected_routes(contract: Dict[str, Any]) -> List[Dict[str, Any]]:
    expected = contract.get("expected_routes") if isinstance(contract.get("expected_routes"), list) else []
    return [
        item
        for item in expected
        if isinstance(item, dict) and item.get("observed") is not True
    ]


def _missing_route_severity(layer_status: str) -> str:
    if layer_status in {"ready", "degraded", "error"}:
        return "warn"
    return "watch"


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


def _layer_evidence(layer_name: str, layer: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "path": f"layer_health.layers.{layer_name}",
        "health": layer.get("health"),
        "event": layer.get("event"),
        "state": layer.get("state"),
        "error": layer.get("error"),
    }


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default
