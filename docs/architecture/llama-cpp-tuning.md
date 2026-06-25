# llama.cpp Tuning Notes

Date: 2026-06-22

## What Changed

TTMEvolve now resolves llama.cpp parameters through `llm/llama_tuning.py` instead of passing magic numbers directly from `config.json`.

Resolved values are exposed through `/health.llm_params`, so the GUI can show the actual runtime state instead of only the requested config.

## Current Machine Result

Current `/health` result after restart:

- `logical_cpus=12`
- `gpu_offload=unavailable`
- `n_ctx=8192`
- `n_batch=1024`
- `n_ubatch=512`
- `n_threads=6`
- `n_threads_batch=12`
- `n_gpu_layers=0`
- `offload_kqv=false`
- `flash_attn=false`
- `kv_cache=false`

This means the current runtime is CPU-only. The previous `n_gpu_layers=999` was misleading because it implied aggressive GPU offload even when the installed llama.cpp build does not support it.

## Rules

- Config values win when explicitly set.
- `"auto"` means resolve from installed llama-cpp-python capabilities.
- `n_gpu_layers="auto"` resolves to `-1` only when GPU offload is supported; otherwise it resolves to `0`.
- `n_batch` is clamped to `n_ctx`.
- `n_ubatch` is clamped to `n_batch`.
- `n_threads` defaults to a conservative decode-thread count.
- `n_threads_batch` defaults to all logical CPUs for prompt processing.
- KV cache remains disabled until a correct pre-generation state strategy is implemented.

## Sources

- llama-cpp-python API reference: https://llama-cpp-python.readthedocs.io/en/latest/api-reference/
- llama.cpp upstream project: https://github.com/ggml-org/llama.cpp

## Next Step

The remaining bottleneck is not only llama.cpp parameters. A smoke call used thousands of prompt tokens for a trivial task. TTMEvolve needs a lightweight local-agent prompt path:

- short intent classifier
- constrained JSON tool choice
- small curated tool list
- route heavy planning to remote/expert models when local throughput is poor
