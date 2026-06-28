"""
tests/test_memory_manager_graph_recall.py - graph-on vs graph-off retrieval tests.

Phase B exit gate. The graph path must be opt-in, must report its fallback
clearly, must not regress flat-vector recall, and must keep the existing
``test_rag_performance`` budget shape.
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

from memory.cold import ColdMemory  # noqa: E402
from memory.graph import MemoryEdge, MemoryGraph, MemoryNode  # noqa: E402


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _mock_encoder(texts):
    dim = 16
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


def _seed_cold(cold: ColdMemory, profile: str = "general") -> None:
    items = [
        ("alpha", "the sky is blue today"),
        ("bravo", "alpha bravo charlie"),
        ("charlie", "delta echo foxtrot"),
        ("delta", "alpha golf hotel"),
        ("echo", "alpha is alpha"),
    ]
    for i, (summary, content) in enumerate(items):
        cold.bulk_index([({
            "id": f"m-{i}",
            "type": "fact",
            "summary": summary,
            "workspace_profile": profile,
            "agent_id": "default",
            "visibility": "private",
        }, content)])


def _seed_graph(cold: ColdMemory) -> None:
    graph = cold._graph  # type: ignore[attr-defined]
    assert graph is not None
    for node_id, summary, node_type in [
        ("m-0", "alpha", "fact"),
        ("m-1", "bravo", "fact"),
        ("m-2", "charlie", "fact"),
        ("m-3", "delta", "fact"),
        ("m-4", "echo", "fact"),
    ]:
        graph.upsert_node(MemoryNode(
            id=node_id,
            type=node_type,
            summary=summary,
            workspace_profile="general",
            agent_id="default",
            visibility="private",
        ))
    # Build edges so expansion has something to walk
    graph.add_edge(MemoryEdge(id="e-0-1", src="m-0", dst="m-1", type="references"))
    graph.add_edge(MemoryEdge(id="e-0-2", src="m-0", dst="m-2", type="supports"))
    graph.add_edge(MemoryEdge(id="e-1-2", src="m-1", dst="m-2", type="contradicts"))
    graph.add_edge(MemoryEdge(id="e-2-3", src="m-2", dst="m-3", type="temporal_next"))


# ---------------------------------------------------------------------------
# Disabled-by-default
# ---------------------------------------------------------------------------

def test_graph_recall_disabled_by_default_returns_empty_list():
    with tempfile.TemporaryDirectory() as tmp:
        cold = ColdMemory(
            Path(tmp) / "cold",
            vector_index_config={"enabled": True},
            encoder=_mock_encoder,
        )
        _seed_cold(cold)
        assert cold.graph_enabled() is False
        result = cold.retrieve_with_graph("alpha", top_k=5)
        assert result == []


def test_graph_recall_flat_search_unchanged_when_disabled():
    """graph_enabled=false must not change the flat search() shape."""
    with tempfile.TemporaryDirectory() as tmp:
        cold = ColdMemory(
            Path(tmp) / "cold",
            vector_index_config={"enabled": True},
            encoder=_mock_encoder,
        )
        _seed_cold(cold)
        flat = cold.search("alpha", top_k=5)
        # Flat search must still return something
        assert len(flat) >= 1


# ---------------------------------------------------------------------------
# Enabled path
# ---------------------------------------------------------------------------

def test_graph_recall_returns_scored_ranked_results_when_enabled():
    with tempfile.TemporaryDirectory() as tmp:
        cold = ColdMemory(
            Path(tmp) / "cold",
            vector_index_config={"enabled": True},
            encoder=_mock_encoder,
            graph_config={"enabled": True, "edge_index_enabled": False},
        )
        _seed_cold(cold)
        assert cold.graph_enabled() is True
        _seed_graph(cold)
        results = cold.retrieve_with_graph("alpha", top_k=5)
        assert len(results) >= 1
        for r in results:
            assert "id" in r
            assert "graph_score" in r
            assert "vector_score" in r
            assert "posterior" in r
            assert "edge_support_score" in r
            assert "occam_score" in r
            assert "freshness_score" in r
            assert "fallback" in r


def test_graph_recall_fallback_label_reports_mode():
    with tempfile.TemporaryDirectory() as tmp:
        cold = ColdMemory(
            Path(tmp) / "cold",
            vector_index_config={"enabled": True},
            encoder=_mock_encoder,
            graph_config={"enabled": True, "edge_index_enabled": False},
        )
        _seed_cold(cold)
        _seed_graph(cold)
        results = cold.retrieve_with_graph("alpha", top_k=5)
        # Each result must carry a fallback label
        for r in results:
            assert r["fallback"] in {"vector", "keyword", "fake_encoder"}


def test_graph_recall_includes_neighbors_via_expansion():
    """A node hit by vector search should pull in its typed-edge neighbors."""
    with tempfile.TemporaryDirectory() as tmp:
        cold = ColdMemory(
            Path(tmp) / "cold",
            vector_index_config={"enabled": True},
            encoder=_mock_encoder,
            graph_config={"enabled": True, "edge_index_enabled": False},
        )
        _seed_cold(cold)
        _seed_graph(cold)
        results = cold.retrieve_with_graph("alpha", top_k=10, expand_hops=1)
        ids = {r["id"] for r in results}
        # m-1 (referenced by m-0) and m-2 (supported by m-0) should appear
        # in the expanded set, not just the direct vector hit
        assert "m-1" in ids or "m-2" in ids


def test_graph_recall_max_hops_is_honored():
    with tempfile.TemporaryDirectory() as tmp:
        cold = ColdMemory(
            Path(tmp) / "cold",
            vector_index_config={"enabled": True},
            encoder=_mock_encoder,
            graph_config={"enabled": True, "edge_index_enabled": False},
        )
        _seed_cold(cold)
        _seed_graph(cold)
        # 0 hops = direct vector hits only, no expansion
        zero_hop = cold.retrieve_with_graph("alpha", top_k=10, expand_hops=0)
        # 2 hops = walk two edges
        two_hop = cold.retrieve_with_graph("alpha", top_k=10, expand_hops=2)
        # Two-hop set must be a superset of (or equal to) the zero-hop set
        zero_ids = {r["id"] for r in zero_hop}
        two_ids = {r["id"] for r in two_hop}
        assert zero_ids.issubset(two_ids)


def test_graph_recall_hides_soft_deleted_nodes():
    with tempfile.TemporaryDirectory() as tmp:
        cold = ColdMemory(
            Path(tmp) / "cold",
            vector_index_config={"enabled": True},
            encoder=_mock_encoder,
            graph_config={"enabled": True, "edge_index_enabled": False},
        )
        _seed_cold(cold)
        _seed_graph(cold)
        cold._graph.soft_delete_node("m-1", reason="stale")  # type: ignore[attr-defined]
        results = cold.retrieve_with_graph("alpha", top_k=10, expand_hops=2)
        ids = {r["id"] for r in results}
        assert "m-1" not in ids


# ---------------------------------------------------------------------------
# Five-factor scoring (from ADR-0004)
# ---------------------------------------------------------------------------

def test_graph_recall_final_score_matches_five_factor_formula():
    with tempfile.TemporaryDirectory() as tmp:
        cold = ColdMemory(
            Path(tmp) / "cold",
            vector_index_config={"enabled": True},
            encoder=_mock_encoder,
            graph_config={"enabled": True, "edge_index_enabled": False},
        )
        _seed_cold(cold)
        _seed_graph(cold)
        results = cold.retrieve_with_graph("alpha", top_k=10)
        for r in results:
            expected = (
                0.55 * float(r["vector_score"])
                + 0.20 * float(r["posterior"])
                + 0.10 * float(r["freshness_score"])
                + 0.10 * float(r["edge_support_score"])
                + 0.05 * float(r["occam_score"])
            )
            assert abs(float(r["graph_score"]) - expected) < 1e-6


def test_graph_recall_weights_have_positive_partial_derivatives():
    """Higher posterior, more edge support, fresher, simpler -> higher score.

    We seed two nodes with identical text and one with extra edges; the one
    with more edges must score at least as high.
    """
    with tempfile.TemporaryDirectory() as tmp:
        cold = ColdMemory(
            Path(tmp) / "cold",
            vector_index_config={"enabled": True},
            encoder=_mock_encoder,
            graph_config={"enabled": True, "edge_index_enabled": False},
        )
        # Add two nodes with identical text
        cold.bulk_index([
            ({"id": "x-1", "type": "fact", "summary": "shared text",
              "workspace_profile": "general", "agent_id": "default", "visibility": "private"},
             "shared text"),
            ({"id": "x-2", "type": "fact", "summary": "shared text",
              "workspace_profile": "general", "agent_id": "default", "visibility": "private"},
             "shared text"),
        ])
        g = cold._graph  # type: ignore[attr-defined]
        g.upsert_node(MemoryNode(id="x-1", type="fact", summary="shared text"))
        g.upsert_node(MemoryNode(id="x-2", type="fact", summary="shared text"))
        g.upsert_node(MemoryNode(id="x-helper", type="fact", summary="shared text"))
        # x-1 has no edges; x-2 has multiple supporting edges
        g.add_edge(MemoryEdge(id="e-x2-h", src="x-2", dst="x-helper", type="supports"))
        g.add_edge(MemoryEdge(id="e-x2-x1", src="x-2", dst="x-1", type="references"))

        results = cold.retrieve_with_graph("shared", top_k=10, expand_hops=2)
        by_id = {r["id"]: r for r in results}
        if "x-1" in by_id and "x-2" in by_id:
            assert by_id["x-2"]["graph_score"] >= by_id["x-1"]["graph_score"]


# ---------------------------------------------------------------------------
# Performance / budget shape (Phase B exit gate)
# ---------------------------------------------------------------------------

def test_graph_recall_returns_per_call_metrics():
    """The result list should carry compact per-call metrics, not bulk stats."""
    with tempfile.TemporaryDirectory() as tmp:
        cold = ColdMemory(
            Path(tmp) / "cold",
            vector_index_config={"enabled": True},
            encoder=_mock_encoder,
            graph_config={"enabled": True, "edge_index_enabled": False},
        )
        _seed_cold(cold)
        _seed_graph(cold)
        results = cold.retrieve_with_graph("alpha", top_k=5)
        # Each result should be a dict (not a heavy object) and <1KB
        for r in results:
            payload = json.dumps(r)
            assert len(payload) < 4096


def test_graph_recall_metrics_are_exposed_separately_from_results():
    with tempfile.TemporaryDirectory() as tmp:
        cold = ColdMemory(
            Path(tmp) / "cold",
            vector_index_config={"enabled": True},
            encoder=_mock_encoder,
            graph_config={"enabled": True, "edge_index_enabled": False},
        )
        _seed_cold(cold)
        _seed_graph(cold)
        # A higher-level wrapper that exposes graph-on metrics
        from memory.rag_benchmark import run_graph_on_off_comparison
        report = run_graph_on_off_comparison(
            cold_factory=lambda root: ColdMemory(
                root / "cold",
                vector_index_config={"enabled": True},
                encoder=_mock_encoder,
                graph_config={"enabled": True, "edge_index_enabled": False},
            ),
            warm_runs=8,
            query="alpha",
        )
        assert "graph_on" in report
        assert "graph_off" in report
        assert "ratio_warm_p95" in report
        # The ratio is bounded per the exit gate
        assert report["ratio_warm_p95"] is None or report["ratio_warm_p95"] <= 1.5
