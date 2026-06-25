"""
memory/hot.py — 工作记忆（Hot）

当前任务的最小上下文。限制大小，避免 Token 爆炸。
"""

from __future__ import annotations
from typing import Any, Callable, Dict, List, Optional


class HotMemory:
    """工作记忆：只保留当前任务的核心信息。"""

    MAX_TOKENS_ESTIMATE = 3000

    def __init__(
        self,
        max_turns: int = 6,
        batch_size: int = 2,
        summarize_fn: Optional[Callable[[List[Dict[str, Any]]], str]] = None,
    ):
        self._turns: List[Dict[str, Any]] = []
        self._system_prompt: str = ""
        self.max_turns = max(2, max_turns)
        self.batch_size = max(1, batch_size)
        self.summarize_fn = summarize_fn

    def set_system_prompt(self, prompt: str) -> None:
        self._system_prompt = prompt

    def set_summarize_fn(self, fn: Optional[Callable[[List[Dict[str, Any]]], str]]) -> None:
        self.summarize_fn = fn

    def add_turn(self, role: str, content: str) -> None:
        self._turns.append({"role": role, "content": content})
        self._compress_if_needed()

    def _compress_if_needed(self) -> None:
        while len(self._turns) > self.max_turns:
            batch = self._turns[: self.batch_size]
            del self._turns[: self.batch_size]
            if self.summarize_fn is not None:
                try:
                    summary = self.summarize_fn(batch)
                    self._turns.insert(
                        0,
                        {"role": "system", "content": f"[摘要] {summary}"},
                    )
                except Exception:
                    # Fall back to dropping if summarizer fails.
                    pass

    def build_context(self) -> List[Dict[str, str]]:
        messages = [{"role": "system", "content": self._system_prompt}]
        messages.extend(self._turns)
        return messages

    def clear(self) -> None:
        self._turns = []
