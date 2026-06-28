"""Production embedding quality evaluation for RAG evidence.

This module evaluates semantic retrieval quality against a labelled golden
corpus. Missing corpus/model evidence returns an explicit unproven report.
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from memory.vector_index import TextChunk, VectorIndex


RAG_QUALITY_EVAL_VERSION = "embedding-quality-eval.v1"
RAG_QUALITY_CORPUS_VERSION = "rag-quality-corpus.v1"
DEFAULT_RAG_QUALITY_BUDGETS = {
    "recall_at_k": 0.8,
    "mrr": 0.5,
    "min_query_count": 1,
}

Encoder = Callable[[List[str]], np.ndarray]


def run_embedding_quality_evaluation(
    *,
    corpus_path: Optional[Path] = None,
    storage_dir: Optional[Path] = None,
    vector_index_config: Optional[Dict[str, Any]] = None,
    encoder: Optional[Encoder] = None,
    encoder_id: Optional[str] = None,
    top_k: int = 5,
    budgets: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Run a labelled semantic recall evaluation.

    The report can prove production embedding quality only when a labelled
    corpus and a real encoder are both present. Test callers may inject an
    encoder explicitly; the AppServer path resolves only local embedding models.
    """
    started = time.perf_counter()
    budgets = dict(DEFAULT_RAG_QUALITY_BUDGETS if budgets is None else budgets)
    top_k = max(1, int(top_k or 5))
    vector_index_config = dict(vector_index_config or {})
    corpus_info = _load_corpus(corpus_path)
    if corpus_info.get("status") != "ready":
        return _unproven_report(
            reason=str(corpus_info.get("reason") or "golden corpus is unavailable"),
            corpus_path=corpus_path,
            elapsed_ms=_elapsed_ms(started),
            missing=["labelled_golden_corpus"],
        )

    corpus = corpus_info["corpus"]
    documents = corpus["documents"]
    queries = corpus["queries"]
    resolved_encoder, encoder_meta = _resolve_encoder(
        encoder=encoder,
        encoder_id=encoder_id,
        vector_index_config=vector_index_config,
    )
    if resolved_encoder is None:
        return _unproven_report(
            reason=str(encoder_meta.get("reason") or "local production embedding model is unavailable"),
            corpus_path=corpus_path,
            corpus_id=str(corpus.get("corpus_id") or ""),
            elapsed_ms=_elapsed_ms(started),
            missing=["production_embedding_model"],
            encoder=encoder_meta,
            sample_count=len(queries),
        )

    with _quality_storage(storage_dir) as actual_storage:
        index = VectorIndex(
            namespace="rag_quality_eval",
            storage_dir=actual_storage,
            model_name=str(vector_index_config.get("model") or encoder_meta.get("model") or "production-embedding"),
            embedding_dim=vector_index_config.get("embedding_dim"),
            enabled=True,
            encoder=resolved_encoder,
        )
        index.clear()
        chunks = [
            TextChunk(
                id=str(doc["id"]),
                text=str(doc["text"]),
                source=str(doc.get("source") or "golden_corpus"),
                meta={
                    "id": str(doc["id"]),
                    "workspace_profile": doc.get("workspace_profile") or "general",
                    "type": doc.get("type") or "golden_document",
                },
            )
            for doc in documents
        ]
        index.add(chunks)
        if not index.is_available:
            return _unproven_report(
                reason=index.last_error() or "vector index is unavailable for quality evaluation",
                corpus_path=corpus_path,
                corpus_id=str(corpus.get("corpus_id") or ""),
                elapsed_ms=_elapsed_ms(started),
                missing=["vector_index"],
                encoder=encoder_meta,
                sample_count=len(queries),
            )

        per_query: List[Dict[str, Any]] = []
        for query in queries:
            expected_ids = [str(item) for item in query.get("expected_ids", [])]
            expected_linked_ids = [str(item) for item in query.get("expected_linked_ids", [])]
            results = index.search(str(query["query"]), top_k=top_k)
            result_ids = [chunk.id for _score, chunk in results]
            first_rank = _first_relevant_rank(result_ids, expected_ids)
            hit_count = len(set(result_ids) & set(expected_ids))
            linked_hit_count = len(set(result_ids) & set(expected_linked_ids))
            per_query.append({
                "id": str(query.get("id") or ""),
                "hit": first_rank > 0,
                "first_rank": first_rank or None,
                "expected_ids": expected_ids,
                "expected_linked_ids": expected_linked_ids,
                "result_ids": result_ids,
                "hit_count": hit_count,
                "linked_hit_count": linked_hit_count,
            })

    metrics = _quality_metrics(per_query, top_k=top_k)
    budget_results = _evaluate_quality_budgets(metrics, budgets)
    budget_status = "pass" if all(item["ok"] for item in budget_results.values()) else "fail"
    # Phase B: graph corpus ids — distinct node ids the corpus expects
    # to be linked from a primary hit. Used by graph recall to compute
    # linked recall@k against the same labelled corpus.
    graph_corpus_ids = corpus.get("graph_corpus_ids") or {}
    return {
        "version": RAG_QUALITY_EVAL_VERSION,
        "status": "ready" if budget_status == "pass" else "fail",
        "budget_status": budget_status,
        "passed": budget_status == "pass",
        "scope": "production_embedding_quality",
        "coverage": "labelled_golden_corpus",
        "corpus_id": str(corpus.get("corpus_id") or Path(corpus_path).stem if corpus_path else "inline"),
        "corpus_path": str(Path(corpus_path).resolve()) if corpus_path else None,
        "embedding_model": encoder_meta.get("model") or encoder_meta.get("encoder_id") or "injected_encoder",
        "production_encoder": True,
        "labelled_corpus": True,
        "sample_count": len(queries),
        "top_k": top_k,
        "metrics": metrics,
        "budgets": budget_results,
        "per_query": per_query[:20],
        "graph_corpus_ids": graph_corpus_ids,
        "required_evidence": [
            "configured production embedding model or local embedding artifact",
            "labelled evaluation corpus or golden query set",
            "semantic recall metric such as recall@k, precision@k, or MRR",
            "sample count greater than zero",
        ],
        "encoder": encoder_meta,
        "no_network_call": encoder_meta.get("no_network_call") is not False,
        "generated_at": time.time(),
        "elapsed_ms": _elapsed_ms(started),
        "truthfulness": "This report proves semantic retrieval quality only for the labelled corpus and encoder shown in the report.",
    }


