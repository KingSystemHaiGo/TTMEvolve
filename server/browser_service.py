from __future__ import annotations

import base64
import json
import os
import queue
import threading
import time
from concurrent.futures import Future
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


def _ensure_playwright_browser_path() -> None:
    if os.getenv("PLAYWRIGHT_BROWSERS_PATH"):
        return
    root = Path(__file__).resolve().parent.parent
    vendor_browser = root / "vendor" / "playwright"
    if vendor_browser.exists():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(vendor_browser)
        return
    cache_root = Path(os.getenv("TTMEVOLVE_CACHE") or (root / "portable" / "cache"))
    browser_cache = cache_root / "playwright"
    browser_cache.mkdir(parents=True, exist_ok=True)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_cache)


class BrowserService:
    """Single persistent Chromium instance behind one dedicated worker thread.

    Playwright's sync API is thread-affine. The app server is threaded, so every
    public browser operation is marshalled onto the worker that owns Playwright.
    """

    def __init__(self, storage_root: Path, headless: bool = True):
        self.storage_root = Path(storage_root)
        self.headless = headless
        self.user_data_dir = self.storage_root / "browser_profile"
        self.user_data_dir.mkdir(parents=True, exist_ok=True)

        self._playwright: Any = None
        self._context: Any = None
        self._page: Any = None
        self._started = False
        self._logs: List[Dict[str, Any]] = []
        self._max_logs = 200
        self._loading = False
        self._init_error: Optional[str] = None

        self._queue: "queue.Queue[Optional[tuple[Callable[..., Dict[str, Any]], tuple[Any, ...], Future]]]" = queue.Queue()
        self._worker: Optional[threading.Thread] = None
        self._worker_lock = threading.Lock()

    def _ensure_worker(self) -> None:
        with self._worker_lock:
            if self._worker and self._worker.is_alive():
                return
            self._worker = threading.Thread(
                target=self._worker_loop,
                name="ttmevolve-browser",
                daemon=True,
            )
            self._worker.start()

    def _worker_loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                break
            fn, args, fut = item
            try:
                fut.set_result(fn(*args))
            except Exception as exc:
                fut.set_result({"ok": False, "error": str(exc)})

    def _run(self, fn: Callable[..., Dict[str, Any]], *args: Any, timeout: float = 45.0) -> Dict[str, Any]:
        self._ensure_worker()
        fut: Future = Future()
        self._queue.put((fn, args, fut))
        try:
            return fut.result(timeout=timeout)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def start(self) -> Dict[str, Any]:
        return self._run(self._start)

    def _start(self) -> Dict[str, Any]:
        _ensure_playwright_browser_path()
        if self._started:
            return {"ok": True, "info": "already started"}
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            self._init_error = f"playwright is not installed: {exc}"
            return {"ok": False, "error": self._init_error}

        try:
            self._playwright = sync_playwright().start()
            self._context = self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.user_data_dir),
                headless=self.headless,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-gpu-compositing",
                ],
            )
            self._page = self._context.new_page()
            self._page.set_viewport_size({"width": 1365, "height": 768})
            self._page.on("console", self._on_console)
            self._page.on("load", self._on_load)
            self._started = True
            self._init_error = None
            return {"ok": True}
        except Exception as exc:
            self._init_error = str(exc)
            self._cleanup()
            return {"ok": False, "error": self._init_error}

    def stop(self) -> Dict[str, Any]:
        return self._run(self._stop)

    def _stop(self) -> Dict[str, Any]:
        self._cleanup()
        self._started = False
        self._logs = []
        return {"ok": True}

    def _cleanup(self) -> None:
        for obj in (self._page, self._context):
            try:
                if obj:
                    obj.close()
            except Exception:
                pass
        self._page = None
        self._context = None
        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        self._playwright = None
        self._started = False

    def _ensure_started(self) -> Optional[Dict[str, Any]]:
        if self._started and self._page:
            return None
        if self._init_error:
            return {"ok": False, "error": self._init_error}
        return {"ok": False, "error": "browser is not started"}

    def navigate(self, url: str) -> Dict[str, Any]:
        self.start()
        return self._run(self._navigate, url)

    def _navigate(self, url: str) -> Dict[str, Any]:
        err = self._ensure_started()
        if err:
            return err
        try:
            self._loading = True
            self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
            self._loading = False
            return {"ok": True, "url": self._page.url, "title": self._page.title()}
        except Exception as exc:
            self._loading = False
            return {"ok": False, "error": str(exc)}

    def refresh(self) -> Dict[str, Any]:
        return self._run(self._refresh)

    def _refresh(self) -> Dict[str, Any]:
        err = self._ensure_started()
        if err:
            return err
        try:
            self._loading = True
            self._page.reload(wait_until="domcontentloaded", timeout=30000)
            self._loading = False
            return {"ok": True, "url": self._page.url, "title": self._page.title()}
        except Exception as exc:
            self._loading = False
            return {"ok": False, "error": str(exc)}

    def evaluate(self, script: str) -> Dict[str, Any]:
        return self._run(self._evaluate, script)

    def _evaluate(self, script: str) -> Dict[str, Any]:
        err = self._ensure_started()
        if err:
            return err
        try:
            return {"ok": True, "result": self._page.evaluate(script)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def click(self, selector: str) -> Dict[str, Any]:
        return self._run(self._click, selector)

    def _click(self, selector: str) -> Dict[str, Any]:
        err = self._ensure_started()
        if err:
            return err
        try:
            self._page.click(selector, timeout=10000)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def click_at(self, x: float, y: float) -> Dict[str, Any]:
        return self._run(self._click_at, x, y)

    def _click_at(self, x: float, y: float) -> Dict[str, Any]:
        err = self._ensure_started()
        if err:
            return err
        try:
            self._page.mouse.click(float(x), float(y))
            return {"ok": True, "x": x, "y": y}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def screenshot(self) -> Dict[str, Any]:
        return self._run(self._screenshot)

    def _screenshot(self) -> Dict[str, Any]:
        err = self._ensure_started()
        if err:
            return err
        try:
            data = self._page.screenshot(type="jpeg", quality=60, scale="css")
            return {
                "ok": True,
                "data": base64.b64encode(data).decode("ascii"),
                "mime": "image/jpeg",
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def get_info(self) -> Dict[str, Any]:
        return self._run(self._get_info)

    def _get_info(self) -> Dict[str, Any]:
        err = self._ensure_started()
        if err:
            return err
        try:
            return {
                "ok": True,
                "url": self._page.url,
                "title": self._page.title(),
                "loading": self._loading,
                "viewport": self._page.viewport_size,
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def get_logs(self) -> Dict[str, Any]:
        return self._run(self._get_logs)

    def _get_logs(self) -> Dict[str, Any]:
        return {"ok": True, "logs": list(self._logs)}

    def _on_console(self, msg: Any) -> None:
        try:
            entry = {
                "type": msg.type,
                "text": msg.text,
                "location": msg.location,
                "time": time.time(),
            }
        except Exception:
            entry = {"type": "unknown", "text": str(msg), "location": {}, "time": time.time()}
        self._logs.append(entry)
        if len(self._logs) > self._max_logs:
            self._logs = self._logs[-self._max_logs:]

    def _on_load(self, _page: Any) -> None:
        self._loading = False

    def to_json(self) -> str:
        return json.dumps(self.get_info(), ensure_ascii=False, default=str)
