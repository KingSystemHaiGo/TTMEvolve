"""
tests/test_app_server_resume.py — App Server 会话持久化与重连回放测试
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.config import Config
from core.intent_classifier import classify_cos_gate
from core.runtime_events import RuntimeEventBus
from llm.llm_factory import LLMFactory
from llm.api_errors import LLMTimeoutError
from llm.mock_llm import MockLLM
from server.app_server import AppServer, Session
from server.approval_bridge import ApprovalBridge
from agent.agent import TapMakerAgent
from server.protocol import SessionRequest
from server.session_store import SessionStore


def _make_server(tmp_path: Path, port: int) -> AppServer:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "project_root": str(tmp_path / "project"),
                "storage_root": str(tmp_path / "storage"),
                "llm": {"provider": "mock"},
                "sandbox": {"mode": "workspace-write"},
                "approval": {"policy": "never"},
                "expert": {"enabled": False},
                "rescue": {
                    "max_consecutive_errors": 3,
                    "max_iterations_ratio": 0.75,
                    "detect_repeated_actions": False,
                    "health_degraded": False,
                    "max_rescue_per_session": 1,
                    "cooldown_seconds": 0,
                    "distill_after_rescue": False,
                },
                "learning": {"skill_generation_enabled": False},
            }
        ),
        encoding="utf-8",
    )
    cfg = Config(str(config_path))
    llm = LLMFactory.create("mock", cfg)
    agent = TapMakerAgent(llm=llm, config=cfg, human_confirm_callback=None)
    store = SessionStore(Path(cfg.storage_root()) / "sessions.db")
    return AppServer(agent, host="127.0.0.1", port=port, approval_bridge=ApprovalBridge(), session_store=store)


class _SlowMockLLM(MockLLM):
    def choose_action(self, task: str, thought: str, tools_description: str) -> Dict[str, Any]:
        time.sleep(0.5)
        return {"done": True, "output": f"slow done: {task}"}


class _TimeoutMockLLM(MockLLM):
    def think(self, task: str, context: str, trajectory, tools_description: str) -> str:
        raise LLMTimeoutError("provider timed out")

    def last_call_stats(self) -> Dict[str, Any]:
        return {
            "provider": "mock-timeout",
            "model": "mock",
            "mode": "api",
            "error_type": "timeout",
            "generate_ms": 123.4,
            "total_tokens": 0,
        }


def test_session_emit_publishes_to_runtime_event_bus_and_store():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = SessionStore(root / "sessions.db")
        store.create_session("s-bus", "bus task")
        bus = RuntimeEventBus()
        seen = []
        bus.subscribe(seen.append, session_id="s-bus")
        session = Session("s-bus", "bus task", store=store, event_bus=bus)

        session.emit({"type": "status", "session_id": "s-bus", "payload": {"message": "started"}})
        queued = next(session.iter_events(timeout=0.01))
        stored = store.get_events("s-bus")

        assert queued["type"] == "status"
        assert queued["meta"]["channel"] == "session"
        assert seen == [queued]
        assert stored[0]["type"] == "status"
        assert stored[0]["meta"]["event_id"] == queued["meta"]["event_id"]
        assert bus.replay(session_id="s-bus") == [queued]


def test_app_server_sessions_share_runtime_event_bus():
    with tempfile.TemporaryDirectory() as tmp:
        server = _make_server(Path(tmp), port=0)
        seen = []
        server.event_bus.subscribe(seen.append, session_id="shared-bus")

        sid = server.create_session(SessionRequest(task="bus task", session_id="shared-bus"))
        session = server.get_session(sid)
        assert session is not None
        session.emit({"type": "status", "session_id": sid, "payload": {"message": "ready"}})

        assert len(seen) == 2
        assert seen[0]["session_id"] == "shared-bus"
        assert seen[0]["type"] == "cos_gate"
        assert seen[1]["type"] == "status"
        assert server.event_bus.replay(session_id="shared-bus") == seen


def test_app_server_create_session_persists_cos_gate_event():
    with tempfile.TemporaryDirectory() as tmp:
        server = _make_server(Path(tmp), port=0)

        sid = server.create_session(SessionRequest(
            task="对代码做审计，模块解耦，设计内部通信总线并优化 RAG 记忆加载",
            session_id="cosgate1",
        ))

        events = server.session_store.get_events(sid)
        gate_events = [event for event in events if event.get("type") == "cos_gate"]

        assert len(gate_events) == 1
        payload = gate_events[0]["payload"]
        assert payload["task_type"] == "refactor_optimization"
        assert payload["level"] == "XL"
        assert payload["mode"] == "System 2"
        assert "分类: 重构优化" in payload["declaration"]
        assert server.event_bus.replay(session_id=sid)[0]["type"] == "cos_gate"


def test_app_server_runtime_metrics_endpoint_uses_bus_observer():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        port = 17374
        server = _make_server(tmp_path, port)
        sid = server.create_session(SessionRequest(task="observe runtime", session_id="observer1"))
        session = server.get_session(sid)
        assert session is not None
        session.emit({
            "type": "context_budget",
            "session_id": sid,
            "payload": {
                "phase": "think",
                "iteration": 0,
                "token_cache_hits": 7,
                "token_cache_misses": 2,
                "context_build_ms": 6.5,
            },
        })
        session.emit({
            "type": "tool_selection",
            "session_id": sid,
            "payload": {
                "phase": "action",
                "iteration": 0,
                "stats": {
                    "candidate_count": 9,
                    "selected_count": 2,
                    "ranking_ms": 1.5,
                    "cache_hit": True,
                    "cache_size": 3,
                },
            },
        })
        thread = threading.Thread(target=server.start, daemon=True)
        thread.start()
        time.sleep(1)

        try:
            data = _get_json(f"http://127.0.0.1:{port}/sessions/observer1/runtime-metrics?steps=10")

            assert data["source"] == "runtime_event_bus_observer"
            assert data["observer"]["status"] == "ready"
            assert data["observer_count"] == 2
            assert data["store_count"] == 2
            assert data["summary"]["token_cache"]["hits"] == 7
            assert data["summary"]["tool_ranking"]["selected_count"] == 2
        finally:
            server.stop()


def test_app_server_project_state_endpoint_uses_bus_observer():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        port = 17375
        server = _make_server(tmp_path, port)
        sid = server.create_session(SessionRequest(task="control project", session_id="projectstate1"))
        session = server.get_session(sid)
        assert session is not None
        session.emit({
            "type": "context_sync",
            "session_id": sid,
            "payload": {
                "snapshot": {
                    "task": "control project",
                    "iteration": 3,
                    "workspace_profile": "coding",
                    "last_tool": "modify_file",
                    "plan_validation": {"verdict": "pass", "summary": "checked", "issues_count": 0},
                    "goal_checklist": {
                        "overall": "active",
                        "counts": {"done": 1, "pending": 1},
                        "next_focus": "Verify project observer",
                    },
                    "continuation_checkpoint": {
                        "resume_ready": True,
                        "resume_mode": "context_handoff",
                        "open_plan_steps": [
                            {"id": "verify", "title": "Verify project observer", "status": "pending"}
                        ],
                        "artifact_count": 1,
                        "artifact_refs": [{"path": "server/project_observer.py"}],
                    },
                },
            },
        })
        thread = threading.Thread(target=server.start, daemon=True)
        thread.start()
        time.sleep(1)

        try:
            data = _get_json(f"http://127.0.0.1:{port}/sessions/projectstate1/project-state")

            assert data["status"] == "ready"
            assert data["source"] == "runtime_event_bus_project_observer"
            assert data["task"] == "control project"
            assert data["next_action"] == "Verify project observer"
            assert data["goal_overall"] == "active"
            assert data["plan_verdict"] == "pass"
            assert data["continuation"]["resume_ready"] is True
            assert data["project_control"]["status"] == "ready"
            assert data["project_control"]["next_action"] == "Verify project observer"
            assert data["project_control"]["classification"]["task_type"] == "pure_discussion"
            assert "GATE_0_DECLARE" in data["project_control"]["completed_gates"]
            assert data["project_control"]["verification"]["status"] == "requires_evidence"
            assert data["project_control"]["layer_control"]["status"] == "needs_action"
            assert data["project_control"]["control_actions"][0]["id"] == "emit_layer_event_or_mark_unobserved"
        finally:
            server.stop()


def test_app_server_project_writeback_endpoint_plans_and_applies():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        project_docs = tmp_path / "project" / "docs"
        project_docs.mkdir(parents=True)
        memory_path = project_docs / "memory-index.md"
        sprint_path = project_docs / "sprint-board.md"
        memory_path.write_text("# Memory\n", encoding="utf-8")
        sprint_path.write_text("# Sprint\n", encoding="utf-8")
        port = 17376
        server = _make_server(tmp_path, port)
        sid = server.create_session(
            SessionRequest(
                task="重构优化 project memory writeback",
                session_id="writebackapi1",
            )
        )
        session = server.get_session(sid)
        assert session is not None
        session.emit({
            "type": "context_sync",
            "session_id": sid,
            "payload": {
                "snapshot": {
                    "task": "重构优化 project memory writeback",
                    "workspace_profile": "coding",
                    "last_tool": "pytest",
                    "plan_validation": {"verdict": "pass", "summary": "checked", "issues_count": 0},
                    "goal_checklist": {
                        "overall": "active",
                        "counts": {"done": 1, "pending": 1},
                        "next_focus": "Apply project writeback",
                    },
                    "continuation_checkpoint": {
                        "resume_ready": True,
                        "resume_mode": "context_handoff",
                        "open_plan_steps": [],
                        "goal_next_focus": "Apply project writeback",
                    },
                },
            },
        })
        thread = threading.Thread(target=server.start, daemon=True)
        thread.start()
        time.sleep(1)

        try:
            plan = _get_json(f"http://127.0.0.1:{port}/sessions/writebackapi1/project-writeback")
            assert plan["status"] == "ready"
            assert plan["applicable"] is True
            assert [op["file"] for op in plan["operations"]] == [
                "docs/memory-index.md",
                "docs/sprint-board.md",
            ]

            dry_run = _post_json(
                f"http://127.0.0.1:{port}/sessions/writebackapi1/project-writeback",
                {},
            )
            assert dry_run["dry_run"] is True
            assert dry_run["apply_required"] is True
            assert memory_path.read_text(encoding="utf-8") == "# Memory\n"

            applied = _post_json(
                f"http://127.0.0.1:{port}/sessions/writebackapi1/project-writeback",
                {"apply": True},
            )
            assert applied["status"] == "applied"
            assert applied["applied_count"] == 2
            memory_text = memory_path.read_text(encoding="utf-8")
            sprint_text = sprint_path.read_text(encoding="utf-8")
            assert "TTMEVOLVE-PROJECT-WRITEBACK session_id=writebackapi1" in memory_text
            assert "TTMEVOLVE-PROJECT-WRITEBACK session_id=writebackapi1" in sprint_text

            repeated = _post_json(
                f"http://127.0.0.1:{port}/sessions/writebackapi1/project-writeback",
                {"apply": True},
            )
            assert repeated["status"] == "already_applied"
            assert memory_path.read_text(encoding="utf-8").count("TTMEVOLVE-PROJECT-WRITEBACK") == 1
            assert sprint_path.read_text(encoding="utf-8").count("TTMEVOLVE-PROJECT-WRITEBACK") == 1
            events = server.session_store.get_events("writebackapi1")
            assert any(event["type"] == "project_writeback" for event in events)
        finally:
            server.stop()


def _make_slow_server(tmp_path: Path, port: int) -> AppServer:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "project_root": str(tmp_path / "project"),
                "storage_root": str(tmp_path / "storage"),
                "llm": {"provider": "mock"},
                "sandbox": {"mode": "workspace-write"},
                "approval": {"policy": "never"},
                "expert": {"enabled": False},
                "learning": {"skill_generation_enabled": False},
            }
        ),
        encoding="utf-8",
    )
    cfg = Config(str(config_path))
    agent = TapMakerAgent(llm=_SlowMockLLM(), config=cfg, human_confirm_callback=None)
    store = SessionStore(Path(cfg.storage_root()) / "sessions.db")
    return AppServer(agent, host="127.0.0.1", port=port, approval_bridge=ApprovalBridge(), session_store=store)


def _make_timeout_server(tmp_path: Path, port: int) -> AppServer:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "project_root": str(tmp_path / "project"),
                "storage_root": str(tmp_path / "storage"),
                "llm": {"provider": "mock"},
                "sandbox": {"mode": "workspace-write"},
                "approval": {"policy": "never"},
                "expert": {"enabled": False},
                "learning": {"skill_generation_enabled": False},
            }
        ),
        encoding="utf-8",
    )
    cfg = Config(str(config_path))
    agent = TapMakerAgent(llm=_TimeoutMockLLM(), config=cfg, human_confirm_callback=None)
    store = SessionStore(Path(cfg.storage_root()) / "sessions.db")
    return AppServer(agent, host="127.0.0.1", port=port, approval_bridge=ApprovalBridge(), session_store=store)


def _post_json(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json(url: str) -> Dict[str, Any]:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read().decode("utf-8")


def test_app_server_session_persisted_and_listed():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        port = 17345
        server = _make_server(tmp_path, port)
        thread = threading.Thread(target=server.start, daemon=True)
        thread.start()
        time.sleep(1)

        try:
            # 创建会话
            created = _post_json(
                f"http://127.0.0.1:{port}/sessions",
                {"task": "say hello"},
            )
            sid = created["session_id"]
            assert created["status"] == "accepted"

            # 等待任务完成
            for _ in range(30):
                status = _get_json(f"http://127.0.0.1:{port}/sessions/{sid}/status")
                if status.get("done"):
                    break
                time.sleep(0.2)
            assert status.get("done") is True

            # 列表端点应包含该会话
            listed = _get_json(f"http://127.0.0.1:{port}/sessions")
            assert any(s["session_id"] == sid for s in listed["sessions"])

            # 详情端点应返回结果
            detail = _get_json(f"http://127.0.0.1:{port}/sessions/{sid}")
            assert detail["session_id"] == sid
            assert detail["task"] == "say hello"
            assert detail["status"] in ("done", "error")
        finally:
            server.stop()


def test_app_server_session_events_replay_on_reconnect():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        port = 17346
        server = _make_server(tmp_path, port)
        thread = threading.Thread(target=server.start, daemon=True)
        thread.start()
        time.sleep(1)

        try:
            created = _post_json(
                f"http://127.0.0.1:{port}/sessions",
                {"task": "say hello"},
            )
            sid = created["session_id"]

            # 等待完成
            for _ in range(30):
                status = _get_json(f"http://127.0.0.1:{port}/sessions/{sid}/status")
                if status.get("done"):
                    break
                time.sleep(0.2)

            # 重新连接 SSE，应收到历史事件回放
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/sessions/{sid}/events",
                method="GET",
                headers={"Accept": "text/event-stream"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                # 读取前几行即可验证有事件被推送
                lines = []
                for _ in range(20):
                    line = resp.readline().decode("utf-8", errors="ignore")
                    lines.append(line)
                    if line.strip() == "":
                        break

            # 至少能解析出一个 data: 行
            data_lines = [ln for ln in lines if ln.startswith("data:")]
            assert len(data_lines) > 0
            first_event = json.loads(data_lines[0][5:].strip())
            assert first_event.get("session_id") == sid
        finally:
            server.stop()


def test_app_server_unconfigured_provider_marks_session_error():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        port = 17347
        server = _make_server(tmp_path, port)
        thread = threading.Thread(target=server.start, daemon=True)
        thread.start()
        time.sleep(1)

        try:
            created = _post_json(
                f"http://127.0.0.1:{port}/sessions",
                {"task": "say hello", "provider": "openai"},
            )
            sid = created["session_id"]

            status = {}
            for _ in range(30):
                status = _get_json(f"http://127.0.0.1:{port}/sessions/{sid}/status")
                if status.get("done"):
                    break
                time.sleep(0.2)

            assert status.get("done") is True
            assert status.get("status") == "error"
            assert "API key" in (status.get("error") or "")
        finally:
            server.stop()


def test_app_server_runs_sessions_without_shared_runtime_queue():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        port = 17349
        server = _make_slow_server(tmp_path, port)
        thread = threading.Thread(target=server.start, daemon=True)
        thread.start()
        time.sleep(1)

        try:
            first = _post_json(f"http://127.0.0.1:{port}/sessions", {"task": "first"})
            second = _post_json(f"http://127.0.0.1:{port}/sessions", {"task": "second"})

            for sid in (first["session_id"], second["session_id"]):
                status = {}
                for _ in range(120):
                    status = _get_json(f"http://127.0.0.1:{port}/sessions/{sid}/status")
                    if status.get("done"):
                        break
                    time.sleep(0.1)
                assert status.get("done") is True

            second_events = server.session_store.get_events(second["session_id"])
            queued = [
                event for event in second_events
                if event.get("type") == "status" and "排队" in event.get("payload", {}).get("message", "")
            ]
            assert queued == []
        finally:
            server.stop()


def test_app_server_persists_layer_and_learning_events():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        port = 17358
        server = _make_server(tmp_path, port)
        thread = threading.Thread(target=server.start, daemon=True)
        thread.start()
        time.sleep(1)

        try:
            created = _post_json(f"http://127.0.0.1:{port}/sessions", {"task": "layer visibility"})
            sid = created["session_id"]

            status = {}
            for _ in range(30):
                status = _get_json(f"http://127.0.0.1:{port}/sessions/{sid}/status")
                if status.get("done"):
                    break
                time.sleep(0.1)

            events = server.session_store.get_events(sid)
            layer_events = [event for event in events if event.get("type") == "layer"]
            learning = _get_json(f"http://127.0.0.1:{port}/sessions/{sid}/learning?steps=5")

            assert status.get("done") is True
            assert any(event.get("payload", {}).get("event") == "agent.run.started" for event in layer_events)
            assert any(event.get("payload", {}).get("event") == "runtime.audit.finished" for event in layer_events)
            assert learning["count"] >= 1
            assert learning["latest"]["event"] == "learning.reflection.skipped"
            assert learning["job"]["status"] == "skipped"
            assert learning["job"]["policy"]["managed"] is True
        finally:
            server.stop()


def test_app_server_can_cancel_running_session():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        port = 17350
        server = _make_slow_server(tmp_path, port)
        thread = threading.Thread(target=server.start, daemon=True)
        thread.start()
        time.sleep(1)

        try:
            created = _post_json(f"http://127.0.0.1:{port}/sessions", {"task": "cancel me"})
            sid = created["session_id"]
            cancelled = _post_json(f"http://127.0.0.1:{port}/sessions/{sid}/cancel", {})
            assert cancelled["ok"] is True
            assert cancelled["canceled"] is True

            status = {}
            for _ in range(30):
                status = _get_json(f"http://127.0.0.1:{port}/sessions/{sid}/status")
                if status.get("done"):
                    break
                time.sleep(0.1)

            assert status.get("done") is True
            assert status.get("status") == "canceled"
            assert status.get("canceled") is True
            assert not status.get("error")
        finally:
            server.stop()


def test_app_server_learning_control_uses_live_agent_or_reports_replay_boundary():
    class _LearningControlAgent:
        def cancel_learning_job(self, session_id: str) -> Dict[str, Any]:
            return {"session_id": session_id, "status": "cancelled", "cancelled": True}

        def retry_learning_job(self, session_id: str) -> Dict[str, Any]:
            return {"session_id": session_id, "status": "queued", "retried": True}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        server = _make_server(tmp_path, 17382)
        sid = server.create_session(SessionRequest(task="learning control"))
        replay_only = server.cancel_learning_job(sid)

        with server._lock:
            session = server._sessions[sid]
            session.active_agent = _LearningControlAgent()

        cancelled = server.cancel_learning_job(sid)
        retried = server.retry_learning_job(sid)

        assert replay_only["status"] == 409
        assert "durable replay cannot be cancelled" in replay_only["error"]
        assert cancelled["ok"] is True
        assert cancelled["job"]["status"] == "cancelled"
        assert retried["ok"] is True
        assert retried["job"]["status"] == "queued"


def test_app_server_emits_llm_usage_on_timeout_error():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        port = 17351
        server = _make_timeout_server(tmp_path, port)
        thread = threading.Thread(target=server.start, daemon=True)
        thread.start()
        time.sleep(1)

        try:
            created = _post_json(f"http://127.0.0.1:{port}/sessions", {"task": "timeout"})
            sid = created["session_id"]

            status = {}
            for _ in range(30):
                status = _get_json(f"http://127.0.0.1:{port}/sessions/{sid}/status")
                if status.get("done"):
                    break
                time.sleep(0.1)

            assert status.get("status") == "error"
            assert "timed out" in (status.get("error") or "")
            events = server.session_store.get_events(sid)
            timeout_usage = [
                event for event in events
                if event.get("type") == "llm_usage"
                and event.get("payload", {}).get("error_type") == "timeout"
            ]
            assert timeout_usage
        finally:
            server.stop()


def test_app_server_commit_history_endpoint():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        port = 17353
        server = _make_server(tmp_path, port)
        server.session_store.create_session("hist1", "write file")
        server.session_store.append_event(
            "hist1",
            "observation",
            {
                "iteration": 2,
                "tool": "modify_file",
                "observation": {
                    "ok": True,
                    "tool": "modify_file",
                    "path": "hello.txt",
                    "idempotency_key": "hist1:modify_file:abc",
                    "committed": True,
                    "observed_at": 123.0,
                },
            },
        )
        thread = threading.Thread(target=server.start, daemon=True)
        thread.start()
        time.sleep(1)

        try:
            data = _get_json(f"http://127.0.0.1:{port}/sessions/hist1/commit-history?steps=5")
            alias = _get_json(f"http://127.0.0.1:{port}/sessions/hist1/submissions?steps=5")

            assert data["session_id"] == "hist1"
            assert data["count"] == 1
            assert data["commit_history"][0]["step"] == 2
            assert data["commit_history"][0]["committed"] is True
            assert data["commit_history"][0]["path"] == "hello.txt"
            assert alias["commit_history"][0]["idempotency_key"] == "hist1:modify_file:abc"
        finally:
            server.stop()


def test_app_server_context_sync_endpoint():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        port = 17355
        server = _make_server(tmp_path, port)
        server.session_store.create_session("ctxhist1", "shared context")
        server.session_store.append_event(
            "ctxhist1",
            "context_sync",
            {
                "iteration": -1,
                "reason": "session_start",
                "revision": 1,
                "changed": True,
                "signature": "sig-1",
                "diff_keys": ["session_id", "task"],
                "snapshot": {
                    "session_id": "ctxhist1",
                    "task": "shared context",
                    "iteration": -1,
                    "trajectory_steps": 0,
                    "last_tool": None,
                    "plan_validation": {"verdict": None},
                    "goal_checklist": {"overall": "active"},
                    "artifact_count": 0,
                    "artifact_refs": [],
                },
            },
        )
        server.session_store.append_event(
            "ctxhist1",
            "context_sync",
            {
                "iteration": 2,
                "reason": "plan_validation",
                "revision": 2,
                "changed": True,
                "signature": "sig-2",
                "previous_signature": "sig-1",
                "diff_keys": ["trajectory_steps", "last_tool", "plan_validation"],
                "snapshot": {
                    "session_id": "ctxhist1",
                    "task": "shared context",
                    "iteration": 2,
                    "trajectory_steps": 3,
                    "last_tool": "query_skills",
                    "plan_validation": {"verdict": "pass"},
                    "goal_checklist": {"overall": "active"},
                    "workspace_profile": "coding",
                    "continuation_checkpoint": {
                        "version": "continuation-checkpoint.v1",
                        "context_revision": 2,
                        "workspace_profile": "coding",
                        "resume_ready": True,
                        "resume_mode": "context_handoff",
                        "open_plan_steps": [
                            {"id": "next", "title": "continue implementation", "status": "pending"}
                        ],
                        "goal_next_focus": "continue implementation",
                        "goal_overall": "active",
                        "last_tool": "query_skills",
                        "last_ok": True,
                        "plan_verdict": "pass",
                        "artifact_count": 1,
                        "artifact_refs": [{"path": "skill.json", "tool": "query_skills"}],
                        "compression": {
                            "needed": False,
                            "summary": "Task: shared context",
                        },
                        "resume_limits": {
                            "process_resurrection": False,
                            "requires_runtime_replay": False,
                            "raw_sse_replay_required": False,
                        },
                    },
                    "artifact_count": 1,
                    "artifact_refs": [{"path": "skill.json", "tool": "query_skills"}],
                },
            },
        )
        thread = threading.Thread(target=server.start, daemon=True)
        thread.start()
        time.sleep(1)

        try:
            data = _get_json(f"http://127.0.0.1:{port}/sessions/ctxhist1/context-sync?steps=1")

            assert data["session_id"] == "ctxhist1"
            assert data["count"] == 1
            assert data["latest"]["revision"] == 2
            assert data["latest"]["last_tool"] == "query_skills"
            assert data["latest"]["plan_verdict"] == "pass"
            assert data["latest"]["workspace_profile"] == "coding"
            assert data["latest"]["resume_ready"] is True
            assert data["latest"]["resume_mode"] == "context_handoff"
            assert data["latest"]["open_plan_count"] == 1
            assert data["latest"]["continuation_checkpoint"]["open_plan_steps"][0]["id"] == "next"
            assert data["latest"]["artifact_count"] == 1
            assert data["latest"]["snapshot"]["artifact_refs"][0]["path"] == "skill.json"

            resume = _get_json(f"http://127.0.0.1:{port}/sessions/ctxhist1/resume-drill?steps=20")
            assert resume["version"] == "resume-drill.v1"
            assert resume["status"] == "ready"
            assert resume["source"] == "session_store_replay"
            assert resume["drill"]["uses_live_runtime_state"] is False
            assert resume["capability_levels"]["durable_handoff"]["status"] == "ready"
            assert resume["capability_levels"]["warm_process"]["status"] == "unproven"
            assert resume["capability_levels"]["hot_tool_call"]["status"] == "unproven"
            assert resume["closure_gate"]["can_claim_long_task_durable_handoff"] is True
            assert resume["closure_gate"]["can_claim_hot_tool_call_resume"] is False
            assert resume["recovered"]["task"] == "shared context"
            assert resume["recovered"]["open_plan_steps"][0]["title"] == "continue implementation"
            assert resume["recovered"]["artifact_refs"][0]["path"] == "skill.json"
        finally:
            server.stop()


def test_app_server_runtime_metrics_endpoint():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        port = 17357
        server = _make_server(tmp_path, port)
        server.session_store.create_session("metrics1", "diagnose runtime")
        server.session_store.append_event(
            "metrics1",
            "tool_selection",
            {
                "iteration": 0,
                "phase": "action",
                "tools": [{"name": "maker_build", "source": "maker_mcp"}],
                "stats": {
                    "candidate_count": 12,
                    "selected_count": 1,
                    "ranking_ms": 2.5,
                    "cache_hit": True,
                    "cache_size": 3,
                },
            },
        )
        server.session_store.append_event(
            "metrics1",
            "context_budget",
            {
                "iteration": 0,
                "phase": "think",
                "token_count": 1200,
                "n_ctx": 8192,
                "token_usage_ratio": 0.14,
                "context_window_ratio": 0.2,
                "compression_applied": False,
                "token_cache_hits": 4,
                "token_cache_misses": 2,
                "token_cache_size": 5,
                "agents_md_hits": 2,
                "cold_recall_hits": 1,
                "context_build_ms": 11.5,
            },
        )
        server.session_store.append_event(
            "metrics1",
            "latency",
            {"phase": "llm_action", "iteration": 0, "elapsed_ms": 310.0},
        )
        server.session_store.append_event(
            "metrics1",
            "llm_usage",
            {"phase": "action", "provider": "openai", "total_tokens": 128},
        )
        thread = threading.Thread(target=server.start, daemon=True)
        thread.start()
        time.sleep(1)

        try:
            data = _get_json(f"http://127.0.0.1:{port}/sessions/metrics1/runtime-metrics?steps=10")

            assert data["session_id"] == "metrics1"
            assert data["count"] == 4
            assert data["summary"]["llm_total_tokens"] == 128
            assert data["summary"]["max_latency"]["phase"] == "llm_action"
            assert data["summary"]["token_cache"]["hits"] == 4
            assert data["summary"]["retrieval"]["agents_md_hits"] == 2
            assert data["summary"]["tool_ranking"]["cache_hit"] is True
            assert data["runtime_metrics"][0]["kind"] == "tool_selection"
            assert data["runtime_metrics"][1]["kind"] == "context_budget"
        finally:
            server.stop()


def test_app_server_maker_guard_endpoint():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        port = 17360
        server = _make_server(tmp_path, port)
        server.session_store.create_session("guardhist1", "build Maker project")
        server.session_store.append_event(
            "guardhist1",
            "maker_briefing_guard",
            {
                "iteration": 0,
                "decision": "block",
                "tool": "write_file",
                "reason": "local side effect before Maker authority",
                "authority": "maker_mcp",
                "selected_template": {"id": "maker_build_or_submit", "status": "ready"},
                "allowed_tools": ["maker_build", "maker_briefing"],
                "suggested_tools": ["maker_build"],
                "recommended_first_action": "Use MakerMCP authority through maker_build.",
                "recommended_endpoint": "/mcp/tools",
            },
        )
        thread = threading.Thread(target=server.start, daemon=True)
        thread.start()
        time.sleep(1)

        try:
            data = _get_json(f"http://127.0.0.1:{port}/sessions/guardhist1/maker-guard?steps=5")

            assert data["session_id"] == "guardhist1"
            assert data["count"] == 1
            assert data["latest"]["decision"] == "block"
            assert data["latest"]["tool"] == "write_file"
            assert data["latest"]["selected_template"]["id"] == "maker_build_or_submit"
            assert data["latest"]["allowed_tools"] == ["maker_build", "maker_briefing"]
        finally:
            server.stop()


def test_app_server_runtime_advice_endpoint_prioritizes_blocked_maker_guard():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        port = 17361
        server = _make_server(tmp_path, port)
        server.session_store.create_session("advice1", "build Maker project")
        server.session_store.append_event(
            "advice1",
            "context_sync",
            {
                "iteration": 0,
                "reason": "session_start",
                "revision": 1,
                "changed": True,
                "signature": "sig",
                "snapshot": {"session_id": "advice1", "task": "build Maker project"},
            },
        )
        server.session_store.append_event(
            "advice1",
            "maker_briefing_guard",
            {
                "iteration": 0,
                "decision": "block",
                "tool": "write_file",
                "reason": "local side effect before Maker authority",
                "authority": "maker_mcp",
                "selected_template": {"id": "maker_build_or_submit", "status": "ready"},
                "allowed_tools": ["maker_build"],
                "suggested_tools": ["maker_build"],
                "recommended_first_action": "Use MakerMCP authority through maker_build.",
                "recommended_endpoint": "/mcp/tools",
            },
        )
        thread = threading.Thread(target=server.start, daemon=True)
        thread.start()
        time.sleep(1)

        try:
            data = _get_json(f"http://127.0.0.1:{port}/sessions/advice1/runtime-advice?steps=5")

            advice = data["runtime_advice"]
            assert advice["status"] == "needs_action"
            assert advice["priority"] == "maker_alignment"
            assert advice["next_action"] == "Use MakerMCP authority through maker_build."
            assert advice["evidence"]["maker_guard"]["decision"] == "block"
        finally:
            server.stop()


def test_app_server_llm_probe_history_endpoint():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        port = 17363
        server = _make_server(tmp_path, port)
        server.session_store.create_session("probehist1", "probe llm")
        server.session_store.append_event(
            "probehist1",
            "llm_probe",
            {
                "ok": True,
                "status": "ok",
                "provider": "minimax",
                "runtime_kind": "api",
                "llm_class": "MiniMaxLLM",
                "model": "MiniMax-M1",
                "base_url": "https://api.minimax.chat/v1",
                "elapsed_ms": 1200.0,
                "output_preview": "TTM_PROBE_OK",
                "last_call_stats": {
                    "endpoint": "https://api.minimax.chat/v1/text/chatcompletion_v2",
                    "http_status": 200,
                    "total_tokens": 12,
                },
            },
        )
        thread = threading.Thread(target=server.start, daemon=True)
        thread.start()
        time.sleep(1)

        try:
            data = _get_json(f"http://127.0.0.1:{port}/sessions/probehist1/llm-probe?steps=5")

            assert data["session_id"] == "probehist1"
            assert data["count"] == 1
            assert data["latest"]["provider"] == "minimax"
            assert data["latest"]["endpoint"].endswith("/text/chatcompletion_v2")
            assert data["latest"]["total_tokens"] == 12
        finally:
            server.stop()


def test_app_server_runtime_readiness_endpoint():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        port = 17373
        server = _make_server(tmp_path, port)
        server.agent.config.data["llm"] = {
            "provider": "minimax",
            "model": "MiniMax-M1",
            "base_url": "https://api.minimax.chat/v1",
            "api_keys": {"minimax": "test-key"},
        }
        server.session_store.create_session("ready1", "build Maker project")
        server.session_store.append_event(
            "ready1",
            "llm_probe",
            {
                "ok": True,
                "status": "ok",
                "provider": "minimax",
                "runtime_kind": "api",
                "llm_class": "MiniMaxLLM",
                "model": "MiniMax-M1",
                "base_url": "https://api.minimax.chat/v1",
                "elapsed_ms": 980.0,
                "last_call_stats": {
                    "endpoint": "https://api.minimax.chat/v1/text/chatcompletion_v2",
                    "http_status": 200,
                    "total_tokens": 10,
                },
            },
        )
        server.session_store.append_event(
            "ready1",
            "context_sync",
            {
                "revision": 1,
                "changed": True,
                "signature": "ready-sig",
                "snapshot": {"session_id": "ready1", "task": "build Maker project"},
            },
        )
        server.session_store.append_event(
            "ready1",
            "layer",
            {
                "layer": "runtime",
                "state": "active",
                "event": "runtime.ready",
                "source_layer": "runtime",
                "target_layer": "agent",
            },
        )
        server.event_bus.publish({
            "type": "context_budget",
            "session_id": "ready1",
            "payload": {
                "phase": "think",
                "iteration": 0,
                "workspace_profile": "maker",
                "agents_md_hits": 2,
                "cold_recall_hits": 1,
                "cold_recall_ms": 6.0,
                "context_build_ms": 10.0,
            },
        })
        server.event_bus.publish({
            "type": "layer",
            "session_id": "ready1",
            "payload": {
                "layer": "learning",
                "state": "done",
                "event": "learning.reflection.finished",
                "detail": "learning complete",
                "source_layer": "learning",
                "target_layer": "memory",
                "metrics": {"elapsed_ms": 9.0, "async": True},
            },
        })
        thread = threading.Thread(target=server.start, daemon=True)
        thread.start()
        time.sleep(1)

        try:
            data = _get_json(f"http://127.0.0.1:{port}/runtime/readiness?session_id=ready1")

            assert data["version"] == "runtime-readiness.v1"
            assert data["no_network_call"] is True
            assert data["status"] == "degraded"
            assert data["summary"]["provider"] == "minimax"
            assert data["summary"]["runtime_kind"] == "api"
            assert data["summary"]["api_key_set"] is True
            assert data["summary"]["probe_status"] == "ok"
            assert data["summary"]["probe_endpoint"].endswith("/text/chatcompletion_v2")
            assert data["summary"]["call_proof"] == "api_call_observed"
            assert data["summary"]["event_bus"] in {"ready", "partial"}
            assert data["runtime_event_bus"]["status"] in {"ready", "partial"}
            assert data["runtime_event_bus"]["observer_health"] == "ready"
            assert data["runtime_event_bus"]["observer_error_count"] == 0
            assert data["runtime_event_bus"]["server_bus"]["status"] == "ready"
            assert data["runtime_event_bus"]["server_bus"]["observer_error_count"] == 0
            assert data["runtime_event_bus"]["runtime_metrics_observer"]["status"] == "ready"
            assert data["runtime_event_bus"]["learning_observer"]["status"] == "ready"
            assert data["runtime_event_bus"]["memory_observer"]["status"] == "ready"
            assert data["learning_observer"]["status"] == "ready"
            assert data["learning_observer"]["latest"]["event"] == "learning.reflection.finished"
            assert data["memory_recall"]["status"] == "ready"
            assert data["memory_recall"]["latest"]["workspace_profile"] == "maker"
            assert data["memory_recall"]["totals"]["cold_recall_hits"] == 1
            assert data["summary"]["engineering_control"] == "ready"
            assert data["summary"]["resume_drill"] == "partial"
            assert data["resume_drill"]["status"] == "partial"
            assert data["resume_drill"]["closure_gate"]["can_claim_long_task_durable_handoff"] is False
            assert data["engineering_control"]["status"] == "ready"
            assert any(check["id"] == "engineering_control" and check["ok"] for check in data["release_gate"]["checks"])
            assert any(check["id"] == "resume_drill" and not check["ok"] for check in data["release_gate"]["checks"])
            assert data["llm_call_proof"]["provider"] == "minimax"
            assert data["llm_call_proof"]["expected_endpoint"].endswith("/text/chatcompletion_v2")
            assert data["llm_call_proof"]["observed_endpoint"].endswith("/text/chatcompletion_v2")
            assert data["llm_call_proof"]["endpoint_matches_expected"] is True
            assert data["llm_call_proof"]["evidence_source"] == "llm_probe"
            assert data["llm_feedback_summary"]["version"] == "llm-feedback-summary.v1"
            assert data["maker_mcp"]["readiness"] == "disconnected"
            assert data["release_gate"]["stable_small_version"] == "ready"
            assert any(check["id"] == "runtime_event_bus" and check["ok"] for check in data["release_gate"]["checks"])
            assert data["endpoints"]["runtime_readiness"] == "/runtime/readiness?session_id=ready1"
            assert data["endpoints"]["resume_drill"] == "/sessions/ready1/resume-drill?steps=20"
            assert data["endpoints"]["llm_feedback_summary"] == "/llm/feedback-summary"
            assert any("GET /mcp/status" in action for action in data["next_actions"])

            feedback = _get_json(f"http://127.0.0.1:{port}/llm/feedback-summary")
            assert feedback["version"] == "llm-feedback-summary.v1"
            assert "total_runs" in feedback
        finally:
            server.stop()


def test_app_server_external_llm_quickstart_endpoint():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        port = 17362
        server = _make_server(tmp_path, port)
        server.session_store.create_session("quick1", "build Maker project")
        server.session_store.append_event(
            "quick1",
            "llm_probe",
            {
                "ok": True,
                "status": "ok",
                "provider": "minimax",
                "runtime_kind": "api",
                "llm_class": "MiniMaxLLM",
                "model": "MiniMax-M1",
                "base_url": "https://api.minimax.chat/v1",
                "elapsed_ms": 1200.0,
                "last_call_stats": {
                    "endpoint": "https://api.minimax.chat/v1/text/chatcompletion_v2",
                    "total_tokens": 12,
                },
            },
        )
        server.session_store.append_event(
            "quick1",
            "context_sync",
            {
                "iteration": -1,
                "reason": "session_start",
                "revision": 1,
                "changed": True,
                "signature": "quick-sig",
                "snapshot": {"session_id": "quick1", "task": "build Maker project"},
            },
        )
        thread = threading.Thread(target=server.start, daemon=True)
        thread.start()
        time.sleep(1)

        try:
            data = _get_json(f"http://127.0.0.1:{port}/agent/quickstart?session_id=quick1&steps=1")

            assert data["version"] == "llm-quickstart.v1"
            assert data["session_id"] == "quick1"
            assert "external coding agent" in data["prompt"]
            assert "# TTMEvolve External Agent Quickstart" in data["prompt_markdown"]
            assert "## Runtime Advice" in data["prompt_markdown"]
            assert "runtime_advice" in data["prompt_markdown"]
            assert data["boot_sequence"][0] == "GET /runtime/portable"
            assert data["boot_sequence"][1] == "GET /runtime/readiness?session_id=quick1"
            assert "GET /agent/quickstart?session_id=quick1&steps=3" in data["boot_sequence"]
            assert "GET /sessions/quick1/evidence?steps=20" in data["boot_sequence"]
            assert data["runtime_advice"]["priority"]
            assert data["maker_briefing"]["selected_template"]["id"] == "maker_build_or_submit"
            assert data["llm_probe"]["status"] == "ok"
            assert data["llm_probe"]["provider"] == "minimax"
            assert data["llm_probe"]["endpoint"].endswith("/text/chatcompletion_v2")
            assert data["latest_context_sync"]["revision"] == 1
            assert data["endpoints"]["runtime_readiness"] == "/runtime/readiness?session_id=quick1"
            assert data["endpoints"]["portable_runtime"] == "/runtime/portable"
            assert data["endpoints"]["runtime_advice"] == "/sessions/quick1/runtime-advice?steps=20"
            assert data["endpoints"]["evidence_bundle"] == "/sessions/quick1/evidence?steps=20"
            assert data["endpoints"]["llm_probe"] == "/llm/probe"
            assert data["endpoints"]["llm_probe_history"] == "/sessions/quick1/llm-probe?steps=20"

            markdown = _get_text(f"http://127.0.0.1:{port}/agent/quickstart?session_id=quick1&steps=1&format=markdown")
            markdown_path = _get_text(f"http://127.0.0.1:{port}/agent/quickstart.md?session_id=quick1&steps=1")
            assert markdown.startswith("# TTMEvolve External Agent Quickstart")
            assert "## Compact Endpoints" in markdown
            assert "## LLM Runtime" in markdown
            assert "llm_probe" in markdown
            assert markdown_path == markdown

            codex = _get_json(f"http://127.0.0.1:{port}/agent/quickstart?session_id=quick1&steps=1&surface=codex")
            codex_markdown = _get_text(f"http://127.0.0.1:{port}/agent/quickstart.md?session_id=quick1&steps=1&surface=codex")
            assert codex["surface"]["id"] == "codex"
            assert codex["surface"]["memory_files"] == ["AGENTS.md"]
            assert "## Surface Profile" in codex["prompt_markdown"]
            assert "surface: `codex`" in codex_markdown
            assert "AGENTS.md" in codex_markdown
            assert any(step.endswith("&surface=codex") for step in codex["boot_sequence"])
        finally:
            server.stop()


def test_app_server_maker_briefing_endpoint():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        port = 17359
        server = _make_server(tmp_path, port)
        server.session_store.create_session("brief1", "build Maker project")
        thread = threading.Thread(target=server.start, daemon=True)
        thread.start()
        time.sleep(1)

        try:
            data = _get_json(f"http://127.0.0.1:{port}/agent/maker-briefing?session_id=brief1&task=build%20Maker%20project")

            assert data["version"] == "maker-briefing.v1"
            assert data["task"] == "build Maker project"
            assert data["readiness"] in {"ready", "degraded", "disconnected"}
            assert data["selected_template"]["id"] == "maker_build_or_submit"
            assert data["evidence_endpoints"]["maker_briefing"] == "/agent/maker-briefing?session_id=brief1"
        finally:
            server.stop()


def test_app_server_external_agent_handoff_endpoint():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        port = 17356
        server = _make_server(tmp_path, port)
        server.session_store.create_session("handoff1", "build Maker project")
        server.session_store.append_event(
            "handoff1",
            "llm_probe",
            {
                "ok": False,
                "status": "error",
                "provider": "minimax",
                "runtime_kind": "api",
                "llm_class": "MiniMaxLLM",
                "model": "MiniMax-M1",
                "base_url": "https://api.minimax.chat/v1",
                "elapsed_ms": 20000.0,
                "error": "timeout",
                "last_call_stats": {
                    "endpoint": "https://api.minimax.chat/v1/text/chatcompletion_v2",
                    "error_type": "timeout",
                },
            },
        )
        server.session_store.append_event(
            "handoff1",
            "context_sync",
            {
                "iteration": -1,
                "reason": "session_start",
                "revision": 1,
                "changed": True,
                "signature": "handoff-sig",
                "diff_keys": ["session_id", "task"],
                "snapshot": {
                    "session_id": "handoff1",
                    "task": "build Maker project",
                    "iteration": -1,
                    "trajectory_steps": 0,
                    "last_tool": None,
                    "plan_validation": {"verdict": None},
                    "goal_checklist": {"overall": "active"},
                    "artifact_count": 0,
                    "artifact_refs": [],
                },
            },
        )
        server.session_store.append_event(
            "handoff1",
            "context_budget",
            {
                "iteration": 0,
                "phase": "think",
                "token_cache_hits": 3,
                "token_cache_misses": 1,
                "agents_md_hits": 1,
                "cold_recall_hits": 0,
                "context_build_ms": 7.0,
            },
        )
        server.session_store.append_event(
            "handoff1",
            "layer",
            {
                "layer": "learning",
                "state": "done",
                "event": "learning.reflection.finished",
                "detail": "learning complete",
                "source_layer": "learning",
                "target_layer": "storage",
                "metrics": {"elapsed_ms": 12.0, "async": True},
            },
        )
        server.session_store.append_event(
            "handoff1",
            "maker_briefing_guard",
            {
                "iteration": 0,
                "decision": "pass",
                "tool": "maker_build",
                "reason": "First action matches Maker briefing authority.",
                "authority": "maker_mcp",
                "selected_template": {"id": "maker_build_or_submit", "status": "ready"},
                "allowed_tools": ["maker_build"],
                "suggested_tools": ["maker_build"],
                "recommended_first_action": "Use MakerMCP authority through maker_build.",
                "recommended_endpoint": "/mcp/tools",
            },
        )
        thread = threading.Thread(target=server.start, daemon=True)
        thread.start()
        time.sleep(1)

        try:
            data = _get_json(f"http://127.0.0.1:{port}/agent/handoff?session_id=handoff1&steps=1")

            assert data["session_id"] == "handoff1"
            assert data["runtime_contract"]["communication"]["handoff_bundle"] == "/agent/handoff?session_id=handoff1&steps=3"
            assert data["maker_briefing"]["selected_template"]["id"] == "maker_build_or_submit"
            assert data["latest_context_sync"]["revision"] == 1
            assert data["latest_context_sync"]["snapshot"]["task"] == "build Maker project"
            assert data["attach_sequence"][0] == "GET /agent/onboarding?session_id=handoff1&steps=20 for the one-stop startup and closure packet"
            assert data["attach_sequence"][1] == "GET /runtime/portable to confirm caches/auth/temp stay inside the TTMEvolve agent folder"
            assert data["attach_sequence"][2] == "GET /runtime/readiness?session_id=handoff1 for the fastest provider/Maker/layer readiness check"
            assert data["attach_sequence"][3] == "GET /agent/quickstart?session_id=handoff1&steps=3"
            assert data["attach_sequence"][4] == "GET /sessions/handoff1/evidence?steps=20 for compact current evidence"
            assert "skill_summary" in data
            assert data["runtime_metrics_summary"]["token_cache"]["hits"] == 3
            assert data["learning_latest"]["event"] == "learning.reflection.finished"
            assert data["maker_guard_latest"]["decision"] == "pass"
            assert data["maker_guard_latest"]["tool"] == "maker_build"
            assert data["llm_probe_latest"]["status"] == "error"
            assert data["llm_probe_latest"]["provider"] == "minimax"
            assert data["runtime_advice"]["status"] == "needs_action"
            assert data["runtime_advice"]["priority"] == "llm_provider"
            assert data["runtime_advice"]["next_action"]
            assert "token_rule" in data
        finally:
            server.stop()


def test_app_server_evidence_bundle_endpoint():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        port = 17364
        server = _make_server(tmp_path, port)
        server.session_store.create_session("evidence1", "build Maker project")
        server.session_store.append_event(
            "evidence1",
            "cos_gate",
            classify_cos_gate("重构优化 Maker project 的运行流程和证据").to_dict(),
            source="cos_gate",
        )
        server.session_store.append_event(
            "evidence1",
            "layer",
            {
                "schema_version": 1,
                "layer": "agent",
                "state": "active",
                "event": "agent.run.started",
                "detail": "planning",
                "source_layer": "user",
                "target_layer": "agent",
                "correlation_id": "evidence1",
                "cause": "user_task",
                "metrics": {"task_chars": 19},
            },
        )
        server.session_store.append_event(
            "evidence1",
            "layer",
            {
                "schema_version": 1,
                "layer": "runtime",
                "state": "done",
                "event": "runtime.audit.finished",
                "detail": "runtime audit complete",
                "source_layer": "runtime",
                "target_layer": "learning",
                "correlation_id": "evidence1",
                "cause": "agent_result",
                "metrics": {"health_status": "healthy"},
            },
        )
        server.session_store.append_event(
            "evidence1",
            "llm_probe",
            {
                "ok": True,
                "status": "ok",
                "provider": "minimax",
                "runtime_kind": "api",
                "llm_class": "MiniMaxLLM",
                "model": "MiniMax-M1",
                "base_url": "https://api.minimax.chat/v1",
                "elapsed_ms": 900.0,
                "last_call_stats": {
                    "endpoint": "https://api.minimax.chat/v1/text/chatcompletion_v2",
                    "total_tokens": 32,
                },
            },
        )
        server.session_store.append_event(
            "evidence1",
            "context_sync",
            {
                "iteration": -1,
                "reason": "session_start",
                "revision": 2,
                "changed": True,
                "signature": "evidence-sig",
                "snapshot": {
                    "session_id": "evidence1",
                    "task": "build Maker project",
                    "workspace_profile": "maker",
                    "continuation_checkpoint": {
                        "version": "continuation-checkpoint.v1",
                        "context_revision": 2,
                        "workspace_profile": "maker",
                        "resume_ready": True,
                        "resume_mode": "context_handoff",
                        "open_plan_steps": [
                            {"id": "build", "title": "Run Maker build", "status": "pending", "tool": "maker_build"}
                        ],
                        "goal_next_focus": "Run Maker build",
                        "goal_overall": "active",
                        "last_tool": "maker_build",
                        "last_ok": True,
                        "plan_verdict": "pass",
                        "artifact_count": 1,
                        "artifact_refs": [{"path": "scripts/main.lua", "tool": "modify_file"}],
                        "compression": {
                            "needed": True,
                            "compressed_step_count": 8,
                            "skipped_step_count": 0,
                            "summary": "Task: build Maker project",
                        },
                        "resume_limits": {
                            "process_resurrection": False,
                            "raw_sse_replay_required": False,
                        },
                    },
                },
            },
        )
        server.session_store.append_event(
            "evidence1",
            "context_budget",
            {
                "iteration": 0,
                "phase": "think",
                "token_cache_hits": 5,
                "token_cache_misses": 0,
                "token_cache_size": 3,
                "workspace_profile": "maker",
                "agents_md_hits": 1,
                "cold_recall_hits": 1,
                "agents_md_ms": 2.0,
                "cold_recall_ms": 3.0,
                "context_build_ms": 4.5,
            },
        )
        server.session_store.append_event(
            "evidence1",
            "tool_selection",
            {
                "iteration": 0,
                "phase": "act",
                "stats": {
                    "candidate_count": 18,
                    "selected_count": 6,
                    "ranking_ms": 3.0,
                    "cache_hit": True,
                    "cache_size": 2,
                },
            },
        )
        server.session_store.append_event(
            "evidence1",
            "layer",
            {
                "layer": "learning",
                "state": "done",
                "event": "learning.reflection.finished",
                "detail": "learning complete",
                "source_layer": "learning",
                "target_layer": "storage",
                "metrics": {"elapsed_ms": 10.0, "async": True},
            },
        )
        server.session_store.append_event(
            "evidence1",
            "maker_briefing_guard",
            {
                "iteration": 0,
                "decision": "pass",
                "tool": "maker_build",
                "reason": "First action matches Maker briefing authority.",
                "authority": "maker_mcp",
                "selected_template": {"id": "maker_build_or_submit", "status": "ready"},
                "allowed_tools": ["maker_build"],
                "suggested_tools": ["maker_build"],
                "recommended_first_action": "Use MakerMCP authority through maker_build.",
                "recommended_endpoint": "/mcp/tools",
            },
        )
        thread = threading.Thread(target=server.start, daemon=True)
        thread.start()
        time.sleep(1)

        try:
            rag_report = _get_json(f"http://127.0.0.1:{port}/memory/rag-benchmark?force=true")
            assert rag_report["status"] == "ready"
            assert rag_report["budget_status"] == "pass", rag_report
            assert rag_report["metrics"]["warm_recall_p95_ms"] < 50.0
            rag_quality = _get_json(f"http://127.0.0.1:{port}/memory/rag-quality?force=true")
            assert rag_quality["status"] == "unproven"
            assert rag_quality["passed"] is False
            assert "labelled_golden_corpus" in rag_quality["missing"]

            data = _get_json(f"http://127.0.0.1:{port}/sessions/evidence1/evidence?steps=5")

            assert data["version"] == "session-evidence.v1"
            assert data["session_id"] == "evidence1"
            assert data["task"] == "build Maker project"
            assert data["cos_gate"]["task_type"] == "refactor_optimization"
            assert data["cos_gate"]["level"] in {"M", "L", "XL"}
            assert data["cos_gate"]["mode"] == "System 2"
            assert data["cos_gate"]["source"] == "session_store_cos_gate"
            assert data["maker_mcp"]["readiness"] == "disconnected"
            assert data["maker_mcp"]["connected"] is False
            assert data["maker_mcp"]["tool_count"] == 0
            assert data["maker_mcp"]["top_tools"] == []
            assert data["latest_context_sync"]["revision"] == 2
            assert data["continuation"]["resume_ready"] is True
            assert data["continuation"]["workspace_profile"] == "maker"
            assert data["continuation"]["open_plan_count"] == 1
            assert data["continuation"]["goal_next_focus"] == "Run Maker build"
            assert data["continuation"]["compression_needed"] is True
            assert data["resume_drill"]["version"] == "resume-drill.v1"
            assert data["resume_drill"]["status"] == "ready"
            assert data["resume_drill"]["capability_levels"]["durable_handoff"]["status"] == "ready"
            assert data["resume_drill"]["capability_levels"]["warm_process"]["status"] == "unproven"
            assert data["resume_drill"]["capability_levels"]["hot_tool_call"]["status"] == "unproven"
            assert data["resume_drill"]["closure_gate"]["can_claim_long_task_durable_handoff"] is True
            assert data["resume_drill"]["closure_gate"]["can_claim_hot_tool_call_resume"] is False
            assert data["layer_summary"]["event_count"] == 3
            assert data["layer_summary"]["latest_by_layer"]["agent"]["event"] == "agent.run.started"
            assert data["layer_summary"]["latest_by_layer"]["runtime"]["event"] == "runtime.audit.finished"
            assert data["layer_summary"]["latest_by_layer"]["learning"]["event"] == "learning.reflection.finished"
            assert data["layer_health"]["version"] == "layer-health.v1"
            assert data["layer_health"]["status"] == "active"
            assert data["layer_health"]["layers"]["agent"]["health"] == "active"
            assert data["layer_health"]["layers"]["runtime"]["health"] == "ready"
            assert data["layer_health"]["layers"]["learning"]["health"] == "ready"
            assert data["layer_health"]["summary"]["learning_queue_depth"] == 0
            assert data["layer_control"]["version"] == "layer-control.v1"
            assert data["layer_control"]["status"] == "watch"
            assert data["layer_control"]["decision"] == "continue_with_monitoring"
            assert data["layer_control"]["closure_gate"]["can_continue_user_task"] is True
            assert data["layer_control"]["closure_gate"]["can_claim_layer_independence"] is False
            assert data["layer_control"]["signals"][0]["id"] == "missing_route_agent_to_runtime"
            assert data["engineering_control"]["version"] == "engineering-control.v1"
            assert data["engineering_control"]["status"] == "ready"
            assert data["engineering_control"]["closure_gate"]["can_claim_memory_rag_optimized"] is True
            expected_routes = {
                item["route"]: item["observed"]
                for item in data["layer_health"]["communication_contract"]["expected_routes"]
            }
            assert expected_routes["user->agent"] is True
            assert expected_routes["runtime->learning"] is True
            assert expected_routes["learning->storage"] is True
            assert data["runtime_metrics_summary"]["token_cache"]["hits"] == 5
            assert data["runtime_metrics_summary"]["tool_ranking"]["selected_count"] == 6
            assert data["learning_latest"]["event"] == "learning.reflection.finished"
            assert data["maker_guard_latest"]["decision"] == "pass"
            assert data["llm_probe_latest"]["status"] == "ok"
            assert data["llm_probe_latest"]["provider"] == "minimax"
            assert data["llm_call_proof"]["conclusion"] == "api_call_observed"
            assert data["llm_call_proof"]["expected_endpoint"].endswith("/text/chatcompletion_v2")
            assert data["llm_call_proof"]["observed_endpoint"].endswith("/text/chatcompletion_v2")
            assert data["llm_feedback_summary"]["version"] == "llm-feedback-summary.v1"
            assert data["shared_memory"]["status"] == "ready"
            assert data["shared_memory"]["default_visibility"] == "private"
            assert data["shared_memory"]["can_read_private_other"] is False
            assert data["shared_memory"]["boundary"] == "owner_private_plus_explicit_shared"
            assert data["shared_memory"]["outcomes"]["promotion_rule"] == "verified_positive_task_evidence_without_unresolved_conflict"
            assert data["shared_memory"]["outcomes"]["default_visibility_rule"] == "private_until_verified"
            assert data["shared_memory"]["outcomes"]["unresolved_conflict_count"] == 0
            assert data["runtime_event_bus"]["status"] in {"ready", "partial"}
            assert data["runtime_event_bus"]["observer_health"] == "ready"
            assert data["runtime_event_bus"]["observer_error_count"] == 0
            assert data["runtime_event_bus"]["server_bus"]["status"] == "ready"
            assert data["runtime_event_bus"]["server_bus"]["observer_error_count"] == 0
            assert data["runtime_event_bus"]["compatibility"] == "sse_sqlite_shape_preserved"
            assert data["runtime_event_bus"]["runtime_metrics_observer"]["status"] == "ready"
            assert data["runtime_event_bus"]["learning_observer"]["status"] == "ready"
            assert data["runtime_event_bus"]["memory_observer"]["status"] == "ready"
            assert data["runtime_metrics_source"] == "session_store"
            assert data["runtime_metrics_observer"]["status"] == "ready"
            assert data["learning_observer"]["status"] == "replay"
            assert data["learning_observer"]["latest"]["event"] == "learning.reflection.finished"
            assert data["memory_recall"]["status"] == "replay"
            assert data["memory_recall"]["source"] == "session_store_context_budget"
            assert data["memory_recall"]["latest"]["workspace_profile"] == "maker"
            assert data["memory_recall"]["latest"]["context_build_ms"] == 4.5
            assert data["memory_recall"]["totals"]["agents_md_hits"] == 1
            assert data["memory_recall"]["totals"]["cold_recall_hits"] == 1
            assert data["rag_benchmark"]["status"] == "ready"
            assert data["rag_benchmark"]["budget_status"] == "pass"
            assert data["rag_benchmark"]["endpoint"] == "/memory/rag-benchmark"
            assert data["rag_benchmark"]["closure_gate"]["can_claim_deterministic_rag_speed"] is True
            assert data["rag_benchmark"]["closure_gate"]["can_claim_production_embedding_quality"] is False
            assert data["rag_benchmark"]["embedding_quality"]["status"] == "unproven"
            assert data["project_state"]["status"] == "replay"
            assert data["project_state"]["source"] == "session_store_context_sync"
            assert data["project_state"]["next_action"] == "Run Maker build"
            assert data["project_state"]["project_control"]["status"] == "ready"
            assert data["project_state"]["project_control"]["next_action"] == "Run Maker build"
            assert data["project_state"]["project_control"]["layer_control"]["status"] == "watch"
            assert data["project_state"]["project_control"]["engineering_control"]["status"] == "ready"
            assert data["project_state"]["project_control"]["control_actions"][0]["id"] == "capture_or_emit_missing_layer_route_evidence"
            assert "POST_MEM" in data["project_state"]["project_control"]["required_gates"]
            assert data["project_state"]["project_control"]["memory_updates_due"][0]["file"] == "docs/memory-index.md"
            assert data["project_writeback"]["status"] == "ready"
            assert data["project_writeback"]["applicable"] is True
            assert data["project_writeback"]["files"] == [
                "docs/memory-index.md",
                "docs/sprint-board.md",
            ]
            assert data["runtime_advice"]["status"] == "needs_action"
            assert data["runtime_advice"]["priority"] == "maker_mcp_connection"
            assert data["counts"]["context_sync"] == 1
            assert data["counts"]["runtime_metrics"] == 2
            assert data["counts"]["learning"] == 1
            assert data["counts"]["layer"] == 3
            assert data["counts"]["maker_guard"] == 1
            assert data["counts"]["llm_probe"] == 1
            assert data["counts"]["cos_gate"] == 1
            assert data["endpoints"]["evidence_bundle"] == "/sessions/evidence1/evidence?steps=20"
            assert data["endpoints"]["handoff_bundle"] == "/agent/handoff?session_id=evidence1&steps=3"
            assert data["endpoints"]["layer_health"] == "/sessions/evidence1/layer-health?steps=20"
            assert data["endpoints"]["layer_control"] == "/sessions/evidence1/layer-control?steps=20"
            assert data["endpoints"]["engineering_control"] == "/sessions/evidence1/engineering-control?steps=20"
            assert data["endpoints"]["resume_drill"] == "/sessions/evidence1/resume-drill?steps=20"
            assert data["endpoints"]["project_writeback"] == "/sessions/evidence1/project-writeback"
            assert data["endpoints"]["rag_quality"] == "/memory/rag-quality"
            assert "token_rule" in data

            layer_health = _get_json(f"http://127.0.0.1:{port}/sessions/evidence1/layer-health?steps=5")
            assert layer_health["session_id"] == "evidence1"
            assert layer_health["status"] == "active"
            assert layer_health["layers"]["learning"]["queue_depth"] == 0

            layer_control = _get_json(f"http://127.0.0.1:{port}/sessions/evidence1/layer-control?steps=5")
            assert layer_control["session_id"] == "evidence1"
            assert layer_control["status"] == "watch"
            assert layer_control["corrective_actions"][0]["id"] == "capture_or_emit_missing_layer_route_evidence"

            engineering_control = _get_json(f"http://127.0.0.1:{port}/sessions/evidence1/engineering-control?steps=5")
            assert engineering_control["session_id"] == "evidence1"
            assert engineering_control["status"] == "ready"
            assert engineering_control["summary"]["tool_failure_count"] == 0

            resume_drill = _get_json(f"http://127.0.0.1:{port}/sessions/evidence1/resume-drill?steps=5")
            assert resume_drill["session_id"] == "evidence1"
            assert resume_drill["status"] == "ready"
            assert resume_drill["recovered"]["goal_next_focus"] == "Run Maker build"
            assert resume_drill["recovered"]["artifact_refs"][0]["path"] == "scripts/main.lua"

            markdown = _get_text(f"http://127.0.0.1:{port}/sessions/evidence1/evidence?steps=5&format=markdown")
            markdown_path = _get_text(f"http://127.0.0.1:{port}/sessions/evidence1/evidence.md?steps=5")
            assert markdown.startswith("# TTMEvolve Session Evidence")
            assert "## Next Action" in markdown
            assert "priority: `maker_mcp_connection`" in markdown
            assert "## COS Gate" in markdown
            assert "task_type: `refactor_optimization`" in markdown
            assert "mode: `System 2`" in markdown
            assert "observer_health: `ready`" in markdown
            assert "layer_health: `active`" in markdown
            assert "layer_control: `watch`" in markdown
            assert "observer_errors=`0`" in markdown
            assert "## Maker Authority" in markdown
            assert "mcp_readiness: `disconnected`" in markdown
            assert "mcp_connected: `False`" in markdown
            assert "mcp_tool_count: `0`" in markdown
            assert "## Project State" in markdown
            assert "next_action: Run Maker build" in markdown
            assert "project_control: `ready`" in markdown
            assert "engineering_control: `ready`" in markdown
            assert "memory_due: docs/memory-index.md, docs/sprint-board.md" in markdown
            assert "project_writeback: `ready` applicable=`True`" in markdown
            assert "## Layer Communication" in markdown
            assert "## Runtime Event Bus" in markdown
            assert "compatibility=`sse_sqlite_shape_preserved`" in markdown
            assert "observers: runtime=`ready` project=`ready` learning=`ready` memory=`ready`" in markdown
            assert "## Memory And RAG" in markdown
            assert "status: `replay` source=`session_store_context_budget` events=`1`" in markdown
            assert "workspace_profiles: `maker`" in markdown
            assert "hits: agents_md=`1.0` cold_recall=`1.0`" in markdown
            assert "rag_benchmark: `ready` budget=`pass`" in markdown
            assert "embedding_quality: `unproven` claim=`False`" in markdown
            assert "## Shared Memory" in markdown
            assert "default_visibility=`private`" in markdown
            assert "private_other=`False`" in markdown
            assert "promotion_rule: `verified_positive_task_evidence_without_unresolved_conflict`" in markdown
            assert "unresolved_conflicts: `0`" in markdown
            assert "## Continuation" in markdown
            assert "workspace_profile: `maker`" in markdown
            assert "resume_drill: `ready` durable=`ready` warm=`unproven` hot=`unproven`" in markdown
            assert "hot_claim=`False`" in markdown
            assert "goal_next_focus: Run Maker build" in markdown
            assert "agent: state=`active` event=`agent.run.started`" in markdown
            assert "runtime: state=`done` event=`runtime.audit.finished`" in markdown
            assert "learning: state=`done` event=`learning.reflection.finished`" in markdown
            assert "llm_call_proof: `api_call_observed`" in markdown
            assert "/text/chatcompletion_v2" in markdown
            assert "tool_ranking: selected=`6`" in markdown
            assert "evidence_bundle: `/sessions/evidence1/evidence?steps=20`" in markdown
            assert markdown_path == markdown

            onboarding = _get_json(f"http://127.0.0.1:{port}/agent/onboarding?session_id=evidence1&steps=5&surface=codex")
            assert onboarding["version"] == "llm-onboarding.v1"
            assert onboarding["release"] == "v0.4.2-onboarding-closure"
            assert onboarding["surface"]["id"] == "codex"
            assert onboarding["summary"]["decision"] in {
                "stable_small_version_ready",
                "stable_small_version_ready_live_validation_pending",
            }
            assert onboarding["summary"]["api_call_proof"] == "api_call_observed"
            assert onboarding["summary"]["continuation"] == "ready"
            assert onboarding["summary"]["cos_gate"] == "System 2"
            assert onboarding["summary"]["layer_control"] == "watch"
            assert onboarding["summary"]["engineering_control"] == "ready"
            assert onboarding["summary"]["resume_drill"] == "ready"
            assert onboarding["summary"]["event_bus"] in {"ready", "partial"}
            assert onboarding["summary"]["project_state"] == "replay"
            assert onboarding["cos_gate"]["task_type"] == "refactor_optimization"
            assert onboarding["cos_gate"]["source"] == "session_store_cos_gate"
            assert onboarding["shared_memory"]["boundary"] == "owner_private_plus_explicit_shared"
            assert onboarding["shared_memory"]["default_visibility"] == "private"
            assert onboarding["runtime_event_bus"]["status"] in {"ready", "partial"}
            assert onboarding["memory_recall"]["status"] == "replay"
            assert onboarding["memory_recall"]["totals"]["cold_recall_hits"] == 1
            assert onboarding["rag_benchmark"]["status"] == "ready"
            assert onboarding["rag_benchmark"]["budget_status"] == "pass"
            assert onboarding["rag_benchmark"]["embedding_quality"]["status"] == "unproven"
            assert onboarding["rag_benchmark"]["closure_gate"]["can_claim_production_embedding_quality"] is False
            assert onboarding["summary"]["rag_embedding_quality"] == "unproven"
            assert onboarding["learning_observer"]["status"] == "replay"
            assert onboarding["layer_control"]["status"] == "watch"
            assert onboarding["engineering_control"]["status"] == "ready"
            assert onboarding["project_state"]["next_action"] == "Run Maker build"
            assert onboarding["project_control"]["status"] == "ready"
            assert onboarding["project_control"]["next_action"] == "Run Maker build"
            assert onboarding["project_writeback"]["status"] == "ready"
            assert onboarding["project_writeback"]["files"] == [
                "docs/memory-index.md",
                "docs/sprint-board.md",
            ]
            assert any(check["id"] == "project_control" and check["status"] == "ready" for check in onboarding["closure_gate"]["checks"])
            assert any(check["id"] == "project_writeback" and check["status"] == "ready" for check in onboarding["closure_gate"]["checks"])
            assert onboarding["continuation"]["workspace_profile"] == "maker"
            assert onboarding["resume_drill"]["status"] == "ready"
            assert onboarding["resume_drill"]["closure_gate"]["can_claim_long_task_durable_handoff"] is True
            assert onboarding["resume_drill"]["closure_gate"]["can_claim_hot_tool_call_resume"] is False
            assert onboarding["continuation"]["open_plan_steps"][0]["id"] == "build"
            assert onboarding["startup_order"][0] == "/agent/onboarding?session_id=evidence1&steps=20"
            assert onboarding["endpoints"]["onboarding_bundle"] == "/agent/onboarding?session_id=evidence1&steps=20"
            assert onboarding["endpoints"]["rag_quality"] == "/memory/rag-quality"
            assert onboarding["closure_gate"]["checks"][0]["id"] == "any_llm_startup"
            assert any(check["id"] == "long_task_continuation" and check["status"] == "ready" for check in onboarding["closure_gate"]["checks"])
            assert any(check["id"] == "shared_memory_policy" and check["status"] == "ready" for check in onboarding["closure_gate"]["checks"])
            assert any(check["id"] == "runtime_event_bus" and check["status"] == "ready" for check in onboarding["closure_gate"]["checks"])
            assert any(check["id"] == "layer_control" and check["status"] == "watch" for check in onboarding["closure_gate"]["checks"])
            assert any(check["id"] == "engineering_control" and check["status"] == "ready" for check in onboarding["closure_gate"]["checks"])
            assert any(check["id"] == "cos_gate" and check["status"] == "ready" for check in onboarding["closure_gate"]["checks"])
            assert any(check["id"] == "memory_rag_observer" and check["status"] == "ready" for check in onboarding["closure_gate"]["checks"])
            assert any(check["id"] == "rag_benchmark" and check["status"] == "ready" for check in onboarding["closure_gate"]["checks"])
            assert any(check["id"] == "rag_embedding_quality" and check["status"] == "unproven" for check in onboarding["closure_gate"]["checks"])
            assert any(check["id"] == "project_management_state" and check["status"] == "ready" for check in onboarding["closure_gate"]["checks"])
            assert "maker_mcp_remote_authority" in onboarding["closure_gate"]["live_validation_gaps"]
            assert "production_embedding_quality_benchmark" in onboarding["closure_gate"]["live_validation_gaps"]
            assert onboarding["token_strategy"]["metrics"]["tool_ranking"]["selected_count"] == 6
            assert onboarding["token_strategy"]["metrics"]["memory_recall"]["totals"]["cold_recall_hits"] == 1
            assert "TapTap Maker Plus" in onboarding["reference_principles"][0]
            assert "# TTMEvolve LLM Onboarding Bundle" in onboarding["prompt_markdown"]

            onboarding_markdown = _get_text(f"http://127.0.0.1:{port}/agent/onboarding.md?session_id=evidence1&steps=5&surface=codex")
            assert onboarding_markdown.startswith("# TTMEvolve LLM Onboarding Bundle")
            assert "release: `v0.4.2-onboarding-closure`" in onboarding_markdown
            assert "surface: `codex`" in onboarding_markdown
            assert "event_bus: `" in onboarding_markdown
            assert "cos_gate: `System 2`" in onboarding_markdown
            assert "layer_control: `watch`" in onboarding_markdown
            assert "engineering_control: `ready`" in onboarding_markdown
            assert "memory_recall: `replay`" in onboarding_markdown
            assert "rag_benchmark: `ready` budget=`pass`" in onboarding_markdown
            assert "rag_embedding_quality: `unproven` claim=`False`" in onboarding_markdown
            assert "rag_quality: `/memory/rag-quality`" in onboarding_markdown
            assert "project_state: `" in onboarding_markdown
            assert "project_control: `ready`" in onboarding_markdown
            assert "project_writeback: `ready` applicable=`True`" in onboarding_markdown
            assert "## Continuation" in onboarding_markdown
            assert "workspace=`maker`" in onboarding_markdown
            assert "resume_drill: `ready` durable=`ready`" in onboarding_markdown
            assert "onboarding_bundle: `/agent/onboarding?session_id=evidence1&steps=20`" in onboarding_markdown
        finally:
            server.stop()


def test_app_server_skill_sync_status_endpoint():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        project_root = tmp_path / "project"
        skill_dir = tmp_path / "storage" / "skills" / "helper"
        skill_dir.mkdir(parents=True)
        (skill_dir / "skill.json").write_text(
            json.dumps(
                {
                    "id": "helper",
                    "name": "helper",
                    "version": "1.0.0",
                    "description": "Test helper",
                    "parameters": {"type": "object", "properties": {}},
                    "body": "Help with tests",
                }
            ),
            encoding="utf-8",
        )
        project_root.mkdir()
        port = 17354
        server = _make_server(tmp_path, port)
        thread = threading.Thread(target=server.start, daemon=True)
        thread.start()
        time.sleep(1)

        try:
            data = _get_json(f"http://127.0.0.1:{port}/skills/sync-status?force=true")

            assert data["registry"]["state"] == "ok"
            assert data["manifest"]["summary"]["total_records"] == 1
            assert data["manifest"]["summary"]["total_skills"] == 1
            assert data["manifest"]["records"][0]["id"] == "helper"
            assert data["export_plan"]["summary"]["create"] == 4
            assert data["skill_graph"]["nodes"][0]["skill_id"] == "helper"
        finally:
            server.stop()


if __name__ == "__main__":
    test_app_server_session_persisted_and_listed()
    test_app_server_session_events_replay_on_reconnect()
    test_app_server_unconfigured_provider_marks_session_error()
    test_app_server_runs_sessions_without_shared_runtime_queue()
    test_app_server_persists_layer_and_learning_events()
    test_app_server_can_cancel_running_session()
    test_app_server_emits_llm_usage_on_timeout_error()
    test_app_server_commit_history_endpoint()
    test_app_server_context_sync_endpoint()
    test_app_server_runtime_metrics_endpoint()
    test_app_server_maker_guard_endpoint()
    test_app_server_runtime_advice_endpoint_prioritizes_blocked_maker_guard()
    test_app_server_llm_probe_history_endpoint()
    test_app_server_runtime_readiness_endpoint()
    test_app_server_external_llm_quickstart_endpoint()
    test_app_server_maker_briefing_endpoint()
    test_app_server_external_agent_handoff_endpoint()
    test_app_server_evidence_bundle_endpoint()
    test_app_server_skill_sync_status_endpoint()
    print("[PASS] app server resume tests")
