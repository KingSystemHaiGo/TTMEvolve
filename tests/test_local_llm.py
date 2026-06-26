"""
tests/test_local_llm.py — 本地模型底座冒烟测试

验证 LocalLLM 可被工厂创建，并对已下载模型执行 think/generate_code。
模型未下载时自动跳过。

新增 MockLlama 测试：
- KV cache 复用时只传入 user 部分
- ContextBudgetManager 被调用并产生预算统计
"""

from __future__ import annotations
import os
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.config import Config
from llm.llm_factory import LLMFactory

try:
    from llm.local_llm import LocalLLM
    from llama_cpp import Llama as _RealLlama
    _LLAMA_AVAILABLE = True
except Exception:
    _LLAMA_AVAILABLE = False
    # Allow mock-based tests to run without the real llama-cpp-python package.
    import llm.local_llm as _local_llm_module
    _local_llm_module.Llama = None  # patched below after MockLlama is defined


class MockLlama:
    """模拟 llama-cpp-python 的 Llama 对象，用于无模型测试。"""

    def __init__(self):
        self.calls: list = []
        self._state = b"mock_state_v1"

    def tokenize(self, text: bytes, add_bos: bool = True) -> list:
        # One token per byte, deterministic and easy to reason about.
        return list(range(len(text)))

    def save_state(self) -> bytes:
        return self._state

    def load_state(self, state: bytes) -> None:
        self._state = state

    def __call__(self, prompt: str, max_tokens: int = 16, **kwargs) -> dict:
        self.calls.append(prompt)
        return {"choices": [{"text": "mock output"}]}


# Patch the module-level Llama placeholder so LocalLLM can be instantiated
# with a mock model even when llama-cpp-python is not installed.
if not _LLAMA_AVAILABLE:
    _local_llm_module.Llama = MockLlama


def _make_mock_local_llm(tmp_dir: Path) -> LocalLLM:
    model_file = tmp_dir / "mock.gguf"
    model_file.write_text("", encoding="utf-8")
    cfg = Config()
    cfg.data = {
        "llm": {
            "model_path": str(model_file),
            "n_ctx": 1024,
            "reserve_tokens": 64,
            "max_history_steps": 6,
            "turn_cache_max_entries": 0,
            "compression": {"enable_kv_cache": True},
        }
    }
    cfg._profiles = {}
    llm = LocalLLM(cfg)
    llm._model = MockLlama()
    return llm


def test_local_llm_smoke():
    if os.environ.get("TTMEVOLVE_RUN_REAL_LOCAL_LLM") != "1":
        pytest.skip("set TTMEVOLVE_RUN_REAL_LOCAL_LLM=1 to run the real GGUF smoke")

    if not _LLAMA_AVAILABLE:
        pytest.skip("llama-cpp-python 未安装")

    config = Config(str(_PROJECT_ROOT / "config.json"))
    model_path = config.local_model_path()

    if not model_path.exists():
        pytest.skip(f"本地模型未找到 {model_path}，运行 python scripts/download_model.py 下载")

    try:
        llm = LLMFactory.create("local", config)
    except ImportError as e:
        pytest.skip(f"无法创建 LocalLLM：{e}")

    thought = llm.think(
        task="列出项目文件",
        context="任务：列出项目文件\n请使用可用工具逐步完成。",
        trajectory=[],
        tools_description="list_directory: 列出目录内容",
    )
    assert isinstance(thought, str) and len(thought) > 0, "think() 返回为空"
    print("✅ think() 正常")

    code = llm.generate_code("编写一个函数 run(input: str) -> dict，返回 {ok: True, output: input}")
    assert isinstance(code, str) and "def run(" in code, "generate_code() 未生成 run 函数"
    print("✅ generate_code() 正常")

    action = llm.choose_action(
        task="列出项目文件",
        thought="我应该先列出目录",
        tools_description="list_directory: 列出目录内容",
    )
    assert isinstance(action, dict), "choose_action() 未返回 dict"
    print(f"✅ choose_action() 返回: {action}")

    print("✅ 本地模型底座冒烟测试通过")


def test_kv_cache_reuse_passes_user_only():
    tmp_dir = _PROJECT_ROOT / "storage" / "tmp_test_local_llm"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    llm = _make_mock_local_llm(tmp_dir)

    system = "你是 TapMaker Agent"
    user = "列出项目文件"

    # First call caches the system state.
    llm._call(system, user, max_tokens=16, enable_thinking=False)
    first_prompt = llm._model.calls[0]
    assert first_prompt.startswith("<|im_start|>system")

    # Second call should load_state and continue from user tokens only.
    llm._call(system, user, max_tokens=16, enable_thinking=False)
    second_prompt = llm._model.calls[1]
    assert not second_prompt.startswith("<|im_start|>system")
    assert len(second_prompt) < len(first_prompt)
    # The user role marker should still be present in the continuation.
    assert "<|im_start|>user" in second_prompt

    print("[PASS] test_kv_cache_reuse_passes_user_only")


def test_turn_cache_reuses_full_prompt():
    tmp_dir = _PROJECT_ROOT / "storage" / "tmp_test_local_llm"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    llm = _make_mock_local_llm(tmp_dir)
    llm._turn_cache_max_entries = 2  # enable turn cache for this test

    system = "你是 TapMaker Agent"
    user = "列出项目文件"

    llm._call(system, user, max_tokens=16, enable_thinking=False)
    first_prompt = llm._model.calls[0]

    llm._call(system, user, max_tokens=16, enable_thinking=False)
    second_prompt = llm._model.calls[1]

    # Turn cache hit passes empty prompt because KV state already contains full prompt.
    assert second_prompt == ""

    print("[PASS] test_turn_cache_reuses_full_prompt")


def test_budget_manager_tracks_stats():
    tmp_dir = _PROJECT_ROOT / "storage" / "tmp_test_local_llm"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    llm = _make_mock_local_llm(tmp_dir)

    llm._call("system", "user input", max_tokens=16, enable_thinking=False)
    stats = llm.last_budget_stats()
    assert stats is not None
    assert stats.token_count > 0
    assert stats.n_ctx == 1024
    assert 0.0 <= stats.token_usage_ratio <= 1.0

    print("[PASS] test_budget_manager_tracks_stats")


def test_budget_manager_truncates_long_user():
    tmp_dir = _PROJECT_ROOT / "storage" / "tmp_test_local_llm"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    llm = _make_mock_local_llm(tmp_dir)

    # n_ctx=1024, reserve=64, max_tokens=16 => budget for system+user = 944 tokens.
    # Each char is one token in MockLlama.tokenize. system is short, so user can
    # be ~900 chars. Build a string that exceeds budget to trigger truncation.
    long_user = "A" * 500 + "Z" * 500  # 1000 chars
    llm._call("system", long_user, max_tokens=16, enable_thinking=False)
    stats = llm.last_budget_stats()
    # token_count should not exceed the allowed budget.
    assert stats.token_count <= 1024 - 64
    # The tail (Z's) should survive because truncation drops from the top.
    assert "Z" in llm._model.calls[0]

    print("[PASS] test_budget_manager_truncates_long_user")


if __name__ == "__main__":
    test_local_llm_smoke()
    test_kv_cache_reuse_passes_user_only()
    test_turn_cache_reuses_full_prompt()
    test_budget_manager_tracks_stats()
    test_budget_manager_truncates_long_user()
    print("\nAll local_llm tests passed.")
