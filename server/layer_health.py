"""Compact health snapshots for Agent, Runtime, and Learning layers."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional


LAYER_HEALTH_VERSION = "layer-health.v1"
REQUIRED_LAYERS = ("agent", "runtime", "learning")
ACTIVE_STATES = {"active", "queued", "running"}
DONE_STATES = {"done", "skipped", "ready"}
ERROR_STATES = {"error", "failed", "crashed", "cancelled", "canceled"}


def build_layer_health_snapshot(
    *,
    session_id: str,
    session_status: Optional[Dict[str, Any]] = None,
    layer_summary: Optional[Dict[str, Any]] = None,
    runtime_metrics_summary: Optional[Dict[str, Any]] = None,
    learning_state: Optional[Dict[str, Any]] = None,
    learning_job: Optional[Dict[str, Any]] = None,
    event_bus_summary: Optional[Dict[str, Any]] = None,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Build one evidence packet for the three-layer runtime contract."""
    timestamp = float(now if now is not None else time.time())
    session_status = session_status if isinstance(session_status, dict) else {}
    layer_summary = layer_summary if isinstance(layer_summary, dict) else {}
    runtime_metrics_summary = runtime_metrics_summary if isinstance(runtime_metrics_summary, dict) else {}
    learning_state = learning_state if isinstance(learning_state, dict) else {}
    learning_job = learning_job if isinstance(learning_job, dict) else {}
    event_bus_summary = event_bus_summary if isinstance(event_bus_summary, dict) else {}

    latest_by_layer = (
        layer_summary.get("latest_by_layer")
        if isinstance(layer_summary.get("latest_by_layer"), dict)
        else {}
    )
    layers = {
        "agent": _agent_layer(latest_by_layer.get("agent"), session_status),
        "runtime": _runtime_layer(latest_by_layer.get("runtime"), runtime_metrics_summary),
        "learning": _learning_layer(latest_by_layer.get("learning"), learning_state, learning_job),
    }
    queue_depth = int(layers["learning"].get("queue_depth") or 0)
    failed_layers = [
        name
        for name, layer in layers.items()
        if layer.get("health") == "error"
    ]
    active_layers = [
        name
        for name, layer in layers.items()
        if layer.get("health") == "active"
    ]
    missing_layers = [
        name
        for name, layer in layers.items()
        if layer.get("health") == "missing"
    ]
    latency_ms = _max_latency(layers, runtime_metrics_summary)
    latency_budget_ms = 30_000.0
    latency_status = "warn" if latency_ms >= latency_budget_ms else "ok"
    observer_errors = int(event_bus_summary.get("observer_error_count") or 0)

    if failed_layers:
        status = "error"
    elif active_layers or queue_depth > 0:
        status = "active"
    elif missing_layers and (layer_summary.get("event_count") or 0) > 0:
        status = "degraded"
    elif missing_layers:
        status = "missing"
    else:
        status = "ready"
    if status == "ready" and (observer_errors or latency_status == "warn"):
        status = "degraded"

    return {
        "version": LAYER_HEALTH_VERSION,
        "session_id": session_id,
        "status": status,
        "source": "layer_events_runtime_metrics_learning_state",
        "checked_at": timestamp,
        "layers": layers,
        "summary": {
            "failed_layers": failed_layers,
            "active_layers": active_layers,
            "missing_layers": missing_layers,
            "learning_queue_depth": queue_depth,
            "max_latency_ms": latency_ms,
            "latency_budget_ms": latency_budget_ms,
            "latency_status": latency_status,
            "observer_error_count": observer_errors,
        },
        "communication_contract": _communication_contract(layer_summary),
        "control": {
            "status_rule": "error_if_any_layer_failed_active_if_any_layer_or_learning_queue_active_ready_when_all_required_layers_observed",
            "learning_queue_rule": "queued_or_running_learning_job_or_active_learning_layer_counts_as_depth_1",
            "latency_rule": "warn_when_any_observed_layer_latency_or_runtime_latency_reaches_30000ms",
            "truthfulness_rule": "missing_or_degraded_status_must_not_be reported_as_complete_layer_independence",
        },
    }


