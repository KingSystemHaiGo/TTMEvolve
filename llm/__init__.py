"""
llm/__init__.py

注意：ClaudeLLM / LocalLLM / OpenAILLM 不在顶层导入，
避免 mock 模式或无依赖环境触发 ImportError。
请通过 llm_factory.LLMFactory.create() 按需创建。
"""

from .content import (
    CONTENT_BLOCK_VERSION,
    ContentBlock,
    ImageBlock,
    TextBlock,
    blocks_from_strings,
    to_anthropic_messages,
    to_openai_messages,
    to_text_fallback,
)
from .interface import LLMInterface
from .llm_factory import LLMFactory
from .mock_llm import MockLLM

__all__ = [
    "LLMInterface",
    "LLMFactory",
    "MockLLM",
    "ContentBlock",
    "TextBlock",
    "ImageBlock",
    "CONTENT_BLOCK_VERSION",
    "to_anthropic_messages",
    "to_openai_messages",
    "to_text_fallback",
    "blocks_from_strings",
]
