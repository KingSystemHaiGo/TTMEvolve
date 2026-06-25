"""Shared API error types and helpers for remote LLM clients."""

from __future__ import annotations

import socket
from typing import Any, Dict
from urllib.error import URLError


class LLMAPIError(RuntimeError):
    """Remote LLM request failed before a valid model response was returned."""


class LLMTimeoutError(LLMAPIError):
    """Remote LLM request exceeded its configured timeout."""


def is_timeout_error(error: BaseException) -> bool:
    if isinstance(error, (TimeoutError, socket.timeout)):
        return True
    if isinstance(error, URLError):
        reason = getattr(error, "reason", None)
        return isinstance(reason, (TimeoutError, socket.timeout))
    return False


def failure_stats(
    *,
    provider: str,
    model: str,
    elapsed_ms: float,
    error_type: str,
    error: BaseException,
) -> Dict[str, Any]:
    return {
        "provider": provider,
        "model": model,
        "mode": "api",
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "generate_ms": round(elapsed_ms, 1),
        "tokens_per_sec": 0.0,
        "error_type": error_type,
        "error": str(error),
    }


def timeout_message(provider: str, timeout: float, elapsed_ms: float) -> str:
    return (
        f"{provider} API request timed out after {elapsed_ms / 1000:.1f}s "
        f"(configured timeout: {timeout}s)."
    )
