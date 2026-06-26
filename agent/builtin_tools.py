"""
agent/builtin_tools.py — 内置工具注册

把 Agent 需要的标准工具描述注册到 ToolRegistry，实际执行统一交给 Executor。
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.tool_registry import ToolRegistry
    from core.executor import Executor


def register_builtin_tools(tools: "ToolRegistry", executor: "Executor") -> None:
    """注册所有内置工具描述。"""
    _register_project_status(tools, executor)
    _register_read_file(tools, executor)
    _register_list_directory(tools, executor)
    _register_search_files(tools, executor)
    _register_create_document(tools, executor)
    _register_modify_file(tools, executor)
    _register_execute_shell(tools, executor)
    _register_delete_file(tools, executor)
    _register_git_commit(tools, executor)
    _register_browser_tools(tools, executor)



def _register_project_status(tools: "ToolRegistry", executor: "Executor") -> None:
    tools.register(
        name="project_status",
        description="查看当前项目概况、Git 状态、主要目录和运行配置，用于了解项目状态或快速诊断工作区。",
        parameters={
            "type": "object",
            "properties": {
                "include_git": {"type": "boolean", "description": "是否包含 git status 摘要，默认 true"},
                "include_files": {"type": "boolean", "description": "是否列出顶层文件和目录，默认 true"},
            },
        },
        handler=executor.propose_action,
        source="builtin",
    )

def _register_read_file(tools: "ToolRegistry", executor: "Executor") -> None:
    tools.register(
        name="read_file",
        description="读取项目内指定路径的文本文件",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "相对项目根的路径"},
            },
            "required": ["path"],
        },
        handler=executor.propose_action,
        source="builtin",
    )


def _register_list_directory(tools: "ToolRegistry", executor: "Executor") -> None:
    tools.register(
        name="list_directory",
        description="列出项目内指定目录的内容",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "相对项目根的路径"},
            },
        },
        handler=executor.propose_action,
        source="builtin",
    )


def _register_search_files(tools: "ToolRegistry", executor: "Executor") -> None:
    tools.register(
        name="search_files",
        description="在项目文本文件中搜索字符串，默认跳过 .git/node_modules/.venv/dist 等重目录和大文件。",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string"},
                "max_results": {"type": "integer", "minimum": 1, "description": "最多返回命中数量，默认 20"},
                "max_file_bytes": {"type": "integer", "minimum": 1024, "description": "单文件最大读取字节数，默认 1MB"},
            },
            "required": ["pattern"],
        },
        handler=executor.propose_action,
        source="builtin",
    )


def _register_create_document(tools: "ToolRegistry", executor: "Executor") -> None:
    tools.register(
        name="create_document",
        description="新建项目内文档或说明文件，可用于创建 Markdown、文本、JSON 等用户可见文档。",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "相对项目根的文档路径，例如 docs/notes.md"},
                "title": {"type": "string", "description": "可选文档标题"},
                "content": {"type": "string", "description": "文档正文内容"},
                "kind": {
                    "type": "string",
                    "enum": ["markdown", "text", "json"],
                    "description": "文档类型，默认 markdown",
                },
                "overwrite": {"type": "boolean", "description": "是否覆盖已有文件，默认 false"},
            },
            "required": ["path", "content"],
        },
        handler=executor.propose_action,
        source="builtin",
    )


def _register_modify_file(tools: "ToolRegistry", executor: "Executor") -> None:
    tools.register(
        name="modify_file",
        description="写入或覆盖项目内的文本文件（高风险，需确认）",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
        handler=executor.propose_action,
        source="builtin",
    )


def _register_execute_shell(tools: "ToolRegistry", executor: "Executor") -> None:
    tools.register(
        name="execute_shell",
        description="执行允许的 shell 命令（git/python/npm/node/npx/cd）",
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout_seconds": {
                    "type": "number",
                    "minimum": 0.1,
                    "description": "可选，单次命令超时秒数，会被运行时默认上限截断",
                },
            },
            "required": ["command"],
        },
        handler=executor.propose_action,
        source="builtin",
    )


def _register_delete_file(tools: "ToolRegistry", executor: "Executor") -> None:
    tools.register(
        name="delete_file",
        description="删除项目内的文件或目录（高风险，需确认）",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
            },
            "required": ["path"],
        },
        handler=executor.propose_action,
        source="builtin",
    )


def _register_git_commit(tools: "ToolRegistry", executor: "Executor") -> None:
    tools.register(
        name="git_commit",
        description="提交当前变更到 git",
        parameters={
            "type": "object",
            "properties": {
                "message": {"type": "string"},
            },
            "required": ["message"],
        },
        handler=executor.propose_action,
        source="builtin",
    )


def _register_browser_tools(tools: "ToolRegistry", executor: "Executor") -> None:
    browser_tools = [
        (
            "browser_navigate",
            "控制内嵌浏览器导航到指定 URL",
            {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "目标 URL"},
                },
                "required": ["url"],
            },
        ),
        (
            "browser_click",
            "在内嵌浏览器中点击指定 CSS selector 的元素",
            {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector"},
                },
                "required": ["selector"],
            },
        ),
        (
            "browser_evaluate",
            "在内嵌浏览器页面中执行 JavaScript",
            {
                "type": "object",
                "properties": {
                    "script": {"type": "string", "description": "JavaScript 代码"},
                },
                "required": ["script"],
            },
        ),
        (
            "browser_screenshot",
            "截取内嵌浏览器当前页面，可保存到项目路径",
            {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "可选，相对项目根的保存路径"},
                },
            },
        ),
    ]
    for name, desc, params in browser_tools:
        tools.register(
            name=name,
            description=desc,
            parameters=params,
            handler=executor.propose_action,
            source="builtin",
        )
