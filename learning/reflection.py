"""
learning/reflection.py — 反思引擎

分析单条轨迹或修复日志，提炼出可复用的规则。
"""

from __future__ import annotations
from typing import Any, Dict, List

from llm.interface import LLMInterface
from learning.knowledge_base import KnowledgeBase


class ReflectionEngine:
    """反思引擎：从经验中提取知识。"""

    def __init__(self, llm: LLMInterface, knowledge_base: KnowledgeBase):
        self.llm = llm
        self.knowledge_base = knowledge_base

    def reflect(
        self,
        session_id: str,
        task: str,
        trajectory: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """对一次任务轨迹进行反思，返回提炼出的知识条目。"""
        # 简单规则：LLM 分析轨迹，输出 JSON 列表
        prompt = self._build_reflection_prompt(session_id, task, trajectory)
        raw = self.llm.reflect(prompt)
        insights = self._parse_insights(raw, session_id)
        return insights

    def reflect_on_repair(
        self,
        session_id: str,
        repair_info: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """从一次修复中学习，沉淀故障模式。"""
        prompt = f"""
一次 Agent 自我修复刚刚成功完成：
会话：{session_id}
修复策略：{repair_info.get('strategy')}
修复前状态：{repair_info.get('state')}

请提炼 1-3 条故障模式或预防规则，格式为 JSON 列表：
[{{"domain": "...", "rule": "...", "context": "...", "tags": ["..."]}}]
"""
        raw = self.llm.reflect(prompt)
        return self._parse_insights(raw, session_id)



    def reflect_on_rescue(
        self,
        session_id: str,
        diff: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """从专家救援的本地-专家差值中学习方法论。"""
        prompt = f"""
一次任务中，本地轻量级模型尝试后失败，随后外部专家 LLM 介入并成功解决。

任务领域：{diff.get('domain', 'general')}

本地模型失败：
{self._format_step(diff.get('local_failure', {}))}

专家成功动作：
{self._format_step(diff.get('expert_success', {}))}

关键差异分析：
{diff.get('diff_text', '')}

请提炼 1-3 条可复用规则或方法论，帮助本地模型下次独立解决类似问题。
输出 JSON 列表：
[{{"domain": "...", "rule": "...", "context": "...", "tags": ["skill", "expert_rescue"], "confidence": 0.8}}]
"""
        raw = self.llm.reflect(prompt)
        return self._parse_insights(raw, session_id)

    def _format_step(self, step: Dict[str, Any]) -> str:
        if not step:
            return "无"
        return f"""
思考：{step.get('thought', '')[:200]}
动作：{step.get('action', {})}
观察：{step.get('observation', {})}
""".strip()

    def _build_reflection_prompt(
        self,
        session_id: str,
        task: str,
        trajectory: List[Dict[str, Any]],
    ) -> str:
        lines = [
            f"任务：{task}",
            f"会话：{session_id}",
            "执行轨迹：",
        ]
        for step in trajectory:
            lines.append(
                f"\nStep {step.get('iteration')}:\n"
                f"  思考：{step.get('thought', '')[:200]}\n"
                f"  动作：{step.get('action', {})}\n"
                f"  观察：{step.get('observation', {})}"
            )
        lines.append(
            "\n请从以上轨迹中反思：\n"
            "1. 哪些步骤成功？原因是什么？\n"
            "2. 哪些步骤失败？根本原因是什么？\n"
            "3. 能否提炼 1-3 条可复用规则或改进建议？\n"
            "输出 JSON 列表："
            '[{"domain": "...", "rule": "...", "context": "...", "tags": ["..."], "confidence": 0.8}]'
        )
        return "\n".join(lines)

    def _parse_insights(self, raw: str, session_id: str) -> List[Dict[str, Any]]:
        """从 LLM 输出解析知识条目。"""
        try:
            # 尝试直接解析
            data = __import__("json").loads(raw)
            if isinstance(data, dict):
                data = [data]
            if isinstance(data, list):
                for item in data:
                    item["source_session"] = session_id
                return data
        except Exception:
            pass

        # 回退：整段文本作为一条经验
        return [{
            "domain": "reflection",
            "rule": raw[:500],
            "context": "LLM 反思输出",
            "tags": ["reflection"],
            "source_session": session_id,
        }]
