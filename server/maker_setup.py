"""Maker setup diagnostics and project switching helpers."""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib import request

from core.portable_env import portable_diagnostics
from server.maker_faults import build_maker_fault_analysis


MAKER_PACKAGE = "@taptap/maker"
MAKER_URL = "https://maker.taptap.cn/"
MAKER_MCP_SERVER_ID = "taptap-maker"

REQUIRED_PROXY_TOOLS = [
    "generate_image",
    "batch_generate_images",
    "edit_image",
    "create_video_task",
    "query_video_task",
    "text_to_music",
    "create_3d_model_task",
    "query_3d_model_task",
]


def build_maker_setup_status(
    *,
    config: Any,
    app_root: Path,
    check_latest: bool = False,
    tool_audit: Optional[Dict[str, Any]] = None,
    pending_auth: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    project_root = Path(config.project_root()).resolve()
    maker_cfg = config.maker_mcp_config()
    configured_version = _configured_maker_version(maker_cfg)
    pinned_maker_version = bool(configured_version and configured_version != "latest")
    project = _project_state(project_root=project_root, app_root=app_root)
    agent_root_mcp = agent_root_mcp_state(app_root)
    auth = _auth_state(maker_cfg)
    runtime_cfg = config.data.get("runtime", {}) if isinstance(getattr(config, "data", None), dict) else {}
    portable_status = portable_diagnostics(
        app_root,
        configured_portable_root=Path(runtime_cfg.get("portable_root")) if runtime_cfg.get("portable_root") else None,
    )
    version = {
        "package": MAKER_PACKAGE,
        "configured": configured_version,
        "npx_available": bool(shutil.which("npx")),
        "latest": None,
        "latest_check": "skipped",
        "update_available": None,
        "install_command": "npx -y @taptap/maker install --ide codex,cursor,claude",
    }
    if check_latest:
        latest = _fetch_latest_version()
        version.update(latest)
        if latest.get("latest") and configured_version and configured_version != "latest":
            version["update_available"] = _versions_differ(configured_version, str(latest["latest"]))
        elif configured_version == "latest":
            version["update_available"] = False

    blockers: List[str] = []
    warnings: List[str] = []
    if not version["npx_available"]:
        blockers.append("npx_missing")
    if not maker_cfg:
        blockers.append("maker_mcp_config_missing")
    if project["is_app_root"]:
        warnings.append("project_root_is_ttmevolve_app_root")
    if not project["maker_initialized"]:
        blockers.append("maker_project_not_initialized")
    elif not project["project_bound"]:
        blockers.append("maker_project_not_bound")
    if not auth["tap_auth_present"]:
        blockers.append("tap_auth_missing")
    if not auth["pat_present"]:
        warnings.append("pat_missing")
    if pinned_maker_version:
        warnings.append("maker_mcp_version_pinned")
    if not agent_root_mcp.get("registered"):
        warnings.append("agent_root_mcp_missing")
    if tool_audit:
        missing_required = [
            row["name"]
            for row in tool_audit.get("required_proxy_tools", [])
            if not row.get("remote_exposed")
        ]
        if missing_required:
            warnings.append("maker_proxy_tools_missing")

    readiness = "ready"
    if blockers:
        readiness = "blocked"
    elif warnings:
        readiness = "degraded"

    status = {
        "version": "maker-setup.v1",
        "readiness": readiness,
        "blockers": blockers,
        "warnings": warnings,
        "app_root": str(app_root.resolve()),
        "project": project,
        "agent_root_mcp": agent_root_mcp,
        "maker_package": version,
        "maker_mcp_config": _maker_mcp_config_diagnostics(maker_cfg),
        "maker_mcp_raw_env": maker_cfg.get("env", {}) if isinstance(maker_cfg, dict) else {},
        "portable_runtime": portable_status,
        "auth": auth,
        "tool_audit": tool_audit or {},
        "pending_auth": pending_auth or {},
        "wizard": _wizard_state(project),
        "commands": {
            "install_maker_mcp": "npx -y @taptap/maker install --ide codex,cursor,claude",
            "init_current_project": "npx -y @taptap/maker init",
            "recommended_next": _recommended_next(blockers, warnings, project),
        },
        "endpoints": {
            "setup_status": "/maker/setup-status",
            "setup_status_markdown": "/maker/setup-status.md",
            "tool_audit": "/maker/tool-audit",
            "project_select": "/maker/project/select",
            "auth_prepare": "/maker/auth/prepare",
            "auth_complete": "/maker/auth/complete",
            "repair": "/maker/repair",
            "maker_page": MAKER_URL,
        },
    }
    status["fault_analysis"] = build_maker_fault_analysis(
        setup_status=status,
        tool_audit=tool_audit or {},
        portable_status=portable_status,
    )
    return status


def build_maker_tool_audit(*, agent: Any) -> Dict[str, Any]:
    mcp_tools: List[Dict[str, Any]] = []
    mcp_connected = False
    mcp_error = ""
    integration = getattr(agent, "mcp_integration", None)
    if integration is not None:
        try:
            status = integration.status()
            mcp_connected = bool(status.get("connected"))
            mcp_tools = status.get("tools") if isinstance(status.get("tools"), list) else []
            mcp_error = str(status.get("last_error") or "")
        except Exception as exc:
            mcp_error = str(exc)

    remote_names = {str(tool.get("name")) for tool in mcp_tools if tool.get("name")}
    registry_tools = getattr(agent, "tools", None)
    registered = set()
    registry_sources: Dict[str, str] = {}
    if registry_tools is not None:
        for tool in registry_tools.list_tools():
            name = str(tool.get("name") or "")
            if not name:
                continue
            registered.add(name)
            registry_sources[name] = str(tool.get("source") or "")

    executor = getattr(agent, "executor", None)
    handlers = set(getattr(executor, "_tool_handlers", {}).keys()) if executor is not None else set()
    proxy_marked = set(getattr(executor, "MAKER_PROXY_TOOLS", set())) if executor is not None else set()

    required_rows = []
    for name in REQUIRED_PROXY_TOOLS:
        required_rows.append({
            "name": name,
            "remote_exposed": name in remote_names,
            "registered": name in registered,
            "executor_handler": name in handlers,
            "side_effect_proxy": name in proxy_marked,
            "source": registry_sources.get(name, ""),
        })

    remote_rows = []
    for name in sorted(remote_names):
        remote_rows.append({
            "name": name,
            "registered": name in registered,
            "executor_handler": name in handlers,
            "source": registry_sources.get(name, ""),
            "required_proxy": name in REQUIRED_PROXY_TOOLS,
        })

    missing_registration = [row["name"] for row in remote_rows if not row["registered"] or not row["executor_handler"]]
    missing_required = [row["name"] for row in required_rows if not row["remote_exposed"]]
    missing_proxy_mark = [row["name"] for row in required_rows if not row["side_effect_proxy"]]
    missing_required_local_handlers = [
        row["name"]
        for row in required_rows
        if not row["registered"] or not row["executor_handler"]
    ]
    local_registration_complete = not missing_registration and not missing_proxy_mark and not missing_required_local_handlers
    remote_capability_complete = not missing_required
    if not mcp_connected:
        readiness = "blocked"
    elif not local_registration_complete:
        readiness = "blocked"
    elif not remote_capability_complete:
        readiness = "degraded"
    else:
        readiness = "ready"
    ok = readiness == "ready"

    return {
        "version": "maker-tool-audit.v1",
        "ok": ok,
        "readiness": readiness,
        "mcp_connected": mcp_connected,
        "mcp_error": mcp_error,
        "remote_tool_count": len(remote_names),
        "registered_tool_count": len(registered),
        "handler_count": len(handlers),
        "required_proxy_tools": required_rows,
        "remote_tools": remote_rows,
        "missing_registration": missing_registration,
        "missing_required_local_handlers": missing_required_local_handlers,
        "missing_required_proxy_tools": missing_required,
        "missing_proxy_side_effect_marks": missing_proxy_mark,
        "local_registration_complete": local_registration_complete,
        "remote_capability_complete": remote_capability_complete,
        "repair_ok": bool(mcp_connected and local_registration_complete),
        "reconnect_can_fix": bool((not mcp_connected) or missing_registration),
        "requires_remote_capability": bool(mcp_connected and local_registration_complete and missing_required),
        "restart_required": False,
        "diagnosis": _tool_audit_diagnosis(
            mcp_connected=mcp_connected,
            missing_registration=missing_registration,
            missing_required_local_handlers=missing_required_local_handlers,
            missing_proxy_mark=missing_proxy_mark,
            missing_required=missing_required,
        ),
        "next_action": _tool_audit_next_action(
            mcp_connected=mcp_connected,
            missing_registration=missing_registration,
            missing_required_local_handlers=missing_required_local_handlers,
            missing_proxy_mark=missing_proxy_mark,
            missing_required=missing_required,
        ),
    }


def render_maker_setup_markdown(status: Dict[str, Any]) -> str:
    project = status.get("project") if isinstance(status.get("project"), dict) else {}
    auth = status.get("auth") if isinstance(status.get("auth"), dict) else {}
    package = status.get("maker_package") if isinstance(status.get("maker_package"), dict) else {}
    audit = status.get("tool_audit") if isinstance(status.get("tool_audit"), dict) else {}
    agent_root_mcp = status.get("agent_root_mcp") if isinstance(status.get("agent_root_mcp"), dict) else {}
    required = audit.get("required_proxy_tools") if isinstance(audit.get("required_proxy_tools"), list) else []
    rows = [
        "# Maker Setup Doctor",
        "",
        f"- readiness: `{status.get('readiness')}`",
        f"- project_root: `{project.get('root')}`",
        f"- maker_initialized: `{project.get('maker_initialized')}`",
        f"- project_id: `{project.get('project_id') or '-'}`",
        f"- project_bound: `{project.get('project_bound')}`",
        f"- agent_root_mcp: `{agent_root_mcp.get('registered')}` files=`{agent_root_mcp.get('registered_count')}/{agent_root_mcp.get('target_count')}`",
        f"- tap_auth: `{auth.get('tap_auth_present')}`",
        f"- pat: `{auth.get('pat_present')}`",
        f"- maker_version: `{package.get('configured') or '-'}` latest=`{package.get('latest') or '-'}`",
        f"- tool_audit: `{audit.get('readiness') or '-'}` `{audit.get('diagnosis') or '-'}`",
        f"- npx_available: `{package.get('npx_available')}`",
        "",
        "## Next",
        f"- `{(status.get('commands') or {}).get('recommended_next') or '-'}`",
        "",
        "## Required Proxy Tools",
    ]
    if required:
        for row in required:
            rows.append(
                f"- `{row.get('name')}` remote=`{row.get('remote_exposed')}` "
                f"registered=`{row.get('registered')}` handler=`{row.get('executor_handler')}` "
                f"side_effect=`{row.get('side_effect_proxy')}`"
            )
    else:
        rows.append("- no audit data")
    rows.extend([
        "",
        "## Fault Analysis",
        f"- readiness: `{(status.get('fault_analysis') or {}).get('readiness') or '-'}`",
        f"- automatic: `{', '.join(((status.get('fault_analysis') or {}).get('one_click_repair') or {}).get('automatic_faults') or []) or '-'}`",
        f"- manual: `{', '.join(((status.get('fault_analysis') or {}).get('one_click_repair') or {}).get('manual_faults') or []) or '-'}`",
        "",
        "## Commands",
        f"- install: `{(status.get('commands') or {}).get('install_maker_mcp')}`",
        f"- init: `{(status.get('commands') or {}).get('init_current_project')}`",
        "",
        "After auth succeeds, open https://maker.taptap.cn/ in the embedded Maker browser.",
    ])
    return "\n".join(rows)


def prepare_auth_flow(auth_url: str = "") -> Dict[str, Any]:
    url = str(auth_url or "").strip()
    maker_home = _maker_home()
    return {
        "version": "maker-auth-flow.v1",
        "ok": True,
        "auth_url": url,
        "open_in_embedded_browser": bool(url),
        "after_success_url": MAKER_URL,
        "poll_files": [str(maker_home / "tap-auth.json"), str(maker_home / "pat.json")],
        "note": (
            "If the Maker CLI prints an authorization URL, pass it here and navigate the Electron BrowserView. "
            "Do not rely on system default browser windows."
        ),
    }


def complete_auth_flow() -> Dict[str, Any]:
    auth = _auth_state()
    ok = bool(auth.get("tap_auth_present"))
    return {
        "ok": ok,
        "auth": auth,
        "navigate_to": MAKER_URL if ok else "",
        "next_action": "Open Maker home in the embedded browser." if ok else "Finish TapTap authorization first.",
    }


def record_recent_project(storage_root: Path, project_root: Path) -> Dict[str, Any]:
    path = storage_root / "maker_projects.json"
    items: List[Dict[str, Any]] = []
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                items = [item for item in loaded if isinstance(item, dict)]
        except Exception:
            items = []
    root_text = str(project_root.resolve())
    items = [item for item in items if item.get("root") != root_text]
    items.insert(0, {"root": root_text, "last_used_at": time.time()})
    items = items[:12]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "recent_projects": items}


