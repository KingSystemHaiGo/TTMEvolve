"""
tests/test_gui_flow.py — GUI 与审批流程测试

覆盖 ApprovalBridge、App Server 静态文件服务、以及 /approve 端点。
"""

from __future__ import annotations
import json
import sys
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
from server.approval_bridge import ApprovalBridge
from server.app_server import AppServer, create_default_app_server


_TEST_PORT_COUNTER = 17345
_TEST_PORT_LOCK = threading.Lock()


def test_approval_bridge_basic():
    """ApprovalBridge 能被正常请求和响应。"""
    bridge = ApprovalBridge(default_timeout=2.0)
    results = {}

    def worker():
        results["allowed"] = bridge.request("s1", "a1")

    t = threading.Thread(target=worker)
    t.start()
    time.sleep(0.1)
    assert bridge.has_pending("s1", "a1")
    assert bridge.respond("s1", "a1", True)
    t.join(timeout=3.0)
    assert results.get("allowed") is True


def test_approval_bridge_timeout_rejects():
    """超时时 ApprovalBridge 返回 False。"""
    bridge = ApprovalBridge(default_timeout=0.2)
    assert bridge.request("s2", "a2") is False


def test_approval_bridge_unknown_response_fails():
    """对不存在的审批请求响应应返回 False。"""
    bridge = ApprovalBridge()
    assert bridge.respond("unknown", "unknown", True) is False


_TEST_PORT_COUNTER = 17345
_TEST_PORT_LOCK = threading.Lock()


class _TestServerHelper:
    """启动 App Server 并在测试结束后关闭的小工具。"""

    def __init__(self, provider: str = "mock"):
        self.provider = provider
        self.server = None
        self.thread = None
        self.host = "127.0.0.1"
        global _TEST_PORT_COUNTER
        with _TEST_PORT_LOCK:
            self.port = _TEST_PORT_COUNTER
            _TEST_PORT_COUNTER += 1

    def start(self):
        self.server = create_default_app_server(
            config_path=str(Path(__file__).resolve().parent.parent / "config.json"),
            provider=self.provider,
        )
        self.server.host = self.host
        self.server.port = self.port
        self.thread = threading.Thread(target=self.server.start, daemon=True)
        self.thread.start()
        last_error = None
        for _ in range(160):
            try:
                with urllib.request.urlopen(f"http://{self.host}:{self.port}/health", timeout=0.5):
                    return
            except Exception as e:
                last_error = e
                time.sleep(0.1)
        raise RuntimeError(f"Test server failed to start on port {self.port}: {last_error}")

    def stop(self):
        if self.server:
            self.server.stop()

    def url(self, path: str) -> str:
        return f"http://{self.host}:{self.port}{path}"

    def post(self, path: str, payload: dict) -> dict:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.url(path),
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get(self, path: str) -> bytes:
        with urllib.request.urlopen(self.url(path), timeout=5.0) as resp:
            return resp.read()


def test_static_file_serving():
    """App Server 能正确返回 web/index.html。"""
    helper = _TestServerHelper()
    try:
        helper.start()
        html = helper.get("/").decode("utf-8")
        assert "TTMEvolve" in html
        css = helper.get("/web/style.css").decode("utf-8")
        assert "--bg" in css
        js = helper.get("/web/app.js").decode("utf-8")
        assert "TTMEvolveGUI" in js
    finally:
        helper.stop()


def test_approve_endpoint_no_pending():
    """对不存在的审批请求调用 /approve 返回 410。"""
    helper = _TestServerHelper()
    try:
        helper.start()
        try:
            helper.post("/sessions/fake/approve", {"action_id": "x", "allowed": True})
            raise AssertionError("Should have raised HTTPError")
        except urllib.error.HTTPError as e:
            assert e.code == 410
    finally:
        helper.stop()


def test_session_creation_and_status():
    """能创建 session 并轮询状态。"""
    helper = _TestServerHelper(provider="mock")
    try:
        helper.start()
        data = helper.post("/sessions", {"task": "say hello"})
        assert "session_id" in data
        sid = data["session_id"]
        status = json.loads(helper.get(f"/sessions/{sid}/status").decode("utf-8"))
        assert status["session_id"] == sid
    finally:
        helper.stop()


def test_end_to_end_approval_flow():
    """模拟前端：提交触发 modify_file 的任务，收到 approval_request 后批准，任务成功。"""
    global _TEST_PORT_COUNTER
    with _TEST_PORT_LOCK:
        port = _TEST_PORT_COUNTER
        _TEST_PORT_COUNTER += 1

    config = Config(str(Path(__file__).resolve().parent.parent / "config.json"))
    llm = MockLLM(scripted_actions=[
        {"tool": "modify_file", "params": {"path": "gui_test_hello.txt", "content": "hello from gui test"}},
        {"done": True, "output": "文件已创建"},
    ])
    agent = TapMakerAgent(llm=llm, config=config, human_confirm_callback=None)
    server = AppServer(agent, port=port)
    thread = threading.Thread(target=server.start, daemon=True)
    thread.start()

    try:
        # 等待 server 就绪
        for _ in range(80):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.1):
                    break
            except Exception:
                time.sleep(0.05)
        else:
            raise RuntimeError("Server not ready")

        # 创建 session
        data = json.loads(_post(port, "/sessions", {"task": "创建一个文件"}).decode("utf-8"))
        sid = data["session_id"]

        # 消费 SSE 事件
        events = []
        action_id = None
        req = urllib.request.Request(f"http://127.0.0.1:{port}/sessions/{sid}/events")
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            while True:
                line = resp.readline().decode("utf-8", errors="replace")
                if not line:
                    break
                if line.startswith("data: "):
                    event = json.loads(line[6:])
                    events.append(event)
                    if event.get("type") == "approval_request":
                        action_id = event["payload"]["action_id"]
                        # 发送批准
                        _post(port, f"/sessions/{sid}/approve", {"action_id": action_id, "allowed": True})
                    if event.get("type") == "status" and event["payload"].get("done"):
                        break

        # 验证审批请求被处理，且最终有 output/status
        assert action_id is not None, "Expected approval_request event"
        assert any(e.get("type") == "observation" and e["payload"].get("observation", {}).get("ok") for e in events)
    finally:
        server.stop()


def _post(port: int, path: str, payload: dict) -> bytes:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5.0) as resp:
        return resp.read()


if __name__ == "__main__":
    test_approval_bridge_basic()
    print("OK test_approval_bridge_basic")

    test_approval_bridge_timeout_rejects()
    print("OK test_approval_bridge_timeout_rejects")

    test_approval_bridge_unknown_response_fails()
    print("OK test_approval_bridge_unknown_response_fails")

    test_static_file_serving()
    print("OK test_static_file_serving")

    test_approve_endpoint_no_pending()
    print("OK test_approve_endpoint_no_pending")

    test_session_creation_and_status()
    print("OK test_session_creation_and_status")

    test_end_to_end_approval_flow()
    print("OK test_end_to_end_approval_flow")

    print("\nAll GUI flow tests passed.")
