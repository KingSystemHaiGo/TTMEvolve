"""Bus-backed memory and RAG observer.

Context-budget events already carry the compact retrieval evidence produced by
MemoryManager. This observer turns those events into a live per-session memory
view without coupling Evidence surfaces to ReActLoop internals.
"""

from __future__ import annotations

import threading
from collections import defaultdict, deque
from typing import Any, Deque, Dict, List, Optional

from core.runtime_events import RuntimeEventBus


class MemoryRecallObserver:
    """Maintain compact RAG/memory recall metrics from context_budget events."""

    def __init__(self, bus: RuntimeEventBus, *, history_limit: int = 200):
        self.bus = bus
        self.history_limit = max(1, int(history_limit or 200))
        self._lock = threading.RLock()
        self._history: Dict[str, Deque[Dict[str, Any]]] = defaultdict(lambda: deque(maxlen=self.history_limit))
        self._event_count = 0
        self._unsubscribe = bus.subscribe(self._handle_event, event_type="context_budget", channel="session", replay=True)

    def close(self) -> None:
        self._unsubscribe()

    def history(self, session_id: str, *, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            history = list(self._history.get(session_id, []))
        if limit > 0:
            return history[-limit:]
        return history

    def summary(self, session_id: str, *, limit: int = 100) -> Dict[str, Any]:
        history = self.history(session_id, limit=limit)
        with self._lock:
            observed_sessions = len(self._history)
            observed_event_count = self._event_count
        return summarize_memory_recall_history(
            history,
            session_id=session_id,
            source="runtime_event_bus_memory_observer",
            status="ready" if history else "missing",
            observed_event_count=observed_event_count,
            observed_session_count=observed_sessions,
            history_limit=self.history_limit,
        )

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "status": "ready",
                "source": "runtime_event_bus_memory_observer",
                "observed_event_count": self._event_count,
                "observed_session_count": len(self._history),
                "history_limit": self.history_limit,
            }

    def _handle_event(self, event: Dict[str, Any]) -> None:
        metric = memory_metric_from_event(event)
        if metric is None:
            return
        session_id = str(event.get("session_id") or "")
        if not session_id:
            return
        with self._lock:
            self._history[session_id].append(metric)
            self._event_count += 1


def memory_metric_from_event(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if event.get("type") != "context_budget":
        return None
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    meta = event.get("meta") if isinstance(event.get("meta"), dict) else {}
    return {
        "phase": payload.get("phase"),
        "iteration": payload.get("iteration"),
        "workspace_profile": payload.get("workspace_profile") or "general",
        "agents_md_hits": payload.get("agents_md_hits"),
        "cold_recall_hits": payload.get("cold_recall_hits"),
        "agents_md_ms": payload.get("agents_md_ms"),
        "cold_recall_ms": payload.get("cold_recall_ms"),
        "context_build_ms": payload.get("context_build_ms"),
        "token_cache_hits": payload.get("token_cache_hits"),
        "token_cache_misses": payload.get("token_cache_misses"),
        "token_cache_size": payload.get("token_cache_size"),
        "token_usage_ratio": payload.get("token_usage_ratio"),
        "context_window_ratio": payload.get("context_window_ratio"),
        "compression_applied": payload.get("compression_applied"),
        "event_id": meta.get("event_id"),
        "timestamp": meta.get("timestamp") or event.get("created_at"),
    }


def memory_metric_from_runtime_metric(metric: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if metric.get("kind") != "context_budget":
        return None
    return {
        "phase": metric.get("phase"),
        "iteration": metric.get("iteration"),
        "workspace_profile": metric.get("workspace_profile") or "general",
        "agents_md_hits": metric.get("agents_md_hits"),
        "cold_recall_hits": metric.get("cold_recall_hits"),
        "agents_md_ms": metric.get("agents_md_ms"),
        "cold_recall_ms": metric.get("cold_recall_ms"),
        "context_build_ms": metric.get("context_build_ms"),
        "token_cache_hits": metric.get("token_cache_hits"),
        "token_cache_misses": metric.get("token_cache_misses"),
        "token_cache_size": metric.get("token_cache_size"),
        "token_usage_ratio": metric.get("token_usage_ratio"),
        "context_window_ratio": metric.get("context_window_ratio"),
        "compression_applied": metric.get("compression_applied"),
        "timestamp": metric.get("timestamp"),
    }


def summarize_memory_recall_history(
    history: List[Dict[str, Any]],
    *,
    session_id: str,
    source: str,
    status: str,
    observed_event_count: int = 0,
    observed_session_count: int = 0,
    history_limit: Optional[int] = None,
) -> Dict[str, Any]:
    latest = history[-1] if history else {}
    total_cold_hits = sum(_number(item.get("cold_recall_hits")) for item in history)
    total_agents_hits = sum(_number(item.get("agents_md_hits")) for item in history)
    max_cold_ms = max([_number(item.get("cold_recall_ms")) for item in history] or [0])
    max_context_ms = max([_number(item.get("context_build_ms")) for item in history] or [0])
    profiles = sorted({str(item.get("workspace_profile") or "general") for item in history})
    return {
        "status": status,
        "source": source,
        "session_id": session_id,
        "event_count": len(history),
        "observed_event_count": observed_event_count,
        "observed_session_count": observed_session_count,
        "history_limit": history_limit,
        "workspace_profiles": profiles,
        "latest": latest,
        "totals": {
            "cold_recall_hits": total_cold_hits,
            "agents_md_hits": total_agents_hits,
        },
        "max_latency": {
            "cold_recall_ms": max_cold_ms,
            "context_build_ms": max_context_ms,
        },
    }


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0
