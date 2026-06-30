"""Explicit placeholder used when an API provider is selected but not configured."""

from __future__ import annotations

from typing import Any, Dict, List

from llm.interface import LLMInterface


class UnconfiguredLLM(LLMInterface):
    """Fail fast with a clear configuration error.

    This is not a mock model: it never returns synthetic agent output. It only
    lets the desktop app boot so the user can configure a real API provider.

    Multimodal: we keep ``supports_multimodal = False``. The default
    ``think_multimodal`` would just render text and call ``think`` (which
    raises), so we override it to raise directly with the same message.
    """

    supports_multimodal = False

    def __init__(self, reason: str):
        self.reason = reason

    def _raise(self) -> None:
        raise RuntimeError(self.reason)

    def think_multimodal(self, *args: Any, **kwargs: Any) -> str:
        self._raise()

    def think(
        self,
        task: str,
        context: str,
        trajectory: List[Dict[str, Any]],
        tools_description: str,
    ) -> str:
        self._raise()

    def choose_action(
        self,
        task: str,
        thought: str,
        tools_description: str,
    ) -> Dict[str, Any]:
        self._raise()

    def reflect(self, prompt: str) -> str:
        self._raise()

    def generate_code(self, prompt: str) -> str:
        self._raise()
