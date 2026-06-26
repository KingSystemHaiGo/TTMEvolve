"""
core/sandbox.py — Codex 风格轻量沙箱

Windows 平台无法做到内核级隔离，这里做应用层校验：
- 文件路径必须落在 project_root 内
- 命令必须匹配当前 sandbox 模式的白名单
- 网络访问默认在 read-only / workspace-write 下禁止
"""

from __future__ import annotations
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


class SandboxMode(str, Enum):
    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    DANGER_FULL_ACCESS = "danger-full-access"


class Sandbox:
    """轻量级应用层沙箱。"""

    # 工具名 -> 允许的文件操作类型
    TOOL_OPS = {
        "project_status": "read",
        "read_file": "read",
        "list_directory": "read",
        "search_files": "read",
        "query_skills": "read",
        "modify_file": "write",
        "delete_file": "write",
        "execute_shell": "execute",
        "git_commit": "execute",
    }

    # 各模式允许的操作类型
    ALLOWED_OPS = {
        SandboxMode.READ_ONLY: {"read"},
        SandboxMode.WORKSPACE_WRITE: {"read", "write", "execute"},
        SandboxMode.DANGER_FULL_ACCESS: {"read", "write", "execute", "network"},
    }

    # workspace-write 下允许执行的命令前缀
    WORKSPACE_ALLOWED_PREFIXES = (
        "git ",
        "python ",
        "python3 ",
        "npm ",
        "node ",
        "npx ",
        "cd ",
        "pip ",
        "pytest ",
        "python -m pytest ",
    )

    # 永远禁止的危险命令关键字（即使 danger 模式也建议拦截）
    DANGEROUS_KEYWORDS = (
        "rm -rf /",
        "format ",
        "mkfs.",
        "dd if=",
        ":(){ :|:",
    )

    def __init__(self, project_root: Path, mode: SandboxMode = SandboxMode.WORKSPACE_WRITE):
        self.project_root = Path(project_root).resolve()
        self.mode = SandboxMode(mode)

    def validate(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """返回 {"allowed": bool, "reason": str}。"""
        op = self.TOOL_OPS.get(tool_name, "unknown")
        allowed_ops = self.ALLOWED_OPS.get(self.mode, set())

        if op == "unknown":
            # 动态/生成工具在 read-only 外允许执行，由 Executor 负责工具存在性校验
            if self.mode == SandboxMode.READ_ONLY:
                return {"allowed": False, "reason": f"沙箱模式 {self.mode.value} 下不允许未知工具 {tool_name}"}
            op = "execute"

        if op not in allowed_ops:
            return {"allowed": False, "reason": f"沙箱模式 {self.mode.value} 下不允许 {op} 操作（{tool_name}）"}

        # 路径校验（所有涉及 path 的工具）
        if "path" in params:
            valid, reason = self._validate_path(params["path"])
            if not valid:
                return {"allowed": False, "reason": reason}

        # 命令校验
        if tool_name == "execute_shell":
            command = params.get("command", "")
            valid, reason = self._validate_command(command)
            if not valid:
                return {"allowed": False, "reason": reason}

        return {"allowed": True, "reason": ""}

    def _validate_path(self, path: Any) -> tuple[bool, str]:
        if not isinstance(path, (str, Path)):
            return False, "path 必须是字符串或 Path"
        try:
            target = self.project_root / str(path)
            target.resolve().relative_to(self.project_root)
        except ValueError:
            return False, f"目标路径超出项目根目录：{path}"
        except Exception as e:
            return False, f"路径校验失败：{e}"
        return True, ""

    def _validate_command(self, command: Any) -> tuple[bool, str]:
        if not isinstance(command, str):
            return False, "command 必须是字符串"

        cmd = command.strip()

        # 全局危险关键字拦截
        for kw in self.DANGEROUS_KEYWORDS:
            if kw in cmd:
                return False, f"检测到危险命令关键字：{kw}"

        if self.mode == SandboxMode.DANGER_FULL_ACCESS:
            return True, ""

        if self.mode == SandboxMode.WORKSPACE_WRITE:
            if any(cmd.startswith(p) for p in self.WORKSPACE_ALLOWED_PREFIXES):
                return True, ""
            return False, f"当前沙箱模式仅允许以下命令前缀：{self.WORKSPACE_ALLOWED_PREFIXES}"

        # read-only 下不允许 execute_shell
        return False, "read-only 模式下禁止执行 shell 命令"

    def can_access_network(self) -> bool:
        return "network" in self.ALLOWED_OPS.get(self.mode, set())
