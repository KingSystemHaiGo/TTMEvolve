"""Settings API — runtime / project / portable / LLM Router summary.

This module gathers the four data sources the Settings page needs:

  * project       — current Maker project
  * runtime       — MCP runtime process state
  * schema        — tool count + per-category counts
  * portable      — embedded runtime status
  * llm_router    — provider health (since v0.7.0)

The functions are pure data builders, so they're unit-testable without
spinning up an HTTP server. The HTTP wiring lives in app_server.py.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from llm.router import LLMRouter
from llm.llm_factory import LLMFactory


SETTINGS_API_VERSION = "settings-api.v1"


def _safe(fn, default=None):
    """Call fn(), returning `default` on any exception (best-effort extraction)."""
    try:
        return fn()
    except Exception:
        return default


def build_project_info(server: Any) -> Optional[Dict[str, Any]]:
    """Extract project info from the server's config / maker setup."""
    config = _safe(lambda: server.agent.config)
    if config is None:
        return None

    project_root_str = _safe(lambda: str(config.project_root())) or ""
    if not project_root_str:
        return None
    project_root = project_root_str

    maker_cfg = _safe(lambda: config.maker_mcp_config()) or {}
    if not isinstance(maker_cfg, dict):
        maker_cfg = {}
    project_id = maker_cfg.get("project_id", "")
    config_path = maker_cfg.get("config_path", "")

    name = project_root.rstrip("/\\").split("/")[-1].split("\\")[-1] or "未命名项目"

    return {
        "name": name,
        "rootPath": project_root,
        "makerProjectId": str(project_id),
        "configPath": str(config_path) if config_path else f"{project_root}/.maker-mcp/config.json",
    }


def build_runtime_info(server: Any) -> Dict[str, Any]:
    """Extract MCP runtime status from the server's MCP integration state."""
    runtime = {
        "status": "idle",
        "processId": None,
        "cwd": "",
        "toolsListUpdatedAt": None,
        "launchCommand": "",
        "lastError": None,
    }

    mcp = _safe(lambda: server.agent.mcp_integration)
    if mcp is None:
        return runtime

    status_text = _safe(lambda: mcp.status_text()) or "idle"
    runtime["status"] = str(status_text)

    process_id = _safe(lambda: mcp.process_id())
    if isinstance(process_id, int):
        runtime["processId"] = process_id

    cwd = _safe(lambda: mcp.cwd())
    if isinstance(cwd, str):
        runtime["cwd"] = cwd

    tools_updated = _safe(lambda: mcp.tools_list_updated_at())
    if tools_updated:
        runtime["toolsListUpdatedAt"] = str(tools_updated)

    config = _safe(lambda: server.agent.config)
    if config is not None:
        maker_cfg = _safe(lambda: config.maker_mcp_config()) or {}
        command = maker_cfg.get("command", "") if isinstance(maker_cfg, dict) else ""
        args = maker_cfg.get("args", []) if isinstance(maker_cfg, dict) else []
        if command:
            runtime["launchCommand"] = " ".join([str(command)] + [str(a) for a in args])

    last_error = _safe(lambda: mcp.last_error())
    if last_error:
        runtime["lastError"] = str(last_error)

    return runtime


def build_schema_summary(server: Any) -> Dict[str, Any]:
    """Count tools + categorize by category."""
    summary = {
        "total": 0,
        "categories": {},
        "formSource": "tools/list inputSchema",
    }

    tools = _safe(lambda: list(server.agent.tools.list_tools())) or []
    summary["total"] = len(tools)

    for tool in tools:
        if isinstance(tool, dict):
            category = tool.get("category") or tool.get("kind") or "general"
        else:
            category = getattr(tool, "category", None) or getattr(tool, "kind", None) or "general"
        summary["categories"][str(category)] = summary["categories"].get(str(category), 0) + 1

    return summary


def build_portable_status(server: Any = None) -> Dict[str, Any]:
    """Embedded runtime status (Python / Node / Maker MCP).

    Calls portable_diagnostics with whatever signature it accepts. The
    argument list is built defensively because the helper has historically
    taken either 0 or 1 positional argument depending on the project state.
    """
    try:
        from core.portable_env import portable_diagnostics
    except Exception:
        diag: Dict[str, Any] = {}
    else:
        diag = {}
        try:
            # Try with project_root first
            if server is not None:
                project_root = _safe(lambda: str(server.agent.config.project_root()))
                diag = portable_diagnostics(project_root)
            else:
                diag = portable_diagnostics()
        except TypeError:
            try:
                diag = portable_diagnostics()
            except Exception:
                diag = {}
        except Exception:
            diag = {}

    if not isinstance(diag, dict):
        diag = {}

    def _info(name: str, fallback_path: str) -> Dict[str, Any]:
        entry = diag.get(name, {}) if isinstance(diag.get(name), dict) else {}
        return {
            "embedded": bool(entry.get("embedded")),
            "version": entry.get("version") or None,
            "path": entry.get("path") or fallback_path,
        }

    return {
        "python": _info("python", "./portable/python/"),
        "node": _info("node", "./portable/node/"),
        "makerMcp": {
            "embedded": bool(diag.get("maker_mcp", {}).get("embedded")) if isinstance(diag.get("maker_mcp"), dict) else False,
            "path": (diag.get("maker_mcp", {}).get("path") if isinstance(diag.get("maker_mcp"), dict) else "./portable/maker-mcp/"),
        },
    }


def build_llm_router_stats(server: Any) -> List[Dict[str, Any]]:
    """Return LLMRouter per-provider stats if available."""
    llm = _safe(lambda: server.agent.llm)
    if isinstance(llm, LLMRouter):
        try:
            return llm.get_stats()
        except Exception:
            return []
    return []


def build_settings_runtime_info(server: Any) -> Dict[str, Any]:
    """Top-level aggregator for GET /api/settings/runtime-info."""
    return {
        "version": SETTINGS_API_VERSION,
        "project": build_project_info(server),
        "runtime": build_runtime_info(server),
        "schema": build_schema_summary(server),
        "portable": build_portable_status(server),
        "llmRouter": {
            "providers": build_llm_router_stats(server),
        },
    }


def build_settings_devtools_clear() -> Dict[str, Any]:
    """POST /api/settings/devtools — clear frontend diagnostics (stub)."""
    # Real log path is held by the front-end; server-side clear is a no-op
    # so the API is symmetric with the GET counterpart.
    return {
        "version": SETTINGS_API_VERSION,
        "ok": True,
        "cleared_at": None,  # filled by app_server if needed
    }


def build_provider_summary(server: Any) -> Dict[str, Any]:
    """Top-level aggregator for GET /api/settings/llm-providers."""
    from llm.provider_presets import PROVIDER_PRESETS, model_hints

    primary = _safe(lambda: server.agent.config.llm_provider()) or "deepseek"
    fallback_entries = _safe(lambda: server.agent.config.get("llm.fallback_providers", [])) or []

    return {
        "version": SETTINGS_API_VERSION,
        "primary": primary,
        "presets": PROVIDER_PRESETS,
        "fallback_providers": fallback_entries,
        "hints": {p["id"]: model_hints(p["id"]) for p in PROVIDER_PRESETS},
        "router_stats": build_llm_router_stats(server),
    }