def _agent_layer(latest: Any, session_status: Dict[str, Any]) -> Dict[str, Any]:
    layer = _base_layer("agent", latest)
    status = str(session_status.get("status") or "").lower()
    if status in {"error"}:
        layer["health"] = "error"
        layer["error"] = session_status.get("error") or "session_error"
    elif status in {"canceled", "cancelled"}:
        layer["health"] = "error"
        layer["error"] = "session_cancelled"
    elif layer["state"] in ERROR_STATES:
        layer["health"] = "error"
    elif layer["state"] in ACTIVE_STATES or (status == "running" and not layer.get("event")):
        layer["health"] = "active"
    elif layer["state"] in DONE_STATES or status == "done":
        layer["health"] = "ready"
    elif not layer.get("event"):
        layer["health"] = "missing"
    return layer


def _runtime_layer(latest: Any, runtime_summary: Dict[str, Any]) -> Dict[str, Any]:
    layer = _base_layer("runtime", latest)
    metrics = layer.get("metrics") if isinstance(layer.get("metrics"), dict) else {}
    health_status = str(metrics.get("health_status") or "").lower()
    max_latency = runtime_summary.get("max_latency") if isinstance(runtime_summary.get("max_latency"), dict) else {}
    layer["runtime_event_count"] = runtime_summary.get("event_count", 0)
    layer["latency_ms"] = _number(metrics.get("elapsed_ms"), _number(max_latency.get("elapsed_ms"), 0.0))
    if health_status in {"crashed", "stalled"} or layer["state"] in ERROR_STATES:
        layer["health"] = "error"
        layer["error"] = health_status or metrics.get("error") or "runtime_error"
    elif health_status and health_status != "healthy":
        layer["health"] = "degraded"
        layer["error"] = health_status
    elif layer["state"] in ACTIVE_STATES:
        layer["health"] = "active"
    elif layer["state"] in DONE_STATES:
        layer["health"] = "ready"
    elif not layer.get("event") and runtime_summary.get("event_count"):
        layer["health"] = "ready"
        layer["event"] = "runtime.metrics.observed"
    elif not layer.get("event"):
        layer["health"] = "missing"
    return layer


def _learning_layer(latest: Any, learning_state: Dict[str, Any], learning_job: Dict[str, Any]) -> Dict[str, Any]:
    state_latest = _learning_latest(learning_state)
    layer = _base_layer("learning", latest or state_latest)
    if not layer.get("event") and state_latest:
        layer = _base_layer("learning", state_latest)
    job_status = str(learning_job.get("status") or "").lower()
    if not job_status:
        job_status = str(learning_state.get("state") or layer.get("state") or "").lower()
    queue_depth = 1 if job_status in {"queued", "running"} or layer.get("state") in ACTIVE_STATES else 0
    layer["queue_depth"] = queue_depth
    layer["job_status"] = job_status or "missing"
    layer["eligible"] = _first_present(learning_job.get("eligible"), learning_state.get("eligible"))
    layer["async"] = _first_present(learning_job.get("async"), learning_state.get("async"))
    layer["attempts"] = learning_job.get("attempts")
    layer["max_attempts"] = learning_job.get("max_attempts")
    layer["retryable"] = learning_job.get("retryable")
    layer["cancel_requested"] = learning_job.get("cancel_requested")
    layer["policy"] = learning_job.get("policy") if isinstance(learning_job.get("policy"), dict) else {}
    layer["insight_count"] = learning_job.get("insight_count")
    layer["shared_memory"] = (
        learning_job.get("shared_memory")
        if isinstance(learning_job.get("shared_memory"), dict)
        else {}
    )
    error = learning_job.get("error") or learning_state.get("error") or layer.get("metrics", {}).get("error")
    if job_status == "error" or layer["state"] in ERROR_STATES or error:
        layer["health"] = "error"
        layer["error"] = error or "learning_error"
    elif queue_depth:
        layer["health"] = "active"
    elif layer["state"] in DONE_STATES or job_status in {"done", "skipped"}:
        layer["health"] = "ready"
    elif not layer.get("event") and learning_state.get("status") in {"ready", "replay"}:
        layer["health"] = "ready"
        layer["event"] = learning_state.get("event") or "learning.state.observed"
    elif not layer.get("event"):
        layer["health"] = "missing"
    return layer


