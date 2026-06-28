"""
tests/test_memory_graph.py - typed-edge graph memory tests.

These tests cover memory/graph.py (MemoryNode, MemoryEdge, MemoryGraph). They are
intentionally written before the implementation. The first run will fail with
ImportError; the implementation in memory/graph.py makes them pass.

Phases:
  Phase A: graph layer (this file)
  Phase B: graph retrieval (ColdMemory.retrieve_with_graph + ranking)
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from memory.graph import (  # noqa: E402
    EDGE_TYPES,
    MemoryEdge,
    MemoryGraph,
    MemoryNode,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

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


def _make_graph(tmp: Path, *, max_edges_per_node: int = 64, expand_hops: int = 1) -> MemoryGraph:
    """Build a fresh MemoryGraph rooted at tmp/graph."""
    return MemoryGraph(
        storage_path=tmp / "graph",
        vector_index=None,  # keyword/encoder fallback only
        config={
            "max_edges_per_node": max_edges_per_node,
            "expand_hops": expand_hops,
            "edge_index_enabled": False,  # keep tests deterministic
        },
        encoder=_mock_encoder,
    )


# ---------------------------------------------------------------------------
# Node CRUD
# ---------------------------------------------------------------------------

def test_graph_upsert_node_writes_to_jsonl():
    with tempfile.TemporaryDirectory() as tmp:
        graph = _make_graph(Path(tmp))
        node = MemoryNode(
            id="n-1",
            type="fact",
            summary="the sky is blue",
            workspace_profile="general",
            agent_id="default",
            visibility="private",
        )
        graph.upsert_node(node)
        path = Path(tmp) / "graph" / "cold_graph_nodes.jsonl"
        assert path.exists()
        lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert len(lines) == 1
        assert lines[0]["id"] == "n-1"
        assert lines[0]["summary"] == "the sky is blue"
        assert lines[0]["soft_deleted"] is False


def test_graph_upsert_node_is_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        graph = _make_graph(Path(tmp))
        node = MemoryNode(id="n-1", type="fact", summary="first")
        graph.upsert_node(node)
        graph.upsert_node(MemoryNode(id="n-1", type="fact", summary="second"))
        fetched = graph.get_node("n-1")
        assert fetched is not None
        assert fetched.summary == "second"


def test_graph_get_node_returns_none_for_missing():
    with tempfile.TemporaryDirectory() as tmp:
        graph = _make_graph(Path(tmp))
        assert graph.get_node("nope") is None


def test_graph_soft_delete_marks_tombstone_and_hides_node():
    with tempfile.TemporaryDirectory() as tmp:
        graph = _make_graph(Path(tmp))
        graph.upsert_node(MemoryNode(id="n-1", type="fact", summary="x"))
        graph.soft_delete_node("n-1", reason="test")
        assert graph.get_node("n-1") is None
        tomb_path = Path(tmp) / "graph" / "cold_graph_tombstones.jsonl"
        assert tomb_path.exists()
        items = [json.loads(line) for line in tomb_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert items[0]["id"] == "n-1"
        assert items[0]["reason"] == "test"


def test_graph_restore_node_brings_node_back():
    with tempfile.TemporaryDirectory() as tmp:
        graph = _make_graph(Path(tmp))
        graph.upsert_node(MemoryNode(id="n-1", type="fact", summary="x"))
        graph.soft_delete_node("n-1", reason="test")
        assert graph.get_node("n-1") is None
        graph.restore_node("n-1")
        assert graph.get_node("n-1") is not None


# ---------------------------------------------------------------------------
# Edge CRUD
# ---------------------------------------------------------------------------

def test_graph_add_edge_writes_to_jsonl():
    with tempfile.TemporaryDirectory() as tmp:
        graph = _make_graph(Path(tmp))
        graph.upsert_node(MemoryNode(id="n-1", type="fact", summary="a"))
        graph.upsert_node(MemoryNode(id="n-2", type="fact", summary="b"))
        graph.add_edge(MemoryEdge(id="e-1", src="n-1", dst="n-2", type="references"))
        path = Path(tmp) / "graph" / "cold_graph_edges.jsonl"
        assert path.exists()
        edges = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert len(edges) == 1
        assert edges[0]["type"] == "references"
        assert edges[0]["src"] == "n-1"
        assert edges[0]["dst"] == "n-2"


def test_graph_add_edge_rejects_unknown_type():
    with tempfile.TemporaryDirectory() as tmp:
        graph = _make_graph(Path(tmp))
        graph.upsert_node(MemoryNode(id="n-1", type="fact", summary="a"))
        graph.upsert_node(MemoryNode(id="n-2", type="fact", summary="b"))
        try:
            graph.add_edge(MemoryEdge(id="e-1", src="n-1", dst="n-2", type="banana"))
        except ValueError:
            return
        raise AssertionError("add_edge should reject unknown edge type")


def test_graph_neighbors_returns_typed_1hop():
    with tempfile.TemporaryDirectory() as tmp:
        graph = _make_graph(Path(tmp), expand_hops=1)
        for i in range(3):
            graph.upsert_node(MemoryNode(id=f"n-{i}", type="fact", summary=f"s{i}"))
        graph.add_edge(MemoryEdge(id="e-1", src="n-0", dst="n-1", type="references"))
        graph.add_edge(MemoryEdge(id="e-2", src="n-0", dst="n-2", type="supports"))
        graph.add_edge(MemoryEdge(id="e-3", src="n-1", dst="n-2", type="contradicts"))
        out = graph.neighbors("n-0")
        assert "n-1" in out and "n-2" in out
        # type filter narrows the result
        only_refs = graph.neighbors("n-0", edge_types={"references"})
        assert only_refs == {"n-1"}


def test_graph_neighbors_honors_max_hops_and_visited_set():
    with tempfile.TemporaryDirectory() as tmp:
        graph = _make_graph(Path(tmp), expand_hops=1)
        # Build a 3-hop chain: n-0 -> n-1 -> n-2 -> n-3
        for i in range(4):
            graph.upsert_node(MemoryNode(id=f"n-{i}", type="fact", summary=f"s{i}"))
        for i in range(3):
            graph.add_edge(MemoryEdge(id=f"e-{i}", src=f"n-{i}", dst=f"n-{i+1}", type="references"))
        # max_hops=1 should only see n-1
        one_hop = graph.neighbors("n-0", max_hops=1)
        assert one_hop == {"n-1"}
        # max_hops=2 should see n-1 and n-2
        two_hop = graph.neighbors("n-0", max_hops=2)
        assert two_hop == {"n-1", "n-2"}
        # Cycle: even with a cycle, visited set must not loop forever
        graph.add_edge(MemoryEdge(id="e-cycle", src="n-3", dst="n-0", type="references"))
        cyclic = graph.neighbors("n-0", max_hops=10)
        # All reachable in a finite graph; visited set prevents infinite recursion
        assert "n-3" in cyclic


def test_graph_max_edges_per_node_is_enforced():
    with tempfile.TemporaryDirectory() as tmp:
        graph = _make_graph(Path(tmp), max_edges_per_node=2)
        for i in range(4):
            graph.upsert_node(MemoryNode(id=f"n-{i}", type="fact", summary=f"s{i}"))
        graph.add_edge(MemoryEdge(id="e-1", src="n-0", dst="n-1", type="references"))
        graph.add_edge(MemoryEdge(id="e-2", src="n-0", dst="n-2", type="references"))
        # Third outgoing edge from n-0 should be rejected
        try:
            graph.add_edge(MemoryEdge(id="e-3", src="n-0", dst="n-3", type="references"))
        except ValueError:
            return
        raise AssertionError("add_edge should enforce max_edges_per_node")


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def test_graph_reload_round_trips_nodes_and_edges():
    with tempfile.TemporaryDirectory() as tmp:
        graph = _make_graph(Path(tmp))
        graph.upsert_node(MemoryNode(id="n-1", type="fact", summary="a"))
        graph.upsert_node(MemoryNode(id="n-2", type="fact", summary="b"))
        graph.add_edge(MemoryEdge(id="e-1", src="n-1", dst="n-2", type="references"))
        # Reload from the same path
        graph2 = _make_graph(Path(tmp))
        assert graph2.get_node("n-1") is not None
        assert graph2.get_node("n-2") is not None
        assert "n-2" in graph2.neighbors("n-1")


def test_graph_meta_file_records_counts():
    with tempfile.TemporaryDirectory() as tmp:
        graph = _make_graph(Path(tmp))
        graph.upsert_node(MemoryNode(id="n-1", type="fact", summary="a"))
        graph.upsert_node(MemoryNode(id="n-2", type="fact", summary="b"))
        graph.add_edge(MemoryEdge(id="e-1", src="n-1", dst="n-2", type="references"))
        meta_path = Path(tmp) / "graph" / "cold_graph_meta.json"
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["node_count"] == 2
        assert meta["edge_count"] == 1


# ---------------------------------------------------------------------------
# Retrieval (Phase A baseline: keyword fallback; vector ranking later)
# ---------------------------------------------------------------------------

def test_graph_retrieve_returns_ranked_candidates():
    with tempfile.TemporaryDirectory() as tmp:
        graph = _make_graph(Path(tmp))
        graph.upsert_node(MemoryNode(id="n-1", type="fact", summary="alpha bravo"))
        graph.upsert_node(MemoryNode(id="n-2", type="fact", summary="charlie delta"))
        graph.upsert_node(MemoryNode(id="n-3", type="fact", summary="alpha charlie"))
        results = graph.retrieve(query="alpha", top_k=5)
        ids = [r["id"] for r in results]
        # Both alpha-containing nodes should appear; n-2 (no "alpha") should not
        assert "n-1" in ids
        assert "n-3" in ids
        assert "n-2" not in ids


def test_graph_retrieve_filters_soft_deleted():
    with tempfile.TemporaryDirectory() as tmp:
        graph = _make_graph(Path(tmp))
        graph.upsert_node(MemoryNode(id="n-1", type="fact", summary="alpha"))
        graph.upsert_node(MemoryNode(id="n-2", type="fact", summary="alpha"))
        graph.soft_delete_node("n-1", reason="stale")
        results = graph.retrieve(query="alpha", top_k=5)
        ids = [r["id"] for r in results]
        assert "n-1" not in ids
        assert "n-2" in ids


# ---------------------------------------------------------------------------
# Edge-type allowlist sanity
# ---------------------------------------------------------------------------

def test_edge_types_allowlist_matches_plan():
    assert EDGE_TYPES == {
        "references", "supersedes", "contradicts", "supports",
        "caused_by", "temporal_next", "decomposes_into", "similar_to",
    }


# ---------------------------------------------------------------------------
# Backward compatibility: disabled-by-default in config
# ---------------------------------------------------------------------------

def test_graph_init_does_not_change_public_vector_index_api():
    """ADR-0004 rule: do not change the public VectorIndex API.

    MemoryGraph must accept vector_index=None and fall back to its own
    encoder + keyword search. VectorIndex is only consulted when an
    external instance is injected.
    """
    with tempfile.TemporaryDirectory() as tmp:
        graph = MemoryGraph(
            storage_path=Path(tmp) / "graph",
            vector_index=None,
            config={"edge_index_enabled": False},
            encoder=_mock_encoder,
        )
        assert graph is not None
        # Empty graph returns empty list
        assert graph.retrieve(query="anything", top_k=3) == []
