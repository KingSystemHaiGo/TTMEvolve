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
from server.project_observer import ProjectManagementObserver
from server.runtime_observer import RuntimeMetricsObserver


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


def test_runtime_metrics_observer_subscribes_to_bus_without_store():
    bus = RuntimeEventBus()
    observer = RuntimeMetricsObserver(bus, history_limit=5)

    bus.publish({
        "type": "context_budget",
        "session_id": "metrics-bus",
        "payload": {
            "phase": "think",
            "iteration": 0,
            "token_cache_hits": 4,
            "token_cache_misses": 1,
            "context_build_ms": 8.5,
        },
    })
    bus.publish({
        "type": "tool_selection",
        "session_id": "metrics-bus",
        "payload": {
            "phase": "action",
            "iteration": 0,
            "stats": {
                "candidate_count": 12,
                "selected_count": 3,
                "ranking_ms": 2.5,
                "cache_hit": True,
            },
            "tools": [{"name": "project_status", "source": "builtin"}],
        },
    })

    history = observer.history("metrics-bus", limit=0)
    summary = observer.summary("metrics-bus", limit=0)

    assert [item["kind"] for item in history] == ["context_budget", "tool_selection"]
    assert history[0]["token_cache_hits"] == 4
    assert history[1]["selected_count"] == 3
    assert summary["source"] == "runtime_event_bus_observer"
    assert summary["event_count"] == 2
    assert summary["latest_by_kind"]["tool_selection"]["candidate_count"] == 12
    assert observer.stats()["observed_session_count"] == 1

    observer.close()


def test_project_management_observer_derives_next_action_from_context_sync():
    bus = RuntimeEventBus()
    observer = ProjectManagementObserver(bus)

    bus.publish({
        "type": "context_sync",
        "session_id": "project-bus",
        "payload": {
            "snapshot": {
                "task": "ship project controls",
                "iteration": 4,
                "workspace_profile": "coding",
                "last_tool": "modify_file",
                "plan_validation": {"verdict": "warn", "summary": "needs proof", "issues_count": 1},
                "goal_checklist": {
                    "overall": "active",
                    "counts": {"done": 2, "pending": 1},
                    "next_focus": "Run focused observer tests",
                },
                "continuation_checkpoint": {
                    "resume_ready": True,
                    "resume_mode": "context_handoff",
                    "open_plan_steps": [
                        {"id": "verify", "title": "Run focused observer tests", "status": "pending"}
                    ],
                    "artifact_count": 1,
                    "artifact_refs": [{"path": "server/project_observer.py"}],
                    "compression": {"needed": True},
                },
            },
        },
    })

    snapshot = observer.snapshot("project-bus")

    assert snapshot["status"] == "ready"
    assert snapshot["source"] == "runtime_event_bus_project_observer"
    assert snapshot["task"] == "ship project controls"
    assert snapshot["next_action"] == "Run focused observer tests"
    assert snapshot["plan_verdict"] == "warn"
    assert snapshot["continuation"]["resume_ready"] is True
    assert "plan_warn" in snapshot["risk_flags"]
    assert "compression_needed" in snapshot["risk_flags"]
    assert observer.stats()["observed_session_count"] == 1

    observer.close()