def agent_root_mcp_state(app_root: Path) -> Dict[str, Any]:
    root = Path(app_root).resolve()
    targets = _agent_root_mcp_targets(root)
    rows = []
    for target in targets:
        path = Path(target["path"])
        registered = _target_has_maker_server(path, target["kind"])
        rows.append({
            **target,
            "path": str(path),
            "exists": path.exists(),
            "registered": registered,
        })
    registered_count = sum(1 for row in rows if row.get("registered"))
    return {
        "version": "agent-root-mcp.v1",
        "root": str(root),
        "server_id": MAKER_MCP_SERVER_ID,
        "registered": registered_count == len(rows),
        "registered_count": registered_count,
        "target_count": len(rows),
        "targets": rows,
    }


def ensure_agent_root_maker_mcp_registration(app_root: Path) -> Dict[str, Any]:
    root = Path(app_root).resolve()
    server = _agent_root_maker_server(root)
    changed = []
    for target in _agent_root_mcp_targets(root):
        path = Path(target["path"])
        before = path.read_text(encoding="utf-8") if path.exists() else ""
        if target["kind"] == "json":
            _write_mcp_json(path, server)
        elif target["kind"] == "codex_toml":
            _write_codex_toml(path, server)
        after = path.read_text(encoding="utf-8") if path.exists() else ""
        if before != after:
            changed.append(str(path))
    state = agent_root_mcp_state(root)
    return {
        "ok": bool(state.get("registered")),
        "changed": changed,
        "state": state,
    }


