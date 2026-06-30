"""Generic OpenAI-compatible chat completions client."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional, Sequence
from urllib import request
from urllib.error import HTTPError, URLError

from core.config import Config
from llm.api_errors import LLMAPIError, LLMTimeoutError, failure_stats, is_timeout_error, timeout_message
from llm.content import (
    ContentBlock,
    ImageBlock,
    TextBlock,
    to_openai_messages,
)
from llm.interface import LLMInterface
from llm.provider_presets import provider_preset
from llm.utils import parse_llm_json


DEFAULT_API_BASE = "https://api.deepseek.com"
DEFAULT_API_MODEL = "deepseek-v4-pro"


class OpenAILLM(LLMInterface):
    """OpenAI-compatible LLM implementation used by most API providers."""

    supports_multimodal = True

    def __init__(self, config: Optional[Config] = None):
        self.cfg = config or Config()
        llm_cfg = self.cfg.llm_config()
        provider = self.cfg.llm_provider()
        preset = provider_preset(provider)
        env_var = preset.get("env_var") or "LLM_API_KEY"
        api_keys = llm_cfg.get("api_keys") or {}

        self.provider = provider
        self.api_key = (
            api_keys.get(provider)
            or llm_cfg.get("api_key")
            or os.getenv(env_var, "")
            or os.getenv("LLM_API_KEY", "")
        ).strip()
        self.base_url = (llm_cfg.get("base_url") or preset.get("base_url") or DEFAULT_API_BASE).rstrip("/")
        self.model = llm_cfg.get("model") or preset.get("model") or DEFAULT_API_MODEL
        self.timeout = self.cfg.get("llm.timeout", 45)
        self._last_call_stats: Dict[str, Any] = {}

        if not self.api_key or self.api_key.startswith("sk-..."):
            raise ValueError(
                f"{preset.get('label', provider)} needs an API key. "
                f"Set llm.api_key in the GUI or export {env_var}/LLM_API_KEY."
            )

    def _call(
        self,
        system: str,
        messages: List[Dict[str, Any]],
        max_tokens: int = 1024,
        temperature: float = 0.2,
        content_blocks: Optional[List[ContentBlock]] = None,
    ) -> str:
        if content_blocks is not None:
            # Replace the trailing user message with a list-typed content
            # carrying both text framing and image blocks.
            serialized: List[Dict[str, Any]] = []
            for raw in messages:
                content = raw.get("content")
                if isinstance(content, list):
                    serialized.append({"role": raw.get("role", "user"), "content": content})
                else:
                    serialized.append({
                        "role": raw.get("role", "user"),
                        "content": [{"type": "text", "text": str(content or "")}],
                    })
            serialized.append({
                "role": "user",
                "content": to_openai_messages(content_blocks),
            })
            messages = serialized
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        start = time.perf_counter()
        endpoint = f"{self.base_url}/chat/completions"
        req = request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
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
            self._last_call_stats.update({"endpoint": endpoint, "http_status": e.code})
            raise RuntimeError(f"{self.provider} API request failed: HTTP {e.code} {error_body}") from e
        except (TimeoutError, URLError, OSError) as e:
            elapsed_ms = (time.perf_counter() - start) * 1000
            if is_timeout_error(e):
                self._last_call_stats = failure_stats(
                    provider=self.provider,
                    model=self.model,
                    elapsed_ms=elapsed_ms,
                    error_type="timeout",
                    error=e,
                )
                self._last_call_stats.update({"endpoint": endpoint})
                raise LLMTimeoutError(timeout_message(self.provider, self.timeout, elapsed_ms)) from e
            self._last_call_stats = failure_stats(
                provider=self.provider,
                model=self.model,
                elapsed_ms=elapsed_ms,
                error_type="network_error",
                error=e,
            )
            self._last_call_stats.update({"endpoint": endpoint})
            raise LLMAPIError(f"{self.provider} API request failed: {e}") from e
        elapsed_ms = (time.perf_counter() - start) * 1000
        data = json.loads(raw)
        usage = data.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or prompt_tokens + completion_tokens)
        tokens_per_sec = completion_tokens / (elapsed_ms / 1000) if elapsed_ms > 0 else 0.0
        self._last_call_stats = {
            "provider": self.provider,
            "model": self.model,
            "mode": "api",
            "endpoint": endpoint,
            "http_status": 200,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "generate_ms": round(elapsed_ms, 1),
            "tokens_per_sec": round(tokens_per_sec, 2),
        }

        choices = data.get("choices", [])
        first_choice = choices[0] if choices else {}
        message = first_choice.get("message") or {}
        content = message.get("content", "")
        reasoning_content = message.get("reasoning_content", "")
        if not isinstance(content, str):
            content = ""
        if not isinstance(reasoning_content, str):
            reasoning_content = ""
        self._last_call_stats.update({
            "choices_count": len(choices),
            "finish_reason": first_choice.get("finish_reason", ""),
            "message_keys": sorted(message.keys()),
            "content_length": len(content),
            "reasoning_content_length": len(reasoning_content),
        })
        if not choices:
            return ""
        return content

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

    def think_multimodal(
        self,
        task: str,
        content: Sequence[ContentBlock],
        trajectory: List[Dict[str, Any]],
        tools_description: str,
        *,
        attachments: Optional[List[ImageBlock]] = None,
    ) -> str:
        """OpenAI-format multimodal think. The trailing user message is
        a list of content blocks; images come last so the model can map
        them to the text framing."""
        system = "你是一个为 TapTap Maker 游戏开发而生的 Agent。请用中文思考。可以看图片。"
        merged: List[ContentBlock] = []
        framing_lines: List[str] = []
        if trajectory:
            last = trajectory[-1]
            framing_lines.append(
                f"上一步：{last.get('action')}\n观察：{last.get('observation')}"
            )
        if tools_description:
            framing_lines.append(tools_description)
        if framing_lines:
            merged.append(TextBlock("\n\n".join(framing_lines)))
        for block in content:
            merged.append(block)
        for image in attachments or []:
            merged.append(image)
        if not any(isinstance(b, TextBlock) and b.text for b in merged):
            merged.append(TextBlock("请思考下一步。"))
        return self._call(system, [], content_blocks=merged)

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
