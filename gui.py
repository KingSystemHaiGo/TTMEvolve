"""
gui.py — TTMEvolve 桌面 GUI 启动器

用 pywebview 把 web/ 前端包成原生桌面窗口，
同时复用已有的 App Server 作为后端。
"""

from __future__ import annotations
import os
import threading
import time
import urllib.request
from typing import Optional

from server.app_server import AppServer


def is_server_running(host: str = "127.0.0.1", port: int = 7345) -> bool:
    """检查 App Server 是否已在运行。"""
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/health", timeout=1.0) as resp:
            return resp.status == 200
    except Exception:
        return False


def start_server_thread(server: AppServer) -> threading.Thread:
    """在后台线程启动 App Server，并等待它就绪。"""
    thread = threading.Thread(target=server.start, daemon=True)
    thread.start()
    for _ in range(50):
        if is_server_running(server.host, server.port):
            return thread
        time.sleep(0.1)
    raise RuntimeError("App Server 未能在 5 秒内启动")


def open_gui(
    server: AppServer,
    title: str = "TTMEvolve Agent",
    width: int = 1200,
    height: int = 800,
    task: Optional[str] = None,
) -> None:
    """
    打开 pywebview 桌面窗口，加载本地 App Server 提供的 GUI 页面。

    Args:
        server: 已配置好的 AppServer 实例（可能已在运行）。
        title: 窗口标题。
        width: 窗口宽度。
        height: 窗口高度。
        task: 可选，自动携带到 URL 中启动任务。
    """
    if os.environ.get("TTM_EVOLVE_HEADLESS") in ("1", "true", "yes"):
        raise RuntimeError("Headless mode: skipping pywebview window")

    try:
        import webview  # type: ignore
    except ImportError as e:
        raise RuntimeError("pywebview 未安装，请运行: pip install pywebview>=5.0") from e

    if not is_server_running(server.host, server.port):
        start_server_thread(server)

    query = ""
    if task:
        from urllib.parse import quote
        query = f"?task={quote(task)}"

    url = f"http://{server.host}:{server.port}/{query}"

    window = webview.create_window(
        title,
        url,
        width=width,
        height=height,
        min_size=(800, 600),
        text_select=True,
    )

    # pywebview 的 start 会阻塞直到窗口关闭
    webview.start(debug=False)


def open_browser(
    host: str = "127.0.0.1",
    port: int = 7345,
    task: Optional[str] = None,
) -> None:
    """退化为浏览器打开（当 pywebview 不可用时）。"""
    import webbrowser
    from urllib.parse import quote

    query = f"?task={quote(task)}" if task else ""
    webbrowser.open(f"http://{host}:{port}/{query}")
