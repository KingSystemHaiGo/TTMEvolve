from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent.mcp_client import MakerMCPClient


def test_mcp_client_initializes_lists_and_calls_tools():
    server = _PROJECT_ROOT / "tests" / "fixtures" / "fake_mcp_server.py"
    client = MakerMCPClient(
        command=sys.executable,
        args=[str(server)],
        cwd=_PROJECT_ROOT,
    )

    try:
        client.start()
        tools = client.list_tools()
        assert "maker_ping" in [tool["name"] for tool in tools]

        result = client.call("maker_ping", {"message": "hello"})
        assert result["ok"] is True
        assert result["result"]["content"][0]["text"] == "pong:hello"
    finally:
        client.stop()


def test_mcp_client_times_out_slow_tool_calls():
    server = _PROJECT_ROOT / "tests" / "fixtures" / "fake_mcp_server.py"
    client = MakerMCPClient(
        command=sys.executable,
        args=[str(server)],
        cwd=_PROJECT_ROOT,
        request_timeout_seconds=0.2,
    )

    try:
        client.start()
        try:
            client.call("maker_slow", {"delay": 1}, timeout_seconds=0.2)
        except TimeoutError as e:
            assert "timed out" in str(e)
        else:
            raise AssertionError("expected TimeoutError")
    finally:
        client.stop()


def test_mcp_client_marks_tool_business_failure():
    server = _PROJECT_ROOT / "tests" / "fixtures" / "fake_mcp_server.py"
    client = MakerMCPClient(
        command=sys.executable,
        args=[str(server)],
        cwd=_PROJECT_ROOT,
    )

    try:
        client.start()
        result = client.call("maker_business_fail", {})

        assert result["ok"] is False
        assert result["error_type"] == "remote_business_failure"
        assert result["failure_type"] == "remote_business_failure"
        assert "图片编辑失败" in result["error"]
        assert result["result_is_error"] is True
        assert result["structured_success"] is False
    finally:
        client.stop()


if __name__ == "__main__":
    test_mcp_client_initializes_lists_and_calls_tools()
    test_mcp_client_times_out_slow_tool_calls()
    test_mcp_client_marks_tool_business_failure()
    print("[PASS] mcp client")
