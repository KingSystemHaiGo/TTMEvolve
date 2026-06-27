from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from server.layer_health import build_layer_health_snapshot


def _layer_summary(*, agent_state: str = "done", runtime_state: str = "done", learning_state: str = "done"):
    return {
        "event_count": 3,
        "latest_by_layer": {
            "agent": {
                "layer": "agent",
                "state": agent_state,
                "event": "agent.run.finished",
                "source_layer": "agent",
                "target_layer": "runtime",
                "metrics": {"elapsed_ms": 12.0},
            },
            "runtime": {
                "layer": "runtime",
                "state": runtime_state,
                "event": "runtime.audit.finished",
                "source_layer": "runtime",
                "target_layer": "learning",
                "metrics": {"health_status": "healthy"},
            },
            "learning": {
                "layer": "learning",
                "state": learning_state,
                "event": "learning.reflection.finished",
                "source_layer": "learning",
                "target_layer": "storage",
                "metrics": {"elapsed_ms": 9.0, "async": True},
            },
        },
        "recent_routes": [
            {"route": "agent->runtime", "layer": "agent"},
            {"route": "runtime->learning", "layer": "runtime"},
            {"route": "learning->storage", "layer": "learning"},
        ],
    }


def test_layer_health_ready_when_all_layers_finished_without_failures():
    snapshot = build_layer_health_snapshot(
        session_id="layer-ready",
        session_status={"status": "done", "done": True},
        layer_summary=_layer_summary(),
        runtime_metrics_summary={
            "event_count": 2,
            "max_latency": {"elapsed_ms": 22.0, "phase": "tool"},
        },
        learning_state={
            "status": "ready",
            "latest": {
                "event": "learning.reflection.finished",
                "state": "done",
                "metrics": {"elapsed_ms": 9.0},
            },
        },
        learning_job={"status": "done", "elapsed_ms": 9.0, "insight_count": 2},
        event_bus_summary={"observer_error_count": 0},
        now=100.0,
    )

    assert snapshot["status"] == "ready"
    assert snapshot["layers"]["agent"]["health"] == "ready"
    assert snapshot["layers"]["runtime"]["health"] == "ready"
    assert snapshot["layers"]["learning"]["health"] == "ready"
    assert snapshot["layers"]["learning"]["queue_depth"] == 0
    assert snapshot["summary"]["max_latency_ms"] == 22.0
    assert snapshot["communication_contract"]["expected_routes"][1]["observed"] is True


def test_layer_health_reports_active_learning_queue_depth():
    snapshot = build_layer_health_snapshot(
        session_id="layer-active",
        session_status={"status": "running", "done": False},
        layer_summary=_layer_summary(agent_state="done", runtime_state="done", learning_state="active"),
        runtime_metrics_summary={"event_count": 1, "max_latency": {"elapsed_ms": 3.0}},
        learning_state={
            "status": "ready",
            "event": "learning.reflection.started",
            "state": "active",
            "async": True,
            "eligible": True,
        },
        learning_job={
            "status": "queued",
            "eligible": True,
            "async": True,
            "attempts": 0,
            "max_attempts": 2,
            "retryable": False,
            "cancel_requested": False,
            "policy": {"managed": True},
        },
        event_bus_summary={"observer_error_count": 0},
        now=101.0,
    )

    assert snapshot["status"] == "active"
    assert snapshot["layers"]["learning"]["health"] == "active"
    assert snapshot["layers"]["learning"]["queue_depth"] == 1
    assert snapshot["layers"]["learning"]["max_attempts"] == 2
    assert snapshot["layers"]["learning"]["policy"]["managed"] is True
    assert snapshot["summary"]["learning_queue_depth"] == 1
    assert snapshot["summary"]["active_layers"] == ["learning"]


def test_layer_health_marks_runtime_error_and_observer_degradation():
    error_snapshot = build_layer_health_snapshot(
        session_id="layer-error",
        session_status={"status": "running", "done": False},
        layer_summary=_layer_summary(runtime_state="error"),
        runtime_metrics_summary={"event_count": 1, "max_latency": {"elapsed_ms": 45_000.0}},
        learning_state={"status": "missing"},
        learning_job={"status": "missing"},
        event_bus_summary={"observer_error_count": 0},
        now=102.0,
    )
    degraded_snapshot = build_layer_health_snapshot(
        session_id="layer-degraded",
        session_status={"status": "done", "done": True},
        layer_summary=_layer_summary(),
        runtime_metrics_summary={"event_count": 1, "max_latency": {"elapsed_ms": 4.0}},
        learning_state={"status": "ready"},
        learning_job={"status": "done"},
        event_bus_summary={"observer_error_count": 2},
        now=103.0,
    )

    assert error_snapshot["status"] == "error"
    assert "runtime" in error_snapshot["summary"]["failed_layers"]
    assert error_snapshot["summary"]["latency_status"] == "warn"
    assert degraded_snapshot["status"] == "degraded"
    assert degraded_snapshot["summary"]["observer_error_count"] == 2
