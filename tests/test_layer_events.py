from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent.agent import TapMakerAgent
from core.config import Config
from core.layer_events import LAYER_EVENT_SCHEMA_VERSION, make_layer_event
from llm.mock_llm import MockLLM


class SlowReflectMockLLM(MockLLM):
    def reflect(self, prompt: str) -> str:
        time.sleep(0.25)
        return super().reflect(prompt)


def _make_agent(root: Path, *, async_learning: bool = True) -> TapMakerAgent:
    config_path = root / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "project_root": str(root / "project"),
                "storage_root": str(root / "storage"),
                "llm": {"provider": "mock"},
                "sandbox": {"mode": "workspace-write"},
                "approval": {"policy": "never"},
                "expert": {"enabled": False},
                "learning": {"skill_generation_enabled": False, "async_enabled": async_learning},
                "agents_md": {"dynamic_tools_enabled": False},
            }
        ),
        encoding="utf-8",
    )
    cfg = Config(str(config_path))
    return TapMakerAgent(
        llm=MockLLM([{"done": True, "output": "ok"}]),
        config=cfg,
        connect_mcp=False,
    )


def test_layer_event_contract_normalizes_payload():
    event = make_layer_event(
        session_id="s1",
        layer="agent",
        state="active",
        event="agent.run.started",
        detail="planning",
        source_layer="user",
        target_layer="agent",
        correlation_id="corr-1",
        cause="user_task",
        metrics={"task_chars": 12},
    ).to_turn_event()

    assert event["type"] == "layer"
    assert event["source"] == "user"
    payload = event["payload"]
    assert payload["schema_version"] == LAYER_EVENT_SCHEMA_VERSION
    assert payload["layer"] == "agent"
    assert payload["state"] == "active"
    assert payload["source_layer"] == "user"
    assert payload["target_layer"] == "agent"
    assert payload["correlation_id"] == "corr-1"
    assert payload["cause"] == "user_task"
    assert payload["metrics"]["task_chars"] == 12


def test_agent_run_emits_ordered_layer_handoff_events():
    with tempfile.TemporaryDirectory() as tmp:
        agent = _make_agent(Path(tmp))
        bus_events = []
        agent.event_bus.subscribe(bus_events.append, session_id="layer-test")
        result = agent.run("make a tiny scene", session_id="layer-test")
        events = [
            event["payload"]
            for event in agent.get_events("layer-test")
            if event.get("type") == "layer"
        ]
        bus_types = [event.get("type") for event in bus_events]

        assert result["output"] == "ok"
        assert "status" in bus_types
        assert "output" in bus_types
        assert [event.get("type") for event in agent.get_events("layer-test")] == bus_types
        assert all(event.get("meta", {}).get("channel") == "session" for event in bus_events)
        assert [event["event"] for event in events] == [
            "agent.run.started",
            "agent.run.finished",
            "runtime.audit.started",
            "runtime.audit.finished",
            "learning.reflection.skipped",
        ]
        assert {event["correlation_id"] for event in events} == {"layer-test"}
        assert events[1]["source_layer"] == "agent"
        assert events[1]["target_layer"] == "runtime"
        assert events[3]["source_layer"] == "runtime"
        assert events[3]["target_layer"] == "learning"
        assert events[3]["metrics"]["health_status"] in {"healthy", "degraded", "stalled", "crashed"}
        assert result["learning_job"]["status"] == "skipped"


def test_agent_event_bus_replays_layer_events_without_direct_queue_access():
    with tempfile.TemporaryDirectory() as tmp:
        agent = _make_agent(Path(tmp))
        agent.run("make a tiny scene", session_id="replay-layer")

        replay = agent.event_bus.replay(session_id="replay-layer", event_type="layer", limit=0)

        assert [event["payload"]["event"] for event in replay] == [
            "agent.run.started",
            "agent.run.finished",
            "runtime.audit.started",
            "runtime.audit.finished",
            "learning.reflection.skipped",
        ]
        assert all(event["meta"]["correlation_id"] == "replay-layer" for event in replay)


def test_agent_learning_layer_runs_async_after_result():
    with tempfile.TemporaryDirectory() as tmp:
        agent = _make_agent(Path(tmp), async_learning=True)

        def noop(**kwargs):
            return {"ok": True, "tool": "noop"}

        agent.executor.register_dynamic_tool("noop", noop, risk_level="low")
        agent.tools.register(
            name="noop",
            description="no operation",
            parameters={"type": "object", "properties": {}},
            handler=agent.executor.propose_action,
        )
        agent.set_llm(SlowReflectMockLLM([
            {"tool": "noop", "params": {}},
            {"done": True, "output": "ok"},
        ]))

        started_at = time.perf_counter()
        result = agent.run("run noop then learn", session_id="async-layer")
        elapsed = time.perf_counter() - started_at

        assert result["output"] == "ok"
        assert result["learning_job"]["async"] is True
        assert result["learning_job"]["status"] in {"queued", "running"}
        assert elapsed < 0.25

        deadline = time.time() + 30
        while time.time() < deadline:
            if agent.get_learning_job("async-layer").get("status") == "done":
                break
            time.sleep(0.02)

        job = agent.get_learning_job("async-layer")
        events = [
            event["payload"]["event"]
            for event in agent.get_events("async-layer")
            if event.get("type") == "layer" and event.get("payload", {}).get("layer") == "learning"
        ]
        assert job["status"] == "done"
        assert "learning.reflection.queued" in events
        assert "learning.reflection.started" in events
        assert "learning.reflection.finished" in events


def test_agent_exposes_maker_briefing_tool():
    with tempfile.TemporaryDirectory() as tmp:
        agent = _make_agent(Path(tmp))

        assert agent.tools.has("maker_briefing")
        briefing = agent.maker_briefing(session_id="brief1", task="build Maker project")

        assert briefing["version"] == "maker-briefing.v1"
        assert briefing["readiness"] == "disconnected"
        assert briefing["authority"] == "local_files"
        assert briefing["evidence_endpoints"]["maker_briefing"] == "/agent/maker-briefing?session_id=brief1"
