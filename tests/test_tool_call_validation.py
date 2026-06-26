"""
tests/test_tool_call_validation.py — tool-call JSON Schema 校验与本地修复测试
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent.react_loop import ReActLoop
from agent.tool_registry import ToolRegistry
from agent.tool_validator import validate_tool_call
from core.event_log import EventLog
from core.executor import Executor
from core.runtime_contract import build_runtime_contract
from core.sandbox import SandboxMode
from core.approval import ApprovalPolicy
from core.version_manager import VersionManager
from llm.mock_llm import MockLLM


class _SlowToolMockLLM(MockLLM):
    def think(self, task, context, trajectory, tools_description):
        time.sleep(0.01)
        return super().think(task, context, trajectory, tools_description)

    def choose_action(self, task, thought, tools_description):
        time.sleep(0.01)
        return super().choose_action(task, thought, tools_description)


def _make_executor(project_root: Path) -> Executor:
    return Executor(
        project_root=project_root,
        event_log=EventLog(project_root / "events.jsonl"),
        version_manager=VersionManager(project_root, project_root / "versions"),
        sandbox_mode=SandboxMode.WORKSPACE_WRITE,
        approval_policy=ApprovalPolicy.NEVER,
    )


def test_validate_missing_required_param():
    spec = {
        "name": "read_file",
        "description": "read",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    }
    result = validate_tool_call("read_file", spec, {})
    assert result["ok"] is False
    assert any("missing required parameter 'path'" in e for e in result["errors"])
    assert result["structured_errors"][0]["rule_id"] == "missing_required"
    assert result["structured_errors"][0]["path"] == "read_file().path"
    assert "params.path" in result["structured_errors"][0]["suggested_fix"]


def test_validate_wrong_type():
    spec = {
        "name": "read_file",
        "description": "read",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    }
    result = validate_tool_call("read_file", spec, {"path": 123})
    assert result["ok"] is False
    assert any("expected string" in e for e in result["errors"])
    assert result["structured_errors"][0]["rule_id"] == "type_mismatch"


def test_validate_array_and_enum():
    spec = {
        "name": "batch",
        "description": "batch",
        "parameters": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                },
                "mode": {"type": "string", "enum": ["fast", "slow"]},
            },
            "required": ["items", "mode"],
        },
    }
    assert validate_tool_call("batch", spec, {"items": ["a"], "mode": "fast"})["ok"] is True

    result = validate_tool_call("batch", spec, {"items": [], "mode": "fast"})
    assert result["ok"] is False
    assert any("at least 1 item" in e for e in result["errors"])
    assert result["structured_errors"][0]["rule_id"] == "min_items"

    result = validate_tool_call("batch", spec, {"items": ["a"], "mode": "unknown"})
    assert result["ok"] is False
    assert any("allowed enum" in e for e in result["errors"])
    assert result["structured_errors"][0]["rule_id"] == "enum_mismatch"


def test_tool_registry_validate_unknown_tool():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        tools = ToolRegistry(root / "skills")
        result = tools.validate_action("not_exist", {})
        assert result["ok"] is False
        assert "不存在" in result["errors"][0]
        assert result["structured_errors"][0]["rule_id"] == "unknown_tool"


def test_tool_registry_validate_builtin_tool():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        tools = ToolRegistry(root / "skills")
        executor = _make_executor(root)
        tools.register(
            name="read_file",
            description="read",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            handler=executor.propose_action,
        )

        assert tools.validate_action("read_file", {"path": "hello.txt"})["ok"] is True
        result = tools.validate_action("read_file", {})
        assert result["ok"] is False
        assert any("missing required parameter 'path'" in e for e in result["errors"])
        assert result["structured_errors"][0]["rule_id"] == "missing_required"


def test_tool_registry_ranks_and_limits_relevant_tools():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        tools = ToolRegistry(root / "skills")
        executor = _make_executor(root)
        tools.register(
            name="read_file",
            description="read project files",
            parameters={"type": "object", "properties": {"path": {"type": "string"}}},
            handler=executor.propose_action,
        )
        tools.register(
            name="browser_navigate",
            description="open url in browser preview",
            parameters={"type": "object", "properties": {"url": {"type": "string"}}},
            handler=executor.propose_action,
        )
        tools.register(
            name="maker_build",
            description="build TapTap Maker project",
            parameters={"type": "object", "properties": {}},
            handler=executor.propose_action,
            source="maker_mcp",
        )

        query = "build TapTap Maker preview"
        ranked = tools.rank_tools(query, limit=2)
        assert [tool["name"] for tool in ranked] == ["maker_build", "browser_navigate"]
        first_stats = tools.last_rank_stats()
        assert first_stats["candidate_count"] == 3
        assert first_stats["selected_count"] == 2
        assert first_stats["cache_hit"] is False
        ranked_again = tools.rank_tools(query, limit=2)
        assert [tool["name"] for tool in ranked_again] == ["maker_build", "browser_navigate"]
        second_stats = tools.last_rank_stats()
        assert second_stats["cache_hit"] is True
        assert second_stats["cache_size"] >= 1
        schema = tools.schema_for_llm(query=query, limit=2)
        assert "maker_build" in schema
        assert "browser_navigate" in schema
        assert "read_file" not in schema


def test_tool_registry_prioritizes_project_status_for_project_questions():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        tools = ToolRegistry(root / "skills")
        executor = _make_executor(root)
        for name, description in [
            ("project_status", "查看当前项目概况、Git 状态、主要目录和运行配置"),
            ("execute_shell", "执行允许的 shell 命令"),
            ("maker_status_lite", "Maker MCP status"),
        ]:
            tools.register(
                name=name,
                description=description,
                parameters={"type": "object", "properties": {}},
                handler=executor.propose_action,
                source="maker_mcp" if name.startswith("maker_") else "builtin",
            )

        ranked = tools.rank_tools("查看项目状态，了解项目", limit=2)

        assert [tool["name"] for tool in ranked] == ["project_status", "execute_shell"]


def test_tool_registry_prioritizes_create_document_for_document_tasks():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        tools = ToolRegistry(root / "skills")
        executor = _make_executor(root)
        for name, description in [
            ("create_document", "新建项目内文档或说明文件"),
            ("modify_file", "写入或覆盖项目内的文本文件"),
            ("execute_shell", "执行允许的 shell 命令"),
        ]:
            tools.register(
                name=name,
                description=description,
                parameters={"type": "object", "properties": {}},
                handler=executor.propose_action,
                source="builtin",
            )

        ranked = tools.rank_tools("新建文档，写一份 README markdown 说明", limit=2)

        assert [tool["name"] for tool in ranked] == ["create_document", "modify_file"]
        assert tools.last_rank_stats()["workspace_profile"] == "docs"


def test_tool_registry_reports_workspace_profile_for_coding_tasks():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        tools = ToolRegistry(root / "skills")
        executor = _make_executor(root)
        for name in ["read_file", "modify_file", "execute_shell"]:
            tools.register(
                name=name,
                description=name,
                parameters={"type": "object", "properties": {}},
                handler=executor.propose_action,
                source="builtin",
            )

        tools.rank_tools("修复 Python 代码并运行测试", limit=2)
        first = tools.last_rank_stats()
        tools.rank_tools("修复 Python 代码并运行测试", limit=2)
        second = tools.last_rank_stats()

        assert first["workspace_profile"] == "coding"
        assert second["workspace_profile"] == "coding"
        assert second["cache_hit"] is True


def test_tool_registry_workspace_profile_reduces_irrelevant_tools():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        tools = ToolRegistry(root / "skills")
        executor = _make_executor(root)
        for name, source in [
            ("create_document", "builtin"),
            ("read_file", "builtin"),
            ("modify_file", "builtin"),
            ("execute_shell", "builtin"),
            ("browser_navigate", "builtin"),
            ("maker_build", "maker_mcp"),
        ]:
            tools.register(
                name=name,
                description=name,
                parameters={"type": "object", "properties": {}},
                handler=executor.propose_action,
                source=source,
            )

        docs_ranked = [tool["name"] for tool in tools.rank_tools("新建文档，写 README markdown 说明", limit=3)]
        assert docs_ranked == ["create_document", "read_file", "modify_file"]
        assert tools.last_rank_stats()["workspace_profile"] == "docs"

        maker_ranked = [tool["name"] for tool in tools.rank_tools("构建 TapTap Maker 游戏并打开预览", limit=3)]
        assert maker_ranked[:2] == ["maker_build", "browser_navigate"]
        assert tools.last_rank_stats()["workspace_profile"] == "maker"


def test_executor_project_status_reports_git_and_top_level():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "package.json").write_text("{}", encoding="utf-8")
        executor = _make_executor(root)

        result = executor.propose_action("s1", "project_status", {})

        assert result["ok"] is True
        assert result["markers"]["package_json"] is True
        assert any(item["name"] == "package.json" for item in result["top_level"])


def test_executor_search_files_skips_heavy_dirs_and_large_files():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "src").mkdir()
        (root / "src" / "app.py").write_text("NEEDLE = True\n", encoding="utf-8")
        (root / "node_modules" / "pkg").mkdir(parents=True)
        (root / "node_modules" / "pkg" / "bad.js").write_text("NEEDLE in dependency\n", encoding="utf-8")
        (root / ".git").mkdir()
        (root / ".git" / "config").write_text("NEEDLE in git\n", encoding="utf-8")
        (root / ".venv" / "Lib").mkdir(parents=True)
        (root / ".venv" / "Lib" / "site.py").write_text("NEEDLE in env\n", encoding="utf-8")
        (root / "large.txt").write_text("NEEDLE\n" + ("x" * 5000), encoding="utf-8")
        executor = _make_executor(root)

        result = executor.propose_action(
            "search1",
            "search_files",
            {"pattern": "NEEDLE", "max_file_bytes": 1024},
        )

        assert result["ok"] is True
        assert result["hits"] == ["src/app.py"]
        assert result["metrics"]["skipped_dirs"] >= 3
        assert result["metrics"]["skipped_large_files"] == 1
        assert result["metrics"]["scanned_files"] == 1


def test_executor_create_document_formats_markdown_and_json():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        executor = _make_executor(root)

        md = executor.propose_action(
            "doc1",
            "create_document",
            {"path": "docs/guide.md", "title": "指南", "content": "正文"},
        )
        duplicate = executor.propose_action(
            "doc1",
            "create_document",
            {"path": "docs/guide.md", "title": "指南", "content": "覆盖尝试"},
        )
        js = executor.propose_action(
            "doc1",
            "create_document",
            {"path": "docs/config.json", "kind": "json", "content": "{\"ok\":true}"},
        )

        assert md["ok"] is True
        assert md["created"] is True
        assert (root / "docs" / "guide.md").read_text(encoding="utf-8") == "# 指南\n\n正文"
        assert duplicate["ok"] is False
        assert "不会覆盖" in duplicate["error"]
        assert js["ok"] is True
        assert (root / "docs" / "config.json").read_text(encoding="utf-8") == "{\n  \"ok\": true\n}\n"


def test_coding_agent_minimal_programming_smoke():
    """Prove the local agent core can do basic programming work end-to-end.

    This covers the user-visible baseline for a coding agent: inspect project
    state, create a source file, run a command against it, and finish with a
    useful answer.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        tools = ToolRegistry(root / "skills")
        executor = _make_executor(root)
        for name, description, parameters in [
            ("project_status", "查看当前项目概况、Git 状态、主要目录和运行配置", {"type": "object", "properties": {}}),
            (
                "modify_file",
                "新建或修改项目内文件",
                {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            ),
            (
                "execute_shell",
                "执行允许的 shell 命令",
                {
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                },
            ),
        ]:
            tools.register(
                name=name,
                description=description,
                parameters=parameters,
                handler=executor.propose_action,
            )

        events = []
        llm = MockLLM([
            {"tool": "project_status", "params": {}},
            {
                "tool": "modify_file",
                "params": {
                    "path": "hello_agent.py",
                    "content": "print('TTMEVOLVE_AGENT_OK')\n",
                },
            },
            {"tool": "execute_shell", "params": {"command": "python hello_agent.py"}},
            {"done": True, "output": "已创建并运行 hello_agent.py，输出 TTMEVOLVE_AGENT_OK。"},
        ])
        loop = ReActLoop(
            llm=llm,
            tools=tools,
            executor=executor,
            event_log=EventLog(root / "events.jsonl"),
            max_iterations=6,
            event_sink=events.append,
        )

        result = loop.run("新建一个 Python 文档并运行验证", session_id="coding-smoke")
        observations = [step.get("observation", {}) for step in result["trajectory"]]
        event_types = [event.get("type") for event in events]

        assert result["output"].startswith("已创建并运行")
        assert (root / "hello_agent.py").read_text(encoding="utf-8") == "print('TTMEVOLVE_AGENT_OK')\n"
        assert [step["action"]["tool"] for step in result["trajectory"][:3]] == [
            "project_status",
            "modify_file",
            "execute_shell",
        ]
        assert observations[0]["ok"] is True
        assert observations[1]["ok"] is True
        assert observations[1]["committed"] is True
        assert observations[2]["ok"] is True
        assert "TTMEVOLVE_AGENT_OK" in observations[2]["stdout"]
        assert "tool_selection" in event_types
        assert "context_sync" in event_types
        assert result["plan_validation"]["counts"]["pass"] >= 3
        assert result["goal_checklist"]["overall"] in {"active", "done"}


def test_coding_agent_can_create_user_document():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        tools = ToolRegistry(root / "skills")
        executor = _make_executor(root)
        tools.register(
            name="create_document",
            description="新建项目内文档或说明文件",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "kind": {"type": "string", "enum": ["markdown", "text", "json"]},
                    "overwrite": {"type": "boolean"},
                },
                "required": ["path", "content"],
            },
            handler=executor.propose_action,
        )
        events = []
        llm = MockLLM([
            {
                "tool": "create_document",
                "params": {
                    "path": "docs/user-note.md",
                    "title": "用户说明",
                    "content": "这是一份由 Agent 新建的文档。",
                    "kind": "markdown",
                },
            },
            {"done": True, "output": "已新建 docs/user-note.md。"},
        ])
        loop = ReActLoop(
            llm=llm,
            tools=tools,
            executor=executor,
            event_log=EventLog(root / "events.jsonl"),
            max_iterations=4,
            event_sink=events.append,
        )

        result = loop.run("新建一份用户说明文档", session_id="doc-smoke")
        observation = result["trajectory"][0]["observation"]

        assert result["output"] == "已新建 docs/user-note.md。"
        assert observation["ok"] is True
        assert observation["tool"] == "create_document"
        assert observation["committed"] is True
        assert (root / "docs" / "user-note.md").read_text(encoding="utf-8") == (
            "# 用户说明\n\n这是一份由 Agent 新建的文档。"
        )


