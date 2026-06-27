"""Runtime event envelope for internal communication.

The app has several event producers: ReAct, Agent layer transitions, AppServer,
and LLM feedback scripts. This module gives them a shared metadata envelope
without changing the existing SSE event shape consumed by the UI.
"""

from __future__ import annotations

import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Callable, Deque, Dict, List, Optional


RUNTIME_EVENT_SCHEMA_VERSION = 1


EventHandler = Callable[[Dict[str, Any]], None]


@dataclass(frozen=True)
class RuntimeEvent:
    type: str
    session_id: str
    payload: Dict[str, Any] = field(default_factory=dict)
    source: str = "runtime"
    channel: str = "session"
    correlation_id: str = ""
    parent_id: Optional[str] = None
    event_id: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        event_id = self.event_id or str(uuid.uuid4())[:12]
        correlation_id = self.correlation_id or self.session_id or event_id
        meta = {
            "schema_version": RUNTIME_EVENT_SCHEMA_VERSION,
            "event_id": event_id,
            "channel": self.channel,
            "source": self.source,
            "correlation_id": correlation_id,
            "parent_id": self.parent_id,
            "timestamp": self.timestamp,
        }
        return {
            "type": self.type,
            "session_id": self.session_id,
            "source": self.source,
            "payload": self.payload,
            "meta": meta,
        }


def envelope_event(
    event: Dict[str, Any],
    *,
    default_source: str = "runtime",
    default_channel: str = "session",
    correlation_id: str = "",
    parent_id: Optional[str] = None,
) -> Dict[str, Any]:
    if event.get("meta"):
        return event
    event_type = str(event.get("type", "unknown"))
    session_id = str(event.get("session_id", ""))
    source = str(event.get("source") or default_source)
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    return RuntimeEvent(
        type=event_type,
        session_id=session_id,
        payload=payload,
        source=source,
        channel=default_channel,
        correlation_id=correlation_id or session_id,
        parent_id=parent_id,
    ).to_dict()


def feedback_event(payload: Dict[str, Any], *, source: str = "llm_feedback") -> Dict[str, Any]:
    run_id = str(payload.get("artifact") or payload.get("provider") or uuid.uuid4())[-24:]
    return RuntimeEvent(
        type="llm_feedback",
        session_id="llm-feedback",
        payload=payload,
        source=source,
        channel="feedback",
        correlation_id=run_id,
    ).to_dict()


class RuntimeEventBus:
    """Small in-process event bus for decoupling runtime producers/consumers.

    The bus keeps the existing event dictionary shape, adds the shared envelope,
    synchronously fans events out to matching subscribers, and retains a bounded
    history for compact evidence/replay surfaces.
    """

    def __init__(self, *, history_limit: int = 500):
        self.history_limit = max(1, int(history_limit or 500))
        self._history: Deque[Dict[str, Any]] = deque(maxlen=self.history_limit)
        self._subscribers: Dict[str, Dict[str, Any]] = {}
        self._observer_error_count = 0
        self._observer_errors_by_handler: Dict[str, int] = {}
        self._last_observer_error: Optional[Dict[str, Any]] = None
        self._lock = RLock()

    def subscribe(
        self,
        handler: EventHandler,
        *,
        event_type: Optional[str] = None,
        channel: Optional[str] = None,
        session_id: Optional[str] = None,
        replay: bool = False,
    ) -> Callable[[], None]:
        subscriber_id = str(uuid.uuid4())
        record = {
            "handler": handler,
            "event_type": event_type,
            "channel": channel,
            "session_id": session_id,
        }
        replay_events: List[Dict[str, Any]] = []
        with self._lock:
            self._subscribers[subscriber_id] = record
            if replay:
                replay_events = [
                    event
                    for event in self._history
                    if self._matches(event, record)
                ]

        for event in replay_events:
            self._safe_call(handler, event)

        def unsubscribe() -> None:
            with self._lock:
                self._subscribers.pop(subscriber_id, None)

        return unsubscribe

    def publish(
        self,
        event: Dict[str, Any],
        *,
        default_source: str = "runtime",
        default_channel: str = "session",
        correlation_id: str = "",
        parent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        enveloped = envelope_event(
            event,
            default_source=default_source,
            default_channel=default_channel,
            correlation_id=correlation_id,
            parent_id=parent_id,
        )
        with self._lock:
            self._history.append(enveloped)
            subscribers = list(self._subscribers.values())
        for subscriber in subscribers:
            if self._matches(enveloped, subscriber):
                self._safe_call(subscriber["handler"], enveloped)
        return enveloped

    def replay(
        self,
        *,
        event_type: Optional[str] = None,
        channel: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        criteria = {
            "event_type": event_type,
            "channel": channel,
            "session_id": session_id,
        }
        with self._lock:
            events = [
                event
                for event in self._history
                if self._matches(event, criteria)
            ]
        if limit > 0:
            return events[-limit:]
        return events

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "schema_version": RUNTIME_EVENT_SCHEMA_VERSION,
                "history_size": len(self._history),
                "history_limit": self.history_limit,
                "subscriber_count": len(self._subscribers),
                "observer_error_count": self._observer_error_count,
                "observer_errors_by_handler": dict(self._observer_errors_by_handler),
                "last_observer_error": dict(self._last_observer_error) if self._last_observer_error else None,
            }

    @staticmethod
    def _matches(event: Dict[str, Any], criteria: Dict[str, Any]) -> bool:
        meta = event.get("meta") if isinstance(event.get("meta"), dict) else {}
        if criteria.get("event_type") and event.get("type") != criteria["event_type"]:
            return False
        if criteria.get("channel") and meta.get("channel") != criteria["channel"]:
            return False
        if criteria.get("session_id") and event.get("session_id") != criteria["session_id"]:
            return False
        return True

    def _safe_call(self, handler: EventHandler, event: Dict[str, Any]) -> None:
        try:
            handler(event)
        except Exception as exc:
            # Observers must not break the runtime path. Record compact
            # diagnostics so engineering-control surfaces can detect drift.
            handler_name = self._handler_name(handler)
            meta = event.get("meta") if isinstance(event.get("meta"), dict) else {}
            with self._lock:
                self._observer_error_count += 1
                self._observer_errors_by_handler[handler_name] = (
                    self._observer_errors_by_handler.get(handler_name, 0) + 1
                )
                self._last_observer_error = {
                    "handler": handler_name,
                    "error_type": exc.__class__.__name__,
                    "error": str(exc),
                    "event_type": event.get("type"),
                    "session_id": event.get("session_id"),
                    "event_id": meta.get("event_id"),
                    "timestamp": time.time(),
                }
            return

    @staticmethod
    def _handler_name(handler: EventHandler) -> str:
        module = getattr(handler, "__module__", "")
        qualname = getattr(handler, "__qualname__", "") or getattr(handler, "__name__", "")
        if not qualname and hasattr(handler, "__class__"):
            qualname = handler.__class__.__name__
        return f"{module}.{qualname}".strip(".")
