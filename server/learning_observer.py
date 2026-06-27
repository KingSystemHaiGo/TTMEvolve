"""Bus-backed learning layer observer.

The observer derives compact Learning-layer state from public RuntimeEventBus
events. It does not read TapMakerAgent private job dictionaries, so readiness
and evidence surfaces can inspect learning progress through the same bus spine
used by runtime/project observers.
"""

from __future__ import annotations

import threading
from collections import defaultdict, deque
from typing import Any, Deque, Dict, List, Optional

from core.runtime_events import RuntimeEventBus


class LearningStateObserver:
    """Maintain session learning state from bus layer events."""

    def __init__(self, bus: RuntimeEventBus, *, history_limit: int = 100):
        self.bus = bus
        self.history_limit = max(1, int(history_limit or 100))
        self._lock = threading.RLock()
        self._history: Dict[str, Deque[Dict[str, Any]]] = defaultdict(lambda: deque(maxlen=self.history_limit))
        self._latest: Dict[str, Dict[str, Any]] = {}
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

    def summary(self, session_id: str) -> Dict[str, Any]:
        with self._lock:
            latest = dict(self._latest.get(session_id, {}))
            observed_sessions = len(self._latest)
            observed_event_count = self._event_count
        if not latest:
            return {
                "status": "missing",
                "source": "runtime_event_bus_learning_observer",
                "session_id": session_id,
                "observed_event_count": observed_event_count,
                "observed_session_count": observed_sessions,
            }
        latest["status"] = latest.get("status") or "ready"
        latest["source"] = "runtime_event_bus_learning_observer"
        latest["session_id"] = session_id
        latest["observed_event_count"] = observed_event_count
        latest["observed_session_count"] = observed_sessions
        return latest

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "status": "ready",
                "source": "runtime_event_bus_learning_observer",
                "observed_event_count": self._event_count,
                "observed_session_count": len(self._latest),
                "history_limit": self.history_limit,
            }

    def _handle_event(self, event: Dict[str, Any]) -> None:
        update = learning_update_from_event(event)
        if update is None:
            return
        session_id = str(event.get("session_id") or "")
        if not session_id:
            return
        with self._lock:
            self._history[session_id].append(update)
            self._latest[session_id] = update
            self._event_count += 1


def learning_update_from_event(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if event.get("type") != "layer":
        return None
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    if payload.get("layer") != "learning":
        return None
    meta = event.get("meta") if isinstance(event.get("meta"), dict) else {}
    event_name = str(payload.get("event") or "")
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    return {
        "state": payload.get("state"),
        "event": event_name,
        "detail": payload.get("detail"),
        "source_layer": payload.get("source_layer"),
        "target_layer": payload.get("target_layer"),
        "cause": payload.get("cause"),
        "async": metrics.get("async"),
        "eligible": metrics.get("eligible"),
        "elapsed_ms": metrics.get("elapsed_ms"),
        "error": metrics.get("error"),
        "event_id": meta.get("event_id"),
        "timestamp": meta.get("timestamp") or event.get("created_at"),
    }