def _project_state(*, project_root: Path, app_root: Path) -> Dict[str, Any]:
    exists = project_root.exists()
    maker_config = project_root / ".maker-mcp" / "config.json"
    project_settings = project_root / ".project" / "settings.json"
    scripts_main = project_root / "scripts" / "main.lua"
    maker_initialized = maker_config.exists() or project_settings.exists()
    project_id = _read_project_id(maker_config) or _read_project_id(project_settings)
    project_bound = _valid_project_id(project_id)
    root_is_empty = False
    if exists and project_root.is_dir():
        try:
            ignored = {".git", ".maker-mcp", ".project"}
            visible = [p for p in project_root.iterdir() if p.name not in ignored]
            root_is_empty = len(visible) == 0
        except Exception:
            root_is_empty = False
    return {
        "root": str(project_root),
        "exists": exists,
        "is_dir": project_root.is_dir() if exists else False,
        "is_app_root": _same_path(project_root, app_root),
        "root_is_empty": root_is_empty,
        "maker_initialized": maker_initialized,
        "maker_config": str(maker_config),
        "maker_config_exists": maker_config.exists(),
        "project_settings": str(project_settings),
        "project_settings_exists": project_settings.exists(),
        "scripts_main_exists": scripts_main.exists(),
        "project_id": project_id,
        "project_bound": project_bound,
    }


