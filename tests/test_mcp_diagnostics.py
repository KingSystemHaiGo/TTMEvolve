from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent.agent import TapMakerAgent
from core.config import Config
from llm.mock_llm import MockLLM
import server.app_server as app_server_module
from server.app_server import AppServer
from server.approval_bridge import ApprovalBridge
from agent.mcp_integration import _match_remote_record, _remote_identity_diagnostics


def _config(tmp_path: Path) -> Config:
    fake_server = _PROJECT_ROOT / "tests" / "fixtures" / "fake_mcp_server.py"
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
                "rescue": {"max_rescue_per_session": 0},
                "learning": {"skill_generation_enabled": False},
                "maker_mcp": {
                    "command": sys.executable,
                    "args": [str(fake_server)],
                    "cwd": str(_PROJECT_ROOT),
                    "env": {},
                },
            }
        ),
        encoding="utf-8",
    )
    return Config(str(config_path))


def _get_json(url: str):
    with urllib.request.urlopen(url, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post_json(url: str, payload: dict | None = None):
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def test_mcp_integration_reports_status_and_last_call():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        cfg = _config(tmp_path)
        agent = TapMakerAgent(llm=MockLLM(), config=cfg)
        try:
            status = agent.mcp_integration.status()
            assert status["connected"] is True
            assert status["tool_count"] >= 1
            assert "maker_ping" in [tool["name"] for tool in status["tools"]]
            assert status["remote_identity"]["status"] == "present"
            assert "maker_list_tasks" in status["remote_identity"]["task_lookup_tools"]
            assert "maker_list_files" in status["remote_identity"]["file_lookup_tools"]

            result = agent.mcp_integration._maker_handler("maker_ping", message="hi")
            assert result["ok"] is True
            status = agent.mcp_integration.status()
            assert status["last_call"]["tool"] == "maker_ping"
            assert status["last_call"]["ok"] is True
            assert status["last_call"]["elapsed_ms"] >= 0
            assert status["last_call"]["params_keys"] == ["message"]

            result = agent.executor.propose_action("s1", "maker_status_lite", {})
            assert result["ok"] is True
            assert result["result"]["status"] == "ok"
            status = agent.mcp_integration.status()
            assert status["last_call"]["tool"] == "maker_status_lite"
            assert status["last_call"]["ok"] is True
            assert status["last_call"]["params_keys"] == []

            result = agent.mcp_integration._maker_handler("maker_list_tasks")
            assert result["ok"] is True
            status = agent.mcp_integration.status()
            assert "result.tasks[0].task_id" in status["last_call"]["id_fields"]
            assert "result.tasks[0].task_id" in status["remote_identity"]["last_call_id_fields"]

            result = agent.mcp_integration._maker_handler("maker_business_fail")
            assert result["ok"] is False
            assert result["failure_type"] == "remote_business_failure"
            status = agent.mcp_integration.status()
            assert status["last_call"]["ok"] is False
            assert status["last_call"]["error_type"] == "remote_business_failure"
            assert status["last_call"]["failure_type"] == "remote_business_failure"
        finally:
            agent.close()


def test_mcp_integration_mounts_unavailable_creative_proxy_tools():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        cfg = _config(tmp_path)
        agent = TapMakerAgent(llm=MockLLM(), config=cfg)
        try:
            names = {tool["name"]: tool for tool in agent.tools.list_tools()}
            assert "generate_image" in names
            assert names["generate_image"]["source"] == "maker_mcp_unavailable"

            result = agent.executor.propose_action("s1", "generate_image", {"prompt": "test"})

            assert result["ok"] is False
            assert result["error_type"] == "maker_proxy_not_exposed"
            assert result["failure_type"] == "remote_capability_missing"
            assert result["repairable"] is True
            assert result["params_keys"] == ["prompt"]
        finally:
            agent.close()


def test_app_server_exposes_mcp_status_and_tools():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        cfg = _config(tmp_path)
        agent = TapMakerAgent(llm=MockLLM(), config=cfg)
        server = AppServer(agent, host="127.0.0.1", port=17352, approval_bridge=ApprovalBridge())
        thread = threading.Thread(target=server.start, daemon=True)
        thread.start()
        time.sleep(1)

        try:
            status = _get_json("http://127.0.0.1:17352/mcp/status")
            assert status["connected"] is True
            assert status["tool_count"] >= 1
            assert status["remote_identity"]["status"] == "present"
            probed_status = _get_json("http://127.0.0.1:17352/mcp/status?probe=true")
            assert probed_status["probe"]["ok"] is True
            assert probed_status["probe"]["source"] == "fresh_stdio_initialize_tools_list"
            assert "maker_ping" in probed_status["probe"]["tools_preview"]
            probe = _get_json("http://127.0.0.1:17352/mcp/probe")
            assert probe["ok"] is True
            assert probe["tool_count"] >= 1
            tools = _get_json("http://127.0.0.1:17352/mcp/tools")
            assert "maker_ping" in [tool["name"] for tool in tools["tools"]]
        finally:
            server.stop()
            agent.close()


def test_app_server_hot_repairs_maker_access_without_restart():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        old_app_root = app_server_module.APP_ROOT
        app_server_module.APP_ROOT = tmp_path / "agent-root"
        app_server_module.APP_ROOT.mkdir(parents=True, exist_ok=True)
        cfg = _config(tmp_path)
        agent = TapMakerAgent(llm=MockLLM(), config=cfg)
        server = AppServer(agent, host="127.0.0.1", port=17353, approval_bridge=ApprovalBridge())
        thread = threading.Thread(target=server.start, daemon=True)
        thread.start()
        time.sleep(1)

        try:
            result = _post_json("http://127.0.0.1:17353/maker/repair")

            assert result["ok"] is True
            assert result["hot_repair"] is True
            assert result["restart_required"] is False
            assert result["repair_status"] in {"success", "degraded_success"}
            assert result["tool_audit"]["repair_ok"] is True
            assert result["tool_audit"]["readiness"] in {"ready", "degraded"}
        finally:
            server.stop()
            agent.close()
            app_server_module.APP_ROOT = old_app_root


def test_remote_identity_diagnostics_reports_missing_lookup_tools():
    diagnostics = _remote_identity_diagnostics(
        [{"name": "maker_ping", "description": "fake ping", "inputSchema": {}}],
        None,
    )

    assert diagnostics["status"] == "missing"
    assert diagnostics["missing"] == ["task_lookup", "file_lookup"]


def test_mcp_remote_commit_resolver_verifies_matching_file_record():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        cfg = _config(tmp_path)
        agent = TapMakerAgent(llm=MockLLM(), config=cfg)
        try:
            observation = {
                "tool": "generate_image",
                "path": "scripts/main.lua",
                "idempotency_key": "s1:generate_image:abc",
                "committed": None,
            }

            reconciled = agent.executor.reconcile_commit_state(observation)

            assert reconciled["committed"] is True
            assert reconciled["reconcile_status"] == "verified_remote"
            assert reconciled["remote_lookup_tool"] == "maker_list_files"
            assert reconciled["remote_match"]["file_id"] == "file-1"
        finally:
            agent.close()


def test_mcp_remote_commit_resolver_keeps_unknown_without_match():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        cfg = _config(tmp_path)
        agent = TapMakerAgent(llm=MockLLM(), config=cfg)
        try:
            observation = {
                "tool": "generate_image",
                "path": "missing.png",
                "idempotency_key": "s1:generate_image:def",
                "committed": None,
            }

            reconciled = agent.executor.reconcile_commit_state(observation)

            assert reconciled["committed"] is None
            assert reconciled["reconcile_status"] == "remote_lookup_no_match"
            assert reconciled["remote_lookup_attempts"]
        finally:
            agent.close()


def test_remote_record_match_does_not_use_tool_name_as_identity():
    observation = {
        "tool": "generate_image",
        "idempotency_key": "s1:generate_image:def",
        "committed": None,
    }
    result = {
        "ok": True,
        "result": {
            "tasks": [
                {"task_id": "task-1", "status": "done", "tool": "generate_image"}
            ]
        },
    }

    assert _match_remote_record(observation, result) is None


if __name__ == "__main__":
    test_mcp_integration_reports_status_and_last_call()
    test_mcp_integration_mounts_unavailable_creative_proxy_tools()
    test_app_server_exposes_mcp_status_and_tools()
    test_app_server_hot_repairs_maker_access_without_restart()
    test_remote_identity_diagnostics_reports_missing_lookup_tools()
    test_mcp_remote_commit_resolver_verifies_matching_file_record()
    test_mcp_remote_commit_resolver_keeps_unknown_without_match()
    test_remote_record_match_does_not_use_tool_name_as_identity()
    print("[PASS] mcp diagnostics")
