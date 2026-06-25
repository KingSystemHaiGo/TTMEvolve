"""
tests/test_dynamic_tools_from_agents_md.py — AGENTS.md 动态工具测试
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent.tool_registry import ToolRegistry
from core.event_log import EventLog
from core.executor import Executor
from core.sandbox import SandboxMode
from core.approval import ApprovalPolicy
from core.version_manager import VersionManager


def _make_executor(project_root: Path) -> Executor:
    return Executor(
        project_root=project_root,
        event_log=EventLog(project_root / "events.jsonl"),
        version_manager=VersionManager(project_root, project_root / "versions"),
        sandbox_mode=SandboxMode.WORKSPACE_WRITE,
        approval_policy=ApprovalPolicy.NEVER,
    )


def test_register_shell_tool():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        tools = ToolRegistry(root / "skills")
        executor = _make_executor(root)

        tools.register_agents_md_tool(
            name="list_py",
            description="List Python files",
            parameters={"type": "object", "properties": {}},
            handler=lambda **kwargs: executor.propose_action(
                session_id=kwargs.get("_session_id", "s1"),
                tool_name="execute_shell",
                params={"command": "python --version"},
            ),
        )
        executor.register_dynamic_tool("list_py", tools.get_handler("list_py"), risk_level="low")

        assert tools.has("list_py")
        result = executor.propose_action("s1", "list_py", {})
        assert result["ok"] is True


def test_builtin_handler_mapping():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "hello.txt").write_text("hi", encoding="utf-8")
        tools = ToolRegistry(root / "skills")
        executor = _make_executor(root)

        def builtin_handler(**kwargs):
            session_id = kwargs.pop("_session_id", "s1")
            return executor.propose_action(session_id, "read_file", kwargs)

        tools.register_agents_md_tool(
            name="read_hello",
            description="Read hello file",
            parameters={"type": "object", "properties": {"path": {"type": "string"}}},
            handler=builtin_handler,
        )
        executor.register_dynamic_tool("read_hello", builtin_handler, risk_level="low")

        result = executor.propose_action("s1", "read_hello", {"path": "hello.txt"})
        assert result["ok"] is True
        assert result["content"] == "hi"


def test_duplicate_tool_ignored():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        tools = ToolRegistry(root / "skills")
        tools.register_agents_md_tool(
            name="same",
            description="first",
            parameters={"type": "object", "properties": {}},
            handler=lambda **kwargs: {"ok": True},
        )
        tools.register_agents_md_tool(
            name="same",
            description="second",
            parameters={"type": "object", "properties": {}},
            handler=lambda **kwargs: {"ok": False},
        )
        desc = tools.describe("same")
        assert desc["description"] == "first"


if __name__ == "__main__":
    test_register_shell_tool()
    print("OK test_register_shell_tool")
    test_builtin_handler_mapping()
    print("OK test_builtin_handler_mapping")
    test_duplicate_tool_ignored()
    print("OK test_duplicate_tool_ignored")
    print("\nAll dynamic tools tests passed.")
