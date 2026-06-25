from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent.react_loop import ReActLoop
from core.goal_tracking import update_goal_checklist
from core.runtime_contract import (
    build_maker_briefing,
    build_runtime_contract,
    render_maker_briefing_for_llm,
    render_runtime_contract_for_llm,
)


def test_runtime_contract_summarizes_maker_and_communication_surfaces():
    contract = build_runtime_contract(
        project_root=Path("D:/project"),
        session_id="s1",
        mcp_status={
            "connected": True,
            "tools": [
                {
                    "name": "maker_publish",
                    "description": "Publish a Maker project",
                    "inputSchema": {"properties": {"project_id": {"type": "string"}}},
                },
                {
                    "name": "maker_query_project",
                    "description": "Query Maker project state",
                    "inputSchema": {"properties": {"project_id": {"type": "string"}}},
                }
            ],
            "remote_identity": {
                "status": "present",
                "missing": [],
                "task_lookup_tools": ["maker_query_task"],
            },
            "last_call": {"tool": "maker_publish", "ok": True},
        },
        skill_status={
            "registry": {"state": "ok"},
            "skill_graph": {"summary": {"total_skills": 3}},
        },
    )

    assert contract["maker_mcp"]["readiness"] == "ready"
    assert contract["maker_mcp"]["top_tools"][0]["name"] == "maker_publish"
    assert contract["maker_mcp"]["top_tools"][0]["params"] == ["project_id"]
    checklist = contract["maker_mcp"]["first_action_checklist"]
    assert [item["id"] for item in checklist][:3] == [
        "read_contract",
        "check_maker_mcp",
        "discover_authority_tools",
    ]
    assert checklist[1]["status"] == "ready"
    assert checklist[-1]["evidence"] == "/sessions/s1/context-sync?steps=3"
    templates = {item["id"]: item for item in contract["maker_mcp"]["task_templates"]}
    assert templates["maker_build_or_submit"]["status"] == "ready"
    assert templates["maker_build_or_submit"]["suggested_tools"] == ["maker_publish"]
    assert "commit_history" in templates["maker_execute_and_verify"]["authority"]
    assert "No provider-specific prompt assumptions are required." in templates["external_agent_handoff"]["acceptance_criteria"]
    assert contract["communication"]["onboarding_bundle"] == "/agent/onboarding?session_id=s1&steps=20"
    assert contract["communication"]["portable_runtime"] == "/runtime/portable"
    assert contract["communication"]["runtime_readiness"] == "/runtime/readiness?session_id=s1"
    assert contract["communication"]["runtime_contract"] == "/agent/runtime-contract?session_id=s1"
    assert contract["communication"]["maker_briefing"] == "/agent/maker-briefing?session_id=s1"
    assert contract["communication"]["quickstart_bundle"] == "/agent/quickstart?session_id=s1&steps=3"
    assert contract["communication"]["handoff_bundle"] == "/agent/handoff?session_id=s1&steps=3"
    assert contract["communication"]["evidence_bundle"] == "/sessions/s1/evidence?steps=20"
    assert contract["communication"]["context_sync"] == "/sessions/s1/context-sync?steps=3"
    assert contract["communication"]["runtime_metrics"] == "/sessions/s1/runtime-metrics?steps=20"
    assert contract["communication"]["learning_status"] == "/sessions/s1/learning?steps=20"
    assert contract["communication"]["maker_guard"] == "/sessions/s1/maker-guard?steps=20"
    assert contract["communication"]["runtime_advice"] == "/sessions/s1/runtime-advice?steps=20"
    assert contract["communication"]["llm_probe"] == "/llm/probe"
    assert contract["communication"]["llm_probe_history"] == "/sessions/s1/llm-probe?steps=20"
    assert contract["communication"]["llm_feedback_summary"] == "/llm/feedback-summary"
    assert contract["communication"]["maker_setup_status"] == "/maker/setup-status"
    assert contract["communication"]["maker_tool_audit"] == "/maker/tool-audit"
    assert contract["communication"]["maker_project_select"] == "/maker/project/select"
    assert contract["external_agents"]["attach_sequence"][0] == "GET /agent/onboarding?session_id=s1&steps=20 for the one-stop startup and closure packet"
    assert contract["external_agents"]["attach_sequence"][1] == "GET /runtime/portable to confirm caches/auth/temp stay inside the TTMEvolve agent folder"
    assert contract["external_agents"]["attach_sequence"][2] == "GET /runtime/readiness?session_id=s1 for the fastest provider/Maker/layer readiness check"
    assert contract["external_agents"]["attach_sequence"][3] == "GET /agent/quickstart?session_id=s1&steps=3"
    assert contract["external_agents"]["attach_sequence"][4] == "GET /sessions/s1/evidence?steps=20 for compact current evidence"
    assert contract["external_agents"]["attach_sequence"][5] == "GET /agent/handoff?session_id=s1&steps=3"
    assert contract["external_agents"]["attach_sequence"][7] == "GET /agent/maker-briefing?session_id=s1 before the first Maker action"
    assert "GET /sessions/s1/runtime-metrics?steps=20 when diagnosing latency/token cost" in contract["external_agents"]["attach_sequence"]
    assert "GET /sessions/s1/maker-guard?steps=20 when checking first-action Maker alignment" in contract["external_agents"]["attach_sequence"]
    assert "GET /sessions/s1/runtime-advice?steps=20 for the next diagnostic action" in contract["external_agents"]["attach_sequence"]
    assert "GET /sessions/s1/learning?steps=20 when checking background learning" in contract["external_agents"]["attach_sequence"]
    assert "POST /llm/probe when provider wiring or API latency is uncertain" in contract["external_agents"]["attach_sequence"]
    assert "GET /sessions/s1/llm-probe?steps=20 when checking provider probe history" in contract["external_agents"]["attach_sequence"]
    assert "GET /llm/feedback-summary when using saved LLM-as-user feedback without sending new project data out" in contract["external_agents"]["attach_sequence"]
    assert "GET /maker/setup-status before real Maker development testing" in contract["external_agents"]["attach_sequence"]
    assert "GET /maker/tool-audit before relying on remote creative proxy tools" in contract["external_agents"]["attach_sequence"]
    assert contract["skill_graph"]["summary"]["total_skills"] == 3
    mechanisms = " ".join(contract["token_efficiency"]["available_mechanisms"])
    assert "runtime contract" in mechanisms
    assert "runtime_metrics pull API" in mechanisms
    assert "session evidence bundle" in mechanisms
    assert "runtime readiness gate" in mechanisms
    assert "portable runtime diagnostics" in mechanisms
    assert "LLM onboarding bundle" in mechanisms
    assert "llm_probe API" in mechanisms
    assert contract["warning_codes"] == []


