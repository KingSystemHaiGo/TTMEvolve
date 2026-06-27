"""
tests/test_app_server.py — App Server 冒烟测试
"""

from __future__ import annotations
import json
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.portable_env import apply_portable_env
from server.app_server import create_default_app_server


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_app_server_health_and_tools():
    apply_portable_env(_PROJECT_ROOT, force=True)
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    server = create_default_app_server(str(_PROJECT_ROOT / "config.json"), "mock", port=port)
    server.session_store.create_session("probe-smoke", "probe llm")
    thread = threading.Thread(target=server.start, daemon=True)
    thread.start()
    time.sleep(1)

    try:
        with urllib.request.urlopen(f"{base_url}/health", timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data.get("status") == "ok"
            assert data.get("provider") == "mock"
            assert data.get("runtime_kind") == "mock"
            assert data.get("llm_class")
            assert "last_call_stats" in data
            print("[PASS] health endpoint")

        with urllib.request.urlopen(f"{base_url}/tools", timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert "tools" in data
            assert len(data["tools"]) > 0
            print("[PASS] tools endpoint")

        with urllib.request.urlopen(f"{base_url}/runtime/portable", timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data.get("version") == "portable-runtime.v1"
            assert data.get("status") in {"ready", "degraded"}
            assert data.get("config", {}).get("portable_root", "").endswith("portable")
            assert data.get("windows_user_dir_leaks") == []
            print("[PASS] portable runtime endpoint")

        probe_req = urllib.request.Request(
            f"{base_url}/llm/probe",
            data=json.dumps({"provider": "mock", "session_id": "probe-smoke"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(probe_req, timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data.get("ok") is True
            assert data.get("provider") == "mock"
            assert data.get("runtime_kind") == "mock"
            assert data.get("llm_class") == "MockLLM"
            assert "output_preview" in data
            print("[PASS] llm probe endpoint")

        with urllib.request.urlopen(f"{base_url}/sessions/probe-smoke/llm-probe?steps=2", timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data.get("count") == 1
            assert data.get("latest", {}).get("provider") == "mock"
            print("[PASS] llm probe history endpoint")
    finally:
        server.stop()


if __name__ == "__main__":
    test_app_server_health_and_tools()
    print("[PASS] all app server tests")
