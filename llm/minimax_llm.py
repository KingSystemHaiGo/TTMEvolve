"""MiniMax ChatCompletion v2 client."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional
from urllib import request
from urllib.error import HTTPError, URLError

from core.config import Config
from llm.api_errors import LLMAPIError, LLMTimeoutError, failure_stats, is_timeout_error, timeout_message
from llm.interface import LLMInterface
from llm.provider_presets import provider_preset
from llm.utils import parse_llm_json


class MiniMaxLLM(LLMInterface):
    """MiniMax API implementation.

    MiniMax's common ChatCompletion v2 route is not the same as the OpenAI
    `/chat/completions` path, so it gets a dedicated client.
    """

    def __init__(self, config: Optional[Config] = None):
        self.cfg = config or Config()
        llm_cfg = self.cfg.llm_config()
        preset = provider_preset("minimax")
        api_keys = llm_cfg.get("api_keys") or {}
        self.provider = "minimax"
        self.api_key = (
            api_keys.get("minimax")
            or llm_cfg.get("api_key")
            or os.getenv("MINIMAX_API_KEY", "")
            or os.getenv("LLM_API_KEY", "")
        ).strip()
        self.model = llm_cfg.get("model") or preset["model"]
        self.base_url = (llm_cfg.get("base_url") or preset["base_url"]).rstrip("/")
        self.timeout = self.cfg.get("llm.timeout", 45)
        self._last_call_stats: Dict[str, Any] = {}

        if not self.api_key or self.api_key.startswith("sk-..."):
            raise ValueError("MiniMax needs an API key. Set llm.api_key in the GUI or export MINIMAX_API_KEY.")

    def _call(
        self,
        system: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "tokens_to_generate": max_tokens,
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        start = time.perf_counter()
        response_started_at: Optional[float] = None
        endpoint = f"{self.base_url}/text/chatcompletion_v2"
        req = request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                response_started_at = time.perf_counter()
                raw = response.read().decode("utf-8")
        except HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            elapsed_ms = (time.perf_counter() - start) * 1000
            self._last_call_stats = failure_stats(
                provider=self.provider,
                model=self.model,
                elapsed_ms=elapsed_ms,
                error_type="http_error",
                error=e,
            )
            self._last_call_stats.update({
                "endpoint": endpoint,
                "http_status": e.code,
                "response_started": response_started_at is not None,
            })
            raise RuntimeError(f"MiniMax API request failed: HTTP {e.code} {error_body}") from e
        except (TimeoutError, URLError, OSError) as e:
            elapsed_ms = (time.perf_counter() - start) * 1000
            base_failure = {
                "endpoint": endpoint,
                "response_started": response_started_at is not None,
            }
            if response_started_at is not None:
                base_failure["time_to_headers_ms"] = round((response_started_at - start) * 1000, 1)
                base_failure["body_read_ms"] = round((time.perf_counter() - response_started_at) * 1000, 1)
            if is_timeout_error(e):
                self._last_call_stats = failure_stats(
                    provider=self.provider,
                    model=self.model,
                    elapsed_ms=elapsed_ms,
                    error_type="timeout",
                    error=e,
                )
                self._last_call_stats.update(base_failure)
                raise LLMTimeoutError(timeout_message("MiniMax", self.timeout, elapsed_ms)) from e
            self._last_call_stats = failure_stats(
                provider=self.provider,
                model=self.model,
                elapsed_ms=elapsed_ms,
                error_type="network_error",
                error=e,
            )
            self._last_call_stats.update(base_failure)
            raise LLMAPIError(f"MiniMax API request failed: {e}") from e
        elapsed_ms = (time.perf_counter() - start) * 1000
        data = json.loads(raw)
        usage = data.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or usage.get("total_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or prompt_tokens + completion_tokens)
        cached_tokens = 0
        if isinstance(usage.get("prompt_tokens_details"), dict):
            cached_tokens = int(usage["prompt_tokens_details"].get("cached_tokens") or 0)
        tokens_per_sec = completion_tokens / (elapsed_ms / 1000) if elapsed_ms > 0 else 0.0
        first_choice = (data.get("choices") or [{}])[0] if isinstance(data.get("choices"), list) else {}
        message = first_choice.get("message") or {}
        base_resp = data.get("base_resp") or {}
        self._last_call_stats = {
            "provider": self.provider,
            "model": self.model,
            "mode": "api",
            "endpoint": endpoint,
            "http_status": 200,
            "request_id": data.get("id", ""),
            "base_resp_status_code": base_resp.get("status_code"),
            "base_resp_status_msg": base_resp.get("status_msg", ""),
            "finish_reason": first_choice.get("finish_reason", ""),
            "response_started": response_started_at is not None,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cached_tokens": cached_tokens,
            "has_reasoning_content": bool(message.get("reasoning_content")),
            "reasoning_details_count": len(message.get("reasoning_details") or []),
            "time_to_headers_ms": round((response_started_at - start) * 1000, 1) if response_started_at else None,
            "body_read_ms": round((time.perf_counter() - response_started_at) * 1000, 1) if response_started_at else None,
            "generate_ms": round(elapsed_ms, 1),
            "tokens_per_sec": round(tokens_per_sec, 2),
        }

        if base_resp and base_resp.get("status_code") not in (0, None):
            raise LLMAPIError(f"MiniMax API returned base_resp error: {base_resp}")

        if isinstance(data.get("reply"), str):
            return data["reply"]
        choices = data.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            if isinstance(message.get("content"), str):
                return message["content"]
            if isinstance(choices[0].get("text"), str):
                return choices[0]["text"]
        return ""

    def last_call_stats(self) -> Dict[str, Any]:
        return dict(self._last_call_stats)

    def think(
        self,
        task: str,
        context: str,
        trajectory: List[Dict[str, Any]],
        tools_description: str,
    ) -> str:
        system = "你是一个为 TapTap Maker 游戏开发而生的 Agent。请用中文思考，逐步推理。"
        if not trajectory and not tools_description:
            messages = [{"role": "user", "content": context}]
        else:
            messages = [{"role": "user", "content": f"{context}\n\n{tools_description}\n\n请思考下一步。"}]
            if trajectory:
                last = trajectory[-1]
                messages.append({
                    "role": "user",
                    "content": f"上一步：{last.get('action')}\n观察：{last.get('observation')}",
                })
        return self._call(system, messages)

    def choose_action(
        self,
        task: str,
        thought: str,
        tools_description: str,
    ) -> Dict[str, Any]:
        system = (
            "You are an action router for a TapTap Maker coding agent. "
            "Output exactly one valid JSON object, no Markdown and no prose. "
            "Use one of these formats only: "
            '{"tool":"tool_name","params":{...}} or {"done":true,"output":"final answer"}. '
            "Pick tool_name only from the candidate tool list."
        )
        messages = [{
            "role": "user",
            "content": f"Task: {task}\nThought: {thought}\n\n{tools_description}\n\nAction JSON:",
        }]
        raw = self._call(system, messages, temperature=0.1, max_tokens=1024)
        action = parse_llm_json(raw, fallback_done=False)
        if not action.get("_parse_error"):
            return action

        repaired = self._call(
            "Repair malformed action output. Return valid JSON only.",
            [{
                "role": "user",
                "content": (
                    "Convert this text to one valid action JSON object.\n"
                    'Valid: {"tool":"tool_name","params":{}} or {"done":true,"output":"final answer"}\n\n'
                    f"{raw}"
                ),
            }],
            temperature=0.0,
            max_tokens=256,
        )
        return parse_llm_json(repaired, fallback_done=False)

    def reflect(self, prompt: str) -> str:
        system = "你是一个反思引擎。请从经验中提炼规则。"
        return self._call(system, [{"role": "user", "content": prompt}], max_tokens=2048)

    def generate_code(self, prompt: str) -> str:
        system = "你是一个代码生成器。只输出代码，不要解释。"
        return self._call(system, [{"role": "user", "content": prompt}], max_tokens=2048, temperature=0.1)
