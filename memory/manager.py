"""
memory/manager.py — 记忆管理器

协调 Hot / Warm / Cold 三层记忆。
同时作为 ReAct 循环的实时上下文编排者，提供 token-aware 的 think payload。
"""

from __future__ import annotations
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.config import Config
from llm.context_budget import ContextBudgetManager
from llm.interface import LLMInterface

from .hot import HotMemory
from .warm import WarmMemory
from .cold import ColdMemory
from .agents_md_index import AgentsMdIndex


DEFAULT_SYSTEM_PROMPT = "你是一个为 TapTap Maker 游戏开发而生的 Agent。请用中文思考，逐步推理。"


class MemoryManager:
    """三层记忆管理器 + 实时上下文预算编排。"""

    def __init__(
        self,
        project_root: Path,
        storage_root: Path,
        skills_dir: Path,
        llm: Optional[LLMInterface] = None,
        budget_manager: Optional[ContextBudgetManager] = None,
        config: Optional[Config] = None,
    ):
        self.config = config or Config()
        self.llm = llm
        self.hot = HotMemory(
            max_turns=self.config.get("llm.hot_memory_max_turns", 6),
            batch_size=2,
            summarize_fn=self._summarize_turns if llm else None,
        )
        self.warm = WarmMemory(project_root, skills_dir)
        self.cold = ColdMemory(
            storage_root / "cold_memory",
            vector_index_config=self.config.vector_index_config(),
        )
        self.budget_manager = budget_manager or ContextBudgetManager(
            n_ctx=self.config.get("llm.n_ctx", 8192),
            reserve_tokens=self.config.get("llm.reserve_tokens", 256),
        )
        self.agents_md_index = AgentsMdIndex(
            project_root=project_root,
            storage_root=storage_root,
            config=self.config,
        )

    def set_system_prompt(self, prompt: str) -> None:
        self.hot.set_system_prompt(prompt)

    def prepare_task_context(
        self,
        system_prompt: str,
        task: str,
        warm_items: List[str],
    ) -> List[Dict[str, str]]:
        self.hot.set_system_prompt(system_prompt)
        self.hot.add_turn("user", task)

        for item in warm_items:
            if item.startswith("skill:"):
                content = self.warm.load_skill(item.split(":", 1)[1])
            elif item.startswith("doc:"):
                content = self.warm.load_doc(item.split(":", 1)[1])
            else:
                content = item
            if content:
                self.hot.add_turn("system", f"[Warm Memory]\n{content[:1500]}")

        return self.hot.build_context()

    def prepare_think_payload(
        self,
        task: str,
        context: str,
        trajectory: List[Dict[str, Any]],
        tools_description: str,
        max_tokens: int = 512,
        workspace_profile: str = "general",
    ) -> Tuple[str, "BudgetStats"]:
        """为 ReAct 循环的 think() 调用准备上下文字符串和预算统计。

        优先级（从高到低）：任务、AGENTS.md 项目规范、当前上下文、
        工具描述、思考提示、历史轨迹。当预算不足时，优先丢弃/截断历史轨迹。
        """
        from llm.context_budget import BudgetStats

        started_at = time.perf_counter()
        system = self.hot._system_prompt or DEFAULT_SYSTEM_PROMPT
        profile = _normalize_workspace_profile(workspace_profile)
        profile_context = f"【Workspace Profile】{profile}"
        trajectory_str = self.budget_manager.slice_trajectory(
            trajectory,
            max_steps=self.config.get("llm.max_history_steps", 6),
            max_chars_per_step=200,
        )

        agents_context = ""
        agents_md_hits = 0
        agents_md_ms = 0.0
        if self.config.get("agents_md.enabled", True):
            agents_started_at = time.perf_counter()
            try:
                chunks = self.agents_md_index.search(task, top_k=self.config.get("agents_md.top_k", 3))
                if chunks:
                    agents_md_hits = len(chunks)
                    lines = ["\n【项目规范】"]
                    for c in chunks:
                        heading = c.get("heading", "")
                        text = c.get("text", "")[:300]
                        lines.append(f"- {heading}: {text}")
                    agents_context = "\n".join(lines)
            except Exception:
                # 检索失败不应中断 ReAct 循环
                pass
            finally:
                agents_md_ms = round((time.perf_counter() - agents_started_at) * 1000, 2)

        cold_context = ""
        cold_recall_hits = 0
        cold_recall_ms = 0.0
        cold_started_at = time.perf_counter()
        try:
            cold_top_k = self._cold_recall_top_k(profile)
            cold_hits = self.recall(
                task,
                top_k=cold_top_k,
                workspace_profile=profile,
            )
            if cold_hits:
                cold_recall_hits = len(cold_hits)
                lines = ["\n【历史归档】"]
                for hit in cold_hits:
                    summary = hit.get("summary", "")
                    hit_type = hit.get("type", "")
                    lines.append(f"- [{hit_type}] {summary}")
                cold_context = "\n".join(lines)
        except Exception:
            pass
        finally:
            cold_recall_ms = round((time.perf_counter() - cold_started_at) * 1000, 2)

        parts: List[Tuple[str, int]] = [
            (task, 6),
            (profile_context, 6),
            (agents_context, 5),
            (cold_context, 4),
            (context, 4),
            (tools_description, 6),
            ("请思考下一步。", 4),
            (trajectory_str, 1),
        ]
        # Drop empty parts so they do not affect priority handling.
        parts = [(text, priority) for text, priority in parts if text.strip()]
        text, stats = self.budget_manager.fit_parts(system, parts, max_tokens)
        stats = replace(
            stats,
            agents_md_hits=agents_md_hits,
            cold_recall_hits=cold_recall_hits,
            agents_md_ms=agents_md_ms,
            cold_recall_ms=cold_recall_ms,
            context_build_ms=round((time.perf_counter() - started_at) * 1000, 2),
            workspace_profile=profile,
        )
        return text, stats

    def archive_session(
        self,
        session_id: str,
        summary: str,
        workspace_profile: str = "general",
        agent_id: str = "default",
        visibility: str = "private",
    ) -> None:
        self.cold.index(
            {
                "id": session_id,
                "type": "session_summary",
                "workspace_profile": _normalize_workspace_profile(workspace_profile),
                "agent_id": agent_id,
                "visibility": visibility,
            },
            summary,
        )

    def recall(
        self,
        query: str,
        top_k: int = 3,
        workspace_profile: str = "general",
        agent_id: str = "default",
    ) -> List[Dict[str, Any]]:
        return self.cold.search(
            query,
            top_k=top_k,
            workspace_profile=_normalize_workspace_profile(workspace_profile),
            agent_id=agent_id,
        )

    def _cold_recall_top_k(self, workspace_profile: str) -> int:
        default_top_k = self.config.get("memory.vector_index.top_k", 3)
        if hasattr(self.cold, "profile_policy"):
            return int(self.cold.profile_policy(workspace_profile, top_k=default_top_k)["top_k"])
        return int(default_top_k)

    def _summarize_turns(self, turns: List[Dict[str, Any]]) -> str:
        """把一组旧 turn 摘要成一句话。优先用 LLM reflect，否则 rule-based。"""
        if self.llm is None:
            return self._rule_based_summary(turns)

        text = "\n".join(f"{t.get('role', '')}: {t.get('content', '')}" for t in turns)
        prompt = (
            "请用一句话总结以下对话轮次，保留关键事实和决策：\n"
            f"{text[:2000]}"
        )
        try:
            return self.llm.reflect(prompt).strip() or self._rule_based_summary(turns)
        except Exception:
            return self._rule_based_summary(turns)

    @staticmethod
    def _rule_based_summary(turns: List[Dict[str, Any]]) -> str:
        snippets = []
        for t in turns:
            content = str(t.get("content", ""))
            if content:
                snippets.append(content[:120])
        if not snippets:
            return "（无内容）"
        return " | ".join(snippets)


def _normalize_workspace_profile(value: str) -> str:
    profile = str(value or "general").strip().lower()
    return profile if profile in {"coding", "docs", "maker", "browser", "general"} else "general"
