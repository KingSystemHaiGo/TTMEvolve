"""
tests/test_vector_index.py — VectorIndex 测试
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

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


def test_reverse_id_map_roundtrip_and_delete():
    with tempfile.TemporaryDirectory() as tmp:
        dir_path = Path(tmp)
        idx = VectorIndex(
            namespace="test",
            storage_dir=dir_path,
            enabled=True,
            encoder=_mock_encoder,
            embedding_dim=8,
        )
        idx.add([
            TextChunk(id="a", text="alpha memory", source="s1"),
            TextChunk(id="b", text="beta memory", source="s1"),
        ])
        if not idx.is_available:
            pytest.skip("FAISS is unavailable; reverse map persistence is only used by vector search.")
        assert idx._reverse_id_map == {internal: cid for cid, internal in idx._id_map.items()}

        idx2 = VectorIndex(
            namespace="test",
            storage_dir=dir_path,
            enabled=True,
            encoder=_mock_encoder,
            embedding_dim=8,
        )
        assert idx2._reverse_id_map == {internal: cid for cid, internal in idx2._id_map.items()}

        removed_internal = idx2._id_map["a"]
        idx2.delete("a")
        assert "a" not in idx2._id_map
        assert removed_internal not in idx2._reverse_id_map

        idx2.clear()
        assert idx2._id_map == {}
        assert idx2._reverse_id_map == {}


def test_batch_add_allocates_unique_internal_ids():
    with tempfile.TemporaryDirectory() as tmp:
        idx = VectorIndex(
            namespace="test",
            storage_dir=Path(tmp),
            enabled=True,
            encoder=_mock_encoder,
            embedding_dim=8,
        )
        idx.add([
            TextChunk(id=f"chunk-{i}", text=f"batch memory {i}", source="s1")
            for i in range(40)
        ])
        if not idx.is_available:
            pytest.skip("FAISS is unavailable; batch internal ids are only allocated for vector search.")

        assert len(idx._id_map) == 40
        assert len(set(idx._id_map.values())) == 40
        assert len(idx._reverse_id_map) == 40


def test_faiss_search_uses_reverse_id_map_fast_path():
    class FakeIndex:
        ntotal = 2

        def search(self, _qvec, _top_k):
            return (
                np.array([[0.99, 0.88]], dtype=np.float32),
                np.array([[101, 202]], dtype=np.int64),
            )

    class NoLinearScanDict(dict):
        def items(self):  # pragma: no cover - failure path proves the fast path is used.
            raise AssertionError("search should not linearly scan _id_map.items()")

    with tempfile.TemporaryDirectory() as tmp:
        idx = VectorIndex(
            namespace="test",
            storage_dir=Path(tmp),
            enabled=True,
            encoder=_mock_encoder,
            embedding_dim=8,
        )
        idx._enabled = True
        idx._faiss_available = True
        idx._st_available = True
        idx._index = FakeIndex()
        idx._chunks = {
            "chunk-a": TextChunk(id="chunk-a", text="vector-only alpha", source="s1"),
            "chunk-b": TextChunk(id="chunk-b", text="vector-only beta", source="s1"),
        }
        idx._id_map = NoLinearScanDict({"chunk-a": 101, "chunk-b": 202})
        idx._reverse_id_map = {101: "chunk-a", 202: "chunk-b"}

        results = idx.search("zzzz", top_k=2)

        assert [chunk.id for _, chunk in results] == ["chunk-a", "chunk-b"]


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
    test_reverse_id_map_roundtrip_and_delete()
    print("OK test_reverse_id_map_roundtrip_and_delete")
    test_batch_add_allocates_unique_internal_ids()
    print("OK test_batch_add_allocates_unique_internal_ids")
    test_faiss_search_uses_reverse_id_map_fast_path()
    print("OK test_faiss_search_uses_reverse_id_map_fast_path")
    print("\nAll vector index tests passed.")