def _base_layer(name: str, latest: Any) -> Dict[str, Any]:
    latest = latest if isinstance(latest, dict) else {}
    metrics = latest.get("metrics") if isinstance(latest.get("metrics"), dict) else {}
    return {
        "name": name,
        "health": "missing",
        "state": str(latest.get("state") or "missing").lower(),
        "event": latest.get("event"),
        "detail": latest.get("detail"),
        "route": f"{latest.get('source_layer') or '-'}->{latest.get('target_layer') or '-'}",
        "source_layer": latest.get("source_layer"),
        "target_layer": latest.get("target_layer"),
        "cause": latest.get("cause"),
        "timestamp": latest.get("timestamp"),
        "latency_ms": _number(metrics.get("elapsed_ms"), 0.0),
        "metrics": metrics,
        "error": metrics.get("error"),
    }


def _learning_latest(learning_state: Dict[str, Any]) -> Dict[str, Any]:
    latest = learning_state.get("latest") if isinstance(learning_state.get("latest"), dict) else {}
    if latest:
        metrics = latest.get("metrics") if isinstance(latest.get("metrics"), dict) else {}
        return {
            "state": latest.get("state"),
            "event": latest.get("event"),
            "detail": latest.get("detail"),
            "source_layer": latest.get("source_layer"),
            "target_layer": latest.get("target_layer"),
            "cause": latest.get("cause"),
            "metrics": metrics,
            "timestamp": latest.get("timestamp"),
        }
    if learning_state.get("event") or learning_state.get("state"):
        return {
            "state": learning_state.get("state"),
            "event": learning_state.get("event"),
            "detail": learning_state.get("detail"),
            "source_layer": learning_state.get("source_layer"),
            "target_layer": learning_state.get("target_layer"),
            "cause": learning_state.get("cause"),
            "metrics": {
                "async": learning_state.get("async"),
                "eligible": learning_state.get("eligible"),
                "elapsed_ms": learning_state.get("elapsed_ms"),
                "error": learning_state.get("error"),
            },
            "timestamp": learning_state.get("timestamp"),
        }
    return {}


def _communication_contract(layer_summary: Dict[str, Any]) -> Dict[str, Any]:
    recent_routes = layer_summary.get("recent_routes") if isinstance(layer_summary.get("recent_routes"), list) else []
    observed = {
        str(item.get("route"))
        for item in recent_routes
        if isinstance(item, dict) and item.get("route")
    }
    expected = [
        {"from": "user", "to": "agent", "route": "user->agent"},
        {"from": "agent", "to": "runtime", "route": "agent->runtime"},
        {"from": "runtime", "to": "learning", "route": "runtime->learning"},
        {"from": "learning", "to": "storage", "route": "learning->storage"},
    ]
    return {
        "expected_routes": [
            {**route, "observed": route["route"] in observed}
            for route in expected
        ],
        "recent_routes": recent_routes[-6:],
    }


def _max_latency(layers: Dict[str, Dict[str, Any]], runtime_summary: Dict[str, Any]) -> float:
    values = [_number(layer.get("latency_ms"), 0.0) for layer in layers.values()]
    max_latency = runtime_summary.get("max_latency") if isinstance(runtime_summary.get("max_latency"), dict) else {}
    values.append(_number(max_latency.get("elapsed_ms"), 0.0))
    return max(values or [0.0])


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None
