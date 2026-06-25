"""
tests/test_vector_index.py — VectorIndex 测试
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from memory.vector_index import TextChunk, VectorIndex


def _mock_encoder(texts):
    """把文本按字符编码成固定维度的 one-hot-ish 向量，用于可复现测试。"""
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


def test_add_and_search_mock():
    with tempfile.TemporaryDirectory() as tmp:
        idx = VectorIndex(
            namespace="test",
            storage_dir=Path(tmp),
            enabled=True,
            encoder=_mock_encoder,
            embedding_dim=8,
        )
        chunks = [
            TextChunk(id="a", text="hello world", source="s1", heading="H1"),
            TextChunk(id="b", text="hello python", source="s1", heading="H1"),
            TextChunk(id="c", text="faiss index", source="s2", heading="H2"),
        ]
        idx.add(chunks)
        assert len(idx) == 3

        results = idx.search("hello", top_k=2)
        assert len(results) <= 2
        ids = [c.id for _, c in results]
        assert "a" in ids or "b" in ids


def test_update_and_delete():
    with tempfile.TemporaryDirectory() as tmp:
        idx = VectorIndex(
            namespace="test",
            storage_dir=Path(tmp),
            enabled=True,
            encoder=_mock_encoder,
            embedding_dim=8,
        )
        idx.add([TextChunk(id="a", text="old text", source="s1")])
        idx.update(TextChunk(id="a", text="new shiny text", source="s1"))
        results = idx.search("shiny", top_k=1)
        assert len(results) == 1
        assert results[0][1].text == "new shiny text"

        idx.delete("a")
        assert len(idx) == 0
        results = idx.search("shiny", top_k=1)
        assert results == []


def test_persistence_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        dir_path = Path(tmp)
        idx = VectorIndex(
            namespace="test",
            storage_dir=dir_path,
            enabled=True,
            encoder=_mock_encoder,
            embedding_dim=8,
        )
        idx.add([TextChunk(id="x", text="persistent data", source="s1")])
        idx.save()

        idx2 = VectorIndex(
            namespace="test",
            storage_dir=dir_path,
            enabled=True,
            encoder=_mock_encoder,
            embedding_dim=8,
        )
        assert len(idx2) == 1
        results = idx2.search("persistent", top_k=1)
        assert len(results) == 1
        assert results[0][1].id == "x"


def test_keyword_fallback_when_disabled():
    with tempfile.TemporaryDirectory() as tmp:
        idx = VectorIndex(
            namespace="test",
            storage_dir=Path(tmp),
            enabled=False,
        )
        idx.add([TextChunk(id="k", text="keyword only", source="s1")])
        assert not idx.is_available
        results = idx.search("keyword", top_k=1)
        assert len(results) == 1
        assert results[0][1].id == "k"


def test_filter_fn():
    with tempfile.TemporaryDirectory() as tmp:
        idx = VectorIndex(
            namespace="test",
            storage_dir=Path(tmp),
            enabled=True,
            encoder=_mock_encoder,
            embedding_dim=8,
        )
        idx.add([
            TextChunk(id="a", text="alpha", source="s1", meta={"tag": "x"}),
            TextChunk(id="b", text="alpha beta", source="s1", meta={"tag": "y"}),
        ])
        results = idx.search("alpha", top_k=2, filter_fn=lambda c: c.meta.get("tag") == "y")
        assert len(results) == 1
        assert results[0][1].id == "b"


if __name__ == "__main__":
    test_add_and_search_mock()
    print("OK test_add_and_search_mock")
    test_update_and_delete()
    print("OK test_update_and_delete")
    test_persistence_roundtrip()
    print("OK test_persistence_roundtrip")
    test_keyword_fallback_when_disabled()
    print("OK test_keyword_fallback_when_disabled")
    test_filter_fn()
    print("OK test_filter_fn")
    print("\nAll vector index tests passed.")
