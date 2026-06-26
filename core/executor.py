"""
core/executor.py — 执行网关（Shield）

Agent 层只负责提出动作候选，核心运转层的 Executor 负责：
1. 调用 Sandbox 验证动作边界
2. 调用 ApprovalEngine 确认高风险动作
3. 执行动作
4. 记录不可变事件日志
5. 拒绝越权动作
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
import hashlib
import inspect
import json
import os
import shutil
import subprocess
import time

from .event_log import EventLog, Event
from .version_manager import VersionManager
from .sandbox import Sandbox, SandboxMode
from .approval import ApprovalEngine, ApprovalPolicy
from .commit_state import CommitStateStore, reconcile_observation


class Executor:
    """
    核心运转层的执行网关。
    所有 Agent 动作必须通过此处执行。
    """

    # 允许直接执行的本地工具
    ALLOWED_LOCAL_TOOLS = {
        "project_status",
        "read_file",
        "list_directory",
        "search_files",
        "query_skills",
        "execute_shell",
        "modify_file",
        "delete_file",
        "git_commit",
        "browser_navigate",
        "browser_click",
        "browser_evaluate",
        "browser_screenshot",
    }

    # Maker MCP 远程代理工具
    MAKER_PROXY_TOOLS = {
        "generate_image",
        "batch_generate_images",
        "edit_image",
        "create_video_task",
        "query_video_task",
        "text_to_music",
        "create_3d_model_task",
        "query_3d_model_task",
    }

    WRITE_LIKE_TOOLS = {
        "modify_file",
        "delete_file",
        "git_commit",
        *MAKER_PROXY_TOOLS,
    }

    def __init__(
        self,
        project_root: Path,
        event_log: EventLog,
        version_manager: VersionManager,
        human_confirm_callback: Optional[Callable[[str], bool]] = None,
        sandbox_mode: SandboxMode = SandboxMode.WORKSPACE_WRITE,
        approval_policy: ApprovalPolicy = ApprovalPolicy.ON_REQUEST,
        risk_levels: Optional[Dict[str, str]] = None,
        browser_service: Optional[Any] = None,
        tool_timeout_seconds: float = 45.0,
        shell_timeout_seconds: Optional[float] = None,
    ):
        self.project_root = Path(project_root)
        self.event_log = event_log
        self.version_manager = version_manager
        self.human_confirm_callback = human_confirm_callback
        self.sandbox = Sandbox(self.project_root, sandbox_mode)
        self.approval = ApprovalEngine(approval_policy, human_confirm_callback, risk_levels)
        self._tool_handlers: Dict[str, Callable[..., Any]] = {}
        self._maker_tool_names: set[str] = set()
        self._dynamic_tools: Dict[str, Dict[str, Any]] = {}
        self._browser_service = browser_service
        self.tool_timeout_seconds = float(tool_timeout_seconds or 45.0)
        self.shell_timeout_seconds = float(shell_timeout_seconds or self.tool_timeout_seconds)
        self.commit_state_store = CommitStateStore(self.project_root / ".ttmevolve" / "commit_state.jsonl")
        self.remote_commit_resolver: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None
        self._register_local_handlers()

    def set_browser_service(self, browser_service: Optional[Any]) -> None:
        """由 AppServer 注入共享的 BrowserService 实例。"""
        self._browser_service = browser_service

    def register_maker_tool(self, name: str, handler: Callable[..., Any]) -> None:
        """注册单个 Maker MCP 工具的调用函数（handler 接收 tool_name, **params）。"""
        self._tool_handlers[name] = handler
        self._maker_tool_names.add(name)

    def clear_maker_tools(self) -> None:
        """Remove remote Maker MCP handlers before reconnecting."""
        for name in list(self._maker_tool_names):
            self._tool_handlers.pop(name, None)
        self._maker_tool_names.clear()

    def set_remote_commit_resolver(
        self,
        resolver: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]],
    ) -> None:
        self.remote_commit_resolver = resolver

    def register_dynamic_tool(self, name: str, handler: Callable[..., Any], risk_level: str = "low") -> None:
        """注册 Agent 自生成的动态工具。"""
        self._tool_handlers[name] = handler
        self._dynamic_tools[name] = {"risk_level": risk_level}
        # 让 approval engine 也知道动态工具的风险等级
        self.approval.risk_levels[name] = risk_level

    def propose_action(
        self,
        session_id: str,
        tool_name: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Agent 层调用此接口提交动作候选。
        返回执行结果或拒绝原因。
        """
        self.event_log.append(Event.create(
            event_type="action_proposed",
            session_id=session_id,
            source="agent",
            payload={"tool": tool_name, "params": params},
        ))

        # 1. Sandbox 校验
        sandbox_verdict = self.sandbox.validate(tool_name, params)
        if not sandbox_verdict["allowed"]:
            self.event_log.append(Event.create(
                event_type="action_rejected",
                session_id=session_id,
                source="runtime",
                payload={"tool": tool_name, "reason": sandbox_verdict["reason"]},
            ))
            return {"ok": False, "error": sandbox_verdict["reason"]}

        # 2. Approval 校验
        approval_verdict = self.approval.check(tool_name, params)
        if not approval_verdict["allowed"]:
            self.event_log.append(Event.create(
                event_type="action_rejected",
                session_id=session_id,
                source="runtime",
                payload={"tool": tool_name, "reason": approval_verdict["reason"]},
            ))
            return {"ok": False, "error": approval_verdict["reason"]}

        result = self._execute(session_id, tool_name, params)
        self.event_log.append(Event.create(
            event_type="action_executed",
            session_id=session_id,
            source="runtime",
            payload={"tool": tool_name, "params": params, "result_summary": self._summarize(result)},
        ))
        return result

    def _execute(self, session_id: str, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        handler = self._tool_handlers.get(tool_name)
        if not handler:
            return {"ok": False, "error": f"未注册工具处理器: {tool_name}"}

        idempotency_key = self._idempotency_key(session_id, tool_name, params)
        side_effecting = self._is_side_effecting_tool(tool_name)
        if tool_name == "execute_shell":
            side_effecting = self._looks_like_write_command(str(params.get("command", "")))
        # 修改文件前自动快照
        if tool_name in {"modify_file", "delete_file"}:
            self.version_manager.snapshot(
                description=f"Before {tool_name} in session {session_id}",
                paths=[params.get("path", "")],
            )

        started_at = time.perf_counter()
        try:
            if tool_name in self.MAKER_PROXY_TOOLS:
                result = handler(tool_name, **params)
            elif tool_name in self._dynamic_tools:
                call_params = dict(params)
                if self._handler_accepts_session_id(handler):
                    call_params["_session_id"] = session_id
                result = handler(**call_params)
            else:
                call_params = dict(params)
                if tool_name == "execute_shell":
                    call_params["_session_id"] = session_id
                result = handler(**call_params)
            if isinstance(result, dict):
                result.setdefault("tool", tool_name)
                result.setdefault("elapsed_ms", round((time.perf_counter() - started_at) * 1000, 1))
                self._attach_commit_state(
                    result,
                    idempotency_key=idempotency_key,
                    side_effecting=side_effecting,
                )
                self.commit_state_store.record(result)
            return result
        except subprocess.TimeoutExpired as e:
            return self._timeout_result(
                tool_name=tool_name,
                timeout_seconds=e.timeout or self.tool_timeout_seconds,
                started_at=started_at,
                idempotency_key=idempotency_key,
                side_effecting=side_effecting,
                stdout=e.stdout,
                stderr=e.stderr,
            )
        except TimeoutError as e:
            return self._timeout_result(
                tool_name=tool_name,
                timeout_seconds=self.tool_timeout_seconds,
                started_at=started_at,
                idempotency_key=idempotency_key,
                side_effecting=side_effecting,
                stderr=str(e),
            )
        except Exception as e:
            result = {
                "ok": False,
                "error": str(e),
                "error_type": e.__class__.__name__,
                "tool": tool_name,
                "elapsed_ms": round((time.perf_counter() - started_at) * 1000, 1),
            }
            self._attach_commit_state(
                result,
                idempotency_key=idempotency_key,
                side_effecting=side_effecting,
            )
            self.commit_state_store.record(result)
            return result

    def _register_local_handlers(self) -> None:
        self._tool_handlers["project_status"] = self._project_status
        self._tool_handlers["read_file"] = self._read_file
        self._tool_handlers["list_directory"] = self._list_directory
        self._tool_handlers["search_files"] = self._search_files
        self._tool_handlers["execute_shell"] = self._execute_shell
        self._tool_handlers["modify_file"] = self._modify_file
        self._tool_handlers["delete_file"] = self._delete_file
        self._tool_handlers["git_commit"] = self._git_commit
        self._tool_handlers["browser_navigate"] = self._browser_navigate
        self._tool_handlers["browser_click"] = self._browser_click
        self._tool_handlers["browser_evaluate"] = self._browser_evaluate
        self._tool_handlers["browser_screenshot"] = self._browser_screenshot

    def _project_status(
        self,
        include_git: bool = True,
        include_files: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        root = self.project_root.resolve()
        result: Dict[str, Any] = {
            "ok": True,
            "project_root": str(root),
            "exists": root.exists(),
            "top_level": [],
            "git": {},
            "markers": {
                "git": (root / ".git").exists(),
                "package_json": (root / "package.json").exists(),
                "pyproject": (root / "pyproject.toml").exists(),
                "config": (root / "config.json").exists(),
                "maker_config": (root / ".maker-mcp" / "config.json").exists(),
                "project_settings": (root / ".project" / "settings.json").exists(),
            },
        }
        if include_files and root.exists():
            items = []
            for p in sorted(root.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))[:40]:
                items.append({"name": p.name, "is_dir": p.is_dir()})
            result["top_level"] = items
        if include_git and (root / ".git").exists():
            git = subprocess.run(
                ["git", "status", "--short", "--branch"],
                cwd=root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=min(5.0, self.shell_timeout_seconds),
            )
            lines = [line for line in git.stdout.splitlines() if line.strip()]
            result["git"] = {
                "ok": git.returncode == 0,
                "returncode": git.returncode,
                "branch": lines[0] if lines else "",
                "changed_count": max(0, len(lines) - 1),
                "changes": lines[1:25],
                "stderr": git.stderr,
            }
        return result

    @staticmethod
    def _handler_accepts_session_id(handler: Callable[..., Any]) -> bool:
        try:
            signature = inspect.signature(handler)
        except (TypeError, ValueError):
            return True
        for param in signature.parameters.values():
            if param.kind == inspect.Parameter.VAR_KEYWORD:
                return True
            if param.name == "_session_id" and param.kind in {
                inspect.Parameter.KEYWORD_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            }:
                return True
        return False

    def _read_file(self, path: str, **kwargs) -> Dict[str, Any]:
        target = self.project_root / path
        if not target.exists():
            return {"ok": False, "error": "文件不存在"}
        return {"ok": True, "content": target.read_text(encoding="utf-8")}

    def _list_directory(self, path: str = ".", **kwargs) -> Dict[str, Any]:
        target = self.project_root / path
        items = []
        for p in target.iterdir():
            items.append({"name": p.name, "is_dir": p.is_dir()})
        return {"ok": True, "items": items}

    def _search_files(self, pattern: str, path: str = ".", **kwargs) -> Dict[str, Any]:
        target = self.project_root / path
        hits = []
        for p in target.rglob("*"):
            if p.is_file() and pattern in p.read_text(encoding="utf-8", errors="ignore"):
                hits.append(str(p.relative_to(self.project_root)))
        return {"ok": True, "hits": hits[:20]}

    def _execute_shell(self, command: str, **kwargs) -> Dict[str, Any]:
        timeout_seconds = self._resolve_timeout(
            kwargs.get("timeout_seconds"),
            default=self.shell_timeout_seconds,
        )
        # sandbox 已经校验过前缀，这里直接执行
        process = subprocess.Popen(
            command,
            shell=True,
            cwd=self.project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        started_at = time.perf_counter()
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            self._kill_process_tree(process)
            try:
                stdout, stderr = process.communicate(timeout=0.2)
            except subprocess.TimeoutExpired:
                stdout, stderr = "", "Process tree killed after timeout; no final output was available."
            return self._timeout_result(
                tool_name="execute_shell",
                timeout_seconds=timeout_seconds,
                started_at=started_at,
                idempotency_key=self._idempotency_key(
                    str(kwargs.get("_session_id", "shell")),
                    "execute_shell",
                    {"command": command},
                ),
                side_effecting=self._looks_like_write_command(command),
                stdout=stdout,
                stderr=stderr,
            )
        return {
            "ok": process.returncode == 0,
            "returncode": process.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "timeout_seconds": timeout_seconds,
        }

    def _modify_file(self, path: str, content: str, **kwargs) -> Dict[str, Any]:
        target = self.project_root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"ok": True, "path": str(target.relative_to(self.project_root))}

    def _delete_file(self, path: str, **kwargs) -> Dict[str, Any]:
        target = self.project_root / path
        if not target.exists():
            return {"ok": False, "error": "文件不存在"}
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        return {"ok": True, "path": str(target.relative_to(self.project_root))}

    def _git_commit(self, message: str, **kwargs) -> Dict[str, Any]:
        if not (self.project_root / ".git").exists():
            return {"ok": False, "error": "项目未初始化 git"}
        subprocess.run(["git", "add", "."], cwd=self.project_root, check=True)
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=self.project_root,
            capture_output=True,
            text=True,
        )
        return {
            "ok": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    def _browser_service_guard(self) -> Optional[Dict[str, Any]]:
        if self._browser_service is None:
            return {"ok": False, "error": "浏览器服务未初始化"}
        return None

    def _browser_navigate(self, url: str, **kwargs) -> Dict[str, Any]:
        err = self._browser_service_guard()
        if err:
            return err
        self._browser_service.start()
        return self._browser_service.navigate(url)

    def _browser_click(self, selector: str, **kwargs) -> Dict[str, Any]:
        err = self._browser_service_guard()
        if err:
            return err
        self._browser_service.start()
        return self._browser_service.click(selector)

    def _browser_evaluate(self, script: str, **kwargs) -> Dict[str, Any]:
        err = self._browser_service_guard()
        if err:
            return err
        self._browser_service.start()
        return self._browser_service.evaluate(script)

    def _browser_screenshot(self, path: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        err = self._browser_service_guard()
        if err:
            return err
        self._browser_service.start()
        result = self._browser_service.screenshot()
        if not result.get("ok"):
            return result
        if path:
            target = self.project_root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            import base64
            target.write_bytes(base64.b64decode(result["data"]))
            return {"ok": True, "path": str(target.relative_to(self.project_root))}
        return {"ok": True, "screenshot": result["data"], "mime": result.get("mime")}

    def _summarize(self, result: Dict[str, Any]) -> str:
        if not result.get("ok"):
            return f"失败: {result.get('error', '未知错误')}"
        if "content" in result:
            return f"内容长度 {len(result['content'])}"
        if "items" in result:
            return f"{len(result['items'])} 项"
        if "hits" in result:
            return f"{len(result['hits'])} 命中"
        return "成功"

    def _resolve_timeout(self, value: Any, default: float) -> float:
        try:
            timeout = float(value) if value is not None else float(default)
        except (TypeError, ValueError):
            timeout = float(default)
        return max(0.1, min(timeout, float(default)))

    def _timeout_result(
        self,
        *,
        tool_name: str,
        timeout_seconds: float,
        started_at: float,
        idempotency_key: str = "",
        side_effecting: bool = False,
        stdout: Any = "",
        stderr: Any = "",
    ) -> Dict[str, Any]:
        result = {
            "ok": False,
            "error": f"{tool_name} timed out after {timeout_seconds:.1f}s",
            "error_type": "tool_timeout",
            "tool": tool_name,
            "timeout_seconds": timeout_seconds,
            "elapsed_ms": round((time.perf_counter() - started_at) * 1000, 1),
            "partial": True,
            "stdout": self._decode_process_text(stdout),
            "stderr": self._decode_process_text(stderr),
        }
        self._attach_commit_state(
            result,
            idempotency_key=idempotency_key,
            side_effecting=side_effecting,
            committed=None if side_effecting else False,
        )
        return result

    @staticmethod
    def _decode_process_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return str(value)

    @staticmethod
    def _kill_process_tree(process: subprocess.Popen) -> None:
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                    check=False,
                )
                try:
                    process.wait(timeout=0.2)
                except Exception:
                    pass
                return
            except Exception:
                pass
        try:
            process.kill()
        except Exception:
            pass

    def _attach_commit_state(
        self,
        result: Dict[str, Any],
        *,
        idempotency_key: str,
        side_effecting: bool,
        committed: Optional[bool] = None,
    ) -> None:
        if not side_effecting:
            return
        if committed is None and result.get("error_type") != "tool_timeout":
            committed = bool(result.get("ok"))
        result.setdefault("idempotency_key", idempotency_key)
        result.setdefault("committed", committed)
        result.setdefault("observed_at", time.time())

    def reconcile_commit_state(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        if not observation.get("idempotency_key"):
            return observation
        reconciled = reconcile_observation(
            self.project_root,
            dict(observation),
            remote_resolver=self.remote_commit_resolver,
        )
        self.commit_state_store.record(reconciled)
        return reconciled

    def _idempotency_key(self, session_id: str, tool_name: str, params: Dict[str, Any]) -> str:
        payload = json.dumps(
            {
                "session_id": session_id,
                "tool": tool_name,
                "params": params,
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        return f"{session_id}:{tool_name}:{digest}"

    def _is_side_effecting_tool(self, tool_name: str) -> bool:
        if tool_name in self.WRITE_LIKE_TOOLS:
            return True
        lowered = tool_name.lower()
        return any(
            token in lowered
            for token in (
                "write",
                "create",
                "delete",
                "update",
                "modify",
                "edit",
                "save",
                "commit",
                "publish",
                "generate",
                "upload",
            )
        )

    @staticmethod
    def _looks_like_write_command(command: str) -> bool:
        lowered = command.lower()
        return any(
            token in lowered
            for token in (
                " > ",
                ">>",
                " tee ",
                "git commit",
                "npm publish",
                "touch ",
                "mkdir ",
                "del ",
                "erase ",
                "remove-item",
                "set-content",
                "out-file",
            )
        )
