"""Bus-backed runtime metrics observer.

This module gives AppServer a decoupled consumer of RuntimeEventBus events.
SQLite remains the durable source for replay after restart; the observer is the
live, subscription-backed view used by project-management and readiness
surfaces while a process is running.
"""

from __future__ import annotations

import threading
from collections import defaultdict, deque
from typing import Any, Deque, Dict, List, Optional

from core.runtime_events import RuntimeEventBus


class RuntimeMetricsObserver:
    """Maintain compact session runtime metrics from bus events."""

    def __init__(self, bus: RuntimeEventBus, *, history_limit: int = 200):
        self.bus = bus
        self.history_limit = max(1, int(history_limit or 200))
        self._lock = threading.RLock()
        self._history: Dict[str, Deque[Dict[str, Any]]] = defaultdict(lambda: deque(maxlen=self.history_limit))
        self._event_count = 0
        self._unsubscribe = bus.subscribe(self._handle_event, channel="session", replay=True)

    def close(self) -> None:
        self._unsubscribe()

    def history(self, session_id: str, *, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            history = list(self._history.get(session_id, []))
        if limit > 0:
            return history[-limit:]
        return history

    def summary(self, session_id: str, *, limit: int = 100) -> Dict[str, Any]:
        metrics = self.history(session_id, limit=limit)
        latest_by_kind: Dict[str, Dict[str, Any]] = {}
        for item in metrics:
            latest_by_kind[str(item.get("kind") or "unknown")] = item
        with self._lock:
            observed_sessions = len(self._history)
            observed_event_count = self._event_count
        return {
            "source": "runtime_event_bus_observer",
            "event_count": len(metrics),
            "observed_event_count": observed_event_count,
            "observed_session_count": observed_sessions,
            "history_limit": self.history_limit,
            "latest_by_kind": latest_by_kind,
        }

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "status": "ready",
                "source": "runtime_event_bus_observer",
                "observed_event_count": self._event_count,
                "observed_session_count": len(self._history),
                "history_limit": self.history_limit,
            }

    def _handle_event(self, event: Dict[str, Any]) -> None:
        metric = runtime_metric_from_event(event)
        if metric is None:
            return
        session_id = str(event.get("session_id") or "")
        if not session_id:
            return
        with self._lock:
            self._history[session_id].append(metric)
            self._event_count += 1


def runtime_metric_from_event(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    event_type = event.get("type")
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    meta = event.get("meta") if isinstance(event.get("meta"), dict) else {}
    metric: Optional[Dict[str, Any]] = None

    if event_type == "latency":
        metric = {
            "kind": "latency",
            "phase": payload.get("phase"),
            "iteration": payload.get("iteration"),
            "elapsed_ms": payload.get("elapsed_ms"),
            "tool": payload.get("tool"),
            "ok": payload.get("ok"),
            "source_phase": payload.get("source_phase"),
        }
    elif event_type == "llm_usage":
        metric = {
            "kind": "llm_usage",
            "phase": payload.get("phase"),
            "provider": payload.get("provider"),
            "mode": payload.get("mode"),
            "prompt_tokens": payload.get("prompt_tokens"),
            "completion_tokens": payload.get("completion_tokens"),
            "total_tokens": payload.get("total_tokens"),
            "generate_ms": payload.get("generate_ms"),
            "tokens_per_sec": payload.get("tokens_per_sec"),
            "error_type": payload.get("error_type"),
        }
    elif event_type == "tool_selection":
        stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
        tools = payload.get("tools") if isinstance(payload.get("tools"), list) else []
        metric = {
            "kind": "tool_selection",
            "phase": payload.get("phase") or "think",
            "iteration": payload.get("iteration"),
            "candidate_count": stats.get("candidate_count"),
            "selected_count": stats.get("selected_count") or len(tools),
            "ranking_ms": stats.get("ranking_ms"),
            "cache_hit": stats.get("cache_hit"),
            "cache_size": stats.get("cache_size"),
            "tools": [
                {
                    "name": tool.get("name"),
                    "source": tool.get("source"),
                }
                for tool in tools[:8]
                if isinstance(tool, dict)
            ],
        }
    elif event_type == "context_budget":
        metric = {
            "kind": "context_budget",
            "phase": payload.get("phase"),
            "iteration": payload.get("iteration"),
            "token_count": payload.get("token_count"),
            "n_ctx": payload.get("n_ctx"),
            "token_usage_ratio": payload.get("token_usage_ratio"),
            "context_window_ratio": payload.get("context_window_ratio"),
            "compression_applied": payload.get("compression_applied"),
            "dropped_parts": payload.get("dropped_parts"),
            "truncated_chars": payload.get("truncated_chars"),
            "token_cache_hits": payload.get("token_cache_hits"),
            "token_cache_misses": payload.get("token_cache_misses"),
            "token_cache_size": payload.get("token_cache_size"),
            "agents_md_hits": payload.get("agents_md_hits"),
            "cold_recall_hits": payload.get("cold_recall_hits"),
            "agents_md_ms": payload.get("agents_md_ms"),
            "cold_recall_ms": payload.get("cold_recall_ms"),
            "context_build_ms": payload.get("context_build_ms"),
        }

    if metric is None:
        return None
    metric["timestamp"] = meta.get("timestamp") or event.get("created_at")
    metric["event_id"] = meta.get("event_id")
    metric["source"] = event.get("source")
    return metric