def compact_embedding_quality_evaluation(report: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(report, dict) or not report:
        return {
            "version": RAG_QUALITY_EVAL_VERSION,
            "status": "not_run",
            "endpoint": "/memory/rag-quality",
            "can_claim_production_embedding_quality": False,
        }
    metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
    return {
        "version": report.get("version") or RAG_QUALITY_EVAL_VERSION,
        "status": report.get("status") or "unknown",
        "budget_status": report.get("budget_status"),
        "endpoint": "/memory/rag-quality",
        "corpus_id": report.get("corpus_id"),
        "embedding_model": report.get("embedding_model"),
        "sample_count": report.get("sample_count"),
        "top_k": report.get("top_k"),
        "metrics": {
            "recall_at_k": metrics.get("recall_at_k"),
            "precision_at_k": metrics.get("precision_at_k"),
            "mrr": metrics.get("mrr"),
        },
        "can_claim_production_embedding_quality": report.get("passed") is True,
        "reason": report.get("reason"),
    }


def default_quality_corpus_path(storage_root: Path) -> Path:
    return Path(storage_root) / "rag_quality" / "golden_corpus.json"


def _load_corpus(corpus_path: Optional[Path]) -> Dict[str, Any]:
    if corpus_path is None:
        return {"status": "missing", "reason": "corpus_path is not configured"}
    path = Path(corpus_path)
    if not path.exists():
        return {"status": "missing", "reason": f"golden corpus not found: {path}"}
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return {"status": "error", "reason": f"golden corpus read failed: {exc}"}
    corpus = _normalize_corpus(raw)
    if corpus.get("status") != "ready":
        return corpus
    return {"status": "ready", "corpus": corpus}


def _normalize_corpus(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {"status": "error", "reason": "golden corpus must be a JSON object"}
    documents = raw.get("documents")
    queries = raw.get("queries")
    if not isinstance(documents, list) or not isinstance(queries, list):
        return {"status": "error", "reason": "golden corpus requires documents[] and queries[]"}

    normalized_docs = []
    doc_ids = set()
    for doc in documents:
        if not isinstance(doc, dict) or not doc.get("id") or not str(doc.get("text") or "").strip():
            continue
        doc_id = str(doc["id"])
        doc_ids.add(doc_id)
        normalized_docs.append({**doc, "id": doc_id, "text": str(doc["text"])})

    normalized_queries = []
    for query in queries:
        if not isinstance(query, dict) or not str(query.get("query") or "").strip():
            continue
        expected = [
            str(item)
            for item in query.get("expected_ids", [])
            if str(item) in doc_ids
        ]
        if not expected:
            continue
        normalized_queries.append({
            **query,
            "id": str(query.get("id") or f"q{len(normalized_queries) + 1}"),
            "query": str(query["query"]),
            "expected_ids": expected,
        })

    if not normalized_docs:
        return {"status": "error", "reason": "golden corpus has no valid documents"}
    if not normalized_queries:
        return {"status": "error", "reason": "golden corpus has no valid labelled queries"}
    return {
        "version": raw.get("version") or RAG_QUALITY_CORPUS_VERSION,
        "status": "ready",
        "corpus_id": raw.get("corpus_id") or raw.get("id") or "golden_corpus",
        "documents": normalized_docs,
        "queries": normalized_queries,
    }


def _resolve_encoder(
    *,
    encoder: Optional[Encoder],
    encoder_id: Optional[str],
    vector_index_config: Dict[str, Any],
) -> Tuple[Optional[Encoder], Dict[str, Any]]:
    if encoder is not None:
        return encoder, {
            "source": "injected_encoder",
            "encoder_id": encoder_id or "injected_encoder",
            "production_encoder": True,
            "no_network_call": True,
        }

    model = str(vector_index_config.get("model") or "").strip()
    model_path = _resolve_local_embedding_model(model)
    if model and model_path is None and not bool(vector_index_config.get("allow_remote_model", False)):
        return None, {
            "source": "local_sentence_transformers",
            "model": model,
            "production_encoder": False,
            "no_network_call": True,
            "reason": "configured embedding model is not a local path and allow_remote_model is false",
        }
    if not model and model_path is None:
        return None, {
            "source": "local_sentence_transformers",
            "production_encoder": False,
            "no_network_call": True,
            "reason": "no local embedding model is configured",
        }

    try:
        from sentence_transformers import SentenceTransformer
        load_name = str(model_path or model)
        local_only = model_path is not None and Path(load_name).exists()
        st_model = SentenceTransformer(load_name, local_files_only=local_only)
    except Exception as exc:
        return None, {
            "source": "local_sentence_transformers",
            "model": str(model_path or model),
            "production_encoder": False,
            "no_network_call": model_path is not None,
            "reason": f"embedding model load failed: {exc}",
        }

    def encode(texts: List[str]) -> np.ndarray:
        return np.asarray(
            st_model.encode(
                texts,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            ),
            dtype=np.float32,
        )

    return encode, {
        "source": "local_sentence_transformers",
        "model": str(model_path or model),
        "production_encoder": True,
        "no_network_call": model_path is not None,
    }


def _resolve_local_embedding_model(model: str) -> Optional[Path]:
    if model:
        direct = Path(model)
        if direct.exists():
            return direct.resolve()
        vendor = Path(__file__).resolve().parent.parent / "vendor" / "embeddings" / Path(model).name
        if vendor.exists():
            return vendor.resolve()
    return None


def _quality_metrics(per_query: Sequence[Dict[str, Any]], *, top_k: int) -> Dict[str, float]:
    total = len(per_query)
    if total == 0:
        return {"recall_at_k": 0.0, "precision_at_k": 0.0, "mrr": 0.0, "query_count": 0.0}
    recall = sum(1 for item in per_query if item.get("hit")) / total
    precision_values = []
    reciprocal_ranks = []
    for item in per_query:
        expected_count = max(1, len(item.get("expected_ids") or []))
        precision_values.append(float(item.get("hit_count") or 0) / min(top_k, expected_count))
        rank = item.get("first_rank")
        reciprocal_ranks.append(1.0 / float(rank) if isinstance(rank, int) and rank > 0 else 0.0)
    return {
        "recall_at_k": recall,
        "precision_at_k": sum(precision_values) / total,
        "mrr": sum(reciprocal_ranks) / total,
        "query_count": float(total),
    }


def _evaluate_quality_budgets(metrics: Dict[str, float], budgets: Dict[str, float]) -> Dict[str, Dict[str, Any]]:
    results: Dict[str, Dict[str, Any]] = {}
    for key, threshold in budgets.items():
        value = float(metrics.get("query_count" if key == "min_query_count" else key) or 0.0)
        results[key] = {
            "value": value,
            "threshold": float(threshold),
            "relation": ">=",
            "ok": value >= float(threshold),
        }
    return results


def _first_relevant_rank(result_ids: Sequence[str], expected_ids: Sequence[str]) -> int:
    expected = set(expected_ids)
    for index, result_id in enumerate(result_ids, start=1):
        if result_id in expected:
            return index
    return 0


def _unproven_report(
    *,
    reason: str,
    corpus_path: Optional[Path],
    elapsed_ms: float,
    missing: List[str],
    corpus_id: str = "",
    encoder: Optional[Dict[str, Any]] = None,
    sample_count: int = 0,
) -> Dict[str, Any]:
    return {
        "version": RAG_QUALITY_EVAL_VERSION,
        "status": "unproven",
        "budget_status": "not_checked",
        "passed": False,
        "scope": "production_embedding_quality",
        "coverage": "missing_required_evidence",
        "corpus_id": corpus_id or None,
        "corpus_path": str(Path(corpus_path).resolve()) if corpus_path else None,
        "production_encoder": False,
        "labelled_corpus": "labelled_golden_corpus" not in missing,
        "sample_count": sample_count,
        "metrics": {},
        "budgets": {},
        "missing": missing,
        "reason": reason,
        "encoder": encoder or {},
        "no_network_call": True,
        "generated_at": time.time(),
        "elapsed_ms": elapsed_ms,
    }


class _quality_storage:
    def __init__(self, storage_dir: Optional[Path]):
        self.storage_dir = Path(storage_dir) if storage_dir is not None else None
        self._tmp: Optional[tempfile.TemporaryDirectory[str]] = None

    def __enter__(self) -> Path:
        if self.storage_dir is not None:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            return self.storage_dir
        self._tmp = tempfile.TemporaryDirectory(prefix="ttm-rag-quality-")
        return Path(self._tmp.name)

    def __exit__(self, *_args: Any) -> None:
        if self._tmp is not None:
            self._tmp.cleanup()


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000