def test_tool_registry_preflight_returns_alternatives():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        tools = ToolRegistry(root / "skills")
        executor = _make_executor(root)
        tools.register(
            name="read_file",
            description="read project files",
            parameters={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
            handler=executor.propose_action,
        )
        tools.register(
            name="search_files",
            description="search project files",
            parameters={"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]},
            handler=executor.propose_action,
        )

        preflight = tools.preflight_action("readfile", {}, query="读取文件")

        assert preflight["ok"] is False
        assert preflight["structured_errors"][0]["rule_id"] == "unknown_tool"
        assert preflight["alternatives"]
        assert preflight["suggested_next_step"]


def test_react_loop_repairs_invalid_tool_call():
    """本地 LLM 第一次给出错误参数，第二次修正后完成任务。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "hello.txt").write_text("world", encoding="utf-8")

        tools = ToolRegistry(root / "skills")
        executor = _make_executor(root)
        tools.register(
            name="read_file",
            description="read",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            handler=executor.propose_action,
        )
        executor._tool_handlers["read_file"] = executor._read_file

        # 第一次调用缺少 path，第二次正确读取，然后结束
        llm = MockLLM([
            {"tool": "read_file", "params": {}},
            {"tool": "read_file", "params": {"path": "hello.txt"}},
        ])

        loop = ReActLoop(
            llm=llm,
            tools=tools,
            executor=executor,
            event_log=EventLog(root / "events.jsonl"),
            max_iterations=5,
        )
        result = loop.run("read hello")

        assert len(result["trajectory"]) == 3  # invalid + valid + done
        assert result["trajectory"][0]["observation"]["ok"] is False
        assert result["trajectory"][0]["observation"]["failure_type"] == "tool_validation"
        assert result["trajectory"][0]["observation"]["rule_id"] == "missing_required"
        assert result["trajectory"][0]["observation"]["structured_errors"][0]["path"] == "read_file().path"
        assert result["trajectory"][1]["observation"]["ok"] is True
        assert result["trajectory"][1]["observation"]["content"] == "world"
        assert result["output"] == "Mock 完成：read hello"


def test_react_loop_rejects_unknown_tool():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        tools = ToolRegistry(root / "skills")
        executor = _make_executor(root)
        llm = MockLLM([
            {"tool": "unknown_tool", "params": {}},
            {"done": True, "output": "gave up"},
        ])

        loop = ReActLoop(
            llm=llm,
            tools=tools,
            executor=executor,
            event_log=EventLog(root / "events.jsonl"),
            max_iterations=5,
        )
        result = loop.run("do something")

        assert result["trajectory"][0]["observation"]["ok"] is False
        assert result["trajectory"][0]["observation"]["failure_type"] == "tool_validation"
        assert result["trajectory"][0]["observation"]["rule_id"] == "unknown_tool"
        assert "unknown_tool" in result["trajectory"][0]["observation"]["error"]


def test_react_loop_emits_tool_preflight_for_invalid_action():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        tools = ToolRegistry(root / "skills")
        executor = _make_executor(root)
        tools.register(
            name="read_file",
            description="read project files",
            parameters={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
            handler=executor.propose_action,
        )
        events = []
        llm = MockLLM([
            {"tool": "readfile", "params": {}},
            {"done": True, "output": "gave up"},
        ])

        loop = ReActLoop(
            llm=llm,
            tools=tools,
            executor=executor,
            event_log=EventLog(root / "events.jsonl"),
            max_iterations=3,
            event_sink=events.append,
        )
        result = loop.run("read hello")
        preflight_events = [event for event in events if event.get("type") == "tool_preflight"]
        plan_validation_events = [event for event in events if event.get("type") == "plan_validation"]
        goal_events = [event for event in events if event.get("type") == "goal_checklist"]
        observation = result["trajectory"][0]["observation"]

        assert preflight_events
        assert preflight_events[0]["payload"]["ok"] is False
        assert preflight_events[0]["payload"]["alternatives"]
        assert plan_validation_events
        assert plan_validation_events[0]["payload"]["verdict"] == "fail"
        assert goal_events
        assert goal_events[-1]["payload"]["overall"] == "fail"
        assert observation["alternatives"]
        assert observation["suggested_next_step"]
        assert result["trajectory"][0]["plan_validation"]["verdict"] == "fail"


def test_react_loop_blocks_first_local_side_effect_when_maker_briefing_requires_authority():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        tools = ToolRegistry(root / "skills")
        executor = _make_executor(root)

        tools.register(
            name="write_file",
            description="write project files",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
            handler=executor.propose_action,
        )
        tools.register(
            name="maker_build",
            description="Build Maker project",
            parameters={"type": "object", "properties": {}},
            handler=executor.propose_action,
        )
        executor.register_dynamic_tool(
            "maker_build",
            lambda *args, **kwargs: {"ok": True, "tool": "maker_build", "built": True},
            risk_level="low",
        )
        contract = build_runtime_contract(
            project_root=root,
            session_id="guard1",
            mcp_status={
                "connected": True,
                "tools": [
                    {"name": "maker_build", "description": "Build Maker project", "inputSchema": {"properties": {}}},
                ],
                "remote_identity": {"status": "present"},
            },
            skill_status={},
        )
        events = []
        llm = MockLLM([
            {"tool": "write_file", "params": {"path": "main.lua", "content": "print('hi')"}},
            {"tool": "maker_build", "params": {}},
        ])
        loop = ReActLoop(
            llm=llm,
            tools=tools,
            executor=executor,
            event_log=EventLog(root / "events.jsonl"),
            max_iterations=4,
            event_sink=events.append,
            runtime_contract_provider=lambda session_id: contract,
        )

        result = loop.run("build and preview Maker project", session_id="guard1")
        guard_events = [event for event in events if event.get("type") == "maker_briefing_guard"]

        assert guard_events
        assert guard_events[0]["payload"]["decision"] == "block"
        assert result["trajectory"][0]["observation"]["failure_type"] == "maker_briefing_guard"
        assert result["trajectory"][0]["observation"]["tool"] == "write_file"
        assert "maker_build" in result["trajectory"][0]["observation"]["allowed_tools"]
        assert result["trajectory"][1]["observation"]["ok"] is True
        assert result["trajectory"][1]["observation"]["tool"] == "maker_build"


def test_react_loop_emits_latency_events():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "hello.txt").write_text("world", encoding="utf-8")

        tools = ToolRegistry(root / "skills")
        executor = _make_executor(root)
        tools.register(
            name="read_file",
            description="read",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            handler=executor.propose_action,
        )
        executor._tool_handlers["read_file"] = executor._read_file
        events = []
        llm = _SlowToolMockLLM([
            {"tool": "read_file", "params": {"path": "hello.txt"}},
        ])
        loop = ReActLoop(
            llm=llm,
            tools=tools,
            executor=executor,
            event_log=EventLog(root / "events.jsonl"),
            max_iterations=3,
            event_sink=events.append,
        )

        result = loop.run("read hello")
        phases = [
            event["payload"]["phase"]
            for event in events
            if event.get("type") == "latency"
        ]
        plan_validation_events = [event for event in events if event.get("type") == "plan_validation"]
        goal_events = [event for event in events if event.get("type") == "goal_checklist"]

        assert result["output"] == "Mock 完成：read hello"
        assert plan_validation_events
        assert plan_validation_events[0]["payload"]["verdict"] == "pass"
        assert goal_events
        assert result["goal_checklist"]["counts"]["done"] >= 3
        assert result["plan_validation"]["counts"]["pass"] == 1
        assert "first_response" in phases
        assert "llm_think" in phases
        assert "llm_action" in phases
        assert "tool_call" in phases
        assert "session_total" in phases
        assert all(
            event["payload"]["elapsed_ms"] >= 0
            for event in events
            if event.get("type") == "latency"
        )


def test_react_loop_emits_tool_progress_heartbeat():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        tools = ToolRegistry(root / "skills")
        executor = _make_executor(root)

        def slow_tool(*args, **kwargs):
            time.sleep(0.18)
            return {"ok": True, "result": "done"}

        executor.register_dynamic_tool("slow_tool", slow_tool, risk_level="low")
        tools.register(
            name="slow_tool",
            description="slow diagnostic tool",
            parameters={"type": "object", "properties": {}},
            handler=executor.propose_action,
        )
        events = []
        llm = MockLLM([
            {"tool": "slow_tool", "params": {}},
        ])
        loop = ReActLoop(
            llm=llm,
            tools=tools,
            executor=executor,
            event_log=EventLog(root / "events.jsonl"),
            max_iterations=3,
            event_sink=events.append,
            tool_progress_interval_seconds=0.05,
        )

        result = loop.run("run slow tool")
        progress_events = [event for event in events if event.get("type") == "tool_progress"]
        observation_index = next(
            index for index, event in enumerate(events) if event.get("type") == "observation"
        )
        first_progress_index = next(
            index for index, event in enumerate(events) if event.get("type") == "tool_progress"
        )

        assert result["trajectory"][0]["observation"]["ok"] is True
        assert progress_events
        assert first_progress_index < observation_index
        assert progress_events[0]["payload"]["tool"] == "slow_tool"
        assert progress_events[0]["payload"]["partial"] is True
        assert progress_events[0]["payload"]["heartbeat_count"] >= 1
        assert progress_events[0]["payload"]["elapsed_ms"] >= 40


def test_react_loop_emits_skill_sync_change_event():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        tools = ToolRegistry(root / "skills")
        executor = _make_executor(root)
        executor.register_dynamic_tool("noop", lambda **kwargs: {"ok": True}, risk_level="low")
        tools.register(
            name="noop",
            description="no operation",
            parameters={"type": "object", "properties": {}},
            handler=executor.propose_action,
        )
        events = []
        statuses = [
            {
                "registry": {"state": "ok", "signature": "sig-1", "changed": False},
                "manifest": {"summary": {"total_records": 1, "total_conflicts": 0}, "conflicts": []},
                "export_plan": {"summary": {"create": 0, "update": 0}, "actions": []},
            },
            {
                "registry": {"state": "ok", "signature": "sig-2", "changed": True},
                "manifest": {"summary": {"total_records": 2, "total_conflicts": 0}, "conflicts": []},
                "export_plan": {
                    "summary": {"create": 1, "update": 0},
                    "actions": [{"action": "create", "skill_id": "new_skill", "target": "codex"}],
                },
            },
        ]

        def skill_sync_status():
            if statuses:
                return statuses.pop(0)
            return {
                "registry": {"state": "ok", "signature": "sig-2", "changed": False},
                "manifest": {"summary": {"total_records": 2, "total_conflicts": 0}, "conflicts": []},
                "export_plan": {"summary": {"create": 1, "update": 0}, "actions": []},
            }

        llm = MockLLM([
            {"tool": "noop", "params": {}},
        ])
        loop = ReActLoop(
            llm=llm,
            tools=tools,
            executor=executor,
            event_log=EventLog(root / "events.jsonl"),
            max_iterations=3,
            event_sink=events.append,
            skill_sync_status=skill_sync_status,
        )

        loop.run("run noop")
        skill_events = [event for event in events if event.get("type") == "skill_sync"]

        assert skill_events[0]["payload"]["reason"] == "session_start"
        assert skill_events[-1]["payload"]["changed"] is True
        assert skill_events[-1]["payload"]["actions_preview"][0]["skill_id"] == "new_skill"
        assert any(tool["name"] == "noop" for tool in tools.list_tools())
        print("[PASS] react loop emits skill sync change event")


def test_react_loop_emits_skill_compatibility_warning_after_plan_validation():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        tools = ToolRegistry(root / "skills")
        executor = _make_executor(root)
        events = []

        def skill_sync_status():
            return {
                "registry": {"state": "conflicts", "signature": "same-sig", "changed": False},
                "manifest": {
                    "summary": {"total_records": 2, "total_conflicts": 1},
                    "conflicts": [{"type": "version_conflict", "skill_id": "shared_skill"}],
                },
                "export_plan": {"summary": {"needs_review": 1}, "actions": []},
            }

        llm = MockLLM([
            {"tool": "missing_tool", "params": {}},
            {"done": True, "output": "stop"},
        ])
        loop = ReActLoop(
            llm=llm,
            tools=tools,
            executor=executor,
            event_log=EventLog(root / "events.jsonl"),
            max_iterations=3,
            event_sink=events.append,
            skill_sync_status=skill_sync_status,
        )

        loop.run("trigger validation")
        skill_events = [event for event in events if event.get("type") == "skill_sync"]

        assert len(skill_events) >= 2
        assert skill_events[-1]["payload"]["reason"] == "plan_validation"
        assert skill_events[-1]["payload"]["compatibility_status"] == "needs_review"
        assert skill_events[-1]["payload"]["conflicts"][0]["skill_id"] == "shared_skill"
        print("[PASS] react loop emits skill compatibility warning after plan validation")


def test_react_loop_emits_context_sync_snapshot():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "hello.txt").write_text("world", encoding="utf-8")

        tools = ToolRegistry(root / "skills")
        executor = _make_executor(root)
        tools.register(
            name="read_file",
            description="read",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            handler=executor.propose_action,
        )
        executor._tool_handlers["read_file"] = executor._read_file
        events = []
        llm = MockLLM([
            {"tool": "read_file", "params": {"path": "hello.txt"}},
        ])
        loop = ReActLoop(
            llm=llm,
            tools=tools,
            executor=executor,
            event_log=EventLog(root / "events.jsonl"),
            max_iterations=3,
            event_sink=events.append,
        )

        loop.run("read hello", session_id="ctx1")
        context_events = [event for event in events if event.get("type") == "context_sync"]

        assert len(context_events) >= 2
        assert context_events[0]["payload"]["reason"] == "session_start"
        assert context_events[0]["payload"]["snapshot"]["session_id"] == "ctx1"
        assert context_events[0]["payload"]["revision"] == 1
        last = context_events[-1]["payload"]
        snapshot = last["snapshot"]
        assert last["reason"] in {"plan_validation", "output"}
        assert snapshot["last_tool"] == "read_file"
        assert snapshot["plan_validation"]["verdict"] == "pass"
        assert snapshot["artifact_count"] == 1
        assert snapshot["artifact_refs"][0]["path"] == "hello.txt"
        assert "trajectory_steps" in last["diff_keys"]


def test_react_loop_context_sync_deduplicates_unchanged_snapshot():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        tools = ToolRegistry(root / "skills")
        executor = _make_executor(root)
        events = []
        loop = ReActLoop(
            llm=MockLLM([]),
            tools=tools,
            executor=executor,
            event_log=EventLog(root / "events.jsonl"),
            max_iterations=1,
            event_sink=events.append,
        )
        loop._session_id = "ctx-dedupe"
        loop._task = "dedupe"
        loop._goal_checklist = {"overall": "active", "counts": {"pending": 1}}

        loop._maybe_emit_context_sync(iteration=-1, reason="manual", force=True)
        loop._maybe_emit_context_sync(iteration=-1, reason="manual")

        context_events = [event for event in events if event.get("type") == "context_sync"]
        assert len(context_events) == 1
        assert context_events[0]["payload"]["revision"] == 1


def test_react_loop_reconciles_uncertain_commit_state():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "hello.txt").write_text("world", encoding="utf-8")

        tools = ToolRegistry(root / "skills")
        executor = _make_executor(root)

        def uncertain_modify_file(path: str, content: str, **kwargs):
            return {
                "ok": False,
                "tool": "modify_file",
                "path": path,
                "error_type": "tool_timeout",
                "error": "simulated timeout",
                "partial": True,
                "idempotency_key": "s1:modify_file:abc",
                "committed": None,
                "observed_at": time.time(),
            }

        executor._tool_handlers["modify_file"] = uncertain_modify_file
        tools.register(
            name="modify_file",
            description="write",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
            handler=executor.propose_action,
        )
        events = []
        llm = MockLLM([
            {"tool": "modify_file", "params": {"path": "hello.txt", "content": "world"}},
        ])
        loop = ReActLoop(
            llm=llm,
            tools=tools,
            executor=executor,
            event_log=EventLog(root / "events.jsonl"),
            max_iterations=3,
            event_sink=events.append,
        )

        result = loop.run("write hello", session_id="s1")
        observation = result["trajectory"][0]["observation"]
        reconcile_events = [event for event in events if event.get("type") == "commit_reconcile"]

        assert observation["committed"] is True
        assert observation["reconcile_status"] == "verified_local"
        assert len(reconcile_events) == 2
        assert reconcile_events[-1]["payload"]["committed"] is True


if __name__ == "__main__":
    test_validate_missing_required_param()
    test_validate_wrong_type()
    test_validate_array_and_enum()
    test_tool_registry_validate_unknown_tool()
    test_tool_registry_validate_builtin_tool()
    test_tool_registry_ranks_and_limits_relevant_tools()
    test_tool_registry_prioritizes_project_status_for_project_questions()
    test_tool_registry_prioritizes_create_document_for_document_tasks()
    test_tool_registry_reports_workspace_profile_for_coding_tasks()
    test_tool_registry_workspace_profile_reduces_irrelevant_tools()
    test_executor_project_status_reports_git_and_top_level()
    test_executor_search_files_skips_heavy_dirs_and_large_files()
    test_executor_create_document_formats_markdown_and_json()
    test_coding_agent_minimal_programming_smoke()
    test_coding_agent_can_create_user_document()
    test_tool_registry_preflight_returns_alternatives()
    test_react_loop_repairs_invalid_tool_call()
    test_react_loop_rejects_unknown_tool()
    test_react_loop_emits_tool_preflight_for_invalid_action()
    test_react_loop_blocks_first_local_side_effect_when_maker_briefing_requires_authority()
    test_react_loop_emits_latency_events()
    test_react_loop_emits_tool_progress_heartbeat()
    test_react_loop_emits_skill_sync_change_event()
    test_react_loop_emits_skill_compatibility_warning_after_plan_validation()
    test_react_loop_emits_context_sync_snapshot()
    test_react_loop_context_sync_deduplicates_unchanged_snapshot()
    test_react_loop_reconciles_uncertain_commit_state()
    print("[PASS] tool call validation tests")
