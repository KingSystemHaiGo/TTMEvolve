from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.intent_classifier import classify_cos_gate
from server.project_control import build_project_control


def test_project_control_turns_cos_gate_into_post_and_verification_work():
    cos_gate = classify_cos_gate(
        "对代码做审计，模块解耦，设计内部通信总线并优化 RAG 记忆加载"
    ).to_dict()
    project_state = {
        "status": "ready",
        "task": "architecture control",
        "next_focus": "Verify project control",
        "next_action": "Verify project control",
        "plan_verdict": "pass",
        "goal_overall": "active",
        "continuation": {"resume_ready": True, "open_plan_steps": []},
    }
    layer_control = {
        "status": "watch",
        "decision": "continue_with_monitoring",
        "signals": [{"id": "missing_route_agent_to_runtime", "severity": "watch"}],
        "corrective_actions": [{
            "id": "capture_or_emit_missing_layer_route_evidence",
            "priority": 2,
            "owner_layer": "agent",
            "reason": "Expected route agent->runtime was not observed.",
        }],
        "closure_gate": {
            "can_claim_layer_independence": False,
            "can_continue_user_task": True,
        },
    }

    control = build_project_control(project_state=project_state, cos_gate=cos_gate, layer_control=layer_control)

    assert control["version"] == "project-control.v1"
    assert control["status"] == "ready"
    assert control["classification"]["level"] in {"L", "XL"}
    assert control["next_action"] == "Verify project control"
    assert control["current_focus"] == "Verify project control"
    assert control["verification"]["status"] == "requires_evidence"
    assert "layer_control" in control["verification"]["evidence_sources"]
    assert control["layer_control"]["status"] == "watch"
    assert control["layer_control"]["top_action"]["id"] == "capture_or_emit_missing_layer_route_evidence"
    assert control["control_actions"][0]["owner_layer"] == "agent"
    assert control["truthfulness"]["requires_evidence"] is True
    assert "POST_MEM" in control["required_gates"]
    assert "GATE_0_DECLARE" in control["completed_gates"]
    assert any(item["file"] == "docs/memory-index.md" for item in control["memory_updates_due"])
    assert any(item["file"] == "docs/sprint-board.md" for item in control["memory_updates_due"])
    assert control["project_manager"]["health_check_required"] is True


def test_project_control_blocks_vague_instruction_until_confirmation():
    cos_gate = classify_cos_gate("把战斗做好玩一点").to_dict()

    control = build_project_control(project_state={"status": "missing"}, cos_gate=cos_gate)

    assert control["status"] == "needs_confirmation"
    assert control["next_action"] == "Confirm decomposed vague subtasks before execution."
    assert any(blocker["id"] == "vague_instruction_needs_confirmation" for blocker in control["blockers"])
    assert "USER_CONFIRM" in control["pending_gates"]
    assert control["verification"]["status"] == "blocked"


def test_project_control_surfaces_engineering_control_actions():
    cos_gate = classify_cos_gate("优化向量记忆和工程控制").to_dict()
    project_state = {
        "status": "ready",
        "task": "engineering control",
        "next_action": "Fix memory recall",
        "plan_verdict": "pass",
    }
    engineering_control = {
        "status": "needs_action",
        "decision": "correct_before_claiming_ready",
        "summary": {
            "memory_total_hits": 0,
            "tool_failure_count": 0,
            "plan_verdict": "pass",
        },
        "signals": [{"id": "memory_recall_zero_hits", "severity": "warn", "domain": "memory_rag"}],
        "corrective_actions": [{
            "id": "inspect_memory_profiles_and_rag_index_before_optimization_claims",
            "source": "engineering_control",
            "priority": 1,
            "owner_layer": "runtime",
            "domain": "memory_rag",
            "reason": "Memory/RAG recall has repeated zero-hit samples.",
        }],
        "closure_gate": {
            "can_claim_engineering_control_ready": False,
            "can_continue_user_task": True,
            "can_claim_memory_rag_optimized": False,
        },
    }

    control = build_project_control(
        project_state=project_state,
        cos_gate=cos_gate,
        engineering_control=engineering_control,
    )

    assert control["status"] == "ready"
    assert control["engineering_control"]["status"] == "needs_action"
    assert control["engineering_control"]["memory_total_hits"] == 0
    assert "engineering_control" in control["verification"]["evidence_sources"]
    assert any(blocker["id"] == "engineering_control_needs_action" for blocker in control["blockers"])
    assert control["control_actions"][0]["source"] == "engineering_control"
    assert control["control_actions"][0]["domain"] == "memory_rag"
