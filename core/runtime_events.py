"""Runtime event envelope for internal communication.

The app has several event producers: ReAct, Agent layer transitions, AppServer,
and LLM feedback scripts. This module gives them a shared metadata envelope
without changing the existing SSE event shape consumed by the UI.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


RUNTIME_EVENT_SCHEMA_VERSION = 1


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
