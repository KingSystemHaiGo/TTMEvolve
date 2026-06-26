"""
tests/test_cold_memory_vector.py — ColdMemory 向量后端测试
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from memory.cold import ColdMemory


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


def test_vector_search():
    with tempfile.TemporaryDirectory() as tmp:
        cold = ColdMemory(
            Path(tmp),
            vector_index_config={"enabled": True, "embedding_dim": 8},
            encoder=_mock_encoder,
        )
        cold.index({"id": "s1", "type": "session_summary"}, "如何创建角色控制器")
        cold.index({"id": "s2", "type": "session_summary"}, "游戏主菜单 UI 设计")
        cold.index({"id": "s3", "type": "session_summary"}, "敌人 AI 巡逻逻辑")

        hits = cold.search("角色控制", top_k=2)
        assert len(hits) >= 1
        ids = {h["id"] for h in hits}
        assert "s1" in ids


def test_rebuild_from_json():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        cold = ColdMemory(
            tmp_path,
            vector_index_config={"enabled": True, "embedding_dim": 8},
            encoder=_mock_encoder,
        )
        cold.index({"id": "s1", "type": "session_summary"}, "角色移动控制")

        # 删除向量索引文件，保留 JSON
        vector_dir = tmp_path / "cold_memory"
        for f in vector_dir.glob("*"):
            f.unlink()

        cold2 = ColdMemory(
            tmp_path,
            vector_index_config={"enabled": True, "embedding_dim": 8},
            encoder=_mock_encoder,
        )
        hits = cold2.search("角色移动", top_k=1)
        assert len(hits) == 1
        assert hits[0]["id"] == "s1"


def test_keyword_fallback_when_disabled():
    with tempfile.TemporaryDirectory() as tmp:
        cold = ColdMemory(
            Path(tmp),
            vector_index_config={"enabled": False, "fallback_to_keyword": True},
            encoder=_mock_encoder,
        )
        cold.index({"id": "s1", "type": "session_summary"}, "关键词匹配兜底")
        hits = cold.search("关键词", top_k=1)
        assert len(hits) == 1
        assert hits[0]["id"] == "s1"


def test_search_filters_by_workspace_profile_with_general_memory():
    with tempfile.TemporaryDirectory() as tmp:
        cold = ColdMemory(
            Path(tmp),
            vector_index_config={"enabled": True, "embedding_dim": 8},
            encoder=_mock_encoder,
        )
        cold.index(
            {"id": "docs1", "type": "session_summary", "workspace_profile": "docs"},
            "README alpha shared design notes",
        )
        cold.index(
            {"id": "maker1", "type": "session_summary", "workspace_profile": "maker"},
            "Maker alpha shared scene build notes",
        )
        cold.index(
            {"id": "general1", "type": "session_summary", "workspace_profile": "general"},
            "Shared alpha cross-project lesson",
        )

        hits = cold.search("alpha shared", top_k=5, workspace_profile="docs")
        ids = {hit["id"] for hit in hits}

        assert "docs1" in ids
        assert "general1" in ids
        assert "maker1" not in ids


def test_profile_search_falls_back_when_no_profile_hits():
    with tempfile.TemporaryDirectory() as tmp:
        cold = ColdMemory(
            Path(tmp),
            vector_index_config={"enabled": True, "embedding_dim": 8},
            encoder=_mock_encoder,
        )
        cold.index(
            {"id": "maker1", "type": "session_summary", "workspace_profile": "maker"},
            "fallback-only particle emitter lesson",
        )

        hits = cold.search("fallback-only", top_k=3, workspace_profile="docs")

        assert [hit["id"] for hit in hits] == ["maker1"]


def test_keyword_fallback_respects_workspace_profile_then_global_fallback():
    with tempfile.TemporaryDirectory() as tmp:
        cold = ColdMemory(
            Path(tmp),
            vector_index_config={"enabled": False, "fallback_to_keyword": True},
            encoder=_mock_encoder,
        )
        cold.index(
            {"id": "docs1", "type": "session_summary", "workspace_profile": "docs"},
            "keyword-profile checklist",
        )
        cold.index(
            {"id": "maker1", "type": "session_summary", "workspace_profile": "maker"},
            "keyword-profile prefab",
        )

        docs_hits = cold.search("keyword-profile", top_k=5, workspace_profile="docs")
        fallback_hits = cold.search("prefab", top_k=5, workspace_profile="docs")

        assert [hit["id"] for hit in docs_hits] == ["docs1"]
        assert [hit["id"] for hit in fallback_hits] == ["maker1"]


def test_profile_policy_can_exclude_general_and_disable_global_fallback():
    with tempfile.TemporaryDirectory() as tmp:
        cold = ColdMemory(
            Path(tmp),
            vector_index_config={
                "enabled": True,
                "embedding_dim": 8,
                "profile_policies": {
                    "docs": {"include_general": False, "allow_fallback": False, "top_k": 4},
                },
            },
            encoder=_mock_encoder,
        )
        cold.index(
            {"id": "general1", "type": "session_summary", "workspace_profile": "general"},
            "policy-only shared lesson",
        )
        cold.index(
            {"id": "maker1", "type": "session_summary", "workspace_profile": "maker"},
            "maker-only sprite policy lesson",
        )

        assert cold.profile_policy("docs", top_k=2)["top_k"] == 4
        assert cold.search("policy-only", top_k=2, workspace_profile="docs") == []
        assert cold.search("maker-only", top_k=2, workspace_profile="docs") == []


def test_profile_policy_overrides_top_k():
    with tempfile.TemporaryDirectory() as tmp:
        cold = ColdMemory(
            Path(tmp),
            vector_index_config={
                "enabled": False,
                "fallback_to_keyword": True,
                "profile_policies": {
                    "coding": {"top_k": 2},
                },
            },
            encoder=_mock_encoder,
        )
        for index in range(4):
            cold.index(
                {"id": f"coding{index}", "type": "session_summary", "workspace_profile": "coding"},
                "bounded-policy recall shared-key",
            )

        hits = cold.search("shared-key", top_k=5, workspace_profile="coding")

        assert len(hits) == 2


if __name__ == "__main__":
    test_vector_search()
    print("OK test_vector_search")
    test_rebuild_from_json()
    print("OK test_rebuild_from_json")
    test_keyword_fallback_when_disabled()
    print("OK test_keyword_fallback_when_disabled")
    test_search_filters_by_workspace_profile_with_general_memory()
    print("OK test_search_filters_by_workspace_profile_with_general_memory")
    test_profile_search_falls_back_when_no_profile_hits()
    print("OK test_profile_search_falls_back_when_no_profile_hits")
    test_keyword_fallback_respects_workspace_profile_then_global_fallback()
    print("OK test_keyword_fallback_respects_workspace_profile_then_global_fallback")
    test_profile_policy_can_exclude_general_and_disable_global_fallback()
    print("OK test_profile_policy_can_exclude_general_and_disable_global_fallback")
    test_profile_policy_overrides_top_k()
    print("OK test_profile_policy_overrides_top_k")
    print("\nAll ColdMemory vector tests passed.")
