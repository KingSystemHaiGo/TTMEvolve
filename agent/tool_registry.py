"""
agent/tool_registry.py — 工具注册表

统一管理本地工具与 Maker MCP 工具。
支持 Agent 自生成技能的动态注册。
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import importlib.util
import json
import time

from agent.tool_validator import validate_tool_call


class ToolRegistry:
    """工具注册表：内置工具 + 动态技能。"""

    def __init__(self, skills_dir: Path):
        self.skills_dir = Path(skills_dir)
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._handlers: Dict[str, Callable[..., Any]] = {}
        self._tools_revision = 0
        self._rank_cache: Dict[str, List[str]] = {}
        self._rank_cache_order: List[str] = []
        self._rank_cache_limit = 64
        self._last_rank_stats: Dict[str, Any] = {}
        self._load_skills()

    def register(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        handler: Callable[..., Any],
        source: str = "builtin",
    ) -> None:
        self._tools[name] = {
            "name": name,
            "description": description,
            "parameters": parameters,
            "source": source,
        }
        self._handlers[name] = handler
        self._invalidate_rank_cache()

    def register_maker_tools(self, tools: List[Dict[str, Any]], handler: Callable[..., Any]) -> None:
        for tool in tools:
            name = tool["name"]
            self._tools[name] = {
                "name": name,
                "description": tool.get("description", ""),
                "parameters": tool.get("inputSchema", {}),
                "source": "maker_mcp",
            }
            self._handlers[name] = handler
        self._invalidate_rank_cache()

    def register_agents_md_tool(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        handler: Callable[..., Any],
        risk_level: str = "medium",
    ) -> None:
        """注册从 AGENTS.md 解析出的动态工具。"""
        if name in self._tools:
            return
        self.register(
            name=name,
            description=description,
            parameters=parameters,
            handler=handler,
            source=f"agents_md:{risk_level}",
        )

    def has(self, name: str) -> bool:
        return name in self._tools

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)
        self._handlers.pop(name, None)
        self._invalidate_rank_cache()

    def unregister_source(self, source: str) -> List[str]:
        removed = [
            name
            for name, tool in self._tools.items()
            if str(tool.get("source") or "") == source
        ]
        for name in removed:
            self._tools.pop(name, None)
            self._handlers.pop(name, None)
        if removed:
            self._invalidate_rank_cache()
        return removed

    def describe(self, name: str) -> Dict[str, Any]:
        return self._tools.get(name, {})

    def validate_action(self, name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """校验工具名是否存在、参数是否符合 JSON Schema。"""
        if not self.has(name):
            available = sorted(self._tools.keys())
            closest = _closest_tool_name(name, available)
            suggested_fix = (
                f"Use '{closest}' instead, or choose one of the registered tool names."
                if closest
                else "Choose one of the registered tool names."
            )
            return {
                "ok": False,
                "errors": [f"工具 {name} 不存在"],
                "structured_errors": [{
                    "rule_id": "unknown_tool",
                    "path": "tool",
                    "reason": f"Tool '{name}' is not registered.",
                    "suggested_fix": suggested_fix,
                    "available_tools": available[:20],
                }],
            }
        return validate_tool_call(name, self.describe(name), params)

    def preflight_action(
        self,
        name: str,
        params: Dict[str, Any],
        *,
        query: str = "",
        limit: int = 3,
    ) -> Dict[str, Any]:
        """Validate an action and attach lightweight alternative routes."""
        validation = self.validate_action(name, params)
        alternatives = self.suggest_alternatives(name, query=query, limit=limit)
        validation["tool"] = name
        validation["alternatives"] = alternatives
        if not validation["ok"]:
            validation["suggested_next_step"] = _preflight_next_step(validation, alternatives)
        return validation

    def suggest_alternatives(
        self,
        name: str,
        *,
        query: str = "",
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        ranked = self.rank_tools(query=query or name, limit=None)
        alternatives: List[Dict[str, Any]] = []
        for tool in ranked:
            if tool.get("name") == name:
                continue
            alternatives.append({
                "name": tool.get("name", ""),
                "source": tool.get("source", ""),
                "reason": _alternative_reason(name, tool, query),
            })
            if len(alternatives) >= limit:
                break
        return alternatives

    def list_tools(self) -> List[Dict[str, Any]]:
        return list(self._tools.values())

    def last_rank_stats(self) -> Dict[str, Any]:
        return dict(self._last_rank_stats)

    def get_handler(self, name: str) -> Callable[..., Any]:
        return self._handlers[name]

    def discover_generated_skills(self) -> None:
        self._load_skills()
        self._load_canonical_skills()

    def _load_canonical_skills(self) -> None:
        """加载 canonical skill 格式：skills/{id}/{version}/skill.json + skill.py。"""
        if not self.skills_dir.exists():
            return
        for skill_json in self.skills_dir.rglob("skill.json"):
            try:
                spec = json.loads(skill_json.read_text(encoding="utf-8"))
                name = spec.get("name") or spec.get("id")
                if not name or name in self._tools:
                    continue
                py_path = skill_json.with_name("skill.py")
                if py_path.exists():
                    handler = self._load_skill_module(py_path)
                    self.register(
                        name=name,
                        description=spec.get("description", ""),
                        parameters=spec.get("parameters", {}),
                        handler=handler,
                        source=f"generated:{skill_json.parent}",
                    )
            except Exception:
                continue

    def _load_skills(self) -> None:
        if not self.skills_dir.exists():
            return
        for path in self.skills_dir.rglob("*.json"):
            # 跳过 canonical 结构中的 skill.json，由 _load_canonical_skills 处理
            if path.name == "skill.json":
                continue
            try:
                spec = json.loads(path.read_text(encoding="utf-8"))
                name = spec.get("name")
                if not name or name in self._tools:
                    continue
                # 动态加载对应的 .py 实现
                py_path = path.with_suffix(".py")
                if py_path.exists():
                    handler = self._load_skill_module(py_path)
                    self.register(
                        name=name,
                        description=spec.get("description", ""),
                        parameters=spec.get("parameters", {}),
                        handler=handler,
                        source=f"generated:{path.name}",
                    )
            except Exception:
                continue

    def schema_for_functions(self) -> List[Dict[str, Any]]:
        """输出 OpenAI 风格的 functions schema。"""
        functions = []
        for tool in self._tools.values():
            functions.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
                },
            })
        return functions

    def _load_skill_module(self, py_path: Path) -> Callable[..., Any]:
        module_name = py_path.stem
        spec = importlib.util.spec_from_file_location(module_name, py_path)
        if not spec or not spec.loader:
            raise ImportError(f"Cannot load skill module {py_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return getattr(module, "run", lambda **kwargs: {"ok": False, "error": "no run() in skill"})

    def generated_tools(self) -> List[Dict[str, Any]]:
        """返回所有自生成技能的工具信息（含 handler）。"""
        return [
            {
                "name": name,
                "handler": self._handlers[name],
                "source": tool.get("source", ""),
            }
            for name, tool in self._tools.items()
            if tool.get("source", "").startswith("generated:")
        ]

    def rank_tools(self, query: str = "", limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Return tools ordered by likely relevance to the current task.

        This is intentionally lightweight and deterministic. It keeps the
        runtime fast, avoids another LLM call, and still gives Maker MCP tools a
        chance to surface for Maker-specific work.
        """
        started_at = time.perf_counter()
        query_l = (query or "").lower()
        query_terms = [term for term in re_split_query(query_l) if len(term) >= 2]
        workspace_profile = _infer_workspace_profile(query_l)
        foundation_intent = _foundation_intent(query_l)
        cache_key = self._rank_cache_key(query_l, limit)
        cached_names = self._rank_cache.get(cache_key)
        if cached_names is not None:
            tools = [self._tools[name] for name in cached_names if name in self._tools]
            self._last_rank_stats = self._rank_stats(
                started_at=started_at,
                cache_hit=True,
                query_terms=query_terms,
                selected_count=len(tools),
                workspace_profile=workspace_profile,
            )
            return tools

        ranked = []
        for order, tool in enumerate(self._tools.values()):
            name = tool.get("name", "")
            desc = tool.get("description", "")
            source = tool.get("source", "")
            haystack = f"{name} {desc} {source}".lower()
            score = 0

            for term in query_terms:
                if term in haystack:
                    score += 4
                if term in name.lower():
                    score += 3

            if source == "maker_mcp" and any(k in query_l for k in ("maker", "taptap", "构建", "预览", "素材", "发布", "游戏")):
                score += 8
            if name.startswith("browser_") and any(k in query_l for k in ("网页", "预览", "浏览器", "打开", "url", "maker.taptap")):
                score += 7
            if name == "project_status" and any(k in query_l for k in ("项目状态", "了解项目", "当前项目", "项目概况", "当前进度", "仓库状态", "代码仓库", "git状态", "git status", "status", "状态检查", "查看状态")):
                score += 10
            if name in ("read_file", "list_directory", "search_files", "project_status") and any(k in query_l for k in ("文件", "目录", "读取", "查找", "搜索", "代码", "项目", "仓库", "状态", "了解")):
                score += 6
            if name == "create_document" and any(k in query_l for k in ("新建文档", "创建文档", "写文档", "新建说明", "创建说明", "readme", "markdown", "笔记", "文档")):
                score += 10
            if name in ("modify_file", "delete_file") and any(k in query_l for k in ("修改", "写入", "创建", "删除", "修复", "实现")):
                score += 6
            if name == "execute_shell" and any(k in query_l for k in ("测试", "运行", "构建", "npm", "python", "node", "cargo", "命令", "cmd", "powershell", "终端", "shell", "控制台", "git status", "git log", "status", "状态", "检查")):
                score += 8

            score += _workspace_profile_score(workspace_profile, name, source)

            # Stable fallback: built-ins remain visible when there is no match.
            if score == 0 and source == "builtin":
                score = 1

            ranked.append((score, order, tool))

        ranked.sort(key=lambda item: (-item[0], item[1]))
        tools = [tool for score, _, tool in ranked if score > 0]
        if not tools:
            tools = list(self._tools.values())
        tools = _pin_foundation_tools(tools, self._tools, foundation_intent)
        selected = tools[:limit] if limit else tools
        self._remember_rank_cache(cache_key, [str(tool.get("name", "")) for tool in selected])
        self._last_rank_stats = self._rank_stats(
            started_at=started_at,
            cache_hit=False,
            query_terms=query_terms,
            selected_count=len(selected),
            workspace_profile=workspace_profile,
        )
        return selected

    def _invalidate_rank_cache(self) -> None:
        self._tools_revision += 1
        self._rank_cache.clear()
        self._rank_cache_order.clear()

    def _rank_cache_key(self, query_l: str, limit: Optional[int]) -> str:
        return json.dumps(
            {
                "revision": self._tools_revision,
                "query": query_l[:4000],
                "limit": limit,
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    def _remember_rank_cache(self, key: str, names: List[str]) -> None:
        self._rank_cache[key] = names
        self._rank_cache_order.append(key)
        while len(self._rank_cache_order) > self._rank_cache_limit:
            old = self._rank_cache_order.pop(0)
            self._rank_cache.pop(old, None)

    def _rank_stats(
        self,
        *,
        started_at: float,
        cache_hit: bool,
        query_terms: List[str],
        selected_count: int,
        workspace_profile: str = "general",
    ) -> Dict[str, Any]:
        return {
            "candidate_count": len(self._tools),
            "selected_count": selected_count,
            "query_terms": len(query_terms),
            "workspace_profile": workspace_profile,
            "ranking_ms": round((time.perf_counter() - started_at) * 1000, 2),
            "cache_hit": cache_hit,
            "cache_size": len(self._rank_cache),
        }

    def schema_for_llm(
        self,
        query: str = "",
        limit: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """生成给 LLM 看的工具描述文本，可按当前任务裁剪候选工具。"""
        selected = tools if tools is not None else self.rank_tools(query=query, limit=limit)
        lines = ["可用操作（只能选择下面的 tool name；不要把这个列表展示给用户）："]
        for tool in selected:
            lines.append(f"\n- {tool['name']}: {short_text(tool.get('description', ''), 120)}")
            lines.append(f"  source={tool.get('source', '')}")
            params = tool.get("parameters", {})
            props = params.get("properties", {}) if isinstance(params, dict) else {}
            required = set(params.get("required", [])) if isinstance(params, dict) else set()
            if props:
                parts = []
                for key, value in props.items():
                    marker = "*" if key in required else ""
                    parts.append(f"{key}{marker}:{value.get('type', 'any')}")
                lines.append(f"  params: {', '.join(parts)}")
        return "\n".join(lines)


def short_text(value: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def re_split_query(query: str) -> List[str]:
    import re

    return re.findall(r"[a-zA-Z0-9_.:/-]+|[\u4e00-\u9fff]{1,4}", query)


def _infer_workspace_profile(query_l: str) -> str:
    if _foundation_intent(query_l).get("project") or _foundation_intent(query_l).get("shell"):
        return "coding"
    if any(k in query_l for k in ("maker", "taptap", "游戏", "素材", "构建", "发布", "预览")):
        return "maker"
    if any(k in query_l for k in ("网页", "浏览器", "url", "http://", "https://", "搜索网页")):
        return "browser"
    if any(k in query_l for k in ("新建文档", "创建文档", "写文档", "readme", "markdown", "笔记", "说明")):
        return "docs"
    if any(k in query_l for k in ("代码", "修复", "实现", "bug", "测试", "python", "npm", "node", "git", "文件", "项目")):
        return "coding"
    return "general"


def _foundation_intent(query_l: str) -> Dict[str, bool]:
    project = any(
        k in query_l
        for k in (
            "项目状态",
            "了解项目",
            "当前项目",
            "项目概况",
            "仓库状态",
            "代码仓库",
            "git status",
            "查看状态",
            "项目结构",
        )
    )
    shell = any(
        k in query_l
        for k in (
            "cmd",
            "powershell",
            "终端",
            "控制台",
            "shell",
            "命令",
            "运行测试",
            "跑测试",
            "执行命令",
            "git log",
            "git status",
            "npm",
            "python",
            "cargo",
            "node",
        )
    )
    return {"project": project, "shell": shell}


def _pin_foundation_tools(
    ranked_tools: List[Dict[str, Any]],
    registry: Dict[str, Dict[str, Any]],
    intent: Dict[str, bool],
) -> List[Dict[str, Any]]:
    """Keep basic project-control tools visible for project/cmd requests.

    Maker and browser context is often present in long tasks. This pinning step
    prevents that background context from crowding out the everyday controls a
    user expects when they ask to inspect the project or run a normal command.
    """
    pinned_names: List[str] = []
    if intent.get("project") and "project_status" in registry:
        pinned_names.append("project_status")
    if intent.get("shell") and "execute_shell" in registry:
        pinned_names.append("execute_shell")
    if intent.get("project"):
        for name in ("read_file", "list_directory", "search_files"):
            if name in registry:
                pinned_names.append(name)

    if not pinned_names:
        return ranked_tools

    seen = set()
    pinned = []
    for name in pinned_names:
        if name in seen:
            continue
        seen.add(name)
        pinned.append(registry[name])

    return pinned + [tool for tool in ranked_tools if tool.get("name") not in seen]


def _workspace_profile_score(profile: str, name: str, source: str) -> int:
    is_maker = source == "maker_mcp" or str(name).startswith("maker_")
    is_browser = str(name).startswith("browser_")
    if profile == "maker":
        if is_maker:
            return 8
        if is_browser:
            return 3
        if name in {"project_status", "read_file", "list_directory", "search_files"}:
            return 2
        return -1
    if profile == "browser":
        if is_browser:
            return 8
        if name in {"read_file", "create_document"}:
            return 1
        if is_maker:
            return -3
        return -1
    if profile == "docs":
        if name in {"create_document", "read_file", "search_files", "list_directory"}:
            return 8
        if name in {"modify_file", "project_status"}:
            return 3
        if is_maker or is_browser:
            return -4
        return -1
    if profile == "coding":
        if name in {"project_status", "read_file", "search_files", "list_directory", "modify_file", "create_document", "execute_shell", "git_commit"}:
            return 6
        if is_maker:
            return -4
        if is_browser:
            return -2
        return 0
    return 0


def _closest_tool_name(name: str, available: List[str]) -> Optional[str]:
    if not name or not available:
        return None
    try:
        from difflib import get_close_matches

        matches = get_close_matches(name, available, n=1, cutoff=0.55)
        return matches[0] if matches else None
    except Exception:
        return None


def _preflight_next_step(validation: Dict[str, Any], alternatives: List[Dict[str, Any]]) -> str:
    structured = validation.get("structured_errors") or []
    if structured:
        first = structured[0]
        fix = first.get("suggested_fix")
        if fix:
            return str(fix)
    if alternatives:
        return f"Try {alternatives[0].get('name')} if it better matches the current task."
    return "Correct the tool name or parameters before executing."


def _alternative_reason(name: str, tool: Dict[str, Any], query: str) -> str:
    source = tool.get("source", "")
    tool_name = tool.get("name", "")
    if source == "maker_mcp":
        return "Maker-specific tool ranked as relevant to the current task."
    if str(tool_name).startswith("browser_"):
        return "Browser tool may inspect or operate the Maker page directly."
    if tool_name in {"read_file", "list_directory", "search_files"}:
        return "Read/search tool can gather context before a write or shell action."
    if name and _closest_tool_name(name, [str(tool_name)]) == tool_name:
        return "Tool name is close to the attempted action."
    if query:
        return "Ranked by current task and recent context."
    return "Available fallback tool."