def test_maker_briefing_selects_build_flow_and_authority():
    contract = build_runtime_contract(
        project_root=Path("D:/project"),
        session_id="s1",
        mcp_status={
            "connected": True,
            "tools": [
                {"name": "maker_publish", "description": "Publish", "inputSchema": {"properties": {}}},
                {"name": "maker_query_project", "description": "Query", "inputSchema": {"properties": {}}},
            ],
            "remote_identity": {"status": "present", "task_lookup_tools": ["maker_query_task"]},
        },
        skill_status={"registry": {"state": "ok"}},
    )

    briefing = build_maker_briefing(contract, task="build and preview Maker project")

    assert briefing["version"] == "maker-briefing.v1"
    assert briefing["readiness"] == "ready"
    assert briefing["authority"] == "maker_mcp"
    assert briefing["selected_template"]["id"] == "maker_build_or_submit"
    assert briefing["suggested_tools"] == ["maker_publish"]
    assert briefing["recommended_endpoint"] == "/mcp/tools"
    assert briefing["evidence_endpoints"]["maker_briefing"] == "/agent/maker-briefing?session_id=s1"
    assert briefing["evidence_endpoints"]["maker_guard"] == "/sessions/s1/maker-guard?steps=20"


def test_maker_briefing_warns_when_mcp_disconnected():
    contract = build_runtime_contract(
        project_root=Path("D:/project"),
        session_id="s2",
        mcp_status={"connected": False, "tools": []},
        skill_status={},
    )

    briefing = build_maker_briefing(contract, task="build Maker project")

    assert briefing["readiness"] == "disconnected"
    assert briefing["authority"] == "local_files"
    assert "maker_mcp_disconnected" in briefing["warning_codes"]
    assert "disconnected" in briefing["recommended_first_action"]


def test_react_context_includes_runtime_contract():
    contract = build_runtime_contract(
        project_root=Path("D:/project"),
        session_id="s2",
        mcp_status={"connected": False, "tools": []},
        skill_status={"registry": {"state": "ok"}, "skill_graph": {"summary": {}}},
    )
    loop = ReActLoop.__new__(ReActLoop)
    loop.runtime_contract_provider = lambda session_id: contract
    loop._session_id = "s2"

    context = ReActLoop._build_context(loop, "build a maker game")

    assert "[runtime_contract]" in context
    assert "[maker_briefing]" in context
    assert "/sessions/s2/context-sync?steps=3" in context
    assert "maker_mcp_disconnected" in context
    assert "recommended_first_action" in context


