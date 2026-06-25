"""
tests/test_memory_manager_recall.py — MemoryManager 冷记忆召回注入测试
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from memory.manager import MemoryManager
from llm.context_budget import ContextBudgetManager


def _mock_encoder(texts):
    dim = 8
    vectors = []
    for text in texts:
        vec = np.zeros(dim, dtype=np.float32)
        for ch in text.lower():
            vec[ord(ch) % dim] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        vectors.append(vec)
    return np.array(vectors, dtype=np.float32)


def test_prepare_think_payload_includes_cold_recall():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        manager = MemoryManager(
            project_root=tmp_path / "project",
            storage_root=tmp_path / "storage",
            skills_dir=tmp_path / "skills",
            budget_manager=ContextBudgetManager(n_ctx=8192, reserve_tokens=256),
        )
        # 替换冷记忆的 encoder 为 mock
        manager.cold = manager.cold.__class__(
            manager.cold.storage_path,
            vector_index_config={"enabled": True, "embedding_dim": 8},
            encoder=_mock_encoder,
        )
        manager.cold.index(
            {"id": "s1", "type": "session_summary"},
            "如何实现角色跳跃物理",
        )

        context, stats = manager.prepare_think_payload(
            task="角色跳跃物理",
            context="当前在实现平台跳跃",
            trajectory=[],
            tools_description="工具列表",
            max_tokens=2048,
        )
        assert "【历史归档】" in context
        assert "角色跳跃" in context


def test_cold_recall_silently_fails_when_no_hits():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        manager = MemoryManager(
            project_root=tmp_path / "project",
            storage_root=tmp_path / "storage",
            skills_dir=tmp_path / "skills",
            budget_manager=ContextBudgetManager(n_ctx=8192, reserve_tokens=256),
        )
        manager.cold = manager.cold.__class__(
            manager.cold.storage_path,
            vector_index_config={"enabled": True, "embedding_dim": 8},
            encoder=_mock_encoder,
        )

        context, stats = manager.prepare_think_payload(
            task="完全不相关的话题",
            context="当前上下文",
            trajectory=[],
            tools_description="工具列表",
            max_tokens=2048,
        )
        assert "【历史归档】" not in context


if __name__ == "__main__":
    test_prepare_think_payload_includes_cold_recall()
    print("OK test_prepare_think_payload_includes_cold_recall")
    test_cold_recall_silently_fails_when_no_hits()
    print("OK test_cold_recall_silently_fails_when_no_hits")
    print("\nAll MemoryManager recall tests passed.")
