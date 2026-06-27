from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from server.agent_bootstrap_api import AgentBootstrapApi
from server.session_store import SessionStore


class _Agent:
    def runtime_contract(self, *, session_id: str) -> Dict[str, Any]:
        return {
            "communication": {
                "portable_runtime": "/runtime/portable",
                "runtime_readiness": f"/runtime/readiness?session_id={session_id}",
                "quickstart_bundle": f"/agent/quickstart?session_id={session_id}&steps=3",
                "evidence_bundle": f"/sessions/{session_id}/evidence?steps=20",
                "resume_drill": f"/sessions/{session_id}/resume-drill?steps=20",
                "runtime_advice": f"/sessions/{session_id}/runtime-advice?steps=20",
                "maker_briefing": f"/agent/maker-briefing?session_id={session_id}",
                "llm_probe": "/llm/probe",
                "llm_probe_history": f"/sessions/{session_id}/llm-probe?steps=20",
                "handoff_bundle": f"/agent/handoff?session_id={session_id}&steps=3",
            },
            "maker_mcp": {"readiness": "ready", "connected": True, "tool_count": 2},
            "external_agents": {"attach_sequence": ["GET /agent/onboarding", "GET /sessions/evidence"]},
            "warning_codes": [],
        }

    def maker_briefing(self, *, session_id: str, task: str = "") -> Dict[str, Any]:
        return {
            "version": "maker-briefing.v1",
            "session_id": session_id,
            "task": task,
            "authority": "maker_mcp",
            "readiness": "ready",
            "selected_template": {"id": "maker_build_or_submit"},
            "recommended_first_action": "Use MakerMCP before local side effects.",
            "suggested_tools": ["maker_publish"],
        }


class _SkillSync:
    def status(self, *, force: bool = False) -> Dict[str, Any]:
        return {
            "registry": {"state": "ok"},
            "skill_graph": {"summary": {"total_skills": 1}},
            "manifest": {"summary": {"total_records": 1}},
        }


class _Server:
    def __init__(self, store: SessionStore):
        self.session_store = store
        self.agent = _Agent()
        self.skill_sync_registry = _SkillSync()

    def get_session(self, _session_id: str):
        return None

    def _latest_llm_probe_for_session(self, session_id: str) -> Dict[str, Any]:
        history = self.session_store.get_llm_probe_history(session_id, limit=1)
        if not history:
            return {}
        latest = dict(history[-1])
        stats: Dict[str, Any] = {}
        for key in ("endpoint", "http_status", "total_tokens", "generate_ms", "error_type"):
            if latest.get(key) is not None:
                stats[key] = latest.get(key)
        latest["last_call_stats"] = stats
        return latest


def test_agent_bootstrap_api_builds_handoff_and_quickstart_from_store_evidence():
    with tempfile.TemporaryDirectory() as tmp:
        store = SessionStore(Path(tmp) / "sessions.db")
        store.create_session("boot1", "build Maker project")
        store.append_event(
            "boot1",
            "context_sync",
            {
                "revision": 3,
                "snapshot": {"task": "build Maker project"},
                "continuation_checkpoint": {"resume_ready": True},
            },
        )
        store.append_event(
            "boot1",
            "context_budget",
            {
                "phase": "think",
                "token_cache_hits": 2,
                "token_cache_misses": 1,
                "context_build_ms": 4.0,
            },
        )
        store.append_event(
            "boot1",
            "llm_probe",
            {
                "ok": True,
                "provider": "minimax",
                "runtime_kind": "api",
                "llm_class": "MiniMaxLLM",
                "last_call_stats": {
                    "endpoint": "https://api.minimax.chat/v1/text/chatcompletion_v2",
                    "total_tokens": 8,
                },
            },
        )
        api = AgentBootstrapApi(_Server(store))

        handoff = api.handoff_bundle("boot1", steps=1)
        quickstart = api.quickstart_bundle("boot1", steps=1, surface="codex")

        assert api.session_available("{session_id}") is True
        assert api.session_available("missing") is False
        assert handoff["session_id"] == "boot1"
        assert handoff["latest_context_sync"]["revision"] == 3
        assert handoff["runtime_metrics_summary"]["token_cache"]["hits"] == 2
        assert handoff["llm_probe_latest"]["provider"] == "minimax"
        assert handoff["skill_summary"]["graph_summary"]["total_skills"] == 1
        assert handoff["token_rule"].startswith("Use this handoff bundle first")
        assert quickstart["version"] == "llm-quickstart.v1"
        assert quickstart["surface"]["id"] == "codex"
        assert quickstart["task"] == "build Maker project"
        assert quickstart["latest_context_sync"]["revision"] == 3
        assert quickstart["llm_probe"]["endpoint"].endswith("/text/chatcompletion_v2")
        assert "GET /agent/quickstart?session_id=boot1&steps=3&surface=codex" in quickstart["boot_sequence"]
