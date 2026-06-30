"""
llm/interface.py — LLM 接口

定义 TTMEvolve 所需的 LLM 能力。
实现者：ClaudeLLM, MockLLM。
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Sequence

from llm.content import (
    ContentBlock,
    ImageBlock,
    TextBlock,
    to_text_fallback,
)


class LLMInterface(ABC):
    """LLM 抽象接口。

    Multimodal 支持（Q1）：子类可以重写 ``*_multimodal`` 方法并把
    ``supports_multimodal`` 翻成 True。默认实现把所有 content blocks
    渲染成文本占位，让不支持多模态的实现也能跑完整流程。
    """

    #: True iff the implementation can accept image blocks. Subclasses
    #: that wire up the Anthropic / OpenAI image format must override.
    supports_multimodal: bool = False

    @abstractmethod
    def think(
        self,
        task: str,
        context: str,
        trajectory: List[Dict[str, Any]],
        tools_description: str,
    ) -> str:
        """根据任务和已执行轨迹生成下一步思考。"""
        ...

    @abstractmethod
    def choose_action(
        self,
        task: str,
        thought: str,
        tools_description: str,
    ) -> Dict[str, Any]:
        """根据思考选择下一步动作。"""
        ...

    @abstractmethod
    def reflect(self, prompt: str) -> str:
        """对学习层提示进行反思，返回文本。"""
        ...

    @abstractmethod
    def generate_code(self, prompt: str) -> str:
        """根据提示生成代码。"""
        ...

    # ------------------------------------------------------------------
    # Multimodal variants. Default implementation = text-only fallback.
    # Subclasses override when they support the relevant image format.
    # ------------------------------------------------------------------

    def think_multimodal(
        self,
        task: str,
        content: Sequence[ContentBlock],
        trajectory: List[Dict[str, Any]],
        tools_description: str,
        *,
        attachments: Optional[List[ImageBlock]] = None,
    ) -> str:
        """Multimodal-aware ``think``. The default collapses every block
        to text and delegates to ``think``, so a text-only LLM stays
        a drop-in replacement. Override to pass images to the model."""
        merged: List[ContentBlock] = list(content)
        for image in attachments or []:
            merged.append(image)
        text = to_text_fallback(merged)
        return self.think(task, text, trajectory, tools_description)

    def choose_action_multimodal(
        self,
        task: str,
        thought: str,
        tools_description: str,
        *,
        attachments: Optional[List[ImageBlock]] = None,
    ) -> Dict[str, Any]:
        """Multimodal-aware ``choose_action``. Default flattens any
        attached images into a textual summary and routes to
        ``choose_action``."""
        if not attachments:
            return self.choose_action(task, thought, tools_description)
        summary = to_text_fallback(attachments)
        return self.choose_action(
            task,
            f"{thought}\n\n[attachments]\n{summary}",
            tools_description,
        )
