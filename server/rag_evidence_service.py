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

from memory.rag_benchmark import attach_embedding_quality, compact_rag_benchmark_report, run_rag_benchmark, run_graph_on_off_comparison
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


@dataclass
class _GraphEvidenceCache:
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
        self._graph_cache = _GraphEvidenceCache()
        self._benchmark_lock = threading.Lock()
        self._quality_lock = threading.Lock()
        self._graph_lock = threading.Lock()

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

    def graph_status(self) -> Dict[str, Any]:
        """Compact graph-on vs graph-off evidence payload.

        Returns a fully-formed payload even when the graph flag is off,
        so callers can rely on the shape. ``status="not_enabled"`` is the
        boundary marker.
        """
        report = self._graph_cache.report
        config = self._config_provider()
        graph_cfg = config.get("memory.graph", {}) if config else {}
        graph_cfg = graph_cfg if isinstance(graph_cfg, dict) else {}
        graph_enabled = bool(graph_cfg.get("enabled", False))
        if not graph_enabled:
            return {
                "version": "rag-graph-on-off.v1",
                "status": "not_enabled",
                "graph_enabled": False,
                "truthfulness": "graph memory is opt-in; enable memory.graph.enabled to produce this evidence",
                "checked_at": self._graph_cache.checked_at or None,
            }
        if not isinstance(report, dict):
            return {
                "version": "rag-graph-on-off.v1",
                "status": "not_run",
                "graph_enabled": True,
                "endpoint": "/memory/graph-on-off",
                "note": "Run GET /memory/graph-on-off?force=true to produce a deterministic local report.",
                "checked_at": None,
            }
        return {
            **report,
            "graph_enabled": True,
            "checked_at": self._graph_cache.checked_at or None,
        }

    def graph_report(self, *, force: bool = False) -> Dict[str, Any]:
        """Build (or return cached) graph-on vs graph-off report.

        Only runs when ``memory.graph.enabled=true`` in config. When the
        flag is off, returns the ``not_enabled`` boundary payload.
        """
        config = self._config_provider()
        graph_cfg = config.get("memory.graph", {}) if config else {}
        graph_cfg = graph_cfg if isinstance(graph_cfg, dict) else {}
        graph_enabled = bool(graph_cfg.get("enabled", False))
        if not graph_enabled:
            return self.graph_status()

        now = self._clock()
        cache_key = _stable_cache_key({"graph": graph_cfg})
        if (
            not force
            and self._graph_cache.report
            and self._graph_cache.config_key == cache_key
            and self._is_cache_fresh(_EvidenceCache(
                checked_at=self._graph_cache.checked_at,
                report=self._graph_cache.report,
            ), now, self._benchmark_ttl_seconds)
        ):
            return {**self._graph_cache.report, "cache": "hit", "graph_enabled": True}

        with self._graph_lock:
            options = self._graph_options()
            report = self._graph_runner(**options)
            self._graph_cache = _GraphEvidenceCache(
                checked_at=self._clock(),
                report=report,
                config_key=cache_key,
            )
            return {**report, "cache": "created" if not force else "miss", "graph_enabled": True}

    def _graph_options(self) -> Dict[str, Any]:
        config = self._config_provider()
        storage_root = Path(config.storage_root())
        graph_cfg = config.get("memory.graph", {}) if config else {}
        graph_cfg = graph_cfg if isinstance(graph_cfg, dict) else {}
        bayes_cfg = config.get("memory.bayes", {}) if config else {}
        bayes_cfg = bayes_cfg if isinstance(bayes_cfg, dict) else {}
        return {
            "storage_dir": storage_root / "cold_memory" / "graph_bench",
            "vector_index_config": config.vector_index_config(),
            "graph_config": {**graph_cfg, "enabled": True},
            "bayes_config": {**bayes_cfg, "enabled": False},
            "warm_runs": int(graph_cfg.get("warm_runs", 16)),
            "query": str(graph_cfg.get("bench_query", "alpha")),
        }

    def _graph_runner(self, **kwargs) -> Dict[str, Any]:
        """Run the graph-on/off benchmark with the configured vector index.

        Kept as a method (not module-level) so it can read
        ``config.vector_index_config()`` cleanly.
        """
        from memory.cold import ColdMemory
        vector_index_config = kwargs.get("vector_index_config", {})
        graph_config = kwargs.get("graph_config", {})
        bayes_config = kwargs.get("bayes_config", {})
        warm_runs = int(kwargs.get("warm_runs", 16))
        query = str(kwargs.get("query", "alpha"))
        storage_dir = kwargs.get("storage_dir")

        def _factory(root):
            return ColdMemory(
                root / "cold",
                vector_index_config=vector_index_config,
                graph_config=graph_config,
                bayes_config=bayes_config,
            )

        return run_graph_on_off_comparison(
            cold_factory=_factory,
            query=query,
            warm_runs=warm_runs,
        )

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
