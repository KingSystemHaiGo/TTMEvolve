"""
llm/interface.py — LLM 接口

定义 TTMEvolve 所需的 LLM 能力。
实现者：ClaudeLLM, MockLLM。
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, List


class LLMInterface(ABC):
    """LLM 抽象接口。"""

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
