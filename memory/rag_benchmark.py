"""Deterministic RAG benchmark for TTMEvolve memory evidence.

The benchmark uses a tiny fake FAISS module and deterministic embeddings so it
can run without network/model dependencies. It is a control gate for the memory
pipeline, not a claim about production embedding quality.
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Iterator, List, Optional

import numpy as np

from memory.cold import ColdMemory


RAG_BENCHMARK_VERSION = "rag-benchmark.v1"
EMBEDDING_QUALITY_BOUNDARY_VERSION = "embedding-quality-boundary.v1"
DEFAULT_RAG_BENCHMARK_SIZE = 10_000
DEFAULT_RAG_BENCHMARK_WARM_RUNS = 24
DEFAULT_RAG_BENCHMARK_BUDGETS = {
    "build_ms": 2000.0,
    "cold_start_ms": 500.0,
    "first_recall_ms": 75.0,
    "warm_recall_p95_ms": 50.0,
    "profile_hit_rate": 1.0,
    "fallback_hit_rate": 1.0,
}

PRODUCTION_EMBEDDING_QUALITY_REQUIREMENTS = [
    "configured production embedding model or local embedding artifact",
    "labelled evaluation corpus or golden query set",
    "semantic recall metric such as recall@k, precision@k, or MRR",
    "sample count greater than zero",
]

_FAKE_FAISS_LOCK = threading.RLock()


def deterministic_benchmark_encoder(texts: List[str]) -> np.ndarray:
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


@contextmanager
def install_fake_faiss() -> Iterator[None]:
    previous = sys.modules.get("faiss")
    had_previous = "faiss" in sys.modules
    with _FAKE_FAISS_LOCK:
        sys.modules["faiss"] = _fake_faiss_module()
        try:
            yield
        finally:
            if had_previous:
                sys.modules["faiss"] = previous  # type: ignore[assignment]
            else:
                sys.modules.pop("faiss", None)


def run_rag_benchmark(
    *,
    storage_dir: Optional[Path] = None,
    record_count: int = DEFAULT_RAG_BENCHMARK_SIZE,
    warm_runs: int = DEFAULT_RAG_BENCHMARK_WARM_RUNS,
    budgets: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    budgets = dict(DEFAULT_RAG_BENCHMARK_BUDGETS if budgets is None else budgets)
    record_count = max(1, int(record_count))
    warm_runs = max(1, int(warm_runs))
    with install_fake_faiss():
        if storage_dir is not None:
            storage_dir = Path(storage_dir)
            storage_dir.mkdir(parents=True, exist_ok=True)
            return _run_rag_benchmark_in_dir(storage_dir, record_count=record_count, warm_runs=warm_runs, budgets=budgets)
        with tempfile.TemporaryDirectory(prefix="ttm-rag-bench-") as tmp:
            return _run_rag_benchmark_in_dir(Path(tmp), record_count=record_count, warm_runs=warm_runs, budgets=budgets)


def compact_rag_benchmark_report(
    report: Optional[Dict[str, Any]],
    quality_evaluation: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not isinstance(report, dict) or not report:
        quality = production_embedding_quality_boundary(quality_evaluation, deterministic_report=None)
        return {
            "status": "not_run",
            "version": RAG_BENCHMARK_VERSION,
            "endpoint": "/memory/rag-benchmark",
            "note": "Run GET /memory/rag-benchmark?force=true to produce a deterministic local report.",
            "embedding_quality": quality,
            "closure_gate": _rag_closure_gate(None, quality),
        }
    metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
    quality = production_embedding_quality_boundary(
        quality_evaluation
        if isinstance(quality_evaluation, dict)
        else report.get("embedding_quality") if isinstance(report.get("embedding_quality"), dict) else None,
        deterministic_report=report,
    )
    return {
        "status": report.get("status") or "unknown",
        "version": report.get("version") or RAG_BENCHMARK_VERSION,
        "budget_status": report.get("budget_status"),
        "endpoint": "/memory/rag-benchmark",
        "record_count": (report.get("config") or {}).get("record_count")
            if isinstance(report.get("config"), dict)
            else None,
        "metrics": {
            "build_ms": metrics.get("build_ms"),
            "cold_start_ms": metrics.get("cold_start_ms"),
            "first_recall_ms": metrics.get("first_recall_ms"),
            "warm_recall_p95_ms": metrics.get("warm_recall_p95_ms"),
            "profile_hit_rate": metrics.get("profile_hit_rate"),
            "fallback_hit_rate": metrics.get("fallback_hit_rate"),
        },
        "embedding_quality": quality,
        "closure_gate": _rag_closure_gate(report, quality),
        "truthfulness": report.get("truthfulness"),
    }


def attach_embedding_quality(
    report: Dict[str, Any],
    quality_evaluation: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Attach production embedding quality claim gates to a benchmark report."""
    next_report = dict(report)
    quality = production_embedding_quality_boundary(quality_evaluation, deterministic_report=next_report)
    next_report["embedding_quality"] = quality
    next_report["closure_gate"] = _rag_closure_gate(next_report, quality)
    return next_report


