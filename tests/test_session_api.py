from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from server.session_api import SessionRouteApi, parse_step_limit
from server.session_store import SessionStore


class _LiveSession:
    session_id = "live1"
    task = "live task"
    done = False
    error = None
    cancelled = False


class _Server:
    def __init__(self, store: SessionStore, live_session: _LiveSession | None = None):
        self.session_store = store
        self._live_session = live_session

    def get_session(self, session_id: str):
        if self._live_session and self._live_session.session_id == session_id:
            return self._live_session
        return None


def test_parse_step_limit_uses_steps_or_limit_and_clamps():
    assert parse_step_limit({"steps": ["5"]}, default=100, maximum=500) == 5
    assert parse_step_limit({"limit": ["9"]}, default=100, maximum=500) == 9
    assert parse_step_limit({"steps": ["999"]}, default=100, maximum=500) == 500
    assert parse_step_limit({"steps": ["0"]}, default=100, maximum=500) == 1
    assert parse_step_limit({"steps": ["bad"]}, default=100, maximum=500) == 100


def test_session_route_api_status_prefers_live_session_and_falls_back_to_store():
    with tempfile.TemporaryDirectory() as tmp:
        store = SessionStore(Path(tmp) / "sessions.db")
        store.create_session("stored1", "stored task")
        store.mark_done("stored1", result={"ok": True})

        live_payload = SessionRouteApi(_Server(store, _LiveSession())).status_payload("live1")
        stored_payload = SessionRouteApi(_Server(store)).status_payload("stored1")
        missing_payload = SessionRouteApi(_Server(store)).status_payload("missing")

        assert live_payload == {
            "session_id": "live1",
            "task": "live task",
            "done": False,
            "status": "running",
            "error": None,
            "canceled": False,
        }
        assert stored_payload is not None
        assert stored_payload["session_id"] == "stored1"
        assert stored_payload["task"] == "stored task"
        assert stored_payload["done"] is True
        assert stored_payload["status"] == "done"
        assert missing_payload is None

