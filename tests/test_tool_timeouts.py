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
from core.approval import ApprovalPolicy
from core.config import Config
from core.commit_state import CommitStateStore, reconcile_observation
from core.event_log import EventLog
from core.executor import Executor
from core.sandbox import SandboxMode
from core.version_manager import VersionManager
from llm.mock_llm import MockLLM


def test_execute_shell_timeout_returns_partial_observation():
    root = _PROJECT_ROOT
    executor = Executor(
        project_root=root,
        event_log=EventLog(root / "storage" / "test-events.jsonl"),
        version_manager=VersionManager(root, root / "storage" / "test-versions"),
        sandbox_mode=SandboxMode.DANGER_FULL_ACCESS,
        approval_policy=ApprovalPolicy.NEVER,
        tool_timeout_seconds=0.3,
        shell_timeout_seconds=0.3,
    )

    command = (
        f'"{sys.executable}" -c '
        '"import time, sys; print(\'started\'); sys.stdout.flush(); time.sleep(2)"'
    )
    result = executor.propose_action("timeout-test", "execute_shell", {"command": command})
    time.sleep(0.2)

    assert result["ok"] is False
    assert result["error_type"] == "tool_timeout"
    assert result["partial"] is True
    assert isinstance(result["stdout"], str)
    assert result["elapsed_ms"] < 2000


def test_write_tools_include_commit_state():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        executor = Executor(
            project_root=root,
            event_log=EventLog(root / "events.jsonl"),
            version_manager=VersionManager(root, root / "versions"),
            sandbox_mode=SandboxMode.WORKSPACE_WRITE,
            approval_policy=ApprovalPolicy.NEVER,
        )

        result = executor.propose_action(
            "commit-state-test",
            "modify_file",
            {"path": "hello.txt", "content": "ok"},
        )

        assert result["ok"] is True
        assert result["committed"] is True
        assert result["idempotency_key"].startswith("commit-state-test:modify_file:")
        assert isinstance(result["observed_at"], float)
        latest = executor.commit_state_store.latest(result["idempotency_key"])
        assert latest is not None
        assert latest["committed"] is True


def test_commit_state_reconcile_verifies_local_file_state():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "hello.txt").write_text("ok", encoding="utf-8")
        observation = {
            "tool": "modify_file",
            "path": "hello.txt",
            "idempotency_key": "s1:modify_file:abc",
            "committed": None,
            "observed_at": time.time(),
        }

        reconciled = reconcile_observation(root, observation)

        assert reconciled["committed"] is True
        assert reconciled["reconcile_status"] == "verified_local"


def test_commit_state_store_records_latest_by_key():
    with tempfile.TemporaryDirectory() as tmp:
        store = CommitStateStore(Path(tmp) / "commit_state.jsonl")
        store.record({"idempotency_key": "k1", "tool": "modify_file", "committed": None})
        store.record({"idempotency_key": "k1", "tool": "modify_file", "committed": True})

        assert store.latest("k1")["committed"] is True


def test_mcp_integration_records_timeout_diagnostics():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
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
                        "request_timeout_seconds": 0.2,
                    },
                }
            ),
            encoding="utf-8",
        )
        agent = TapMakerAgent(llm=MockLLM(), config=Config(config_path))
        try:
            result = agent.mcp_integration._maker_handler("maker_slow", delay=1)
            assert result["ok"] is False
            assert result["error_type"] == "tool_timeout"
            assert result["partial"] is True

            last_call = agent.mcp_integration.status()["last_call"]
            assert last_call["tool"] == "maker_slow"
            assert last_call["ok"] is False
            assert last_call["error_type"] == "tool_timeout"
            assert last_call["timeout_seconds"] == 0.2
        finally:
            agent.close()


if __name__ == "__main__":
    test_execute_shell_timeout_returns_partial_observation()
    test_write_tools_include_commit_state()
    test_commit_state_reconcile_verifies_local_file_state()
    test_commit_state_store_records_latest_by_key()
    test_mcp_integration_records_timeout_diagnostics()
    print("[PASS] tool timeout tests")
