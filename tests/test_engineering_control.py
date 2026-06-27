from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from server.engineering_control import build_engineering_control_snapshot


def _memory(*, events: int = 2, agents_hits: int = 1, cold_hits: int = 1) -> dict:
    return {
        "status": "ready",
        "event_count": events,
        "totals": {
            "agents_md_hits": agents_hits,
            "cold_recall_hits": cold_hits,
        },
        "max_latency": {
            "context_build_ms": 12.0,
            "cold_recall_ms": 4.0,
        },
    }


def _observation(tool: str, failure_type: str = "tool_validation") -> dict:
    return {
        "type": "observation",
        "session_id": "eng1",
        "payload": {
            "iteration": 1,
            "tool": tool,
            "observation": {
                "ok": False,
                "failure_type": failure_type,
                "tool": tool,
                "error": "failed",
            },
        },
        "created_at": 1.0,
    }


def _plan(verdict: str) -> dict:
    return {
        "type": "plan_validation",
        "session_id": "eng1",
        "payload": {
            "verdict": verdict,
            "summary": "plan gate",
            "issues": [{"code": "not_committed"}] if verdict == "fail" else [],
        },
        "created_at": 2.0,
    }


def test_engineering_control_ready_when_memory_and_plan_are_healthy():
    control = build_engineering_control_snapshot(
        session_id="eng1",
        memory_recall=_memory(),
        project_state={"plan_verdict": "pass", "goal_overall": "active"},
        recent_events=[_plan("pass")],
    )

    assert control["version"] == "engineering-control.v1"
    assert control["status"] == "ready"
    assert control["signals"] == []
    assert control["summary"]["memory_total_hits"] == 2
    assert control["closure_gate"]["can_claim_memory_rag_optimized"] is True
    assert control["closure_gate"]["can_claim_engineering_control_ready"] is True


def test_engineering_control_flags_repeated_memory_misses():
    control = build_engineering_control_snapshot(
        session_id="eng1",
        memory_recall=_memory(events=2, agents_hits=0, cold_hits=0),
        project_state={"plan_verdict": "pass"},
        recent_events=[_plan("pass")],
    )

    assert control["status"] == "needs_action"
    assert any(signal["id"] == "memory_recall_zero_hits" for signal in control["signals"])
    assert control["corrective_actions"][0]["id"] == "inspect_memory_profiles_and_rag_index_before_optimization_claims"
    assert control["closure_gate"]["can_claim_memory_rag_optimized"] is False


def test_engineering_control_blocks_repeated_tool_failures():
    control = build_engineering_control_snapshot(
        session_id="eng1",
        memory_recall=_memory(),
        project_state={"plan_verdict": "pass"},
        recent_events=[
            _observation("maker_tool"),
            _observation("maker_tool"),
            _observation("maker_tool", "tool_timeout"),
            _observation("other_tool", "remote_business_failure"),
        ],
    )

    assert control["status"] == "blocked"
    assert control["tool_failures"]["failure_count"] == 4
    assert control["tool_failures"]["most_failed_tool"] == {"key": "maker_tool", "count": 3}
    assert {signal["id"] for signal in control["signals"]} >= {
        "repeated_tool_failures_block",
        "same_tool_repeated_failure",
    }
    assert control["closure_gate"]["can_continue_user_task"] is False


def test_engineering_control_blocks_failed_plan_gate():
    control = build_engineering_control_snapshot(
        session_id="eng1",
        memory_recall=_memory(),
        project_state={"plan_verdict": "fail", "goal_overall": "active"},
        recent_events=[_plan("fail")],
    )

    assert control["status"] == "blocked"
    assert control["summary"]["plan_verdict"] == "fail"
    assert any(signal["id"] == "plan_gate_failed" for signal in control["signals"])
    assert control["corrective_actions"][0]["id"] == "repair_failed_plan_gate_before_more_side_effects"
    assert control["closure_gate"]["can_claim_plan_control_ready"] is False
