from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.runtime_events import (
    RUNTIME_EVENT_SCHEMA_VERSION,
    RuntimeEventBus,
    envelope_event,
    feedback_event,
)


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


def test_runtime_event_bus_filters_and_replays_by_session_channel_and_type():
    bus = RuntimeEventBus(history_limit=10)
    seen = []
    bus.subscribe(
        seen.append,
        event_type="status",
        channel="session",
        session_id="s1",
    )

    event = bus.publish({"type": "status", "session_id": "s1", "payload": {"message": "one"}})
    bus.publish({"type": "status", "session_id": "s2", "payload": {"message": "two"}})
    bus.publish({"type": "llm_feedback", "session_id": "s1", "payload": {}}, default_channel="feedback")

    assert seen == [event]
    assert event["meta"]["schema_version"] == RUNTIME_EVENT_SCHEMA_VERSION
    assert event["meta"]["channel"] == "session"
    assert bus.replay(session_id="s1", channel="session") == [event]
    assert bus.stats()["history_size"] == 3
    assert bus.stats()["subscriber_count"] == 1


def test_runtime_event_bus_replay_on_subscribe_and_unsubscribe():
    bus = RuntimeEventBus(history_limit=3)
    for index in range(4):
        bus.publish({"type": "status", "session_id": "s1", "payload": {"index": index}})

    replayed = []
    unsubscribe = bus.subscribe(replayed.append, session_id="s1", replay=True)

    assert [event["payload"]["index"] for event in replayed] == [1, 2, 3]

    unsubscribe()
    bus.publish({"type": "status", "session_id": "s1", "payload": {"index": 4}})

    assert [event["payload"]["index"] for event in replayed] == [1, 2, 3]
    assert [event["payload"]["index"] for event in bus.replay(session_id="s1", limit=0)] == [2, 3, 4]


def test_runtime_event_bus_observer_errors_do_not_break_publish():
    bus = RuntimeEventBus()
    seen = []

    def broken(_event):
        raise RuntimeError("observer failed")

    bus.subscribe(broken)
    bus.subscribe(seen.append)

    event = bus.publish({"type": "status", "session_id": "s1", "payload": {"ok": True}})

    assert seen == [event]
