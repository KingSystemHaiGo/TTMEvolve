from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from server.layer_control import build_layer_control_snapshot


def _health(**summary_overrides):
    summary = {
        "failed_layers": [],
        "active_layers": [],
        "missing_layers": [],
        "learning_queue_depth": 0,
        "max_latency_ms": 12.0,
        "latency_budget_ms": 30_000.0,
        "latency_status": "ok",
        "observer_error_count": 0,
    }
    summary.update(summary_overrides)
    return {
        "version": "layer-health.v1",
        "session_id": "control1",
        "status": "ready",
        "summary": summary,
        "layers": {
            "agent": {"health": "ready", "event": "agent.run.finished", "state": "done"},
            "runtime": {"health": "ready", "event": "runtime.audit.finished", "state": "done"},
            "learning": {"health": "ready", "event": "learning.reflection.finished", "state": "done"},
        },
        "communication_contract": {
            "expected_routes": [
                {"route": "user->agent", "observed": True, "from": "user", "to": "agent"},
                {"route": "agent->runtime", "observed": True, "from": "agent", "to": "runtime"},
                {"route": "runtime->learning", "observed": True, "from": "runtime", "to": "learning"},
                {"route": "learning->storage", "observed": True, "from": "learning", "to": "storage"},
            ],
            "recent_routes": [],
        },
    }


def test_layer_control_ready_when_no_control_signals_fire():
    control = build_layer_control_snapshot(layer_health=_health())

    assert control["version"] == "layer-control.v1"
    assert control["status"] == "ready"
    assert control["decision"] == "continue"
    assert control["signals"] == []
    assert control["closure_gate"]["can_claim_layer_independence"] is True


def test_layer_control_blocks_failed_layer_and_high_latency():
    health = _health(
        failed_layers=["runtime"],
        max_latency_ms=75_000.0,
    )
    health["status"] = "error"
    health["layers"]["runtime"] = {
        "health": "error",
        "event": "runtime.audit.failed",
        "state": "error",
        "error": "timeout",
    }

    control = build_layer_control_snapshot(layer_health=health)

    assert control["status"] == "blocked"
    assert control["decision"] == "block_completion_claims"
    assert control["closure_gate"]["can_claim_layer_independence"] is False
    assert control["closure_gate"]["can_continue_user_task"] is False
    assert {signal["id"] for signal in control["signals"]} >= {
        "runtime_layer_failed",
        "layer_latency_block",
    }
    assert control["corrective_actions"][0]["priority"] == 0


def test_layer_control_warns_on_observer_errors_and_ready_missing_route():
    health = _health(observer_error_count=1)
    health["communication_contract"]["expected_routes"][1]["observed"] = False

    control = build_layer_control_snapshot(layer_health=health)

    assert control["status"] == "needs_action"
    assert any(signal["id"] == "observer_errors_warn" for signal in control["signals"])
    route_signal = next(signal for signal in control["signals"] if signal["id"] == "missing_route_agent_to_runtime")
    assert route_signal["severity"] == "warn"
    assert "missing_route_agent_to_runtime" in control["closure_gate"]["missing_evidence"]


def test_layer_control_allows_active_learning_queue_as_watch():
    health = _health(
        active_layers=["learning"],
        learning_queue_depth=1,
    )
    health["status"] = "active"
    health["layers"]["learning"]["health"] = "active"
    health["communication_contract"]["expected_routes"][1]["observed"] = False

    control = build_layer_control_snapshot(layer_health=health)

    assert control["status"] == "watch"
    assert control["decision"] == "continue_with_monitoring"
    assert control["closure_gate"]["can_continue_user_task"] is True
    assert control["closure_gate"]["can_claim_layer_independence"] is False
    assert any(signal["id"] == "learning_queue_watch" for signal in control["signals"])
