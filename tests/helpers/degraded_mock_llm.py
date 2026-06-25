"""
tests/helpers/degraded_mock_llm.py — 故意失败的 Mock LLM

前 N 步返回错误动作，用于稳定触发 rescue。
"""

from __future__ import annotations
from typing import Any, Dict, List

from llm.interface import LLMInterface


class DegradedMockLLM(LLMInterface):
    """Mock LLM：前 fail_steps 步返回错误动作，之后按 scripted 执行。"""

    def __init__(
        self,
        fail_steps: int = 3,
        fail_action: Dict[str, Any] = None,
        scripted_actions: List[Dict[str, Any]] = None,
    ):
        self.fail_steps = fail_steps
        self.fail_action = fail_action or {"tool": "read_file", "params": {"path": "missing.txt"}}
        self.scripted = scripted_actions or []
        self.step = 0

    def think(self, task: str, context: str, trajectory: List[Dict[str, Any]], tools_description: str) -> str:
        return f"Degraded mock thinking for: {task}"

    def choose_action(self, task: str, thought: str, tools_description: str) -> Dict[str, Any]:
        if self.step < self.fail_steps:
            self.step += 1
            return dict(self.fail_action)
        if self.step - self.fail_steps < len(self.scripted):
            action = self.scripted[self.step - self.fail_steps]
            self.step += 1
            return action
        return {"done": True, "output": f"Degraded mock 完成：{task}"}

    def reflect(self, prompt: str) -> str:
        import json
        return json.dumps([{
            "domain": "mock",
            "rule": "degraded mock reflection",
            "context": prompt[:100],
            "tags": ["mock"],
            "confidence": 0.5,
        }], ensure_ascii=False)

    def generate_code(self, prompt: str) -> str:
        return "def run(input: str) -> dict:\n    return {'ok': True, 'output': 'mock skill'}\n"
