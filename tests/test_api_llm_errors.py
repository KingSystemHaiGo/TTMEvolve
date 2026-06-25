from __future__ import annotations

import socket
import sys
from pathlib import Path
from urllib.error import URLError
from unittest.mock import patch

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.config import Config
from llm.api_errors import LLMAPIError, LLMTimeoutError
from llm.openai_llm import OpenAILLM
from llm.minimax_llm import MiniMaxLLM


def _api_config() -> Config:
    cfg = Config()
    cfg.data = {
        "llm": {
            "provider": "deepseek",
            "model": "deepseek-test",
            "api_key": "sk-test",
            "base_url": "https://example.invalid",
            "timeout": 0.01,
        }
    }
    cfg._profiles = {}
    return cfg


def test_openai_compatible_timeout_raises_structured_error():
    llm = OpenAILLM(_api_config())
    with patch("llm.openai_llm.request.urlopen", side_effect=TimeoutError("slow")):
        try:
            llm._call("system", [{"role": "user", "content": "hello"}])
        except LLMTimeoutError as e:
            assert "timed out" in str(e)
        else:
            raise AssertionError("expected LLMTimeoutError")

    stats = llm.last_call_stats()
    assert stats["error_type"] == "timeout"
    assert stats["generate_ms"] >= 0
    assert stats["total_tokens"] == 0


def test_openai_compatible_url_timeout_is_detected():
    llm = OpenAILLM(_api_config())
    with patch("llm.openai_llm.request.urlopen", side_effect=URLError(socket.timeout("slow"))):
        try:
            llm._call("system", [{"role": "user", "content": "hello"}])
        except LLMTimeoutError:
            pass
        else:
            raise AssertionError("expected LLMTimeoutError")

    assert llm.last_call_stats()["error_type"] == "timeout"


def test_openai_compatible_network_error_raises_api_error():
    llm = OpenAILLM(_api_config())
    with patch("llm.openai_llm.request.urlopen", side_effect=OSError("network down")):
        try:
            llm._call("system", [{"role": "user", "content": "hello"}])
        except LLMAPIError as e:
            assert "network down" in str(e)
        else:
            raise AssertionError("expected LLMAPIError")

    assert llm.last_call_stats()["error_type"] == "network_error"


class _FakeMiniMaxResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return (
            b'{"id":"req-1","choices":[{"finish_reason":"stop","message":'
            b'{"content":"{\\"ok\\":true}","reasoning_content":"brief"}}],'
            b'"usage":{"prompt_tokens":10,"completion_tokens":2,"total_tokens":12,'
            b'"prompt_tokens_details":{"cached_tokens":3}},'
            b'"base_resp":{"status_code":0,"status_msg":""}}'
        )


def _minimax_config() -> Config:
    cfg = Config()
    cfg.data = {
        "llm": {
            "provider": "minimax",
            "model": "MiniMax-M3",
            "api_key": "sk-test",
            "base_url": "https://api.minimax.chat/v1",
            "timeout": 5,
        }
    }
    cfg._profiles = {}
    return cfg


def test_minimax_success_records_request_diagnostics():
    llm = MiniMaxLLM(_minimax_config())
    with patch("llm.minimax_llm.request.urlopen", return_value=_FakeMiniMaxResponse()):
        raw = llm._call("system", [{"role": "user", "content": "hello"}], max_tokens=8)

    stats = llm.last_call_stats()
    assert raw == '{"ok":true}'
    assert stats["endpoint"].endswith("/text/chatcompletion_v2")
    assert stats["http_status"] == 200
    assert stats["request_id"] == "req-1"
    assert stats["base_resp_status_code"] == 0
    assert stats["finish_reason"] == "stop"
    assert stats["cached_tokens"] == 3
    assert stats["has_reasoning_content"] is True


if __name__ == "__main__":
    test_openai_compatible_timeout_raises_structured_error()
    test_openai_compatible_url_timeout_is_detected()
    test_openai_compatible_network_error_raises_api_error()
    test_minimax_success_records_request_diagnostics()
    print("[PASS] api llm error tests")
