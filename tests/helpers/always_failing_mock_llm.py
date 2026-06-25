"""
tests/helpers/always_failing_mock_llm.py — 每步都失败的 Mock LLM

用于让专家救援被反复触发，从而允许真实专家通过多次 direct_action 完成任务。
"""

from __future__ import annotations
import json
from typing import Any, Dict, List

from llm.interface import LLMInterface


class AlwaysFailingMockLLM(LLMInterface):
    """Mock LLM：每步都尝试读取不存在的文件，永远失败。"""

    def __init__(self, fail_action: Dict[str, Any] = None):
        self.fail_action = fail_action or {"tool": "read_file", "params": {"path": "missing.txt"}}

    def think(self, task: str, context: str, trajectory: List[Dict[str, Any]], tools_description: str) -> str:
        return "always failing mock think"

    def choose_action(self, task: str, thought: str, tools_description: str) -> Dict[str, Any]:
        return dict(self.fail_action)

    def reflect(self, prompt: str) -> str:
        return json.dumps([{
            "domain": "mock",
            "rule": "always failing reflection",
            "context": prompt[:100],
            "tags": ["mock"],
            "confidence": 0.5,
        }], ensure_ascii=False)

    def generate_code(self, prompt: str) -> str:
        return "def run(input: str) -> dict:\n    return {'ok': False, 'error': 'mock'}\n"
