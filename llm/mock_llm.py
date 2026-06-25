"""
llm/mock_llm.py — Mock LLM 实现

用于测试和离线开发，不调用真实 API。
"""

from __future__ import annotations
from typing import Any, Dict, List
import json

from llm.interface import LLMInterface


class MockLLM(LLMInterface):
    """Mock LLM：按规则返回固定动作，方便测试。"""

    def __init__(self, scripted_actions: List[Dict[str, Any]] = None):
        self.scripted = scripted_actions or []
        self.step = 0

    def think(self, task: str, context: str, trajectory: List[Dict[str, Any]], tools_description: str) -> str:
        return f"Mock thinking for: {task}"

    def choose_action(self, task: str, thought: str, tools_description: str) -> Dict[str, Any]:
        if self.step < len(self.scripted):
            action = self.scripted[self.step]
            self.step += 1
            return action
        return {"done": True, "output": f"Mock 完成：{task}"}

    def reflect(self, prompt: str) -> str:
        return json.dumps([{
            "domain": "mock",
            "rule": "当用户要求列出文件时，先调用 list_directory 工具获取目录内容再总结",
            "context": prompt[:100],
            "tags": ["mock", "skill"],
            "confidence": 0.85,
        }], ensure_ascii=False)

    def generate_code(self, prompt: str) -> str:
        return """
def run(input: str) -> dict:
    return {"ok": True, "output": f"Mock skill processed: {input}"}
"""
