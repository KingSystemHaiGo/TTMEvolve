"""
tests/test_browser_endpoints.py — 浏览器 HTTP 端点测试

若当前环境未安装 playwright / chromium，则自动跳过。
"""

from __future__ import annotations
import base64
import json
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent.agent import TapMakerAgent
from core.config import Config
from llm.llm_factory import LLMFactory
from server.app_server import AppServer
from server.approval_bridge import ApprovalBridge

TEST_PORT = 17348


def _playwright_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        executable = pw.chromium.executable_path
        pw.stop()
        return bool(executable and Path(executable).exists())
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _playwright_available(),
    reason="playwright / chromium binary not available",
)


def _make_server(tmpdir: Path) -> AppServer:
    config_path = tmpdir / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "llm": {"provider": "mock"},
                "project_root": str(tmpdir),
                "storage_root": str(tmpdir / "storage"),
                "sandbox": {"mode": "workspace-write"},
                "approval": {"policy": "on-request"},
            }
        ),
        encoding="utf-8",
    )
    cfg = Config(str(config_path))
    llm = LLMFactory.create("mock", cfg)
    agent = TapMakerAgent(llm=llm, config=cfg)
    return AppServer(agent, port=TEST_PORT, approval_bridge=ApprovalBridge())


@pytest.fixture
def server(tmp_path: Path):
    """为每个测试启动一个隔离的 AppServer（仅在 playwright 可用时执行）。"""
    srv = _make_server(tmp_path)
    thread = threading.Thread(target=srv.start, daemon=True)
    thread.start()
    for _ in range(50):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{TEST_PORT}/health", timeout=0.1):
                break
        except Exception:
            time.sleep(0.05)
    yield srv
    srv.stop()


def _post_json(path: str, body: dict) -> dict:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{TEST_PORT}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = {"error": body}
        data["_http_status"] = e.code
        return data


def _get_json(path: str) -> dict:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{TEST_PORT}{path}", timeout=10
        ) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = {"error": body}
        data["_http_status"] = e.code
        return data


def _get_bytes(path: str) -> tuple[int, bytes, dict]:
    req = urllib.request.Request(f"http://127.0.0.1:{TEST_PORT}{path}")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, resp.read(), dict(resp.headers)


def test_navigate(server: AppServer, tmp_path: Path):
    res = _post_json("/browser/navigate", {"url": "data:text/html,<title>EP</title>"})
    assert res.get("ok") is True, res
    assert res.get("title") == "EP", res
    print("[PASS] endpoint navigate")


def test_info_and_logs(server: AppServer, tmp_path: Path):
    _post_json("/browser/navigate", {"url": 'data:text/html,<script>console.log("ep-log")</script>'})
    time.sleep(0.5)
    info = _get_json("/browser/info")
    assert info.get("ok") is True, info
    logs = _get_json("/browser/logs")
    assert logs.get("ok") is True, logs
    texts = [log["text"] for log in logs.get("logs", [])]
    assert "ep-log" in texts, texts
    print("[PASS] endpoint info/logs")


def test_screenshot(server: AppServer, tmp_path: Path):
    _post_json("/browser/navigate", {"url": "data:text/html,<h1>X</h1>"})
    status, data, headers = _get_bytes("/browser/screenshot")
    assert status == 200, status
    assert headers.get("Content-Type") == "image/jpeg", headers
    assert data[:2] == b"\xff\xd8", data[:8]
    print("[PASS] endpoint screenshot")


def test_evaluate(server: AppServer, tmp_path: Path):
    _post_json("/browser/navigate", {"url": "data:text/html,<script>y=7</script>"})
    res = _post_json("/browser/evaluate", {"script": "y * 6"})
    assert res.get("ok") is True, res
    assert res.get("result") == 42, res
    print("[PASS] endpoint evaluate")


def test_missing_param(server: AppServer, tmp_path: Path):
    res = _post_json("/browser/navigate", {})
    assert res.get("_http_status") == 400 or res.get("ok") is False, res
    print("[PASS] endpoint missing param")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        server = _make_server(tmpdir)
        thread = threading.Thread(target=server.start, daemon=True)
        thread.start()
        time.sleep(1)

        try:
            test_navigate(tmpdir)
            test_info_and_logs(tmpdir)
            test_screenshot(tmpdir)
            test_evaluate(tmpdir)
            test_missing_param(tmpdir)
            print("[PASS] all browser endpoint tests")
        finally:
            server.stop()
