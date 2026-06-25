# API-first LLM runtime

## Decision

TTMEvolve now treats remote/API LLMs as the primary agent runtime. The local
GGUF/llama.cpp path stays available as `local`, but it is explicit and
experimental rather than the default execution path.

## Why

The desktop agent needs stable reasoning, tool-call JSON, token usage reporting,
and predictable latency. The current local GGUF path can load and generate, but
it is too slow and too brittle for the main Maker development loop. API providers
give a better baseline while the local runtime is improved separately.

## Runtime flow

1. GUI loads `/llm/providers` and `/config`.
2. User selects provider, model, base URL, and API key in the Agent panel.
3. `POST /config/llm` persists the choice and updates the in-memory agent LLM.
4. `POST /sessions` sends the active provider override for that task.
5. `AppServer.run_session()` applies the runtime config before calling
   `agent.run()`.
6. `TapMakerAgent.set_llm()` swaps every component that holds an LLM reference:
   agent, ReAct loop, memory manager, reflection engine, and skill generator.

## Built-in providers

The GUI presets live in `llm/provider_presets.py`.

- DeepSeek: `https://api.deepseek.com`, `deepseek-v4-pro`
- OpenAI: `https://api.openai.com/v1`, `gpt-4.1`
- OpenRouter: `https://openrouter.ai/api/v1`, `openai/gpt-4.1`
- DashScope/Qwen: `https://dashscope.aliyuncs.com/compatible-mode/v1`, `qwen-max`
- Zhipu GLM: `https://open.bigmodel.cn/api/paas/v4`, `glm-4-plus`
- Moonshot/Kimi: `https://api.moonshot.cn/v1`, `moonshot-v1-8k`
- SiliconFlow: `https://api.siliconflow.cn/v1`, `deepseek-ai/DeepSeek-V3`
- MiniMax: `https://api.minimax.chat/v1`, `MiniMax-M1`
- Anthropic Claude: `https://api.anthropic.com/v1`, `claude-sonnet-4-5-20250929`
- Local GGUF: explicit experimental fallback

OpenAI-compatible providers share `OpenAILLM`; Claude uses `ClaudeLLM`; MiniMax
uses `MiniMaxLLM` because its ChatCompletion v2 route is provider-specific. API
implementations use Python standard library HTTP calls, so the desktop runtime
does not depend on optional SDK packages.

## Key handling

API keys are stored per provider in `llm.api_keys`. A legacy `llm.api_key` is
migrated to the previously active provider when the runtime config is applied.
Switching provider without entering a matching key no longer leaks the previous
provider key into the new provider.

If an API provider is selected without a usable key, the server uses
`UnconfiguredLLM`. It is not a mock model: it never fabricates responses. It only
lets the GUI boot and fails task execution with a clear configuration error.

## Token usage

API clients record `last_call_stats()` from provider response usage fields and
elapsed request time. `ReActLoop` emits `llm_usage` events after the thinking and
action-selection calls, and the GUI aggregates them in the token meter.

## Local runtime position

`local` still uses the llama.cpp tuning path documented in
`docs/architecture/llama-cpp-tuning.md`. It should not be treated as the default
agent brain until prompt size, tool JSON reliability, and generation speed are
good enough for normal Maker work.
