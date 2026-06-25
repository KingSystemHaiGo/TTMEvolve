from __future__ import annotations

from core.config import Config
from llm.llama_tuning import resolve_llama_tuning


def _config(llm: dict) -> Config:
    cfg = Config()
    cfg.data = {"llm": llm}
    cfg._profiles = {}
    return cfg


def test_resolve_llama_tuning_cpu_auto_is_bounded():
    tuning = resolve_llama_tuning(
        _config({
            "n_ctx": 4096,
            "n_gpu_layers": "auto",
            "n_batch": 8192,
            "n_ubatch": 2048,
            "n_threads": "auto",
            "n_threads_batch": "auto",
        })
    )

    assert tuning.n_ctx == 4096
    assert tuning.n_batch == 4096
    assert tuning.n_ubatch <= tuning.n_batch
    assert tuning.n_threads >= 1
    assert tuning.n_threads_batch >= tuning.n_threads
    assert tuning.n_gpu_layers in (-1, 0)


def test_resolve_llama_tuning_normalizes_large_gpu_layers():
    tuning = resolve_llama_tuning(
        _config({
            "n_ctx": 8192,
            "n_gpu_layers": 1000,
        })
    )

    assert tuning.n_gpu_layers == -1
    assert "n_gpu_layers>999 normalized to -1/all" in tuning.notes
