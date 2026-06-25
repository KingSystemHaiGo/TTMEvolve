"""
Typed layer event contract for the three-layer agent runtime.

These events are both UI state and audit material: they describe which layer is
talking to which layer, why the transition happened, and the small set of
metrics needed to diagnose latency, repair, and learning flow.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


LAYER_EVENT_SCHEMA_VERSION = 1
VALID_LAYERS = {"user", "agent", "runtime", "learning", "storage"}
VALID_STATES = {"idle", "active", "done", "error"}


@dataclass(frozen=True)
class LayerEvent:
    session_id: str
    layer: str
    state: str
    event: str
    detail: str = ""
    source_layer: str = "runtime"
    target_layer: Optional[str] = None
    correlation_id: str = ""
    cause: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def payload(self) -> Dict[str, Any]:
        layer = self.layer if self.layer in VALID_LAYERS else "runtime"
        source_layer = self.source_layer if self.source_layer in VALID_LAYERS else "runtime"
        target_layer = self.target_layer or layer
        if target_layer not in VALID_LAYERS:
            target_layer = layer
        state = self.state if self.state in VALID_STATES else "idle"
        return {
            "schema_version": LAYER_EVENT_SCHEMA_VERSION,
            "layer": layer,
            "state": state,
            "event": self.event,
            "detail": self.detail,
            "source_layer": source_layer,
            "target_layer": target_layer,
            "correlation_id": self.correlation_id or str(uuid.uuid4())[:8],
            "cause": self.cause,
            "metrics": self.metrics or {},
            "timestamp": self.timestamp,
        }

    def to_turn_event(self) -> Dict[str, Any]:
        return {
            "type": "layer",
            "session_id": self.session_id,
            "source": self.source_layer,
            "payload": self.payload(),
        }


def make_layer_event(
    session_id: str,
    layer: str,
    state: str,
    event: str,
    detail: str = "",
    *,
    source_layer: str = "runtime",
    target_layer: Optional[str] = None,
    correlation_id: str = "",
    cause: str = "",
    metrics: Optional[Dict[str, Any]] = None,
) -> LayerEvent:
    return LayerEvent(
        session_id=session_id,
        layer=layer,
        state=state,
        event=event,
        detail=detail,
        source_layer=source_layer,
        target_layer=target_layer,
        correlation_id=correlation_id,
        cause=cause,
        metrics=metrics or {},
    )
