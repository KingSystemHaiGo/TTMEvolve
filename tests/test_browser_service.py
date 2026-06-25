"""
tests/test_browser_service.py — BrowserService 单元测试

如果当前环境未安装 playwright 或未下载 Chromium 二进制，
测试会自动跳过并打印提示。
"""

from __future__ import annotations
import sys
import tempfile
import time
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from server.browser_service import BrowserService


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


def test_start_stop():
    with tempfile.TemporaryDirectory() as tmp:
        svc = BrowserService(Path(tmp))
        res = svc.start()
        assert res["ok"], res
        assert svc._started
        res2 = svc.stop()
        assert res2["ok"]
        assert not svc._started
        print("[PASS] start/stop")


def test_navigate_and_info():
    with tempfile.TemporaryDirectory() as tmp:
        svc = BrowserService(Path(tmp))
        svc.start()
        try:
            res = svc.navigate("data:text/html,<title>HelloBrowser</title>")
            assert res["ok"], res
            info = svc.get_info()
            assert info["ok"], info
            assert info["title"] == "HelloBrowser"
        finally:
            svc.stop()
    print("[PASS] navigate and info")


def test_screenshot():
    with tempfile.TemporaryDirectory() as tmp:
        svc = BrowserService(Path(tmp))
        svc.start()
        try:
            svc.navigate("data:text/html,<h1>Hi</h1>")
            res = svc.screenshot()
            assert res["ok"], res
            data = __import__("base64").b64decode(res["data"])
            # JPEG magic bytes
            assert data[:2] == b"\xff\xd8", data[:8]
        finally:
            svc.stop()
    print("[PASS] screenshot")


def test_evaluate():
    with tempfile.TemporaryDirectory() as tmp:
        svc = BrowserService(Path(tmp))
        svc.start()
        try:
            svc.navigate("data:text/html,<script>x=42</script>")
            res = svc.evaluate("x + 1")
            assert res["ok"], res
            assert res["result"] == 43
        finally:
            svc.stop()
    print("[PASS] evaluate")


def test_click():
    with tempfile.TemporaryDirectory() as tmp:
        svc = BrowserService(Path(tmp))
        svc.start()
        try:
            svc.navigate(
                'data:text/html,<button id="btn" onclick="document.title=\'clicked\'">Go</button>'
            )
            res = svc.click("#btn")
            assert res["ok"], res
            time.sleep(0.5)
            info = svc.get_info()
            assert info["title"] == "clicked", info
        finally:
            svc.stop()
    print("[PASS] click")


def test_click_at():
    with tempfile.TemporaryDirectory() as tmp:
        svc = BrowserService(Path(tmp))
        svc.start()
        try:
            svc.navigate(
                "data:text/html,"
                "<button style='position:absolute;left:0;top:0;width:120px;height:80px' "
                "onclick=\"document.title='clicked-at'\">Go</button>"
            )
            res = svc.click_at(20, 20)
            assert res["ok"], res
            time.sleep(0.5)
            info = svc.get_info()
            assert info["title"] == "clicked-at", info
        finally:
            svc.stop()
    print("[PASS] click_at")


def test_console_logs():
    with tempfile.TemporaryDirectory() as tmp:
        svc = BrowserService(Path(tmp))
        svc.start()
        try:
            svc.navigate('data:text/html,<script>console.log("browser-log-test")</script>')
            time.sleep(0.5)
            logs = svc.get_logs()
            assert logs["ok"], logs
            texts = [log["text"] for log in logs["logs"]]
            assert "browser-log-test" in texts, texts
        finally:
            svc.stop()
    print("[PASS] console logs")


def test_persistence():
    with tempfile.TemporaryDirectory() as tmp:
        profile = Path(tmp)
        svc = BrowserService(profile)
        svc.start()
        try:
            svc.navigate("data:text/html,<script>document.cookie='key=value; path=/';</script>")
            time.sleep(0.5)
        finally:
            svc.stop()

        svc2 = BrowserService(profile)
        svc2.start()
        try:
            svc2.navigate("data:text/html,<title>Check</title>")
            res = svc2.evaluate("document.cookie")
            assert res["ok"], res
            assert "key=value" in (res["result"] or ""), res
        finally:
            svc2.stop()
    print("[PASS] persistence")


if __name__ == "__main__":
    test_start_stop()
    test_navigate_and_info()
    test_screenshot()
    test_evaluate()
    test_click()
    test_click_at()
    test_console_logs()
    test_persistence()
    print("[PASS] all browser service tests")