def test_react_loop_builds_and_emits_maker_briefing():
    contract = build_runtime_contract(
        project_root=Path("D:/project"),
        session_id="s2b",
        mcp_status={
            "connected": True,
            "tools": [{"name": "maker_build", "description": "", "inputSchema": {"properties": {}}}],
            "remote_identity": {"status": "present"},
        },
        skill_status={},
    )
    events = []
    loop = ReActLoop.__new__(ReActLoop)
    loop.runtime_contract_provider = lambda session_id: contract
    loop._runtime_contract_snapshot = contract
    loop._session_id = "s2b"
    loop.event_sink = lambda event: events.append(event)

    briefing = ReActLoop._build_maker_briefing_snapshot(loop, "build and preview Maker project")
    loop._maker_briefing_snapshot = briefing
    ReActLoop._emit(loop, "s2b", "maker_briefing", briefing)

    rendered = render_maker_briefing_for_llm(briefing, max_chars=800)

    assert briefing["selected_template"]["id"] == "maker_build_or_submit"
    assert briefing["authority"] == "maker_mcp"
    assert len(rendered) <= 830
    assert events[-1]["type"] == "maker_briefing"
    assert events[-1]["payload"]["recommended_first_action"]


def test_runtime_contract_marks_maker_checklist_warnings_when_disconnected():
    contract = build_runtime_contract(
        project_root=Path("D:/project"),
        session_id="s3",
        mcp_status={"connected": False, "tools": [], "remote_identity": {"status": "missing"}},
        skill_status={},
    )
    checklist = {item["id"]: item for item in contract["maker_mcp"]["first_action_checklist"]}

    assert checklist["check_maker_mcp"]["status"] == "warn"
    assert checklist["discover_authority_tools"]["status"] == "warn"
    assert checklist["verify_side_effect"]["status"] == "warn"
    assert "report missing remote authority" in checklist["check_maker_mcp"]["action"]
    templates = {item["id"]: item for item in contract["maker_mcp"]["task_templates"]}
    assert templates["maker_inspect_project"]["status"] == "warn"
    assert templates["maker_build_or_submit"]["status"] == "warn"
    assert "maker_mcp_disconnected" in contract["warning_codes"]
    assert "maker_remote_identity_incomplete" in contract["warning_codes"]


def test_react_loop_can_seed_goal_checklist_from_runtime_contract_templates():
    contract = build_runtime_contract(
        project_root=Path("D:/project"),
        session_id="s4",
        mcp_status={
            "connected": True,
            "tools": [{"name": "maker_publish", "description": "", "inputSchema": {"properties": {}}}],
            "remote_identity": {"status": "present", "task_lookup_tools": ["maker_query_task"]},
        },
        skill_status={},
    )
    loop = ReActLoop.__new__(ReActLoop)
    loop.runtime_contract_provider = lambda session_id: contract
    loop._session_id = "s4"

    snapshot = ReActLoop._load_runtime_contract_snapshot(loop)
    templates = ReActLoop._extract_maker_goal_templates(snapshot)
    checklist = update_goal_checklist(
        task="build a TapTap Maker game",
        trajectory=[],
        maker_templates=templates,
    )
    seeded = [
        item for item in checklist["criteria"]
        if item.get("source") == "maker_template"
    ]

    assert seeded
    assert any(item["id"].startswith("maker:maker_build_or_submit:") for item in seeded)
    assert any(item["status"] == "done" and item["evidence"] == ["runtime_contract"] for item in seeded)


def test_runtime_contract_renderer_caps_prompt_size():
    contract = build_runtime_contract(
        project_root=Path("D:/project"),
        mcp_status={
            "connected": True,
            "tools": [
                {"name": f"maker_tool_{i}", "description": "x" * 300, "inputSchema": {"properties": {}}}
                for i in range(30)
            ],
        },
        skill_status={},
    )

    rendered = render_runtime_contract_for_llm(contract, max_chars=900)

    assert len(rendered) <= 930
    assert "runtime_contract" in rendered
    assert "task_templates" in rendered
    assert "external_agent_handoff" in rendered


if __name__ == "__main__":
    test_runtime_contract_summarizes_maker_and_communication_surfaces()
    test_react_context_includes_runtime_contract()
    test_react_loop_builds_and_emits_maker_briefing()
    test_runtime_contract_marks_maker_checklist_warnings_when_disconnected()
    test_react_loop_can_seed_goal_checklist_from_runtime_contract_templates()
    test_runtime_contract_renderer_caps_prompt_size()
    print("[PASS] runtime contract tests")
