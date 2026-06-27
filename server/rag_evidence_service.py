"""RAG benchmark and embedding-quality evidence service.

This keeps RAG evidence caching and config/path resolution out of AppServer so
HTTP routing can stay separate from memory-quality control gates.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from memory.rag_benchmark import attach_embedding_quality, compact_rag_benchmark_report, run_rag_benchmark
from memory.rag_quality import (
    compact_embedding_quality_evaluation,
    default_quality_corpus_path,
    run_embedding_quality_evaluation,
)


ConfigProvider = Callable[[], Any]
BenchmarkRunner = Callable[[], Dict[str, Any]]
QualityRunner = Callable[..., Dict[str, Any]]


@dataclass
class _EvidenceCache:
    checked_at: float = 0.0
    report: Optional[Dict[str, Any]] = None
    config_key: str = ""


class RagEvidenceService:
    """Build cached RAG speed and semantic-quality evidence reports."""

    def __init__(
        self,
        config_provider: ConfigProvider,
        *,
        benchmark_ttl_seconds: float = 300.0,
        quality_ttl_seconds: float = 300.0,
        benchmark_runner: BenchmarkRunner = run_rag_benchmark,
        quality_runner: QualityRunner = run_embedding_quality_evaluation,
        clock: Callable[[], float] = time.time,
    ):
        self._config_provider = config_provider
        self._benchmark_ttl_seconds = float(benchmark_ttl_seconds)
        self._quality_ttl_seconds = float(quality_ttl_seconds)
        self._benchmark_runner = benchmark_runner
        self._quality_runner = quality_runner
        self._clock = clock
        self._benchmark_cache = _EvidenceCache(config_key="deterministic-rag-benchmark")
        self._quality_cache = _EvidenceCache()
        self._benchmark_lock = threading.Lock()
        self._quality_lock = threading.Lock()

    def benchmark_status(self) -> Dict[str, Any]:
        report = self._benchmark_cache.report
        quality_report = self._quality_cache.report
        compact = compact_rag_benchmark_report(
            report if isinstance(report, dict) else None,
            quality_report if isinstance(quality_report, dict) else None,
        )
        compact["checked_at"] = self._benchmark_cache.checked_at or None
        compact["quality_checked_at"] = self._quality_cache.checked_at or None
        return compact

    def benchmark_report(self, *, force: bool = False) -> Dict[str, Any]:
        now = self._clock()
        cached = self._benchmark_cache.report
        if not force and self._is_cache_fresh(self._benchmark_cache, now, self._benchmark_ttl_seconds):
            return self._benchmark_response(cached, cache="hit")

        with self._benchmark_lock:
            now = self._clock()
            cached = self._benchmark_cache.report
            if not force and self._is_cache_fresh(self._benchmark_cache, now, self._benchmark_ttl_seconds):
                return self._benchmark_response(cached, cache="hit")

            report = attach_embedding_quality(
                self._benchmark_runner(),
                self._quality_cache.report if isinstance(self._quality_cache.report, dict) else None,
            )
            self._benchmark_cache = _EvidenceCache(
                checked_at=self._clock(),
                report=report,
                config_key="deterministic-rag-benchmark",
            )
            return self._benchmark_response(report, cache="miss" if force else "created")

    def quality_status(self) -> Dict[str, Any]:
        report = self._quality_cache.report
        compact = compact_embedding_quality_evaluation(report if isinstance(report, dict) else None)
        compact["checked_at"] = self._quality_cache.checked_at or None
        return compact

    def quality_report(self, *, force: bool = False) -> Dict[str, Any]:
        options = self._quality_options()
        cache_key = _stable_cache_key(options)
        now = self._clock()
        cached = self._quality_cache.report
        if (
            not force
            and self._quality_cache.config_key == cache_key
            and self._is_cache_fresh(self._quality_cache, now, self._quality_ttl_seconds)
        ):
            return self._quality_response(cached, cache="hit")

        with self._quality_lock:
            options = self._quality_options()
            cache_key = _stable_cache_key(options)
            now = self._clock()
            cached = self._quality_cache.report
            if (
                not force
                and self._quality_cache.config_key == cache_key
                and self._is_cache_fresh(self._quality_cache, now, self._quality_ttl_seconds)
            ):
                return self._quality_response(cached, cache="hit")

            report = self._quality_runner(**options)
            self._quality_cache = _EvidenceCache(
                checked_at=self._clock(),
                report=report,
                config_key=cache_key,
            )
            return self._quality_response(report, cache="miss" if force else "created")

    def _benchmark_response(self, report: Optional[Dict[str, Any]], *, cache: str) -> Dict[str, Any]:
        quality_report = self._quality_cache.report
        attached = attach_embedding_quality(
            report if isinstance(report, dict) else {},
            quality_report if isinstance(quality_report, dict) else None,
        )
        return {
            **attached,
            "cache": cache,
            "cache_ttl_seconds": self._benchmark_ttl_seconds,
            "checked_at": self._benchmark_cache.checked_at,
        }

    def _quality_response(self, report: Optional[Dict[str, Any]], *, cache: str) -> Dict[str, Any]:
        payload = dict(report) if isinstance(report, dict) else {}
        return {
            **payload,
            "cache": cache,
            "cache_ttl_seconds": self._quality_ttl_seconds,
            "checked_at": self._quality_cache.checked_at,
        }

    def _quality_options(self) -> Dict[str, Any]:
        config = self._config_provider()
        storage_root = Path(config.storage_root())
        quality_cfg = config.get("memory.rag_quality", {})
        quality_cfg = quality_cfg if isinstance(quality_cfg, dict) else {}
        corpus_path = quality_cfg.get("corpus_path")
        corpus = Path(corpus_path) if corpus_path else default_quality_corpus_path(storage_root)
        if corpus_path and not corpus.is_absolute():
            corpus = (config.base_dir / corpus).resolve()
        budgets = quality_cfg.get("budgets") if isinstance(quality_cfg.get("budgets"), dict) else None
        return {
            "corpus_path": corpus,
            "storage_dir": storage_root / "rag_quality" / "eval_index",
            "vector_index_config": config.vector_index_config(),
            "top_k": _safe_int(quality_cfg.get("top_k"), default=5, minimum=1),
            "budgets": budgets,
        }

    @staticmethod
    def _is_cache_fresh(cache: _EvidenceCache, now: float, ttl_seconds: float) -> bool:
        return isinstance(cache.report, dict) and bool(cache.report) and now - cache.checked_at < ttl_seconds


def _safe_int(value: Any, *, default: int, minimum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)


def _stable_cache_key(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
