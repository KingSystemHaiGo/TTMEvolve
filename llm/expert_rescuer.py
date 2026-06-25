"""
llm/expert_rescuer.py — 专家救援器

负责：
1. 根据配置实例化外部专家 LLM。
2. 构建救援上下文并调用专家 LLM。
3. 解析专家返回的 RescueAction。
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional

from core.config import Config
from llm.expert_protocol import EXPERT_RESCUE_PROMPT, RescueAction, RescueContext
from llm.utils import parse_llm_json


class ExpertRescuer:
    """外部专家 LLM 救援器。"""

    def __init__(self, config: Optional[Config] = None):
        self.cfg = config or Config()
        self._llm = None
        self._enabled = self.cfg.get("expert.enabled", False)

    @property
    def llm(self):
        """懒加载专家 LLM。"""
        if self._llm is None:
            from llm.llm_factory import LLMFactory
            self._llm = LLMFactory.create_expert(self.cfg)
        return self._llm

    def is_available(self) -> bool:
        """专家是否可用。"""
        if not self._enabled:
            return False
        try:
            _ = self.llm
            return True
        except Exception:
            return False

    def rescue(
        self,
        task: str,
        trajectory: List[Dict[str, Any]],
        health_state: Optional[Dict[str, Any]],
        tools_description: str,
        warm_context: str,
    ) -> RescueAction:
        """调用专家 LLM 获取救援动作。"""
        if not self._enabled:
            raise RuntimeError("Expert rescuer is not enabled")

        ctx = RescueContext.build(
            task=task,
            trajectory=trajectory,
            health_state=health_state,
            tools_description=tools_description,
            warm_context=warm_context,
        )
        prompt = EXPERT_RESCUE_PROMPT.format(**ctx.to_prompt_kwargs())

        raw = self.llm.reflect(prompt)
        parsed = parse_llm_json(raw)

        return RescueAction.from_dict(parsed)
