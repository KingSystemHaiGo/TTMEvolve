from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.runtime_events import RUNTIME_EVENT_SCHEMA_VERSION, envelope_event, feedback_event


def test_envelope_event_adds_shared_metadata():
    event = envelope_event(
        {"type": "status", "session_id": "s1", "payload": {"message": "started"}},
        default_source="react",
    )

    assert event["type"] == "status"
    assert event["source"] == "react"
    assert event["meta"]["schema_version"] == RUNTIME_EVENT_SCHEMA_VERSION
    assert event["meta"]["channel"] == "session"
    assert event["meta"]["correlation_id"] == "s1"
    assert event["meta"]["event_id"]


def test_feedback_event_uses_feedback_channel():
    event = feedback_event({"ok": False, "failure_type": "timeout", "provider": "mock"})

    assert event["type"] == "llm_feedback"
    assert event["session_id"] == "llm-feedback"
    assert event["meta"]["channel"] == "feedback"
    assert event["payload"]["failure_type"] == "timeout"
