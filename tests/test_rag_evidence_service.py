from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from core.config import Config
from server.rag_evidence_service import RagEvidenceService


def _write_config(path: Path, payload: Dict[str, Any]) -> Config:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return Config(path)


def test_rag_evidence_service_caches_benchmark_and_attaches_quality(tmp_path: Path):
    cfg = _write_config(
        tmp_path / "config.json",
        {
            "storage_root": str(tmp_path / "storage"),
            "memory": {"vector_index": {"enabled": True, "embedding_dim": 16}},
        },
    )
    calls = {"benchmark": 0, "quality": 0}

    def benchmark_runner() -> Dict[str, Any]:
        calls["benchmark"] += 1
        return {
            "version": "rag-benchmark.v1",
            "status": "ready",
            "budget_status": "pass",
            "engine": "unit_fake_faiss",
            "no_network_call": True,
            "config": {"record_count": 1},
            "metrics": {
                "build_ms": 1.0,
                "cold_start_ms": 1.0,
                "first_recall_ms": 1.0,
                "warm_recall_p95_ms": 1.0,
                "profile_hit_rate": 1.0,
                "fallback_hit_rate": 1.0,
            },
        }

    def quality_runner(**_options: Any) -> Dict[str, Any]:
        calls["quality"] += 1
        return {
            "version": "embedding-quality-eval.v1",
            "status": "ready",
            "budget_status": "pass",
            "passed": True,
            "embedding_model": "local-prod-embedding",
            "corpus_id": "unit-golden-corpus",
            "sample_count": 3,
            "metrics": {"recall_at_k": 1.0, "precision_at_k": 1.0, "mrr": 1.0},
        }

    service = RagEvidenceService(
        lambda: cfg,
        benchmark_runner=benchmark_runner,
        quality_runner=quality_runner,
        clock=lambda: 100.0,
    )

    assert service.benchmark_status()["status"] == "not_run"

    first = service.benchmark_report(force=True)
    second = service.benchmark_report()

    assert calls["benchmark"] == 1
    assert first["cache"] == "miss"
    assert second["cache"] == "hit"
    assert first["closure_gate"]["can_claim_deterministic_rag_speed"] is True
    assert first["closure_gate"]["can_claim_production_embedding_quality"] is False

    quality = service.quality_report(force=True)
    enriched = service.benchmark_report()
    status = service.benchmark_status()

    assert calls["quality"] == 1
    assert quality["cache"] == "miss"
    assert enriched["cache"] == "hit"
    assert enriched["embedding_quality"]["status"] == "ready"
    assert enriched["closure_gate"]["can_claim_production_embedding_quality"] is True
    assert status["quality_checked_at"] == quality["checked_at"]


def test_rag_evidence_service_resolves_quality_paths_and_invalidates_config_cache(tmp_path: Path):
    cfg = _write_config(
        tmp_path / "config.json",
        {
            "storage_root": str(tmp_path / "storage"),
            "memory": {
                "vector_index": {"enabled": True, "embedding_dim": 16, "model": "local-embed"},
                "rag_quality": {
                    "corpus_path": "quality/golden.json",
                    "top_k": 3,
                    "budgets": {"recall_at_k": 0.75, "mrr": 0.4, "min_query_count": 2},
                },
            },
        },
    )
    seen_options = []

    def quality_runner(**options: Any) -> Dict[str, Any]:
        seen_options.append(options)
        return {
            "version": "embedding-quality-eval.v1",
            "status": "unproven",
            "budget_status": "not_checked",
            "passed": False,
            "sample_count": 0,
            "metrics": {},
            "call": len(seen_options),
        }

    service = RagEvidenceService(
        lambda: cfg,
        quality_runner=quality_runner,
        clock=lambda: 200.0,
    )

    first = service.quality_report()
    second = service.quality_report()

    assert first["cache"] == "created"
    assert second["cache"] == "hit"
    assert len(seen_options) == 1
    assert seen_options[0]["corpus_path"] == (tmp_path / "quality" / "golden.json").resolve()
    assert seen_options[0]["storage_dir"] == cfg.storage_root() / "rag_quality" / "eval_index"
    assert seen_options[0]["vector_index_config"]["model"] == "local-embed"
    assert seen_options[0]["top_k"] == 3
    assert seen_options[0]["budgets"]["recall_at_k"] == 0.75

    cfg.data["memory"]["rag_quality"]["top_k"] = 7
    third = service.quality_report()

    assert third["cache"] == "created"
    assert third["call"] == 2
    assert len(seen_options) == 2
    assert seen_options[1]["top_k"] == 7
