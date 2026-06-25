"""
server/approval_bridge.py — Server 模式下的人类审批桥

将同步的 Executor/ApprovalEngine 与异步的 HTTP GUI 连接起来：
- 当 Agent 执行高风险动作需要人类确认时，通过 SSE 发送 approval_request 事件；
- 工作线程在 threading.Event 上阻塞等待；
- GUI 通过 POST /sessions/{id}/approve 提交决定后，唤醒工作线程继续执行。
"""

from __future__ import annotations
import threading
import time
from typing import Dict, Optional


class ApprovalBridge:
    """同步 Executor 与异步 HTTP GUI 之间的审批桥。"""

    DEFAULT_TIMEOUT = 300.0  # 5 分钟无响应则自动拒绝

    def __init__(self, default_timeout: float = DEFAULT_TIMEOUT):
        self._default_timeout = default_timeout
        self._pending: Dict[str, threading.Event] = {}
        self._results: Dict[str, bool] = {}
        self._lock = threading.Lock()

    def request(self, session_id: str, action_id: str, timeout: Optional[float] = None) -> bool:
        """
        由 Executor 工作线程调用（阻塞）。

        Returns:
            True 表示人类批准，False 表示拒绝或超时。
        """
        key = self._key(session_id, action_id)
        event = threading.Event()
        with self._lock:
            self._pending[key] = event
            self._results[key] = False

        wait_seconds = timeout or self._default_timeout
        start = time.time()
        event.wait(timeout=wait_seconds)

        with self._lock:
            result = self._results.pop(key, False)
            self._pending.pop(key, None)

        # 如果是因为超时醒来且结果仍为 False，说明没有收到响应
        if not result and (time.time() - start) >= wait_seconds:
            return False
        return result

    def respond(self, session_id: str, action_id: str, allowed: bool) -> bool:
        """
        由 HTTP handler 调用，通知等待中的工作线程审批结果。

        Returns:
            True 表示成功找到并唤醒了对应的等待线程。
        """
        key = self._key(session_id, action_id)
        with self._lock:
            event = self._pending.get(key)
            if event is None:
                return False
            self._results[key] = allowed
            event.set()
            return True

    def has_pending(self, session_id: str, action_id: str) -> bool:
        """查询指定审批是否仍在等待中。"""
        key = self._key(session_id, action_id)
        with self._lock:
            return key in self._pending and not self._pending[key].is_set()

    @staticmethod
    def _key(session_id: str, action_id: str) -> str:
        return f"{session_id}:{action_id}"
