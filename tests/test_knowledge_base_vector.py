"""
tests/test_knowledge_base_vector.py — KnowledgeBase 向量后端测试
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from learning.knowledge_base import KnowledgeBase


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
        kb = KnowledgeBase(
            Path(tmp),
            vector_index_config={"enabled": True, "embedding_dim": 8},
            encoder=_mock_encoder,
        )
        kb.store({
            "domain": "ui",
            "rule": "按钮点击后必须播放音效",
            "context": "主菜单和设置界面都适用",
            "tags": ["ui", "audio"],
        })
        kb.store({
            "domain": "ai",
            "rule": "敌人到达巡逻点需等待 2 秒",
            "context": "巡逻状态机逻辑",
            "tags": ["ai", "patrol"],
        })

        hits = kb.search("按钮音效", top_k=2)
        assert len(hits) >= 1
        domains = {h["domain"] for h in hits}
        assert "ui" in domains


def test_source_filter():
    with tempfile.TemporaryDirectory() as tmp:
        kb = KnowledgeBase(
            Path(tmp),
            vector_index_config={"enabled": True, "embedding_dim": 8},
            encoder=_mock_encoder,
        )
        kb.store({
            "domain": "ui",
            "rule": "规则 A",
            "context": "上下文 A",
            "tags": ["expert_rescue"],
            "source_session": "sess-abc",
        })
        kb.store({
            "domain": "ai",
            "rule": "规则 B",
            "context": "上下文 B",
            "tags": ["ai"],
            "source_session": "sess-xyz",
        })

        hits = kb.search("规则", top_k=5, source_filter="expert_rescue")
        assert len(hits) == 1
        assert hits[0]["domain"] == "ui"

        hits2 = kb.search("规则", top_k=5, source_filter="sess-xyz")
        assert len(hits2) == 1
        assert hits2[0]["domain"] == "ai"


def test_keyword_fallback_when_disabled():
    with tempfile.TemporaryDirectory() as tmp:
        kb = KnowledgeBase(
            Path(tmp),
            vector_index_config={"enabled": False, "fallback_to_keyword": True},
            encoder=_mock_encoder,
        )
        kb.store({
            "domain": "general",
            "rule": "关键词兜底规则",
            "context": "测试",
            "tags": ["fallback"],
        })
        hits = kb.search("兜底", top_k=1)
        assert len(hits) == 1
        assert hits[0]["rule"] == "关键词兜底规则"


if __name__ == "__main__":
    test_vector_search()
    print("OK test_vector_search")
    test_source_filter()
    print("OK test_source_filter")
    test_keyword_fallback_when_disabled()
    print("OK test_keyword_fallback_when_disabled")
    print("\nAll KnowledgeBase vector tests passed.")