def production_embedding_quality_boundary(
    evaluation: Optional[Dict[str, Any]] = None,
    *,
    deterministic_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return the claim boundary for production embedding semantic quality.

    The deterministic benchmark proves local pipeline speed only. Production
    embedding quality needs a real embedding model plus a labelled corpus/golden
    query evaluation before TTMEvolve can make semantic recall claims.
    """
    evaluation = evaluation if isinstance(evaluation, dict) else {}
    if evaluation.get("version") == EMBEDDING_QUALITY_BOUNDARY_VERSION:
        boundary = dict(evaluation)
        boundary.setdefault("required_evidence", list(PRODUCTION_EMBEDDING_QUALITY_REQUIREMENTS))
        boundary.setdefault("can_claim_production_embedding_quality", False)
        boundary.setdefault("can_claim_semantic_recall_quality", False)
        boundary.setdefault("current_evidence", _embedding_quality_current_evidence(deterministic_report, {}))
        return boundary

    metrics = evaluation.get("metrics") if isinstance(evaluation.get("metrics"), dict) else {}
    quality_metric_keys = [
        key
        for key in ("recall_at_k", "recall_at_5", "precision_at_k", "precision_at_5", "mrr")
        if isinstance(metrics.get(key), (int, float))
    ]
    sample_count = _safe_positive_int(
        evaluation.get("sample_count")
        or evaluation.get("query_count")
        or evaluation.get("golden_query_count")
    )
    production_encoder = bool(evaluation.get("production_encoder") or evaluation.get("embedding_model"))
    labelled_corpus = bool(
        evaluation.get("labelled_corpus")
        or evaluation.get("corpus_id")
        or evaluation.get("golden_set_id")
    )
    if "passed" in evaluation:
        passed = evaluation.get("passed") is True
    else:
        passed = str(evaluation.get("status") or "").lower() in {"ready", "pass", "passed"}
    can_claim = production_encoder and labelled_corpus and bool(quality_metric_keys) and sample_count > 0 and passed
    return {
        "version": EMBEDDING_QUALITY_BOUNDARY_VERSION,
        "status": "ready" if can_claim else "unproven",
        "scope": "production_embedding_quality",
        "coverage": "production_embedding_quality_evaluated" if can_claim else "deterministic_pipeline_only",
        "can_claim_production_embedding_quality": can_claim,
        "can_claim_semantic_recall_quality": can_claim,
        "reason": (
            "Production embedding quality evaluation passed."
            if can_claim
            else "No production embedding model plus labelled corpus quality evaluation has been run."
        ),
        "required_evidence": list(PRODUCTION_EMBEDDING_QUALITY_REQUIREMENTS),
        "current_evidence": _embedding_quality_current_evidence(
            deterministic_report,
            {
                "production_encoder": production_encoder,
                "labelled_corpus": labelled_corpus,
                "quality_metrics": quality_metric_keys,
                "sample_count": sample_count,
            },
        ),
    }


def _run_rag_benchmark_in_dir(
    storage_dir: Path,
    *,
    record_count: int,
    warm_runs: int,
    budgets: Dict[str, float],
) -> Dict[str, Any]:
    config = {
        "enabled": True,
        "embedding_dim": 16,
        "fallback_to_keyword": True,
        "profile_policies": {
            "browser": {"include_general": False, "allow_fallback": True},
        },
    }
    cold = ColdMemory(storage_dir, vector_index_config=config, encoder=deterministic_benchmark_encoder)

    started = time.perf_counter()
    indexed_count = cold.bulk_index(_benchmark_items(record_count))
    build_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    reloaded = ColdMemory(storage_dir, vector_index_config=config, encoder=deterministic_benchmark_encoder)
    cold_start_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    first_hits = reloaded.search("alpha recall benchmark", top_k=8, workspace_profile="maker")
    first_recall_ms = (time.perf_counter() - started) * 1000

    warm_times = []
    warm_hits = []
    for _ in range(warm_runs):
        started = time.perf_counter()
        warm_hits = reloaded.search("alpha recall benchmark", top_k=8, workspace_profile="maker")
        warm_times.append((time.perf_counter() - started) * 1000)

    fallback_hits = reloaded.search("docs-only fallback-signal", top_k=3, workspace_profile="browser")
    allowed_profiles = {"maker", "general"}
    profile_hit_rate = (
        sum(1 for hit in warm_hits if hit.get("workspace_profile") in allowed_profiles) / len(warm_hits)
        if warm_hits
        else 0.0
    )
    fallback_hit_rate = 1.0 if any(hit.get("id") == "docs-fallback" for hit in fallback_hits) else 0.0
    metrics = {
        "index_size": indexed_count,
        "build_ms": build_ms,
        "cold_start_ms": cold_start_ms,
        "first_recall_ms": first_recall_ms,
        "warm_recall_p95_ms": _p95(warm_times),
        "warm_recall_max_ms": max(warm_times),
        "profile_hit_rate": profile_hit_rate,
        "fallback_hit_rate": fallback_hit_rate,
        "first_hit_count": len(first_hits),
        "warm_hit_count": len(warm_hits),
    }
    budget_results = _evaluate_budgets(metrics, budgets)
    report = {
        "version": RAG_BENCHMARK_VERSION,
        "status": "ready",
        "budget_status": "pass" if all(item["ok"] for item in budget_results.values()) else "fail",
        "no_network_call": True,
        "engine": "fake_faiss_deterministic_embeddings",
        "benchmark_scope": "deterministic_local_pipeline_speed",
        "config": {
            "record_count": indexed_count,
            "requested_record_count": record_count,
            "warm_runs": warm_runs,
            "embedding_dim": 16,
            "top_k": 8,
        },
        "metrics": metrics,
        "budgets": budget_results,
        "truthfulness": "This benchmark proves deterministic local pipeline performance only; it does not prove production embedding quality.",
        "generated_at": time.time(),
    }
    return attach_embedding_quality(report)


def _evaluate_budgets(metrics: Dict[str, Any], budgets: Dict[str, float]) -> Dict[str, Dict[str, Any]]:
    results: Dict[str, Dict[str, Any]] = {}
    for key, threshold in budgets.items():
        value = float(metrics.get(key) or 0.0)
        if key.endswith("_hit_rate"):
            ok = value >= float(threshold)
            relation = ">="
        else:
            ok = value < float(threshold)
            relation = "<"
        results[key] = {
            "value": value,
            "threshold": float(threshold),
            "relation": relation,
            "ok": ok,
        }
    return results


def _rag_closure_gate(report: Optional[Dict[str, Any]], quality: Dict[str, Any]) -> Dict[str, Any]:
    speed_ready = bool(
        isinstance(report, dict)
        and report.get("status") == "ready"
        and report.get("budget_status") == "pass"
    )
    return {
        "can_claim_deterministic_rag_speed": speed_ready,
        "can_claim_production_embedding_quality": quality.get("can_claim_production_embedding_quality") is True,
        "truthfulness_rule": (
            "RAG speed claims require deterministic benchmark pass; production embedding quality claims require "
            "embedding_quality.can_claim_production_embedding_quality=true."
        ),
    }


def _embedding_quality_current_evidence(
    deterministic_report: Optional[Dict[str, Any]],
    evaluation_evidence: Dict[str, Any],
) -> Dict[str, Any]:
    deterministic_report = deterministic_report if isinstance(deterministic_report, dict) else {}
    return {
        "deterministic_speed_benchmark": deterministic_report.get("status") == "ready",
        "deterministic_engine": deterministic_report.get("engine"),
        "no_network_call": deterministic_report.get("no_network_call") is True,
        "production_encoder": bool(evaluation_evidence.get("production_encoder")),
        "labelled_corpus": bool(evaluation_evidence.get("labelled_corpus")),
        "quality_metrics": list(evaluation_evidence.get("quality_metrics") or []),
        "sample_count": _safe_positive_int(evaluation_evidence.get("sample_count")),
    }


def _safe_positive_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except Exception:
        return 0


def _benchmark_items(count: int):
    items = []
    for index in range(count):
        if index % 10 == 0:
            profile = "general"
        elif index % 3 == 0:
            profile = "docs"
        else:
            profile = "maker"
        item = {
            "id": f"mem-{index}",
            "type": "session_summary",
            "workspace_profile": profile,
            "agent_id": "default",
            "visibility": "private",
        }
        content = f"{profile} alpha recall benchmark lesson {index}"
        items.append((item, content))
    items.append((
        {
            "id": "docs-fallback",
            "type": "session_summary",
            "workspace_profile": "docs",
            "agent_id": "default",
            "visibility": "private",
        },
        "docs-only fallback-signal benchmark lesson",
    ))
    return items


def _p95(values: List[float]) -> float:
    ordered = sorted(values)
    index = max(0, int(len(ordered) * 0.95) - 1)
    return ordered[index]


# ---------------------------------------------------------------------------
# Phase B: graph-on vs graph-off comparison
# ---------------------------------------------------------------------------

GRAPH_ON_OFF_VERSION = "rag-graph-on-off.v1"
DEFAULT_GRAPH_RATIO_BUDGET = 1.5  # graph-on p95 must be <= 1.5x graph-off


def run_graph_on_off_comparison(
    *,
    cold_factory,
    query: str = "alpha",
    warm_runs: int = 16,
    top_k: int = 5,
    ratio_budget: float = DEFAULT_GRAPH_RATIO_BUDGET,
    seed_items: Optional[List[Tuple[Dict[str, Any], str]]] = None,
) -> Dict[str, Any]:
    """Compare graph-on and graph-off retrieval latency and ranking.

    The factory is called twice with two distinct storage directories so the
    two paths do not share state. ``cold_factory(root: Path) -> ColdMemory``
    should produce a fully initialized instance. The factory is responsible
    for passing the right ``graph_config`` to each instance — the caller
    builds the comparison by running the factory once with graph-enabled
    config and once with graph-disabled config.

    This helper intentionally only times the public ``retrieve_with_graph``
    (when enabled) and ``search`` (when disabled) APIs, not the
    pre-warm bulk_index, so the ratio reflects user-visible cost.
    """
    if not callable(cold_factory):
        raise ValueError("cold_factory must be a callable taking a Path")

    if seed_items is None:
        seed_items = [
            ({"id": f"g-{i}", "type": "fact", "workspace_profile": "general",
              "agent_id": "default", "visibility": "private"},
             f"alpha bravo charlie delta {i}")
            for i in range(50)
        ]
        # Add a few edges worth of nodes
        for i in range(10, 30):
            seed_items.append(
                ({"id": f"g-{i}", "type": "fact", "workspace_profile": "general",
                  "agent_id": "default", "visibility": "private"},
                 f"alpha extra charlie {i}")
            )

    def _measure(off: bool) -> Dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="ttm-graph-") as tmp:
            root = Path(tmp)
            cold = cold_factory(root)
            cold.bulk_index(seed_items)
            if not off and cold.graph_enabled():
                graph = cold._graph  # type: ignore[attr-defined]
                if graph is not None:
                    from memory.graph import MemoryEdge, MemoryNode
                    for i in range(20):
                        try:
                            graph.upsert_node(MemoryNode(
                                id=f"g-{i}", type="fact", summary=f"alpha bravo {i}"))
                        except Exception:
                            continue
                    for i in range(15):
                        try:
                            graph.add_edge(MemoryEdge(
                                id=f"ge-{i}", src=f"g-{i}", dst=f"g-{i+1}", type="references"))
                        except Exception:
                            continue
            # Warmup
            for _ in range(3):
                if off:
                    cold.search(query, top_k=top_k)
                else:
                    cold.retrieve_with_graph(query, top_k=top_k)
            latencies: List[float] = []
            for _ in range(max(1, int(warm_runs))):
                started = time.perf_counter()
                if off:
                    cold.search(query, top_k=top_k)
                else:
                    cold.retrieve_with_graph(query, top_k=top_k)
                latencies.append((time.perf_counter() - started) * 1000.0)
            return {
                "warm_p50_ms": round(_p50(latencies), 4),
                "warm_p95_ms": round(_p95(latencies), 4),
                "warm_runs": len(latencies),
            }

    off = _measure(off=True)
    on = _measure(off=False)
    ratio = None
    if off["warm_p95_ms"] > 0 and on["warm_p95_ms"] > 0:
        ratio = on["warm_p95_ms"] / off["warm_p95_ms"]
    budget_status = "pass" if (ratio is None or ratio <= ratio_budget) else "fail"
    return {
        "version": GRAPH_ON_OFF_VERSION,
        "status": "ready",
        "graph_on": on,
        "graph_off": off,
        "ratio_warm_p95": round(ratio, 4) if ratio is not None else None,
        "ratio_budget": ratio_budget,
        "budget_status": budget_status,
        "truthfulness": "deterministic speed only; embedding_quality remains unproven",
    }


def _p50(values: List[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def _fake_faiss_module():
    class FakeFlatIndex:
        def __init__(self, dim):
            self.d = dim

    class FakeIdMapIndex:
        def __init__(self, base):
            self.base = base
            self.d = base.d
            self.ntotal = 0
            self.ids: List[int] = []
            self.vectors: List[List[float]] = []

        def add_with_ids(self, vectors, ids):
            self.ids.extend(int(item) for item in ids)
            array = np.asarray(vectors, dtype=np.float32)
            self.vectors.extend(array.tolist())
            self.ntotal = len(self.ids)

        def search(self, qvec, top_k):
            if not self.ids or not self.vectors:
                return (
                    np.array([[0.0] * top_k], dtype=np.float32),
                    np.array([[-1] * top_k], dtype=np.int64),
                )
            query = np.asarray(qvec, dtype=np.float32)[0]
            vectors = np.asarray(self.vectors, dtype=np.float32)
            scores = vectors @ query
            order = np.argsort(scores)[::-1][:top_k]
            ids = [self.ids[int(index)] for index in order]
            score_values = [float(scores[int(index)]) for index in order]
            if len(ids) < top_k:
                missing = top_k - len(ids)
                ids.extend([-1] * missing)
                score_values.extend([0.0] * missing)
            return np.array([score_values], dtype=np.float32), np.array([ids], dtype=np.int64)

    class FakeSelector:
        def __init__(self, *_args):
            pass

    def write_index(index, path):
        payload = {
            "d": index.d,
            "ids": getattr(index, "ids", []),
            "vectors": getattr(index, "vectors", []),
        }
        Path(path).write_text(json.dumps(payload), encoding="utf-8")

    def read_index(path):
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        index = FakeIdMapIndex(FakeFlatIndex(int(payload.get("d") or 16)))
        index.ids = [int(item) for item in payload.get("ids", [])]
        index.vectors = payload.get("vectors") or []
        index.ntotal = len(index.ids)
        return index

    return SimpleNamespace(
        IndexFlatIP=FakeFlatIndex,
        IndexIDMap2=FakeIdMapIndex,
        IDSelectorBatch=FakeSelector,
        write_index=write_index,
        read_index=read_index,
    )
