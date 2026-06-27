from __future__ import annotations

import sys
import tempfile
import json
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from memory.cold import ColdMemory
from memory.rag_benchmark import (
    DEFAULT_RAG_BENCHMARK_BUDGETS,
    compact_rag_benchmark_report,
    deterministic_benchmark_encoder,
    install_fake_faiss,
    production_embedding_quality_boundary,
    run_rag_benchmark,
)
from memory.rag_quality import (
    compact_embedding_quality_evaluation,
    run_embedding_quality_evaluation,
)


def test_cold_memory_bulk_index_preserves_profile_and_shared_policy():
    with install_fake_faiss():
        with tempfile.TemporaryDirectory() as tmp:
            cold = ColdMemory(
                Path(tmp),
                vector_index_config={"enabled": True, "embedding_dim": 16},
                encoder=deterministic_benchmark_encoder,
            )

            count = cold.bulk_index([
                (
                    {"id": "maker1", "type": "session_summary", "workspace_profile": "maker"},
                    "maker alpha bulk lesson",
                ),
                (
                    {"id": "docs1", "type": "session_summary", "workspace_profile": "docs"},
                    "docs alpha bulk lesson",
                ),
            ])

            maker_hits = cold.search("alpha bulk", top_k=5, workspace_profile="maker")
            maker_ids = {hit["id"] for hit in maker_hits}

            assert count == 2
            assert "maker1" in maker_ids
            assert "docs1" not in maker_ids


def test_rag_benchmark_fake_embeddings_meets_budget():
    busy_suite_budgets = {
        **DEFAULT_RAG_BENCHMARK_BUDGETS,
        "build_ms": 5000.0,
        "cold_start_ms": 1500.0,
        "first_recall_ms": 750.0,
    }
    with tempfile.TemporaryDirectory() as tmp:
        report = run_rag_benchmark(storage_dir=Path(tmp), budgets=busy_suite_budgets)

    assert report["version"] == "rag-benchmark.v1"
    assert report["status"] == "ready"
    assert report["budget_status"] == "pass", report["budgets"]
    assert report["config"]["record_count"] == 10_001
    assert report["metrics"]["first_hit_count"] == 8
    assert report["metrics"]["warm_hit_count"] == 8
    assert report["metrics"]["profile_hit_rate"] == 1.0
    assert report["metrics"]["fallback_hit_rate"] == 1.0
    assert report["metrics"]["build_ms"] < busy_suite_budgets["build_ms"]
    assert report["metrics"]["cold_start_ms"] < busy_suite_budgets["cold_start_ms"]
    assert report["metrics"]["first_recall_ms"] < busy_suite_budgets["first_recall_ms"]
    assert report["metrics"]["warm_recall_p95_ms"] < busy_suite_budgets["warm_recall_p95_ms"]
    assert report["budgets"]["warm_recall_p95_ms"]["ok"] is True
    assert report["benchmark_scope"] == "deterministic_local_pipeline_speed"
    assert report["closure_gate"]["can_claim_deterministic_rag_speed"] is True
    assert report["closure_gate"]["can_claim_production_embedding_quality"] is False
    assert report["embedding_quality"]["status"] == "unproven"
    assert report["embedding_quality"]["can_claim_production_embedding_quality"] is False
    assert report["embedding_quality"]["current_evidence"]["deterministic_speed_benchmark"] is True
    assert report["embedding_quality"]["current_evidence"]["production_encoder"] is False


def test_compact_rag_benchmark_keeps_production_quality_unproven_until_evaluated():
    compact = compact_rag_benchmark_report(None)

    assert compact["status"] == "not_run"
    assert compact["closure_gate"]["can_claim_deterministic_rag_speed"] is False
    assert compact["closure_gate"]["can_claim_production_embedding_quality"] is False
    assert compact["embedding_quality"]["status"] == "unproven"
    assert compact["embedding_quality"]["required_evidence"]


def test_production_embedding_quality_boundary_requires_real_quality_evidence():
    partial = production_embedding_quality_boundary({
        "status": "ready",
        "embedding_model": "local-prod-embedding",
        "metrics": {"recall_at_5": 0.82},
    })
    failed = production_embedding_quality_boundary({
        "status": "ready",
        "passed": False,
        "embedding_model": "local-prod-embedding",
        "corpus_id": "golden-maker-rag-v1",
        "sample_count": 12,
        "metrics": {"recall_at_5": 0.82},
    })
    ready = production_embedding_quality_boundary({
        "status": "ready",
        "embedding_model": "local-prod-embedding",
        "corpus_id": "golden-maker-rag-v1",
        "sample_count": 12,
        "metrics": {"recall_at_5": 0.82},
    })

    assert partial["status"] == "unproven"
    assert partial["can_claim_production_embedding_quality"] is False
    assert failed["status"] == "unproven"
    assert failed["can_claim_production_embedding_quality"] is False
    assert ready["status"] == "ready"
    assert ready["can_claim_production_embedding_quality"] is True
    assert ready["current_evidence"]["quality_metrics"] == ["recall_at_5"]


def test_embedding_quality_evaluation_with_golden_corpus_can_claim_quality():
    with install_fake_faiss():
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus_path = root / "golden_corpus.json"
            corpus_path.write_text(
                json.dumps({
                    "version": "rag-quality-corpus.v1",
                    "corpus_id": "unit-golden-corpus",
                    "documents": [
                        {"id": "distractor-a", "text": "unrelated browser navigation note"},
                        {"id": "distractor-b", "text": "unrelated shell command note"},
                        {"id": "target", "text": "maker build publish scene quality target"},
                    ],
                    "queries": [
                        {"id": "q1", "query": "maker build target", "expected_ids": ["target"]},
                        {"id": "q2", "query": "publish scene target", "expected_ids": ["target"]},
                        {"id": "q3", "query": "quality target", "expected_ids": ["target"]},
                    ],
                }),
                encoding="utf-8",
            )

            report = run_embedding_quality_evaluation(
                corpus_path=corpus_path,
                storage_dir=root / "eval",
                vector_index_config={"enabled": True, "embedding_dim": 16},
                encoder=deterministic_benchmark_encoder,
                encoder_id="unit-test-production-encoder",
                top_k=1,
                budgets={"recall_at_k": 1.0, "mrr": 1.0, "min_query_count": 3},
            )
            boundary = production_embedding_quality_boundary(report)
            compact = compact_embedding_quality_evaluation(report)

    assert report["version"] == "embedding-quality-eval.v1"
    assert report["status"] == "ready"
    assert report["budget_status"] == "pass"
    assert report["passed"] is True
    assert report["sample_count"] == 3
    assert report["metrics"]["recall_at_k"] == 1.0
    assert report["metrics"]["mrr"] == 1.0
    assert boundary["can_claim_production_embedding_quality"] is True
    assert compact["can_claim_production_embedding_quality"] is True
    assert compact["endpoint"] == "/memory/rag-quality"


def test_embedding_quality_evaluation_missing_corpus_stays_unproven():
    with tempfile.TemporaryDirectory() as tmp:
        report = run_embedding_quality_evaluation(
            corpus_path=Path(tmp) / "missing.json",
            vector_index_config={"enabled": True, "embedding_dim": 16},
            encoder=deterministic_benchmark_encoder,
            encoder_id="unit-test-production-encoder",
        )
        compact = compact_embedding_quality_evaluation(report)

    assert report["status"] == "unproven"
    assert report["passed"] is False
    assert "labelled_golden_corpus" in report["missing"]
    assert compact["status"] == "unproven"
    assert compact["can_claim_production_embedding_quality"] is False
