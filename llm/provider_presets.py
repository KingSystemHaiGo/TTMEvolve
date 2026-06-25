"""Built-in LLM provider presets for the desktop GUI.

The normal path is API-first. Local GGUF remains available as an explicit
experimental provider, but it is not selected implicitly by the GUI presets.
"""

from __future__ import annotations

from typing import Dict, List


OPENAI_COMPATIBLE_ALIASES = {
    "api",
    "openai",
    "deepseek",
    "openrouter",
    "qwen",
    "dashscope",
    "zhipu",
    "glm",
    "moonshot",
    "kimi",
    "siliconflow",
}


PROVIDER_PRESETS: List[Dict[str, str]] = [
    {
        "id": "deepseek",
        "label": "DeepSeek",
        "kind": "openai-compatible",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-pro",
        "env_var": "DEEPSEEK_API_KEY",
    },
    {
        "id": "openai",
        "label": "OpenAI",
        "kind": "openai-compatible",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4.1",
        "env_var": "OPENAI_API_KEY",
    },
    {
        "id": "openrouter",
        "label": "OpenRouter",
        "kind": "openai-compatible",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "openai/gpt-4.1",
        "env_var": "OPENROUTER_API_KEY",
    },
    {
        "id": "qwen",
        "label": "通义千问 DashScope",
        "kind": "openai-compatible",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-max",
        "env_var": "DASHSCOPE_API_KEY",
    },
    {
        "id": "zhipu",
        "label": "智谱 GLM",
        "kind": "openai-compatible",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-plus",
        "env_var": "ZHIPU_API_KEY",
    },
    {
        "id": "moonshot",
        "label": "Moonshot/Kimi",
        "kind": "openai-compatible",
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
        "env_var": "MOONSHOT_API_KEY",
    },
    {
        "id": "siliconflow",
        "label": "SiliconFlow",
        "kind": "openai-compatible",
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "deepseek-ai/DeepSeek-V3",
        "env_var": "SILICONFLOW_API_KEY",
    },
    {
        "id": "minimax",
        "label": "MiniMax",
        "kind": "minimax",
        "base_url": "https://api.minimax.chat/v1",
        "model": "MiniMax-M1",
        "env_var": "MINIMAX_API_KEY",
    },
    {
        "id": "claude",
        "label": "Anthropic Claude",
        "kind": "anthropic",
        "base_url": "https://api.anthropic.com/v1",
        "model": "claude-sonnet-4-5-20250929",
        "env_var": "ANTHROPIC_API_KEY",
    },
    {
        "id": "local",
        "label": "Local GGUF (experimental)",
        "kind": "local",
        "base_url": "",
        "model": "MiniCPM5-1B-Q4_K_M",
        "env_var": "",
    },
]


PROVIDER_MODEL_HINTS: Dict[str, List[str]] = {
    "deepseek": ["deepseek-v4-pro", "deepseek-v4-flash"],
    "openai": ["gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini"],
    "openrouter": [
        "openai/gpt-4.1",
        "anthropic/claude-sonnet-4.5",
        "deepseek/deepseek-chat",
        "google/gemini-2.5-pro",
    ],
    "qwen": ["qwen-max", "qwen-plus", "qwen-turbo", "qwen-long"],
    "dashscope": ["qwen-max", "qwen-plus", "qwen-turbo", "qwen-long"],
    "zhipu": ["glm-4-plus", "glm-4-air", "glm-4-flash"],
    "glm": ["glm-4-plus", "glm-4-air", "glm-4-flash"],
    "moonshot": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
    "kimi": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
    "siliconflow": ["deepseek-ai/DeepSeek-V3", "deepseek-ai/DeepSeek-R1", "Qwen/Qwen2.5-72B-Instruct"],
    "minimax": ["MiniMax-M1", "MiniMax-Text-01"],
    "claude": ["claude-sonnet-4-5-20250929", "claude-opus-4-1-20250805", "claude-haiku-3-5-20241022"],
    "anthropic": ["claude-sonnet-4-5-20250929", "claude-opus-4-1-20250805", "claude-haiku-3-5-20241022"],
    "local": ["MiniCPM5-1B-Q4_K_M"],
}


def provider_preset(provider: str) -> Dict[str, str]:
    normalized = (provider or "").lower().strip()
    for preset in PROVIDER_PRESETS:
        if preset["id"] == normalized:
            return dict(preset)
    return {
        "id": normalized or "api",
        "label": normalized or "Custom OpenAI-compatible API",
        "kind": "openai-compatible",
        "base_url": "",
        "model": "",
        "env_var": "LLM_API_KEY",
    }


def model_hints(provider: str) -> List[str]:
    normalized = (provider or "").lower().strip()
    preset = provider_preset(normalized)
    hints = list(PROVIDER_MODEL_HINTS.get(normalized, []))
    default_model = preset.get("model", "")
    if default_model and default_model not in hints:
        hints.insert(0, default_model)
    return hints