def _agent_root_mcp_targets(root: Path) -> List[Dict[str, str]]:
    return [
        {"id": "cursor", "label": "Cursor", "kind": "json", "path": str(root / ".cursor" / "mcp.json")},
        {"id": "claude", "label": "Claude", "kind": "json", "path": str(root / ".mcp.json")},
        {"id": "codex_json", "label": "Codex MCP JSON", "kind": "json", "path": str(root / ".codex" / "mcp.json")},
        {"id": "codex_toml", "label": "Codex config", "kind": "codex_toml", "path": str(root / ".codex" / "config.toml")},
    ]


def _agent_root_maker_server(root: Path) -> Dict[str, Any]:
    env = {
        "TAPTAP_MCP_ENV": "production",
        "TAPTAP_MAKER_HOME": str(root / "portable" / "home" / ".taptap-maker"),
        "TTM_MAKER_HOME": str(root / "portable" / "home" / ".taptap-maker"),
    }
    if os.name == "nt":
        return {
            "command": "cmd.exe",
            "args": ["/d", "/s", "/c", "npx.cmd", "-y", "-p", MAKER_PACKAGE, "taptap-maker"],
            "cwd": str(root),
            "env": env,
        }
    return {
        "command": "npx",
        "args": ["-y", "-p", MAKER_PACKAGE, "taptap-maker"],
        "cwd": str(root),
        "env": env,
    }


