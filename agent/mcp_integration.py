"""
agent/mcp_integration.py — Maker MCP 连接与工具同步

负责启动外部 MCP 服务，把其工具注册到 ToolRegistry，并在 Executor 中桥接调用。
"""

from __future__ import annotations
from pathlib import Path
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from agent.tool_registry import ToolRegistry
    from core.config import Config
    from core.event_log import EventLog
    from core.executor import Executor


class MCPIntegration:
    """管理 Maker MCP 客户端生命周期与工具同步。"""

    def __init__(
        self,
        config: "Config",
        tools: "ToolRegistry",
        executor: "Executor",
        event_log: "EventLog",
    ):
        self.config = config
        self.tools = tools
        self.executor = executor
        self.event_log = event_log
        self.connected_at: Optional[float] = None
        self.last_error: Optional[str] = None
        self.last_call: Optional[Dict[str, Any]] = None
        self.mcp_client = self._connect_mcp()

    def attach(self, tools: "ToolRegistry", executor: "Executor") -> None:
        """Attach this shared MCP client to another session's tool/executor pair."""
        if not self.mcp_client:
            return
        executor.set_remote_commit_resolver(self.resolve_remote_commit_state)
        remote_tools = self.mcp_client.list_tools()
        for tool in remote_tools:
            name = tool.get("name")
            if not name:
                continue
            tools.register(
                name=name,
                description=tool.get("description", ""),
                parameters=tool.get("inputSchema", {}),
                handler=lambda **kwargs: {"ok": False, "error": "MCP 工具应通过 Executor 调用"},
                source="maker_mcp",
            )
            executor.register_maker_tool(name, self._maker_handler)
        self._register_unavailable_proxy_tools(tools, executor, remote_tools)

    def _connect_mcp(self) -> Optional[Any]:
        """根据配置连接 Maker MCP。"""
        from agent.mcp_client import MakerMCPClient

        mcp_cfg = self.config.maker_mcp_config()
        if not mcp_cfg:
            return None
        try:
            client = MakerMCPClient(
                command=mcp_cfg.get("command", "node"),
                args=mcp_cfg.get("args", []),
                cwd=Path(mcp_cfg.get("cwd", self.config.project_root())),
                env=mcp_cfg.get("env"),
                request_timeout_seconds=self.config.maker_mcp_request_timeout_seconds(),
            )
            client.start()
            self.connected_at = time.time()
            self.last_error = None
            self.executor.set_remote_commit_resolver(self.resolve_remote_commit_state)
            remote_tools = client.list_tools()
            for tool in remote_tools:
                name = tool.get("name")
                if not name:
                    continue
                self.tools.register(
                    name=name,
                    description=tool.get("description", ""),
                    parameters=tool.get("inputSchema", {}),
                    handler=lambda **kwargs: {"ok": False, "error": "MCP 工具应通过 Executor 调用"},
                    source="maker_mcp",
                )
                self.executor.register_maker_tool(name, self._maker_handler)
            self._register_unavailable_proxy_tools(self.tools, self.executor, remote_tools)
            return client
        except Exception as e:
            self.connected_at = None
            self.last_error = str(e)
            from core.event_log import Event
            self.event_log.append(Event.create(
                "mcp_connection_failed",
                session_id="init",
                source="runtime",
                payload={"error": str(e)},
            ))
            return None

    def _register_unavailable_proxy_tools(
        self,
        tools: "ToolRegistry",
        executor: "Executor",
        remote_tools: List[Dict[str, Any]],
    ) -> None:
        """Expose expected Maker creative tools as controlled local proxies.

        When the official MCP server does not list a creative proxy tool, the
        Agent still needs a stable, machine-readable route instead of an
        unknown-tool failure. These placeholders do not pretend that the remote
        capability exists; execution returns a structured remote-capability
        error that the LLM and GUI can repair around.
        """
        remote_names = {str(tool.get("name") or "") for tool in remote_tools}
        required = sorted(str(name) for name in getattr(executor, "MAKER_PROXY_TOOLS", set()))
        for name in required:
            if not name or name in remote_names:
                continue
            tools.register(
                name=name,
                description=(
                    "受控 Maker 创意代理占位：当前 Maker MCP tools/list 未暴露该远程工具。"
                    "调用会返回 maker_proxy_not_exposed，用于一键修复后的可诊断降级。"
                ),
                parameters={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": True,
                },
                handler=lambda **kwargs: {"ok": False, "error": "MCP 工具应通过 Executor 调用"},
                source="maker_mcp_unavailable",
            )
            executor.register_maker_tool(name, self._unavailable_proxy_handler)

    def _unavailable_proxy_handler(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        result = {
            "ok": False,
            "tool": tool_name,
            "error": f"Maker MCP 当前未暴露远程工具：{tool_name}",
            "error_type": "maker_proxy_not_exposed",
            "failure_type": "remote_capability_missing",
            "remote_exposed": False,
            "repairable": True,
            "suggested_fix": (
                "请在 GUI 的 Maker 接入中点击一键修复完成安装/升级/授权/重连；"
                "如果重连后仍缺失，说明当前官方 Maker MCP 未向该账号或环境开放此远程能力。"
            ),
            "params_keys": sorted(kwargs.keys()),
            "timestamp": time.time(),
        }
        self.last_error = result["error"]
        self.last_call = {
            "tool": tool_name,
            "ok": False,
            "elapsed_ms": 0,
            "error": result["error"],
            "error_type": result["error_type"],
            "timeout_seconds": None,
            "partial": False,
            "params_keys": result["params_keys"],
            "id_fields": [],
            "timestamp": result["timestamp"],
        }
        return result

    def _maker_handler(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Executor 调用 MCP 工具的桥接。"""
        started_at = time.perf_counter()
        if not self.mcp_client:
            result = {"ok": False, "error": "Maker MCP 未连接"}
            self._record_call(tool_name, kwargs, started_at, result)
            return result
        try:
            timeout_seconds = self.config.maker_mcp_request_timeout_seconds()
            result = self.mcp_client.call(tool_name, kwargs, timeout_seconds=timeout_seconds)
            if isinstance(result, dict):
                result.setdefault("timeout_seconds", timeout_seconds)
        except Exception as e:
            result = {"ok": False, "error": str(e), "error_type": e.__class__.__name__}
            if isinstance(e, TimeoutError):
                result.update({
                    "error_type": "tool_timeout",
                    "partial": True,
                    "timeout_seconds": self.config.maker_mcp_request_timeout_seconds(),
                })
                self.mcp_client = None
        self._record_call(tool_name, kwargs, started_at, result)
        return result

    def _record_call(
        self,
        tool_name: str,
        params: Dict[str, Any],
        started_at: float,
        result: Dict[str, Any],
    ) -> None:
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 1)
        ok = bool(result.get("ok"))
        if not ok:
            self.last_error = str(result.get("error", "MCP call failed"))
        self.last_call = {
            "tool": tool_name,
            "ok": ok,
            "elapsed_ms": elapsed_ms,
            "error": result.get("error"),
            "error_type": result.get("error_type"),
            "failure_type": result.get("failure_type"),
            "timeout_seconds": result.get("timeout_seconds"),
            "partial": result.get("partial", False),
            "params_keys": sorted(params.keys()),
            "id_fields": _find_id_fields(result),
            "timestamp": time.time(),
        }

    def status(self) -> Dict[str, Any]:
        tools = self.mcp_client.list_tools() if self.mcp_client else []
        cfg = self.config.maker_mcp_config()
        return {
            "connected": bool(self.mcp_client),
            "connected_at": self.connected_at,
            "tool_count": len(tools),
            "tools": [
                {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("inputSchema", {}),
                }
                for tool in tools
            ],
            "last_error": self.last_error,
            "last_call": self.last_call,
            "remote_identity": _remote_identity_diagnostics(tools, self.last_call),
            "command": cfg.get("command", ""),
            "args": cfg.get("args", []),
            "cwd": str(Path(cfg.get("cwd", self.config.project_root()))),
            "env": cfg.get("env", {}),
        }

    def stop(self) -> None:
        if self.mcp_client:
            self.mcp_client.stop()
            self.mcp_client = None

    def resolve_remote_commit_state(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        """Best-effort remote commit lookup using discovered Maker MCP tools.

        This is intentionally conservative: it only marks ``committed`` when a
        returned remote record can be matched to the uncertain observation.
        """
        if not self.mcp_client:
            return {
                "reconcile_status": "remote_lookup_unavailable",
                "reconcile_hint": "Maker MCP is not connected, so remote side effects cannot be checked.",
            }
        tools = self.mcp_client.list_tools()
        diagnostics = _remote_identity_diagnostics(tools, self.last_call)
        lookup_tools = _candidate_lookup_tools_for_observation(observation, diagnostics)
        if not lookup_tools:
            return {
                "reconcile_status": "remote_lookup_unavailable",
                "remote_identity": diagnostics,
                "reconcile_hint": "Maker MCP exposes no matching task/file lookup tool for this observation.",
            }

        attempts = []
        for tool_name in lookup_tools[:3]:
            result = self._maker_handler(tool_name)
            attempts.append({
                "tool": tool_name,
                "ok": bool(result.get("ok")),
                "id_fields": _find_id_fields(result),
                "error": result.get("error"),
            })
            if not result.get("ok"):
                continue
            match = _match_remote_record(observation, result)
            if match is not None:
                return {
                    "committed": _remote_record_committed(match),
                    "reconcile_status": "verified_remote",
                    "remote_lookup_tool": tool_name,
                    "remote_match": match,
                    "remote_lookup_attempts": attempts,
                    "observed_at": time.time(),
                }

        return {
            "reconcile_status": "remote_lookup_no_match",
            "remote_identity": diagnostics,
            "remote_lookup_attempts": attempts,
            "reconcile_hint": "Remote lookup ran, but no returned task/file matched the uncertain observation.",
            "observed_at": time.time(),
        }


def _remote_identity_diagnostics(
    tools: List[Dict[str, Any]],
    last_call: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    task_lookup_tools = []
    file_lookup_tools = []
    id_parameter_tools = []
    for tool in tools:
        name = str(tool.get("name", ""))
        haystack = f"{name} {tool.get('description', '')}".lower()
        if _is_lookup_tool(haystack) and _mentions_task(haystack):
            task_lookup_tools.append(name)
        if _is_lookup_tool(haystack) and _mentions_file(haystack):
            file_lookup_tools.append(name)
        schema = tool.get("inputSchema", {})
        if _schema_has_id_parameter(schema):
            id_parameter_tools.append(name)

    missing = []
    if not task_lookup_tools:
        missing.append("task_lookup")
    if not file_lookup_tools:
        missing.append("file_lookup")
    status = "present" if not missing else ("partial" if len(missing) == 1 else "missing")
    last_id_fields = (last_call or {}).get("id_fields") or []
    return {
        "status": status,
        "task_lookup_tools": task_lookup_tools,
        "file_lookup_tools": file_lookup_tools,
        "id_parameter_tools": id_parameter_tools,
        "missing": missing,
        "last_call_id_fields": last_id_fields,
        "summary": _remote_identity_summary(status, missing, last_id_fields),
    }


def _remote_identity_summary(status: str, missing: List[str], last_id_fields: List[str]) -> str:
    if status == "present":
        base = "Maker MCP exposes task/file lookup tools."
    elif status == "partial":
        base = f"Maker MCP remote identity lookup is partial; missing {', '.join(missing)}."
    else:
        base = "Maker MCP does not expose obvious task/file lookup tools."
    if last_id_fields:
        return f"{base} Last call returned id fields: {', '.join(last_id_fields[:6])}."
    return f"{base} No id fields observed in the last call yet."


def _is_lookup_tool(text: str) -> bool:
    return any(word in text for word in (
        "list", "get", "query", "search", "find", "fetch", "describe", "status",
        "查", "列", "搜索", "获取", "读取", "详情", "状态",
    ))


def _mentions_task(text: str) -> bool:
    return any(word in text for word in ("task", "job", "build", "任务", "构建"))


def _mentions_file(text: str) -> bool:
    return any(word in text for word in ("file", "asset", "media", "resource", "文件", "素材", "资源"))


def _schema_has_id_parameter(schema: Any) -> bool:
    if not isinstance(schema, dict):
        return False
    props = schema.get("properties", {})
    if not isinstance(props, dict):
        return False
    return any(_is_id_key(str(key)) for key in props.keys())


def _find_id_fields(value: Any, prefix: str = "", limit: int = 24) -> List[str]:
    found: List[str] = []

    def walk(current: Any, path: str) -> None:
        if len(found) >= limit:
            return
        if isinstance(current, dict):
            for key, nested in current.items():
                next_path = f"{path}.{key}" if path else str(key)
                if _is_id_key(str(key)):
                    found.append(next_path)
                    if len(found) >= limit:
                        return
                walk(nested, next_path)
        elif isinstance(current, list):
            for index, item in enumerate(current[:20]):
                walk(item, f"{path}[{index}]")

    walk(value, prefix)
    return found


def _is_id_key(key: str) -> bool:
    normalized = key.replace("-", "_").lower()
    return (
        normalized == "id"
        or normalized == "uuid"
        or normalized.endswith("_id")
        or normalized.endswith("id")
        or normalized in {"taskid", "fileid", "assetid", "resourceid"}
    )


def _candidate_lookup_tools_for_observation(
    observation: Dict[str, Any],
    diagnostics: Dict[str, Any],
) -> List[str]:
    text = f"{observation.get('tool', '')} {observation.get('path', '')}".lower()
    if _mentions_file(text):
        return list(diagnostics.get("file_lookup_tools") or [])
    if _mentions_task(text):
        return list(diagnostics.get("task_lookup_tools") or [])
    return [
        *(diagnostics.get("task_lookup_tools") or []),
        *(diagnostics.get("file_lookup_tools") or []),
    ]


def _match_remote_record(observation: Dict[str, Any], result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    candidates = _flatten_remote_records(result)
    match_values = _observation_match_values(observation)
    if not match_values:
        return None
    for record in candidates:
        record_text = json_dumps_compact(record).lower()
        if any(value and value in record_text for value in match_values):
            return record
    return None


def _observation_match_values(observation: Dict[str, Any]) -> List[str]:
    values = []
    for key in ("remote_id", "task_id", "file_id", "asset_id", "resource_id", "path", "idempotency_key"):
        value = observation.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip().lower())
    return values


def _flatten_remote_records(value: Any, limit: int = 80) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []

    def walk(current: Any) -> None:
        if len(records) >= limit:
            return
        if isinstance(current, dict):
            if any(_is_id_key(str(key)) for key in current.keys()):
                records.append(current)
            for nested in current.values():
                walk(nested)
        elif isinstance(current, list):
            for item in current[:limit]:
                walk(item)

    walk(value)
    return records


def _remote_record_committed(record: Dict[str, Any]) -> bool:
    status = str(record.get("status") or record.get("state") or "").lower()
    if status:
        if any(token in status for token in ("fail", "error", "cancel", "deleted", "missing")):
            return False
        if any(token in status for token in ("done", "success", "complete", "ready", "uploaded", "created")):
            return True
    committed = record.get("committed")
    if isinstance(committed, bool):
        return committed
    return True


def json_dumps_compact(value: Any) -> str:
    try:
        import json

        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        return str(value)
