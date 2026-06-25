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


if __name__ == "__main__":
    test_vector_search()
    print("OK test_vector_search")
    test_rebuild_from_json()
    print("OK test_rebuild_from_json")
    test_keyword_fallback_when_disabled()
    print("OK test_keyword_fallback_when_disabled")
    print("\nAll ColdMemory vector tests passed.")
