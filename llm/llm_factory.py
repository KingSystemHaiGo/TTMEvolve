"""LLM factory."""

from __future__ import annotations

from typing import Optional

from core.config import Config
from llm.interface import LLMInterface
from llm.provider_presets import OPENAI_COMPATIBLE_ALIASES


class LLMFactory:
    """Create the active LLM implementation from config."""

    @staticmethod
    def create(provider: str, config: Optional[Config] = None) -> LLMInterface:
        cfg = config or Config()
        normalized = (provider or cfg.llm_provider()).lower().strip()

        if normalized in {"local", "gguf"}:
            from llm.local_llm import LocalLLM

            return LocalLLM(cfg)

        if normalized == "mock":
            from llm.mock_llm import MockLLM

            return MockLLM()

        if normalized in OPENAI_COMPATIBLE_ALIASES:
            from llm.openai_llm import OpenAILLM

            return OpenAILLM(cfg)

        if normalized == "minimax":
            from llm.minimax_llm import MiniMaxLLM

            return MiniMaxLLM(cfg)

        if normalized in {"claude", "anthropic"}:
            from llm.claude_llm import ClaudeLLM

            return ClaudeLLM(cfg)

        raise ValueError(f"Unsupported LLM provider: {provider}")

    @staticmethod
    def create_expert(config: Optional[Config] = None) -> LLMInterface:
        cfg = config or Config()
        expert_provider = cfg.get("expert.provider", "openai")
        return LLMFactory.create(expert_provider, cfg)

    @staticmethod
    def default_provider(config: Optional[Config] = None) -> str:
        cfg = config or Config()
        return cfg.get("llm.provider", "deepseek")
