"""
core/health.py — 健康状态观测

维护 Agent 层的实时状态，供核心运转层判断是否异常。
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Deque, Optional
import json
import time
from collections import deque


@dataclass
class AgentHealthState:
    pid: int
    last_heartbeat: float
    last_progress_event: float
    iteration_count: int
    progress_metric: float       # 0.0 ~ 1.0
    token_usage_ratio: float     # 0.0 ~ 1.0
    context_window_ratio: float  # 0.0 ~ 1.0
    error_count: int
    recent_actions: Deque[str] = field(default_factory=lambda: deque(maxlen=20))
    status: str = "healthy"      # healthy / degraded / stalled / crashed
    context_saturation: str = "normal"  # normal / elevated / high / critical

    def is_stalled(self, now: Optional[float] = None) -> bool:
        now = now or time.time()
        # 60 秒没有心跳视为 stalled
        return (now - self.last_heartbeat) > 60

    def is_progress_stalled(self, now: Optional[float] = None) -> bool:
        now = now or time.time()
        # 120 秒没有进展事件视为进度停滞
        return (now - self.last_progress_event) > 120

    def to_dict(self) -> dict:
        return {
            "pid": self.pid,
            "last_heartbeat": self.last_heartbeat,
            "last_progress_event": self.last_progress_event,
            "iteration_count": self.iteration_count,
            "progress_metric": self.progress_metric,
            "token_usage_ratio": self.token_usage_ratio,
            "context_window_ratio": self.context_window_ratio,
            "error_count": self.error_count,
            "recent_actions": list(self.recent_actions),
            "status": self.status,
            "context_saturation": self.context_saturation,
        }


class HealthMonitor:
    """健康监控：接收心跳、更新状态、检测异常。"""

    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._state_path = storage_path / "health_state.json"
        self._state: Optional[AgentHealthState] = None
        self._load()

    def heartbeat(self, update: dict) -> AgentHealthState:
        now = time.time()
        if self._state is None:
            self._state = AgentHealthState(
                pid=update.get("pid", 0),
                last_heartbeat=now,
                last_progress_event=update.get("last_progress_event", now),
                iteration_count=update.get("iteration_count", 0),
                progress_metric=update.get("progress_metric", 0.0),
                token_usage_ratio=update.get("token_usage_ratio", 0.0),
                context_window_ratio=update.get("context_window_ratio", 0.0),
                error_count=update.get("error_count", 0),
            )
        else:
            self._state.pid = update.get("pid", self._state.pid)
            self._state.last_heartbeat = now
            self._state.last_progress_event = update.get(
                "last_progress_event", self._state.last_progress_event
            )
            self._state.iteration_count = update.get("iteration_count", self._state.iteration_count)
            self._state.progress_metric = update.get("progress_metric", self._state.progress_metric)
            self._state.token_usage_ratio = update.get("token_usage_ratio", self._state.token_usage_ratio)
            self._state.context_window_ratio = update.get("context_window_ratio", self._state.context_window_ratio)
            self._state.error_count = update.get("error_count", self._state.error_count)

        if update.get("action"):
            self._state.recent_actions.append(update["action"])

        self._state.context_saturation = self._classify_context_saturation(
            self._state.context_window_ratio
        )
        self._state.status = self._classify(self._state, now)
        self._save()
        return self._state

    def _classify(self, state: AgentHealthState, now: float) -> str:
        if state.is_stalled(now):
            return "stalled"
        if (
            state.error_count > 5
            or state.token_usage_ratio > 0.95
            or state.context_window_ratio > 0.9
        ):
            return "degraded"
        if state.is_progress_stalled(now):
            return "degraded"
        return "healthy"

    def _classify_context_saturation(self, ratio: float) -> str:
        if ratio >= 0.95:
            return "critical"
        if ratio >= 0.9:
            return "high"
        if ratio >= 0.8:
            return "elevated"
        return "normal"

    def get_state(self) -> Optional[AgentHealthState]:
        return self._state

    def _save(self) -> None:
        if self._state:
            self._state_path.write_text(
                json.dumps(self._state.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def _load(self) -> None:
        if not self._state_path.exists():
            return
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            data["recent_actions"] = deque(data.get("recent_actions", []), maxlen=20)
            data.setdefault("context_saturation", self._classify_context_saturation(
                float(data.get("context_window_ratio", 0.0) or 0.0)
            ))
            self._state = AgentHealthState(**data)
        except Exception:
            self._state = None
