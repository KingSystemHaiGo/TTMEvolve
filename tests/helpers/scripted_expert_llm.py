"""
tests/helpers/scripted_expert_llm.py — 预设脚本的专家 LLM

按固定脚本返回 RescueAction，无需真实 API key，用于 CI 或 fallback。
"""

from __future__ import annotations
import json
from typing import Any, Dict, List

from llm.interface import LLMInterface


class ScriptedExpertLLM(LLMInterface):
    """测试用专家 LLM：reflect() 返回固定 RescueAction 序列。"""

    def __init__(self, scripted_rescues: List[Dict[str, Any]] = None):
        self.scripted = scripted_rescues or []
        self.index = 0

    def think(self, task: str, context: str, trajectory: List[Dict[str, Any]], tools_description: str) -> str:
        return "scripted expert think"

    def choose_action(self, task: str, thought: str, tools_description: str) -> Dict[str, Any]:
        return {"done": True, "output": "scripted expert output"}

    def reflect(self, prompt: str) -> str:
        if self.index < len(self.scripted):
            action = self.scripted[self.index]
            self.index += 1
            return json.dumps(action, ensure_ascii=False)
        return json.dumps({
            "mode": "thought_injection",
            "thought": "继续执行下一步。",
        }, ensure_ascii=False)

    def generate_code(self, prompt: str) -> str:
        return "def run(input: str) -> dict:\n    return {'ok': True}\n"
