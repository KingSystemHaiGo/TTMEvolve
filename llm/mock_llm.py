"""
llm/mock_llm.py — Mock LLM 实现

用于测试和离线开发，不调用真实 API。
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
import json

from llm.interface import LLMInterface


class MockLLM(LLMInterface):
    """Mock LLM：按规则返回固定动作，方便测试。

    Multimodal recording: every call to ``think_multimodal`` and
    ``choose_action_multimodal`` is appended to ``self.multimodal_calls``
    so tests can assert what the agent sent. ``supports_multimodal`` is
    True so the routing layer knows this mock can simulate a vision model.
    """

    supports_multimodal = True

    def __init__(self, scripted_actions: List[Dict[str, Any]] = None):
        self.scripted = scripted_actions or []
        self.step = 0
        self.multimodal_calls: List[Dict[str, Any]] = []
        self.think_multimodal_text: Optional[str] = None

    def think(self, task: str, context: str, trajectory: List[Dict[str, Any]], tools_description: str) -> str:
        return f"Mock thinking for: {task}"

    def think_multimodal(
        self,
        task: str,
        content,
        trajectory,
        tools_description,
        *,
        attachments=None,
    ) -> str:
        # Record what the agent sent so tests can assert on it.
        try:
            from llm.content import ImageBlock, TextBlock
            attachments = list(attachments or [])
            text_blocks = [b for b in content if isinstance(b, TextBlock)]
            image_blocks = [b for b in content if isinstance(b, ImageBlock)]
        except Exception:
            text_blocks, image_blocks, attachments = [], [], []
        self.multimodal_calls.append({
            "task": task,
            "text_block_count": len(text_blocks),
            "content_image_count": len(image_blocks),
            "attachments": [getattr(a, "source", "") for a in attachments],
            "tools_description_chars": len(tools_description or ""),
        })
        if self.think_multimodal_text is not None:
            return self.think_multimodal_text
        return f"Mock multimodal think for: {task} (saw {len(attachments)} image(s))"

    def choose_action(self, task: str, thought: str, tools_description: str) -> Dict[str, Any]:
        if self.step < len(self.scripted):
            action = self.scripted[self.step]
            self.step += 1
            return action
        return {"done": True, "output": f"Mock 完成：{task}"}

    def choose_action_multimodal(
        self,
        task: str,
        thought: str,
        tools_description: str,
        *,
        attachments=None,
    ) -> Dict[str, Any]:
        # Always return the same scripted/done action; multimodal
        # routing is exercised by the call site.
        return self.choose_action(task, thought, tools_description)

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
