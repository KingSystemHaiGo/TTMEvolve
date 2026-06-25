"""
llm/__init__.py

注意：ClaudeLLM / LocalLLM / OpenAILLM 不在顶层导入，
避免 mock 模式或无依赖环境触发 ImportError。
请通过 llm_factory.LLMFactory.create() 按需创建。
"""

from .interface import LLMInterface
from .llm_factory import LLMFactory
from .mock_llm import MockLLM

__all__ = ["LLMInterface", "LLMFactory", "MockLLM"]
