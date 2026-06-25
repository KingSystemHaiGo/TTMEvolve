"""
tests/test_session_store.py — SQLite 会话持久化单元测试
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from server.session_store import SessionStore


def test_create_and_get_session():
    with tempfile.TemporaryDirectory() as tmp:
        store = SessionStore(Path(tmp) / "sessions.db")
        store.create_session("s1", "list files", provider="mock", profile="safe")

        session = store.get_session("s1")
        assert session is not None
        assert session["session_id"] == "s1"
        assert session["task"] == "list files"
        assert session["provider"] == "mock"
        assert session["profile"] == "safe"
        assert session["status"] == "running"


def test_append_and_get_events():
    with tempfile.TemporaryDirectory() as tmp:
        store = SessionStore(Path(tmp) / "sessions.db")
        store.create_session("s1", "list files")
        store.append_event(
            "s1",
            "status",
            {"message": "started"},
            meta={"event_id": "e1", "channel": "session"},
            source="react",
        )
        store.append_event("s1", "thought", {"iteration": 0, "thought": "hi"})

        events = store.get_events("s1")
        assert len(events) == 2
        assert events[0]["type"] == "status"
        assert events[0]["session_id"] == "s1"
        assert events[0]["payload"]["message"] == "started"
        assert events[0]["source"] == "react"
        assert events[0]["meta"]["event_id"] == "e1"
        assert events[1]["type"] == "thought"


def test_mark_done_with_result():
    with tempfile.TemporaryDirectory() as tmp:
        store = SessionStore(Path(tmp) / "sessions.db")
        store.create_session("s1", "list files")
        store.mark_done("s1", result={"output": "done"})

        session = store.get_session("s1")
        assert session["status"] == "done"
        assert session["result"] == {"output": "done"}
        assert session["error"] is None


def test_mark_done_with_error():
    with tempfile.TemporaryDirectory() as tmp:
        store = SessionStore(Path(tmp) / "sessions.db")
        store.create_session("s1", "list files")
        store.mark_done("s1", error="boom")

        session = store.get_session("s1")
        assert session["status"] == "error"
        assert session["error"] == "boom"


def test_mark_cancelled():
    with tempfile.TemporaryDirectory() as tmp:
        store = SessionStore(Path(tmp) / "sessions.db")
        store.create_session("s1", "long task")
        store.mark_cancelled("s1", result={"cancelled": True})

        session = store.get_session("s1")
        assert session["status"] == "canceled"
        assert session["result"] == {"cancelled": True}
        assert session["error"] is None


def test_list_sessions_ordered_by_updated():
    with tempfile.TemporaryDirectory() as tmp:
        store = SessionStore(Path(tmp) / "sessions.db")
        store.create_session("s1", "first")
        store.create_session("s2", "second")
        store.create_session("s3", "third")

        sessions = store.list_sessions(limit=10)
        assert len(sessions) == 3
        # 默认按 updated_at 倒序，最后创建的在最前
        assert sessions[0]["session_id"] == "s3"
        assert sessions[1]["session_id"] == "s2"
        assert sessions[2]["session_id"] == "s1"


def test_list_sessions_filter_by_status():
    with tempfile.TemporaryDirectory() as tmp:
        store = SessionStore(Path(tmp) / "sessions.db")
        store.create_session("s1", "running task")
        store.create_session("s2", "done task")
        store.mark_done("s2", result={"output": "ok"})

        running = store.list_sessions(status="running")
        done = store.list_sessions(status="done")
        assert len(running) == 1 and running[0]["session_id"] == "s1"
        assert len(done) == 1 and done[0]["session_id"] == "s2"


def test_events_survive_reopen():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "sessions.db"
        store = SessionStore(db_path)
        store.create_session("s1", "list files")
        store.append_event("s1", "output", {"output": "hello"})
        store.mark_done("s1", result={"output": "hello"})

        # 模拟重启：新建 SessionStore 实例读取同一文件
        store2 = SessionStore(db_path)
        session = store2.get_session("s1")
        assert session["status"] == "done"
        events = store2.get_events("s1")
        assert len(events) == 1
        assert events[0]["payload"]["output"] == "hello"


def test_commit_history_extracts_observation_and_reconcile_events():
    with tempfile.TemporaryDirectory() as tmp:
        store = SessionStore(Path(tmp) / "sessions.db")
        store.create_session("s1", "write file")
        store.append_event("s1", "thought", {"iteration": 0, "thought": "write"})
        store.append_event(
            "s1",
            "observation",
            {
                "iteration": 0,
                "tool": "modify_file",
                "observation": {
                    "ok": False,
                    "tool": "modify_file",
                    "path": "hello.txt",
                    "idempotency_key": "s1:modify_file:abc",
                    "committed": None,
                    "observed_at": 1.0,
                },
            },
        )
        store.append_event(
            "s1",
            "commit_reconcile",
            {
                "iteration": 0,
                "tool": "modify_file",
                "status": "verified_local",
                "committed": True,
                "observation": {
                    "tool": "modify_file",
                    "path": "hello.txt",
                    "idempotency_key": "s1:modify_file:abc",
                    "committed": True,
                    "reconcile_status": "verified_local",
                    "observed_at": 2.0,
                },
            },
        )

        history = store.get_commit_history("s1", limit=10)

        assert len(history) == 2
        assert history[0]["event_type"] == "observation"
        assert history[0]["committed"] is None
        assert history[1]["event_type"] == "commit_reconcile"
        assert history[1]["committed"] is True
        assert history[1]["reconcile_status"] == "verified_local"


def test_llm_probe_history_extracts_endpoint_stats():
    with tempfile.TemporaryDirectory() as tmp:
        store = SessionStore(Path(tmp) / "sessions.db")
        store.create_session("s1", "probe llm")
        store.append_event(
            "s1",
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
                    "generate_ms": 1199.0,
                },
            },
        )

        history = store.get_llm_probe_history("s1", limit=5)

        assert len(history) == 1
        assert history[0]["provider"] == "minimax"
        assert history[0]["endpoint"].endswith("/text/chatcompletion_v2")
        assert history[0]["total_tokens"] == 12


if __name__ == "__main__":
    test_create_and_get_session()
    test_append_and_get_events()
    test_mark_done_with_result()
    test_mark_done_with_error()
    test_mark_cancelled()
    test_list_sessions_ordered_by_updated()
    test_list_sessions_filter_by_status()
    test_events_survive_reopen()
    test_llm_probe_history_extracts_endpoint_stats()
    test_commit_history_extracts_observation_and_reconcile_events()
    print("[PASS] session store tests")
