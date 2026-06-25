"""Adaptive llama.cpp parameter selection.

The goal is correctness first, then predictable performance. Values in
config.json always win; "auto" or missing values are resolved from host
capabilities and the installed llama-cpp-python build.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class LlamaTuning:
    n_ctx: int
    n_batch: int
    n_ubatch: int
    n_threads: int
    n_threads_batch: int
    n_gpu_layers: int
    offload_kqv: bool
    flash_attn: bool
    use_mmap: bool
    use_mlock: bool
    notes: tuple[str, ...]

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _int_or_none(value: Any) -> Optional[int]:
    if value is None or value == "auto":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bool_or_default(value: Any, default: bool) -> bool:
    if value is None or value == "auto":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _supports_gpu_offload() -> bool:
    try:
        import llama_cpp  # type: ignore

        checker = getattr(llama_cpp, "llama_supports_gpu_offload", None)
        return bool(checker()) if checker else False
    except Exception:
        return False


def resolve_llama_tuning(config: Any) -> LlamaTuning:
    logical_cpus = max(1, os.cpu_count() or 1)
    notes: list[str] = [f"logical_cpus={logical_cpus}"]

    n_ctx = _int_or_none(config.get("llm.n_ctx", None)) or 8192
    if n_ctx <= 0:
        # llama.cpp accepts n_ctx=0 as "from model", but this app needs a known
        # budget for prompt fitting and UI display.
        n_ctx = 8192
        notes.append("n_ctx reset to 8192 for deterministic budget management")

    default_decode_threads = max(1, min(8, logical_cpus // 2 or 1))
    default_batch_threads = max(default_decode_threads, logical_cpus)
    n_threads = _int_or_none(config.get("llm.n_threads", None)) or default_decode_threads
    n_threads_batch = (
        _int_or_none(config.get("llm.n_threads_batch", None))
        or default_batch_threads
    )

    requested_batch = _int_or_none(config.get("llm.n_batch", None)) or min(1024, n_ctx)
    n_batch = max(1, min(n_ctx, requested_batch))
    requested_ubatch = _int_or_none(config.get("llm.n_ubatch", None)) or min(512, n_batch)
    n_ubatch = max(1, min(n_batch, requested_ubatch))

    gpu_supported = _supports_gpu_offload()
    raw_gpu_layers = config.get("llm.n_gpu_layers", "auto")
    if raw_gpu_layers == "auto" or raw_gpu_layers is None:
        n_gpu_layers = -1 if gpu_supported else 0
        notes.append(
            "gpu_offload=enabled" if gpu_supported else "gpu_offload=unavailable"
        )
    else:
        n_gpu_layers = _int_or_none(raw_gpu_layers)
        if n_gpu_layers is None:
            n_gpu_layers = 0
            notes.append("invalid n_gpu_layers reset to 0")
        elif n_gpu_layers > 999:
            n_gpu_layers = -1
            notes.append("n_gpu_layers>999 normalized to -1/all")

    has_gpu_layers = n_gpu_layers != 0
    offload_kqv = _bool_or_default(config.get("llm.offload_kqv", None), has_gpu_layers)
    flash_attn = _bool_or_default(config.get("llm.flash_attn", None), False)
    if flash_attn and not has_gpu_layers:
        flash_attn = False
        notes.append("flash_attn disabled because GPU offload is not active")

    return LlamaTuning(
        n_ctx=n_ctx,
        n_batch=n_batch,
        n_ubatch=n_ubatch,
        n_threads=max(1, n_threads),
        n_threads_batch=max(1, n_threads_batch),
        n_gpu_layers=n_gpu_layers,
        offload_kqv=offload_kqv,
        flash_attn=flash_attn,
        use_mmap=_bool_or_default(config.get("llm.use_mmap", None), True),
        use_mlock=_bool_or_default(config.get("llm.use_mlock", None), False),
        notes=tuple(notes),
    )
