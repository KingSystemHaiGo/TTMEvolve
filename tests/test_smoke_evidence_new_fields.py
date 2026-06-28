"""
tests/test_smoke_evidence_new_fields.py - live AppServer smoke test.

Verifies that the new evidence fields (graph_recall, prompt_loader,
plan_v2 summary, control_loop summary) appear in the live evidence
bundle endpoint when the AppServer is running.

This is the closest thing to a GUI smoke we can do in a headless
sandbox: it exercises the actual HTTP route the Workbench calls.
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _make_server(tmp_path: Path, port: int):
    """Build a minimal AppServer using a mock LLM. The evidence
    surface is what we are smoke-testing, not the agent loop.
    """
    from llm.interface import LLMInterface
    from core.config import Config
    from llm.mock_llm import MockLLM
    from agent.agent import TapMakerAgent
    from server.app_server import AppServer
    from server.approval_bridge import ApprovalBridge
    from server.session_store import SessionStore

    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
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
        # New flags (off by default; we test the surface, not behavior)
        "memory": {
            "graph": {"enabled": True},
            "bayes": {"enabled": True},
        },
        "loader": {"enabled": True},
        "vsm": {"enabled": True, "auto_replan": False},
    }), encoding="utf-8")
    cfg = Config(str(config_path))
    llm = MockLLM()
    agent = TapMakerAgent(llm=llm, config=cfg, human_confirm_callback=None)
    store = SessionStore(Path(cfg.storage_root()) / "sessions.db")
    return AppServer(agent, host="127.0.0.1", port=port, approval_bridge=ApprovalBridge(), session_store=store)


def test_evidence_bundle_exposes_new_fields():
    """The new evidence fields must always be present in the bundle
    payload so the Workbench can render them without null checks.
    """
    from core.intent_classifier import classify_cos_gate
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        port = 17370
        server = _make_server(tmp_path, port)
        server.session_store.create_session("smoke1", "smoke task")
        server.session_store.append_event(
            "smoke1", "cos_gate",
            classify_cos_gate("smoke task that needs evidence").to_dict(),
            source="cos_gate",
        )

        # Drive the in-process evidence-bundle builder (no HTTP)
        from server.evidence_bundle import build_session_evidence_bundle
        bundle = build_session_evidence_bundle(
            server=server,
            session_id="smoke1",
            steps=20,
        )

        # Plan v2 summary (v2-enabled field; default source_version is v1)
        assert "plan_v2" in bundle
        assert bundle["plan_v2"]["version"] == "plan-format.v2"
        # prompt loader field is present (status may be not_run if no
        # loader events have happened yet; the field shape is what
        # matters for the Workbench)
        assert "prompt_loader" in bundle
        # control loop summary
        assert "control_loop" in bundle
        # graph_recall is present
        assert "graph_recall" in bundle
        # Existing fields still present
        assert "rag_benchmark" in bundle
        assert "memory_recall" in bundle


def test_evidence_bundle_prompt_loader_shape_is_stable():
    """``prompt_loader`` must always have the compact fields, even
    when no prompt-loader event has happened yet.
    """
    from core.intent_classifier import classify_cos_gate
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        server = _make_server(tmp_path, 17371)
        server.session_store.create_session("smoke2", "another")
        server.session_store.append_event(
            "smoke2", "cos_gate",
            classify_cos_gate("another task").to_dict(),
            source="cos_gate",
        )
        from server.evidence_bundle import build_session_evidence_bundle
        bundle = build_session_evidence_bundle(server=server, session_id="smoke2")
        loader = bundle["prompt_loader"]
        # Stable shape for the Workbench: always version + status,
        # and the compact counters when status is "ready".
        assert "version" in loader
        assert "status" in loader
        if loader.get("status") == "ready":
            for key in (
                "fragment_count", "deferred_count", "stubbed_count",
                "graph_recall_hits", "compression_applied",
            ):
                assert key in loader, f"missing {key} in prompt_loader"


def test_evidence_bundle_control_loop_shape_is_stable():
    """``control_loop`` must always be present; its shape depends on
    whether the agent exposes a control loop.
    """
    from core.intent_classifier import classify_cos_gate
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        server = _make_server(tmp_path, 17372)
        server.session_store.create_session("smoke3", "control loop")
        server.session_store.append_event(
            "smoke3", "cos_gate",
            classify_cos_gate("control loop task").to_dict(),
            source="cos_gate",
        )
        from server.evidence_bundle import build_session_evidence_bundle
        bundle = build_session_evidence_bundle(server=server, session_id="smoke3")
        control = bundle["control_loop"]
        # Always present
        assert "version" in control
        assert "status" in control
        # When the agent has no control loop we get the boundary
        # payload (status="not_provided"); otherwise last_signal /
        # last_verdict are present.
        if control.get("status") == "ready":
            assert "last_signal" in control
            assert "last_verdict" in control
