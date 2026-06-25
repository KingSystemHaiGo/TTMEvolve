"""Machine-readable Maker MCP fault classification and repair planning."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


MAKER_FAULT_RULES_VERSION = "maker-fault-rules.v1"


def build_maker_fault_analysis(
    *,
    setup_status: Dict[str, Any],
    tool_audit: Optional[Dict[str, Any]] = None,
    portable_status: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Turn Maker setup/audit facts into ordered repairable fault records."""
    tool_audit = tool_audit or {}
    portable_status = portable_status or {}
    blockers = set(_as_list(setup_status.get("blockers")))
    warnings = set(_as_list(setup_status.get("warnings")))
    project = setup_status.get("project") if isinstance(setup_status.get("project"), dict) else {}
    auth = setup_status.get("auth") if isinstance(setup_status.get("auth"), dict) else {}
    package = setup_status.get("maker_package") if isinstance(setup_status.get("maker_package"), dict) else {}
    maker_cfg = setup_status.get("maker_mcp_config") if isinstance(setup_status.get("maker_mcp_config"), dict) else {}
    agent_root = setup_status.get("agent_root_mcp") if isinstance(setup_status.get("agent_root_mcp"), dict) else {}

    faults: List[Dict[str, Any]] = []
    if "npx_missing" in blockers:
        faults.append(_fault(
            code="npx_missing",
            severity="blocker",
            layer="local_runtime",
            automatic=False,
            evidence={"npx_available": package.get("npx_available")},
            repair_action="Install Node.js/npm or use the bundled runtime, then rerun Maker repair.",
        ))
    if "maker_mcp_config_missing" in blockers:
        faults.append(_fault(
            code="maker_mcp_config_missing",
            severity="blocker",
            layer="maker_mcp_config",
            automatic=True,
            evidence={"configured_version": maker_cfg.get("configured_version")},
            repair_action="Run one-click repair to normalize TTMEvolve and agent-root MCP configs.",
        ))
    if "project_root_is_ttmevolve_app_root" in warnings or project.get("is_app_root"):
        faults.append(_fault(
            code="project_root_is_ttmevolve_app_root",
            severity="warning",
            layer="maker_project",
            automatic=True,
            evidence={"project_root": project.get("root")},
            repair_action="Select or create a separate Maker game directory under workspace/.",
        ))
    if "maker_project_not_initialized" in blockers:
        faults.append(_fault(
            code="maker_project_not_initialized",
            severity="blocker",
            layer="maker_project",
            automatic=False,
            evidence={
                "maker_config_exists": project.get("maker_config_exists"),
                "project_settings_exists": project.get("project_settings_exists"),
            },
            repair_action="Run Maker init from the GUI Maker Access center and keep auth/project selection inside the GUI.",
        ))
    if "maker_project_not_bound" in blockers:
        faults.append(_fault(
            code="maker_project_not_bound",
            severity="blocker",
            layer="maker_project",
            automatic=False,
            evidence={"project_id": project.get("project_id"), "project_bound": project.get("project_bound")},
            repair_action="Run Maker init/binding again and choose or create a real Maker app; project_id=0 is not bound.",
        ))
    if "tap_auth_missing" in blockers:
        faults.append(_fault(
            code="tap_auth_missing",
            severity="blocker",
            layer="maker_auth",
            automatic=False,
            evidence={"tap_auth_path": auth.get("tap_auth_path"), "maker_home": auth.get("maker_home")},
            repair_action="Open the Maker CLI auth URL inside the embedded BrowserView and complete TapTap authorization.",
        ))
    if "pat_missing" in warnings:
        faults.append(_fault(
            code="pat_missing",
            severity="warning",
            layer="maker_auth",
            automatic=False,
            evidence={"pat_path": auth.get("pat_path")},
            repair_action="Let Maker CLI prepare PAT during project init if remote build or pull requires it.",
        ))
    if _maker_home_env_fault(setup_status):
        faults.append(_fault(
            code="maker_home_env_mismatch",
            severity="blocker",
            layer="maker_auth",
            automatic=True,
            evidence={
                "maker_home": auth.get("maker_home"),
                "env": (setup_status.get("maker_mcp_raw_env") or {}),
            },
            repair_action="Normalize both TAPTAP_MAKER_HOME and TTM_MAKER_HOME to portable/home/.taptap-maker.",
        ))
    if "maker_mcp_version_pinned" in warnings:
        faults.append(_fault(
            code="maker_mcp_version_pinned",
            severity="warning",
            layer="maker_mcp_config",
            automatic=True,
            evidence={"configured_version": maker_cfg.get("configured_version")},
            repair_action="Normalize internal Maker MCP launch config to npx -p @taptap/maker taptap-maker.",
        ))
    if "agent_root_mcp_missing" in warnings or not agent_root.get("registered", True):
        faults.append(_fault(
            code="agent_root_mcp_missing",
            severity="warning",
            layer="external_agent_bridge",
            automatic=True,
            evidence={
                "registered_count": agent_root.get("registered_count"),
                "target_count": agent_root.get("target_count"),
            },
            repair_action="Write Maker MCP registration into Cursor, Claude, and Codex root configs.",
        ))

    if tool_audit:
        if not tool_audit.get("mcp_connected", True):
            faults.append(_fault(
                code="maker_mcp_disconnected",
                severity="blocker",
                layer="maker_mcp_transport",
                automatic=True,
                evidence={"mcp_error": tool_audit.get("mcp_error")},
                repair_action="Reconnect the Maker MCP subprocess after normalizing config and env.",
            ))
        if tool_audit.get("missing_registration") or tool_audit.get("missing_required_local_handlers"):
            faults.append(_fault(
                code="maker_tool_registration_incomplete",
                severity="blocker",
                layer="agent_tool_bridge",
                automatic=True,
                evidence={
                    "missing_registration": tool_audit.get("missing_registration", []),
                    "missing_required_local_handlers": tool_audit.get("missing_required_local_handlers", []),
                },
                repair_action="Clear stale maker_mcp tools, reconnect MCP, and re-register remote and placeholder proxy tools.",
            ))
        missing_required = tool_audit.get("missing_required_proxy_tools") or []
        if missing_required and tool_audit.get("local_registration_complete"):
            faults.append(_fault(
                code="maker_remote_capability_missing",
                severity="warning",
                layer="maker_remote_capability",
                automatic=False,
                evidence={"missing_required_proxy_tools": missing_required},
                repair_action="Local placeholder proxies are ready; wait for account/env/official MCP exposure or retry after upgrade/auth.",
            ))

    if portable_status.get("blockers"):
        faults.append(_fault(
            code="portable_runtime_leak",
            severity="blocker",
            layer="portable_runtime",
            automatic=True,
            evidence={"blockers": portable_status.get("blockers")},
            repair_action="Reapply portable runtime env before launching Maker CLI or MCP.",
        ))

    ordered = sorted(faults, key=lambda item: (_severity_rank(item["severity"]), item["code"]))
    return {
        "version": MAKER_FAULT_RULES_VERSION,
        "readiness": _readiness(ordered),
        "fault_count": len(ordered),
        "faults": ordered,
        "repair_plan": _repair_plan(ordered),
        "one_click_repair": {
            "endpoint": "/maker/repair",
            "can_run_now": any(item.get("automatic") for item in ordered),
            "automatic_faults": [item["code"] for item in ordered if item.get("automatic")],
            "manual_faults": [item["code"] for item in ordered if not item.get("automatic")],
        },
        "knowledge_queries": [
            "Maker MCP project binding auth TAPTAP_MAKER_HOME tools/list",
            "Maker creative proxy tools generate_image text_to_music video 3D",
            "Codex AGENTS.md skills MCP repair loop",
            "Claude Code CLAUDE.md hooks subagents MCP memory",
        ],
    }


