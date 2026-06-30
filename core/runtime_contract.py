"""Compact runtime contract for onboarding any LLM into TTMEvolve."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def build_runtime_contract(
    *,
    project_root: Path,
    mcp_status: Optional[Dict[str, Any]] = None,
    skill_status: Optional[Dict[str, Any]] = None,
    session_id: str = "{session_id}",
) -> Dict[str, Any]:
    """Build a concise machine-readable contract for coding agents."""
    mcp_status = mcp_status or {}
    skill_status = skill_status or {}
    tools = mcp_status.get("tools") if isinstance(mcp_status.get("tools"), list) else []
    skill_graph = skill_status.get("skill_graph") if isinstance(skill_status.get("skill_graph"), dict) else {}
    remote_identity = (
        mcp_status.get("remote_identity")
        if isinstance(mcp_status.get("remote_identity"), dict)
        else {}
    )
    connected = bool(mcp_status.get("connected"))
    readiness = "ready" if connected and tools else ("degraded" if connected else "disconnected")
    warnings: List[str] = []
    warning_codes: List[str] = []
    if not connected:
        warning_codes.append("maker_mcp_disconnected")
        warnings.append("MakerMCP is not connected; prefer local inspection and report missing remote authority.")
    if remote_identity.get("status") in {"partial", "missing"}:
        warning_codes.append("maker_remote_identity_incomplete")
        warnings.append("MakerMCP remote identity lookup is incomplete; do not assume remote writes committed.")
    if (skill_status.get("registry") or {}).get("state") in {"conflicts", "error"}:
        warning_codes.append("skill_registry_needs_review")
        warnings.append("Skill registry needs review before relying on generated or cross-agent skills.")
    checklist = _maker_first_action_checklist(
        connected=connected,
        tools=tools,
        remote_identity=remote_identity,
        session_id=session_id,
    )
    task_templates = _maker_task_templates(
        connected=connected,
        tools=tools,
        remote_identity=remote_identity,
        session_id=session_id,
    )

    return {
        "version": "runtime-contract.v1",
        "purpose": "Help any LLM start coding in TTMEvolve with MakerMCP, layered runtime communication, and token discipline.",
        "project_root": str(Path(project_root)),
        "llm_onboarding": {
            "first_moves": [
                "Read this contract before selecting tools.",
                "Use MakerMCP tools for Maker project authority when connected.",
                "Use local file tools for repository inspection and code edits.",
                "After side-effecting actions, check commit/context evidence before claiming success.",
                "If a tool call is rejected, use structured validation fields and alternatives instead of guessing.",
            ],
            "coding_loop": [
                "inspect",
                "plan one small verifiable change",
                "execute through the right tool authority",
                "validate observation and plan_validation",
                "summarize exact files, artifacts, and remaining risks",
            ],
        },
        "maker_mcp": {
            "readiness": readiness,
            "connected": connected,
            "tool_count": len(tools),
            "top_tools": _compact_tools(tools, limit=10),
            "first_action_checklist": checklist,
            "task_templates": task_templates,
            "remote_identity": remote_identity,
            "last_call": mcp_status.get("last_call"),
        },
        "layers": {
            "agent": {
                "owns": ["ReAct planning", "tool selection", "tool-call validation", "goal checklist"],
                "emits": ["thought", "action", "tool_preflight", "plan_validation", "goal_checklist", "context_sync"],
            },
            "core_runtime": {
                "owns": ["Executor", "Sandbox", "Approval", "timeouts", "commit reconciliation", "MakerMCP bridge"],
                "emits": ["tool_call", "tool_progress", "observation", "commit_reconcile", "latency"],
            },
            "learning": {
                "owns": ["trajectory collection", "reflection", "skill registry", "skill graph", "knowledge base"],
                "emits": ["skill_sync", "layer", "llm_feedback"],
            },
        },
        "communication": {
            "onboarding_bundle": f"/agent/onboarding?session_id={session_id}&steps=20",
            "portable_runtime": "/runtime/portable",
            "runtime_readiness": f"/runtime/readiness?session_id={session_id}",
            "quickstart_bundle": f"/agent/quickstart?session_id={session_id}&steps=3",
            "runtime_contract": f"/agent/runtime-contract?session_id={session_id}",
            "maker_briefing": f"/agent/maker-briefing?session_id={session_id}",
            "handoff_bundle": f"/agent/handoff?session_id={session_id}&steps=3",
            "evidence_bundle": f"/sessions/{session_id}/evidence?steps=20",
            "context_sync": f"/sessions/{session_id}/context-sync?steps=3",
            "goal_loop": f"/sessions/{session_id}/goal-loop?steps=100",
            "resume_drill": f"/sessions/{session_id}/resume-drill?steps=20",
            "runtime_metrics": f"/sessions/{session_id}/runtime-metrics?steps=20",
            "layer_health": f"/sessions/{session_id}/layer-health?steps=20",
            "layer_control": f"/sessions/{session_id}/layer-control?steps=20",
            "engineering_control": f"/sessions/{session_id}/engineering-control?steps=20",
            "project_state": f"/sessions/{session_id}/project-state",
            "project_writeback": f"/sessions/{session_id}/project-writeback",
            "learning_status": f"/sessions/{session_id}/learning?steps=20",
            "learning_cancel": f"/sessions/{session_id}/learning/cancel",
            "learning_retry": f"/sessions/{session_id}/learning/retry",
            "maker_guard": f"/sessions/{session_id}/maker-guard?steps=20",
            "runtime_advice": f"/sessions/{session_id}/runtime-advice?steps=20",
            "commit_history": f"/sessions/{session_id}/commit-history?steps=5",
            "rag_benchmark": "/memory/rag-benchmark",
            "rag_quality": "/memory/rag-quality",
            "llm_probe": "/llm/probe",
            "llm_probe_history": f"/sessions/{session_id}/llm-probe?steps=20",
            "llm_feedback_summary": "/llm/feedback-summary",
            "maker_setup_status": "/maker/setup-status",
            "maker_setup_status_markdown": "/maker/setup-status.md",
            "maker_tool_audit": "/maker/tool-audit",
            "maker_project_select": "/maker/project/select",
            "maker_auth_prepare": "/maker/auth/prepare",
            "maker_auth_complete": "/maker/auth/complete",
            "maker_repair": "/maker/repair",
            "mcp_status": "/mcp/status",
            "mcp_tools": "/mcp/tools",
            "skill_sync": "/skills/sync-status",
            "tools": "/tools",
        },
        "external_agents": {
            "compatible_surfaces": ["Claude Code", "Codex", "opencode", "OpenClaw", "Hermes-style agents"],
            "attach_sequence": [
                f"GET /agent/onboarding?session_id={session_id}&steps=20 for the one-stop startup and closure packet",
                "GET /runtime/portable to confirm caches/auth/temp stay inside the TTMEvolve agent folder",
                f"GET /runtime/readiness?session_id={session_id} for the fastest provider/Maker/layer readiness check",
                f"GET /agent/quickstart?session_id={session_id}&steps=3",
                f"GET /sessions/{session_id}/evidence?steps=20 for compact current evidence",
                f"GET /sessions/{session_id}/project-state for bus-derived next action and project control state",
                f"GET /sessions/{session_id}/project-writeback before applying POST memory writeback",
                f"GET /agent/handoff?session_id={session_id}&steps=3",
                f"GET /agent/runtime-contract?session_id={session_id}",
                f"GET /agent/maker-briefing?session_id={session_id} before the first Maker action",
                f"GET /sessions/{session_id}/context-sync?steps=3",
                f"GET /sessions/{session_id}/resume-drill?steps=20 before claiming long-task durable handoff",
                f"GET /sessions/{session_id}/runtime-metrics?steps=20 when diagnosing latency/token cost",
                f"GET /sessions/{session_id}/layer-health?steps=20 when checking Agent/Core Runtime/Learning independence",
                f"GET /sessions/{session_id}/layer-control?steps=20 when checking engineering-control thresholds and corrective actions",
                f"GET /sessions/{session_id}/engineering-control?steps=20 when checking memory misses, repeated tool failures, and plan gates",
                "GET /memory/rag-benchmark when checking memory/RAG speed claims",
                "GET /memory/rag-quality when checking production embedding semantic recall quality",
                "Inspect /memory/rag-benchmark embedding_quality before claiming production semantic recall quality",
                f"GET /sessions/{session_id}/maker-guard?steps=20 when checking first-action Maker alignment",
                f"GET /sessions/{session_id}/runtime-advice?steps=20 for the next diagnostic action",
                f"GET /sessions/{session_id}/learning?steps=20 when checking background learning",
                "POST /llm/probe when provider wiring or API latency is uncertain",
                f"GET /sessions/{session_id}/llm-probe?steps=20 when checking provider probe history",
                "GET /llm/feedback-summary when using saved LLM-as-user feedback without sending new project data out",
                "GET /maker/setup-status before real Maker development testing",
                "GET /maker/tool-audit before relying on remote creative proxy tools",
                "POST /maker/repair when setup_status.fault_analysis.one_click_repair.can_run_now is true and no session is active",
                "POST /maker/project/select when switching or creating a Maker game directory",
                "POST /maker/auth/prepare with the Maker CLI authorization URL, then open it in the embedded browser",
                "GET /mcp/status",
                "GET /mcp/tools when Maker authority is needed",
                "Use query_skills only when a reusable skill is relevant",
            ],
            "handoff_rule": "Use context_sync plus runtime_contract instead of replaying the full SSE transcript.",
        },
        "token_efficiency": {
            "rules": [
                "Prefer ranked tool subsets over full tool lists.",
                "Query skills or MCP status only when relevant to the current step.",
                "Use context_sync and commit_history instead of replaying full transcripts.",
                "Keep plans short and evidence-driven; avoid restating completed mechanisms.",
                "Preserve task, current files, recent failures, commit state, and MakerMCP ids under compression.",
            ],
            "available_mechanisms": [
                "ContextBudgetManager",
                "MemoryManager hot/warm/cold recall",
                "vector memory and AGENTS.md index",
                "tool ranking/capping",
                "runtime contract",
                "maker_briefing next-action API",
                "context_sync pull API",
                "resume_drill durable handoff check",
                "runtime_metrics pull API",
                "layer_health pull API",
                "layer_control pull API",
                "engineering_control pull API",
                "RAG benchmark report",
                "RAG production embedding quality evaluator",
                "RAG embedding quality claim gate",
                "session evidence bundle",
                "project-control writeback plan",
                "runtime readiness gate",
                "portable runtime diagnostics",
                "LLM onboarding bundle",
                "llm_probe API",
                "Maker Setup Doctor",
                "Maker tool audit",
                "project directory switch endpoint",
            ],
        },
        "skill_graph": {
            "registry": skill_status.get("registry", {}),
            "summary": skill_graph.get("summary", {}),
            "query_tool": "query_skills",
        },
        "warnings": warnings,
        "warning_codes": warning_codes,
    }


def render_runtime_contract_for_llm(contract: Dict[str, Any], max_chars: int = 2400) -> str:
    """Render the contract as a compact prompt block."""
    maker_mcp = contract.get("maker_mcp", {}) if isinstance(contract.get("maker_mcp"), dict) else {}
    compact_maker = {
        "readiness": maker_mcp.get("readiness"),
        "connected": maker_mcp.get("connected"),
        "tool_count": maker_mcp.get("tool_count"),
        "task_templates": _compact_templates_for_llm(
            maker_mcp.get("task_templates", [])
        ),
        "first_action_checklist": _compact_checklist_for_llm(
            maker_mcp.get("first_action_checklist", [])
        ),
        "top_tools": _compact_top_tools_for_llm(maker_mcp.get("top_tools", [])),
        "remote_identity": maker_mcp.get("remote_identity", {}),
    }
    compact = {
        "version": contract.get("version"),
        "warning_codes": contract.get("warning_codes", []),
        "maker_mcp": compact_maker,
        "communication": _compact_communication_for_llm(contract.get("communication", {})),
        "external_agents": _compact_external_agents_for_llm(contract.get("external_agents", {})),
        "first_moves": (contract.get("llm_onboarding") or {}).get("first_moves", [])[:3],
        "layers": _compact_layers_for_llm(contract.get("layers", {})),
        "token_rules": (contract.get("token_efficiency") or {}).get("rules", [])[:4],
        "warnings": contract.get("warnings", []),
    }
    text = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 120)] + "...[runtime_contract_truncated]"


def _compact_communication_for_llm(communication: Any) -> Dict[str, Any]:
    if not isinstance(communication, dict):
        return {}
    keys = [
        "runtime_contract",
        "onboarding_bundle",
        "portable_runtime",
        "runtime_readiness",
        "evidence_bundle",
        "quickstart_bundle",
        "maker_briefing",
        "runtime_advice",
        "context_sync",
        "goal_loop",
        "resume_drill",
        "layer_health",
        "layer_control",
        "project_writeback",
        "rag_benchmark",
        "rag_quality",
        "llm_probe",
        "maker_setup_status",
        "maker_tool_audit",
    ]
    return {key: communication.get(key) for key in keys if communication.get(key)}


def _compact_external_agents_for_llm(external_agents: Any) -> Dict[str, Any]:
    if not isinstance(external_agents, dict):
        return {}
    attach_sequence = external_agents.get("attach_sequence")
    if not isinstance(attach_sequence, list):
        attach_sequence = []
    return {
        "attach_sequence": attach_sequence[:5],
        "handoff_rule": external_agents.get("handoff_rule"),
    }


def build_maker_briefing(contract: Dict[str, Any], task: str = "") -> Dict[str, Any]:
    """Build a compact next-action briefing for Maker-focused work."""
    maker = contract.get("maker_mcp") if isinstance(contract.get("maker_mcp"), dict) else {}
    communication = contract.get("communication") if isinstance(contract.get("communication"), dict) else {}
    readiness = str(maker.get("readiness") or "unknown")
    connected = bool(maker.get("connected"))
    warnings = contract.get("warning_codes") if isinstance(contract.get("warning_codes"), list) else []
    templates = maker.get("task_templates") if isinstance(maker.get("task_templates"), list) else []
    checklist = maker.get("first_action_checklist") if isinstance(maker.get("first_action_checklist"), list) else []
    top_tools = maker.get("top_tools") if isinstance(maker.get("top_tools"), list) else []
    template = _select_maker_template(templates, task)
    suggested_tools = template.get("suggested_tools") if isinstance(template.get("suggested_tools"), list) else []
    if not suggested_tools:
        suggested_tools = [
            tool.get("name")
            for tool in top_tools
            if isinstance(tool, dict) and tool.get("name")
        ][:4]

    if not connected:
        authority = "local_files"
        first_action = "Inspect local project files and report that MakerMCP remote authority is disconnected."
        first_endpoint = communication.get("mcp_status", "/mcp/status")
    elif suggested_tools:
        authority = "maker_mcp"
        first_action = f"Use MakerMCP authority through {suggested_tools[0]} if it matches the task; otherwise inspect /mcp/tools."
        first_endpoint = communication.get("mcp_tools", "/mcp/tools")
    else:
        authority = "maker_mcp_status"
        first_action = "Fetch MakerMCP tools/status before choosing a side-effecting action."
        first_endpoint = communication.get("mcp_tools", "/mcp/tools")

    return {
        "version": "maker-briefing.v1",
        "task": task,
        "readiness": readiness,
        "connected": connected,
        "warning_codes": warnings,
        "authority": authority,
        "selected_template": {
            "id": template.get("id"),
            "label": template.get("label"),
            "status": template.get("status"),
            "acceptance_criteria": template.get("acceptance_criteria", [])[:3]
                if isinstance(template.get("acceptance_criteria"), list)
                else [],
        },
        "recommended_first_action": first_action,
        "recommended_endpoint": first_endpoint,
        "suggested_tools": suggested_tools[:4],
        "checklist": [
            {
                "id": item.get("id"),
                "status": item.get("status"),
                "evidence": item.get("evidence"),
                "action": item.get("action"),
            }
            for item in checklist[:6]
            if isinstance(item, dict)
        ],
        "evidence_endpoints": {
            key: communication.get(key)
            for key in [
                "runtime_contract",
                "maker_briefing",
                "context_sync",
                "resume_drill",
                "runtime_metrics",
                "maker_guard",
                "learning_status",
                "learning_cancel",
                "learning_retry",
                "commit_history",
                "mcp_status",
                "mcp_tools",
            ]
            if communication.get(key)
        },
        "token_rule": "Use this briefing plus context_sync/resume_drill before fetching full tool lists or transcripts.",
    }


def render_maker_briefing_for_llm(briefing: Dict[str, Any], max_chars: int = 1100) -> str:
    """Render the Maker briefing as a tiny first-action prompt block."""
    selected = briefing.get("selected_template")
    if not isinstance(selected, dict):
        selected = {}
    endpoints = briefing.get("evidence_endpoints")
    if not isinstance(endpoints, dict):
        endpoints = {}
    compact = {
        "version": briefing.get("version"),
        "task": briefing.get("task"),
        "readiness": briefing.get("readiness"),
        "connected": briefing.get("connected"),
        "warning_codes": briefing.get("warning_codes", []),
        "authority": briefing.get("authority"),
        "selected_template": {
            "id": selected.get("id"),
            "status": selected.get("status"),
            "acceptance_criteria": (selected.get("acceptance_criteria") or [])[:2]
                if isinstance(selected.get("acceptance_criteria"), list)
                else [],
        },
        "recommended_first_action": briefing.get("recommended_first_action"),
        "recommended_endpoint": briefing.get("recommended_endpoint"),
        "suggested_tools": (briefing.get("suggested_tools") or [])[:3]
            if isinstance(briefing.get("suggested_tools"), list)
            else [],
        "evidence_endpoints": {
            key: endpoints.get(key)
            for key in ["context_sync", "resume_drill", "runtime_metrics", "maker_guard", "commit_history", "mcp_status", "mcp_tools"]
            if endpoints.get(key)
        },
        "token_rule": briefing.get("token_rule"),
    }
    text = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 80)] + "...[maker_briefing_truncated]"


def _compact_checklist_for_llm(items: Any) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []
    compact: List[Dict[str, Any]] = []
    for item in items[:6]:
        if not isinstance(item, dict):
            continue
        compact.append({
            "id": item.get("id"),
            "status": item.get("status"),
            "evidence": item.get("evidence"),
        })
    return compact


def _compact_templates_for_llm(items: Any) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []
    compact: List[Dict[str, Any]] = []
    ordered = sorted(
        [item for item in items if isinstance(item, dict)],
        key=lambda item: 0 if item.get("id") == "external_agent_handoff" else 1,
    )
    for item in ordered[:5]:
        if not isinstance(item, dict):
            continue
        row = {
            "id": item.get("id"),
            "status": item.get("status"),
        }
        suggested_tools = item.get("suggested_tools", [])
        if isinstance(suggested_tools, list) and suggested_tools:
            row["suggested_tools"] = suggested_tools[:4]
        compact.append(row)
    return compact


def _compact_top_tools_for_llm(items: Any) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []
    compact: List[Dict[str, Any]] = []
    for item in items[:6]:
        if not isinstance(item, dict):
            continue
        compact.append({
            "name": item.get("name"),
            "params": item.get("params", [])[:5] if isinstance(item.get("params"), list) else [],
        })
    return compact


def _compact_layers_for_llm(layers: Any) -> Dict[str, Dict[str, Any]]:
    if not isinstance(layers, dict):
        return {}
    compact: Dict[str, Dict[str, Any]] = {}
    for name in ("agent", "core_runtime", "learning"):
        value = layers.get(name)
        if isinstance(value, dict):
            compact[name] = {
                "owns": value.get("owns", [])[:3],
                "emits": value.get("emits", [])[:6],
            }
    return compact


def _compact_tools(tools: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    compact = []
    for tool in tools[:limit]:
        schema = tool.get("parameters") or tool.get("inputSchema") or {}
        properties = schema.get("properties") if isinstance(schema, dict) else {}
        compact.append({
            "name": tool.get("name", ""),
            "description": str(tool.get("description", ""))[:180],
            "params": sorted(properties.keys()) if isinstance(properties, dict) else [],
        })
    return compact


def _maker_first_action_checklist(
    *,
    connected: bool,
    tools: List[Dict[str, Any]],
    remote_identity: Dict[str, Any],
    session_id: str,
) -> List[Dict[str, Any]]:
    tool_names = [str(tool.get("name", "")) for tool in tools if tool.get("name")]
    has_lookup = bool(remote_identity.get("task_lookup_tools") or remote_identity.get("file_lookup_tools"))
    has_tools = bool(tool_names)
    return [
        {
            "id": "read_contract",
            "label": "Read Runtime Contract",
            "status": "ready",
            "why": "Align provider behavior before selecting tools.",
            "evidence": "runtime_contract",
            "action": "Use this contract as the first prompt-side operating guide.",
        },
        {
            "id": "check_maker_mcp",
            "label": "Check MakerMCP readiness",
            "status": "ready" if connected else "warn",
            "why": "Maker project authority should come from MakerMCP when connected.",
            "evidence": "/mcp/status",
            "action": "If disconnected, inspect locally and report missing remote authority.",
        },
        {
            "id": "discover_authority_tools",
            "label": "Discover Maker authority tools",
            "status": "ready" if has_tools else "warn",
            "why": "Choose MakerMCP tools for remote project state; choose file tools for repo edits.",
            "evidence": "/mcp/tools",
            "action": "Prefer relevant Maker tools before generic shell/file guesses.",
            "sample_tools": tool_names[:5],
        },
        {
            "id": "plan_small_change",
            "label": "Plan one verifiable Maker change",
            "status": "ready",
            "why": "Small steps preserve context and make plan_validation useful.",
            "evidence": "plan_validation",
            "action": "State the file/tool/artifact you expect to change before acting.",
        },
        {
            "id": "verify_side_effect",
            "label": "Verify side effects before claiming done",
            "status": "ready" if has_lookup else "warn",
            "why": "Remote Maker writes can be uncertain after timeout/cancel.",
            "evidence": f"/sessions/{session_id}/commit-history?steps=5",
            "action": "Use commit/context evidence; do not infer remote commit from tool name only.",
        },
        {
            "id": "sync_context",
            "label": "Sync compact context",
            "status": "ready",
            "why": "Avoid replaying full transcripts; keep token use low.",
            "evidence": f"/sessions/{session_id}/context-sync?steps=3",
            "action": "Use context_sync for handoff, artifacts, plan verdict, and latest tool state.",
        },
    ]


def _maker_task_templates(
    *,
    connected: bool,
    tools: List[Dict[str, Any]],
    remote_identity: Dict[str, Any],
    session_id: str,
) -> List[Dict[str, Any]]:
    tool_names = [str(tool.get("name", "")) for tool in tools if tool.get("name")]
    has_tools = bool(tool_names)
    has_lookup = bool(remote_identity.get("task_lookup_tools") or remote_identity.get("file_lookup_tools"))
    build_tools = _suggest_tools(tool_names, ["build", "publish", "submit", "sync", "deploy"], limit=4)
    file_tools = _suggest_tools(tool_names, ["file", "asset", "resource", "script", "scene"], limit=4)
    inspect_tools = _suggest_tools(tool_names, ["status", "list", "get", "read", "query", "project"], limit=4)
    return [
        {
            "id": "maker_inspect_project",
            "label": "Inspect Maker project state",
            "status": "ready" if connected and has_tools else "warn",
            "when": "Start of a Maker task, after resume, or when remote/local state may differ.",
            "authority": ["runtime_contract", "/mcp/status", "/mcp/tools", "local_files"],
            "steps": [
                "Read runtime_contract warning_codes and MakerMCP readiness.",
                "Check /mcp/status before assuming remote authority.",
                "Use /mcp/tools or suggested tools only for Maker remote facts.",
                f"Pull compact handoff context from /sessions/{session_id}/context-sync?steps=3.",
            ],
            "acceptance_criteria": [
                "MakerMCP readiness and warning_codes are known.",
                "The next action names whether it uses MakerMCP authority or local file authority.",
                "No full transcript replay is needed before the first action.",
            ],
            "token_strategy": "Use runtime_contract and context_sync; avoid asking for all tools unless status says Maker authority is needed.",
            "suggested_tools": inspect_tools,
        },
        {
            "id": "maker_plan_small_change",
            "label": "Plan one verifiable Maker change",
            "status": "ready",
            "when": "Before editing scripts/assets/config or invoking a Maker side-effect tool.",
            "authority": ["Agent plan_validation", "local_files", "MakerMCP when connected"],
            "steps": [
                "State one user-visible outcome and one expected artifact.",
                "Select at most one primary edit/action path.",
                "Name the verification surface before acting.",
            ],
            "acceptance_criteria": [
                "Plan has a single expected outcome.",
                "Plan references exact files, Maker artifact ids, or tool evidence.",
                "plan_validation can pass or produce a concrete repair instruction.",
            ],
            "token_strategy": "Keep the plan under five bullets and preserve only task/files/tool evidence under compression.",
            "suggested_tools": file_tools,
        },
        {
            "id": "maker_execute_and_verify",
            "label": "Execute and verify side effects",
            "status": "ready" if connected and has_lookup else "warn",
            "when": "After a file write, MakerMCP write, build, submit, publish, or timeout recovery.",
            "authority": ["Executor", "commit_history", "context_sync", "MakerMCP lookup tools"],
            "steps": [
                "Execute through the lowest-risk authority that can perform the change.",
                "Read observation fields, especially idempotency_key, committed, observed_at, and reconcile_status.",
                f"Check /sessions/{session_id}/commit-history?steps=5 when committed is unknown.",
                "If remote lookup is incomplete, report uncertainty instead of claiming success.",
            ],
            "acceptance_criteria": [
                "Every side effect has observation evidence.",
                "Remote success is proven by explicit id/file/task identity, not tool name alone.",
                "Unknown remote state is surfaced as warn, not hidden.",
            ],
            "token_strategy": "Prefer commit_history/context_sync summaries over pasting tool observations repeatedly.",
            "suggested_tools": _suggest_tools(tool_names, ["lookup", "query", "status", "commit", "history"], limit=4),
        },
        {
            "id": "maker_build_or_submit",
            "label": "Build or submit Maker project",
            "status": "ready" if connected and build_tools else "warn",
            "when": "User asks to build, preview, submit, push, or validate the Maker project remotely.",
            "authority": ["MakerMCP build/submit tools", "Maker remote identity", "commit_history"],
            "steps": [
                "Confirm MakerMCP is connected and remote identity is not missing.",
                "Use MakerMCP build/submit authority instead of generic git/shell for Maker remote flow.",
                "After the tool returns, reconcile commit/submission state before reporting done.",
            ],
            "acceptance_criteria": [
                "Build/submit tool was selected from MakerMCP discovered tools.",
                "Result includes remote url/id/status or a clear failure reason.",
                "If build fails after push/submit, the response says code may already be on remote.",
            ],
            "token_strategy": "Keep build logs summarized; fetch detailed logs only after failure or user request.",
            "suggested_tools": build_tools,
        },
        {
            "id": "external_agent_handoff",
            "label": "Hand off to another coding agent",
            "status": "ready",
            "when": "Claude Code, Codex, opencode, OpenClaw, or another agent attaches mid-session.",
            "authority": ["runtime_contract", "context_sync", "skill_graph"],
            "steps": [
                f"Fetch /agent/runtime-contract?session_id={session_id}.",
                f"Fetch /sessions/{session_id}/context-sync?steps=3.",
                "Query skills only when the current task needs a reusable capability.",
                "Continue from compact context rather than replaying raw SSE.",
            ],
            "acceptance_criteria": [
                "The receiving agent knows MakerMCP readiness and warning_codes.",
                "The receiving agent has latest plan/tool/artifact state.",
                "No provider-specific prompt assumptions are required.",
            ],
            "token_strategy": "Runtime contract plus context_sync is the default handoff payload.",
            "suggested_tools": ["runtime_contract", "query_skills"],
        },
    ]


def _suggest_tools(tool_names: List[str], keywords: List[str], limit: int) -> List[str]:
    matches: List[str] = []
    lowered = [(name, name.lower()) for name in tool_names]
    for keyword in keywords:
        for name, lower in lowered:
            if keyword in lower and name not in matches:
                matches.append(name)
                if len(matches) >= limit:
                    return matches
    return matches


def _select_maker_template(templates: List[Dict[str, Any]], task: str) -> Dict[str, Any]:
    by_id = {
        str(item.get("id")): item
        for item in templates
        if isinstance(item, dict) and item.get("id")
    }
    task_l = str(task or "").lower()
    if any(word in task_l for word in ["build", "submit", "publish", "deploy", "preview", "构建", "提交", "发布", "预览"]):
        return by_id.get("maker_build_or_submit") or by_id.get("maker_execute_and_verify") or _first_template(templates)
    if any(word in task_l for word in ["handoff", "claude", "codex", "opencode", "external", "交接", "外部"]):
        return by_id.get("external_agent_handoff") or _first_template(templates)
    if any(word in task_l for word in ["inspect", "status", "query", "read", "查看", "检查", "状态"]):
        return by_id.get("maker_inspect_project") or _first_template(templates)
    if any(word in task_l for word in ["verify", "timeout", "commit", "reconcile", "验证", "超时"]):
        return by_id.get("maker_execute_and_verify") or _first_template(templates)
    return by_id.get("maker_plan_small_change") or _first_template(templates)


def _first_template(templates: List[Dict[str, Any]]) -> Dict[str, Any]:
    for item in templates:
        if isinstance(item, dict):
            return item
    return {}