def _target_has_maker_server(path: Path, kind: str) -> bool:
    if not path.exists():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return False
    if kind == "codex_toml":
        return MAKER_MCP_SERVER_ID in text and MAKER_PACKAGE in text
    try:
        data = json.loads(text)
    except Exception:
        return False
    servers = data.get("mcpServers") or data.get("mcp_servers") or {}
    if not isinstance(servers, dict):
        return False
    server = servers.get(MAKER_MCP_SERVER_ID) or servers.get("maker") or servers.get("taptap_maker")
    if not isinstance(server, dict):
        return False
    haystack = " ".join([str(server.get("command") or ""), *[str(arg) for arg in server.get("args") or []]])
    return MAKER_PACKAGE in haystack or "taptap-maker" in haystack


def _write_mcp_json(path: Path, server: Dict[str, Any]) -> None:
    data: Dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except Exception:
            data = {}
    servers = data.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        data["mcpServers"] = {}
        servers = data["mcpServers"]
    servers[MAKER_MCP_SERVER_ID] = server
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_codex_toml(path: Path, server: Dict[str, Any]) -> None:
    block = _codex_toml_block(server)
    start = "# TTMEvolve Maker MCP begin"
    end = "# TTMEvolve Maker MCP end"
    text = ""
    if path.exists():
        text = path.read_text(encoding="utf-8")
    pattern = re.compile(rf"{re.escape(start)}.*?{re.escape(end)}\s*", re.S)
    replacement = f"{start}\n{block}\n{end}\n"
    if pattern.search(text):
        text = pattern.sub(replacement, text)
    else:
        text = text.rstrip() + ("\n\n" if text.strip() else "") + replacement
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _codex_toml_block(server: Dict[str, Any]) -> str:
    args = ", ".join(json.dumps(str(arg), ensure_ascii=False) for arg in server.get("args") or [])
    env = server.get("env") if isinstance(server.get("env"), dict) else {}
    lines = [
        f'[mcp_servers."{MAKER_MCP_SERVER_ID}"]',
        f'command = {json.dumps(str(server.get("command") or ""), ensure_ascii=False)}',
        f"args = [{args}]",
        f'cwd = {json.dumps(str(server.get("cwd") or ""), ensure_ascii=False)}',
        f'[mcp_servers."{MAKER_MCP_SERVER_ID}".env]',
    ]
    for key, value in env.items():
        lines.append(f"{key} = {json.dumps(str(value), ensure_ascii=False)}")
    return "\n".join(lines)