def _fault(
    *,
    code: str,
    severity: str,
    layer: str,
    automatic: bool,
    evidence: Dict[str, Any],
    repair_action: str,
) -> Dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "layer": layer,
        "automatic": automatic,
        "evidence": evidence,
        "repair_action": repair_action,
        "repair_endpoint": "/maker/repair" if automatic else "",
    }


def _repair_plan(faults: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    steps: List[Dict[str, Any]] = []
    for fault in faults:
        if not fault.get("automatic"):
            continue
        steps.append({
            "id": f"repair:{fault['code']}",
            "fault": fault["code"],
            "layer": fault["layer"],
            "endpoint": fault.get("repair_endpoint") or "/maker/repair",
            "action": fault["repair_action"],
        })
    if any(not fault.get("automatic") for fault in faults):
        steps.append({
            "id": "manual:maker_human_gate",
            "fault": "manual_required",
            "layer": "human_auth_or_project_choice",
            "endpoint": "",
            "action": "Complete auth, project binding, or official capability enablement in the GUI Maker Access flow.",
        })
    return steps


def _readiness(faults: List[Dict[str, Any]]) -> str:
    if any(item.get("severity") == "blocker" for item in faults):
        return "blocked"
    if faults:
        return "degraded"
    return "ready"


def _severity_rank(value: str) -> int:
    return {"blocker": 0, "warning": 1, "info": 2}.get(value, 3)


def _as_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _maker_home_env_fault(setup_status: Dict[str, Any]) -> bool:
    raw_env = setup_status.get("maker_mcp_raw_env")
    if not isinstance(raw_env, dict):
        return False
    official = str(raw_env.get("TAPTAP_MAKER_HOME") or "")
    compat = str(raw_env.get("TTM_MAKER_HOME") or "")
    return not official or not compat or official != compat
