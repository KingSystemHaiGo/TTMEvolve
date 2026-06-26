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
from core.config import Config


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


def test_prepare_think_payload_filters_cold_recall_by_workspace_profile():
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
        manager.cold.index(
            {"id": "docs1", "type": "session_summary", "workspace_profile": "docs"},
            "README shared-profile bilingual structure",
        )
        manager.cold.index(
            {"id": "maker1", "type": "session_summary", "workspace_profile": "maker"},
            "Maker shared-profile sprite import flow",
        )

        context, stats = manager.prepare_think_payload(
            task="shared-profile README structure",
            context="当前正在整理文档",
            trajectory=[],
            tools_description="工具列表",
            max_tokens=2048,
            workspace_profile="docs",
        )

        assert "README shared-profile" in context
        assert "Maker shared-profile" not in context
        assert stats.cold_recall_hits >= 1


def test_prepare_think_payload_uses_profile_policy_top_k():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        cfg = Config()
        cfg.data = {
            "llm": {"n_ctx": 8192, "reserve_tokens": 256},
            "memory": {
                "vector_index": {
                    "enabled": False,
                    "fallback_to_keyword": True,
                    "top_k": 5,
                    "profile_policies": {
                        "docs": {"top_k": 1},
                    },
                }
            },
        }
        cfg._profiles = {}
        manager = MemoryManager(
            project_root=tmp_path / "project",
            storage_root=tmp_path / "storage",
            skills_dir=tmp_path / "skills",
            budget_manager=ContextBudgetManager(n_ctx=8192, reserve_tokens=256),
            config=cfg,
        )
        manager.cold.index(
            {"id": "docs1", "type": "session_summary", "workspace_profile": "docs"},
            "policy-topk unique-token first",
        )
        manager.cold.index(
            {"id": "docs2", "type": "session_summary", "workspace_profile": "docs"},
            "policy-topk unique-token second",
        )

        context, stats = manager.prepare_think_payload(
            task="policy-topk unique-token",
            context="当前正在整理文档",
            trajectory=[],
            tools_description="工具列表",
            max_tokens=2048,
            workspace_profile="docs",
        )

        assert stats.cold_recall_hits == 1
        assert "policy-topk unique-token first" in context
        assert "policy-topk unique-token second" not in context


if __name__ == "__main__":
    test_prepare_think_payload_includes_cold_recall()
    print("OK test_prepare_think_payload_includes_cold_recall")
    test_cold_recall_silently_fails_when_no_hits()
    print("OK test_cold_recall_silently_fails_when_no_hits")
    test_prepare_think_payload_filters_cold_recall_by_workspace_profile()
    print("OK test_prepare_think_payload_filters_cold_recall_by_workspace_profile")
    test_prepare_think_payload_uses_profile_policy_top_k()
    print("OK test_prepare_think_payload_uses_profile_policy_top_k")
    print("\nAll MemoryManager recall tests passed.")