def _auth_state(maker_cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    maker_home = _maker_home(maker_cfg)
    tap_auth = maker_home / "tap-auth.json"
    pat = maker_home / "pat.json"
    return {
        "maker_home": str(maker_home),
        "tap_auth_path": str(tap_auth),
        "tap_auth_present": tap_auth.exists(),
        "pat_path": str(pat),
        "pat_present": pat.exists(),
    }


def _maker_home(maker_cfg: Optional[Dict[str, Any]] = None) -> Path:
    cfg_env = maker_cfg.get("env") if isinstance(maker_cfg, dict) else {}
    if not isinstance(cfg_env, dict):
        cfg_env = {}
    return Path(
        cfg_env.get("TAPTAP_MAKER_HOME")
        or cfg_env.get("TTM_MAKER_HOME")
        or os.environ.get("TAPTAP_MAKER_HOME")
        or os.environ.get("TTM_MAKER_HOME")
        or (Path.home() / ".taptap-maker")
    ).resolve()


def _wizard_state(project: Dict[str, Any]) -> Dict[str, Any]:
    actions = [
        {
            "id": "new_empty_directory",
            "label": "Create or choose an empty Maker game directory",
            "endpoint": "/maker/project/select",
            "payload": {"path": "D:/CC/<game-name>", "create": True, "initialize": False},
        },
        {
            "id": "switch_existing_directory",
            "label": "Switch to an existing local Maker directory",
            "endpoint": "/maker/project/select",
            "payload": {"path": project.get("root"), "create": False, "initialize": False},
        },
        {
            "id": "initialize_selected_directory",
            "label": "Initialize the selected directory with Maker CLI",
            "command": "npx -y @taptap/maker init",
        },
        {
            "id": "pull_or_bind_remote_project",
            "label": "Use Maker CLI project binding after switching directory",
            "command": "npx -y @taptap/maker init",
        },
    ]
    return {
        "active_project_root": project.get("root"),
        "safe_to_init_here": bool(project.get("exists") and project.get("is_dir") and not project.get("is_app_root")),
        "actions": actions,
        "rule": "Keep the TTMEvolve app root separate from each Maker game project root.",
    }


def _configured_maker_version(maker_cfg: Dict[str, Any]) -> str:
    args = maker_cfg.get("args") if isinstance(maker_cfg, dict) else []
    if not isinstance(args, list):
        return ""
    text_args = " ".join(str(arg) for arg in args)
    for arg in args:
        text = str(arg)
        match = re.search(r"@taptap/maker@([^\s]+)", text)
        if match:
            return match.group(1)
    if "@taptap/maker" in text_args:
        return "latest"
    return ""


def _maker_mcp_config_diagnostics(maker_cfg: Dict[str, Any]) -> Dict[str, Any]:
    args = maker_cfg.get("args") if isinstance(maker_cfg, dict) else []
    args_text = " ".join(str(arg) for arg in args) if isinstance(args, list) else str(args or "")
    configured_version = _configured_maker_version(maker_cfg)
    return {
        "command": str(maker_cfg.get("command") or "") if isinstance(maker_cfg, dict) else "",
        "args": args if isinstance(args, list) else [],
        "cwd": str(maker_cfg.get("cwd") or "") if isinstance(maker_cfg, dict) else "",
        "configured_version": configured_version,
        "uses_latest_package": configured_version == "latest",
        "looks_like_taptap_maker": "@taptap/maker" in args_text or "taptap-maker" in args_text,
    }


def ensure_internal_maker_mcp_latest_config(config: Any, project_root: Path) -> Dict[str, Any]:
    """Keep TTMEvolve's own Maker MCP launcher on the latest package.

    The official installer updates external IDE MCP configs. TTMEvolve also has
    its own config entry, so reconnect must not keep using an old pinned package.
    """
    maker_cfg = config.data.setdefault("maker_mcp", {})
    if not isinstance(maker_cfg, dict):
        config.data["maker_mcp"] = {}
        maker_cfg = config.data["maker_mcp"]

    before = json.loads(json.dumps(maker_cfg, ensure_ascii=False, default=str))
    current_args = maker_cfg.get("args") if isinstance(maker_cfg.get("args"), list) else []
    args_text = " ".join(str(arg) for arg in current_args)
    can_normalize = not current_args or "@taptap/maker" in args_text or "taptap-maker" in args_text

    if can_normalize:
        if os.name == "nt":
            maker_cfg["command"] = "cmd.exe"
            maker_cfg["args"] = ["/d", "/s", "/c", "npx.cmd", "-y", "-p", MAKER_PACKAGE, "taptap-maker"]
        else:
            maker_cfg["command"] = "npx"
            maker_cfg["args"] = ["-y", "-p", MAKER_PACKAGE, "taptap-maker"]
    maker_cfg["cwd"] = str(Path(project_root).resolve())
    env = maker_cfg.setdefault("env", {})
    if isinstance(env, dict):
        env["TAPTAP_MCP_ENV"] = "production"
        maker_home = _config_maker_home(config)
        env["TAPTAP_MAKER_HOME"] = str(maker_home)
        env["TTM_MAKER_HOME"] = str(maker_home)
    maker_cfg.setdefault("request_timeout_seconds", 30)

    after = json.loads(json.dumps(maker_cfg, ensure_ascii=False, default=str))
    return {
        "changed": before != after,
        "normalized": can_normalize,
        "before": _maker_mcp_config_diagnostics(before),
        "after": _maker_mcp_config_diagnostics(after),
    }


def _config_maker_home(config: Any) -> Path:
    try:
        portable_root = config.portable_root()
    except Exception:
        portable_root = Path(getattr(config, "base_dir", Path.cwd())) / "portable"
    return (Path(portable_root).resolve() / "home" / ".taptap-maker").resolve()


def _fetch_latest_version() -> Dict[str, Any]:
    try:
        req = request.Request(
            "https://registry.npmjs.org/@taptap%2Fmaker/latest",
            headers={"Accept": "application/json"},
            method="GET",
        )
        with request.urlopen(req, timeout=2.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return {"latest": data.get("version"), "latest_check": "ok"}
    except Exception as exc:
        return {"latest": None, "latest_check": "unavailable", "latest_error": str(exc)}


def _versions_differ(current: str, latest: str) -> bool:
    return current.strip().lower() != latest.strip().lower()


def _read_project_id(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    for key, value in _walk_json(data):
        normalized = key.replace("-", "_").lower()
        if normalized in {"project_id", "projectid", "app_id", "appid"} and isinstance(value, (str, int)):
            return str(value)
    return ""


def _valid_project_id(value: str) -> bool:
    text = str(value or "").strip().lower()
    return bool(text and text not in {"0", "none", "null", "undefined"})


def _walk_json(value: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, nested in value.items():
            yield str(key), nested
            yield from _walk_json(nested)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_json(item)


def _same_path(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except Exception:
        return str(a).lower() == str(b).lower()


def _recommended_next(blockers: List[str], warnings: List[str], project: Dict[str, Any]) -> str:
    if "maker_mcp_config_missing" in blockers:
        return "请先安装或升级 Maker MCP，然后重新检测。"
    if project.get("is_app_root"):
        return "请选择或新建一个单独的空白 Maker 游戏项目目录。"
    if "maker_project_not_initialized" in blockers:
        return "请在当前选择的游戏目录中执行 Maker 初始化。"
    if "maker_project_not_bound" in blockers:
        return "当前目录只有残缺 Maker 配置，尚未绑定真实 Maker 项目；请重新执行 Maker 初始化并选择或创建项目。"
    if "tap_auth_missing" in blockers:
        return "请在内置 Maker 浏览器中完成 TapTap 授权。"
    if "maker_mcp_version_pinned" in warnings:
        return "内部 Maker MCP 仍固定旧版本；请点击一键修复或重连审计，切换为自动使用最新版。"
    if "agent_root_mcp_missing" in warnings:
        return "TTMEvolve Agent 根目录尚未注册 Maker MCP；请点击一键修复写入根目录 MCP 配置。"
    if "maker_proxy_tools_missing" in warnings:
        return "请重连 Maker MCP，并重新检查远程是否暴露创意代理工具。"
    return "已可开始一个小型 Maker 实战任务。"


def _tool_audit_diagnosis(
    *,
    mcp_connected: bool,
    missing_registration: List[str],
    missing_required_local_handlers: List[str],
    missing_proxy_mark: List[str],
    missing_required: List[str],
) -> str:
    if not mcp_connected:
        return "Maker MCP 未连接，无法读取远程工具列表。"
    if missing_registration:
        return "远程工具已暴露，但尚未同步注册到 Agent；当前进程可通过重连修复。"
    if missing_required_local_handlers:
        return "创意代理工具尚未挂载到 Agent 占位入口；请点击一键修复重连注册。"
    if missing_proxy_mark:
        return "执行器缺少代理副作用标记，需要更新本地执行器配置。"
    if missing_required:
        return (
            f"一键修复已完成本地挂载；Maker MCP 当前 tools/list 仍未暴露 {len(missing_required)} 个创意代理远程能力，"
            "调用这些工具会得到可诊断的 maker_proxy_not_exposed，等待升级、授权或官方开放后即可转为真调用。"
        )
    return "Maker MCP 远程工具已暴露，并已同步注册到 Agent 与执行器。"


def _tool_audit_next_action(
    *,
    mcp_connected: bool,
    missing_registration: List[str],
    missing_required_local_handlers: List[str],
    missing_proxy_mark: List[str],
    missing_required: List[str],
) -> str:
    if not mcp_connected:
        return "请先修复 Maker MCP 连接，再检查远程代理工具。"
    if missing_registration:
        return "请重连 Maker MCP，让远程工具重新注册到 Agent 和执行器。"
    if missing_required_local_handlers:
        return "请点击一键修复，把缺失创意工具挂载为受控代理入口。"
    if missing_proxy_mark:
        return "请补齐执行器中的代理工具标记，确保远程副作用可追踪。"
    if missing_required:
        return "本地代理入口已修复；远程 Maker MCP 尚未暴露全部创意能力，等待升级、授权或官方开放。"
    return "Maker MCP 工具已暴露、已注册，并可通过执行器调用。"
