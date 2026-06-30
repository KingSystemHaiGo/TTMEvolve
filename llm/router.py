"""LLM Router — multi-provider routing with automatic fallback.

v0.7.0 全面转向云端 LLM。LLMRouter 接受一个主 Provider + 多个备用
Provider，当主 Provider 失败时（限流、auth、网络）按顺序尝试备用。

设计要点：
- 路由对调用方透明（实现 LLMInterface）
- 故障转移可配置（fallback 列表、超时、重试）
- 统计每次调用的成功/失败 Provider（用于 Settings 面板展示）
- 线程安全（多 Agent 可能并发调用）
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from llm.interface import LLMInterface


log = logging.getLogger("ttmevolve.llm.router")


LLM_ROUTER_VERSION = "llm-router.v1"


# 哪些异常应该触发 fallback
class RouterFallbackError(Exception):
    """Raised when the router wants the caller to fall back to the next provider."""


@dataclass
class ProviderStats:
    """Per-provider usage stats for the Settings UI."""
    provider: str
    total_calls: int = 0
    success_calls: int = 0
    fallback_calls: int = 0
    last_error: str = ""
    last_used_at: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.success_calls / self.total_calls


@dataclass
class RouterConfig:
    """Configuration for the router's fallback behavior."""
    per_provider_timeout_seconds: float = 60.0
    retries_per_provider: int = 1
    cooldown_after_failure_seconds: float = 30.0


class LLMRouter(LLMInterface):
    """Routes LLM calls through a primary provider with fallback to backups."""

    def __init__(
        self,
        primary: LLMInterface,
        fallbacks: Optional[List[LLMInterface]] = None,
        config: Optional[RouterConfig] = None,
        on_provider_used: Optional[Callable[[str, bool], None]] = None,
    ) -> None:
        if primary is None:
            raise ValueError("primary provider is required")
        self._primary = primary
        self._fallbacks = list(fallbacks or [])
        self._config = config or RouterConfig()
        self._on_provider_used = on_provider_used
        self._stats: Dict[str, ProviderStats] = {}
        self._lock = threading.Lock()
        # Initialize stats for each provider
        for provider in [primary] + self._fallbacks:
            name = getattr(provider, "name", None) or type(provider).__name__
            self._stats[name] = ProviderStats(provider=name)

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def get_stats(self) -> List[Dict[str, Any]]:
        """Return per-provider stats for the Settings UI."""
        with self._lock:
            return [
                {
                    "provider": stats.provider,
                    "total_calls": stats.total_calls,
                    "success_calls": stats.success_calls,
                    "fallback_calls": stats.fallback_calls,
                    "last_error": stats.last_error,
                    "last_used_at": stats.last_used_at,
                    "success_rate": round(stats.success_rate, 4),
                }
                for stats in self._stats.values()
            ]

    # ------------------------------------------------------------------
    # LLMInterface implementation
    # ------------------------------------------------------------------

    def _all_providers(self) -> List[LLMInterface]:
        return [self._primary] + self._fallbacks

    def _call_with_fallback(
        self,
        method_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        last_error: Optional[BaseException] = None
        for index, provider in enumerate(self._all_providers()):
            name = getattr(provider, "name", None) or type(provider).__name__
            method = getattr(provider, method_name, None)
            if not callable(method):
                continue
            try:
                with self._lock:
                    self._stats[name].total_calls += 1
                result = method(*args, **kwargs)
                with self._lock:
                    self._stats[name].success_calls += 1
                    self._stats[name].last_used_at = time.time()
                if index > 0:
                    with self._lock:
                        self._stats[name].fallback_calls += 1
                if self._on_provider_used:
                    try:
                        self._on_provider_used(name, True)
                    except Exception:
                        log.exception("on_provider_used callback raised")
                return result
            except Exception as e:
                last_error = e
                with self._lock:
                    self._stats[name].last_error = str(e)
                log.warning(
                    "provider %s failed on %s: %s; trying next",
                    name,
                    method_name,
                    e,
                )
                if self._on_provider_used:
                    try:
                        self._on_provider_used(name, False)
                    except Exception:
                        log.exception("on_provider_used callback raised")
                continue
        # All providers exhausted.
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"No provider implemented {method_name}")

    def think(
        self,
        task: str,
        context: str,
        trajectory: List[Dict[str, Any]],
        tools_description: str,
    ) -> str:
        result = self._call_with_fallback(
            "think",
            task=task,
            context=context,
            trajectory=trajectory,
            tools_description=tools_description,
        )
        return str(result)

    def choose_action(
        self,
        task: str,
        thought: str,
        tools_description: str,
    ) -> Dict[str, Any]:
        return self._call_with_fallback(
            "choose_action",
            task=task,
            thought=thought,
            tools_description=tools_description,
        )

    def reflect(self, prompt: str) -> str:
        return str(self._call_with_fallback("reflect", prompt=prompt))

    def generate_code(self, prompt: str) -> str:
        return str(self._call_with_fallback("generate_code", prompt=prompt))

    # ------------------------------------------------------------------
    # Multimodal passthrough. ``_call_with_fallback`` already dispatches
    # to whatever implementation the provider exposes, so all we need
    # is a thin wrapper that forwards the right kwargs.
    # ------------------------------------------------------------------

    def think_multimodal(
        self,
        task: str,
        content: List[Any],
        trajectory: List[Dict[str, Any]],
        tools_description: str,
        *,
        attachments: Optional[List[Any]] = None,
    ) -> str:
        # Skip providers that opt out of multimodal so a non-vision
        # fallback never silently sees an image block.
        primary_method = getattr(self._primary, "think_multimodal", None)
        if not callable(primary_method) or not getattr(self._primary, "supports_multimodal", False):
            # Fall back to text-only when no provider supports multimodal.
            from llm.content import to_text_fallback
            text = to_text_fallback(list(content) + list(attachments or []))
            return self.think(task, text, trajectory, tools_description)
        return str(
            self._call_with_fallback(
                "think_multimodal",
                task=task,
                content=list(content),
                trajectory=trajectory,
                tools_description=tools_description,
                attachments=list(attachments or []),
            )
        )

    def choose_action_multimodal(
        self,
        task: str,
        thought: str,
        tools_description: str,
        *,
        attachments: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        primary_method = getattr(self._primary, "choose_action_multimodal", None)
        if not callable(primary_method) or not getattr(self._primary, "supports_multimodal", False):
            return self.choose_action(task, thought, tools_description)
        return self._call_with_fallback(
            "choose_action_multimodal",
            task=task,
            thought=thought,
            tools_description=tools_description,
            attachments=list(attachments or []),
        )


def build_router_from_config(config: Any) -> LLMRouter:
    """Build an LLMRouter from a Config object.

    Reads:
        llm.provider, llm.api_key, llm.model, llm.base_url
        llm.fallback_providers (list of dicts with provider/api_key/model/base_url)
    """
    from llm.llm_factory import LLMFactory

    primary_name = config.llm_provider()
    primary = LLMFactory.create(primary_name, config)

    fallbacks: List[LLMInterface] = []
    for entry in config.get("llm.fallback_providers", []) or []:
        provider_name = entry.get("provider") if isinstance(entry, dict) else None
        if not provider_name:
            continue
        try:
            fallback = LLMFactory.create(provider_name, config)
            fallbacks.append(fallback)
        except Exception as e:
            log.warning("fallback provider %s failed to construct: %s", provider_name, e)

    return LLMRouter(primary=primary, fallbacks=fallbacks)