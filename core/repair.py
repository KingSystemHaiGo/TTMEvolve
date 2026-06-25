"""
core/repair.py — 修复调度器

当健康监控检测到 Agent 异常时，RepairScheduler 执行：
1. 保存故障快照
2. 尝试确定性修复（重启 / 回滚 / 恢复出厂）
3. 如果修复失败，进入降级模式并通知人类
4. 修复成功后触发学习转化层复盘
"""

from __future__ import annotations
from pathlib import Path
from typing import Callable, Optional
import time

from .health import HealthMonitor, AgentHealthState
from .version_manager import VersionManager
from .event_log import EventLog, Event


class RepairScheduler:
    """核心运转层的修复调度器。"""

    def __init__(
        self,
        health: HealthMonitor,
        version_manager: VersionManager,
        event_log: EventLog,
        max_attempts: int = 3,
        on_repair_success: Optional[Callable[[str, dict], None]] = None,
    ):
        self.health = health
        self.version_manager = version_manager
        self.event_log = event_log
        self.max_attempts = max_attempts
        self.on_repair_success = on_repair_success
        self._attempt_count = 0
        self._degraded_mode = False

    def check_and_repair(self, session_id: str) -> Optional[str]:
        state = self.health.get_state()
        if not state:
            return None
        if state.status == "healthy":
            self._attempt_count = 0
            return None

        if self._degraded_mode:
            self.event_log.append(Event.create(
                event_type="repair_skipped_degraded",
                session_id=session_id,
                source="runtime",
                payload={"status": state.status},
            ))
            return "degraded"

        self._attempt_count += 1
        if self._attempt_count > self.max_attempts:
            self._enter_degraded_mode(session_id, state)
            return "degraded"

        self.event_log.append(Event.create(
            event_type="repair_started",
            session_id=session_id,
            source="runtime",
            payload={
                "status": state.status,
                "attempt": self._attempt_count,
                "error_count": state.error_count,
            },
        ))

        # 策略：先回滚到上一个健康版本
        result = self._rollback_strategy(session_id, state)
        if result:
            self.event_log.append(Event.create(
                event_type="repair_finished",
                session_id=session_id,
                source="runtime",
                payload={"strategy": "rollback", "result": "success"},
            ))
            self._attempt_count = 0
            if self.on_repair_success:
                self.on_repair_success(session_id, {
                    "strategy": "rollback",
                    "state": state.to_dict(),
                })
            return "repaired"

        # 策略二：重置到出厂默认（如果有 factory_default 快照）
        result = self._factory_reset_strategy(session_id)
        if result:
            self.event_log.append(Event.create(
                event_type="repair_finished",
                session_id=session_id,
                source="runtime",
                payload={"strategy": "factory_reset", "result": "success"},
            ))
            self._attempt_count = 0
            return "repaired"

        self._enter_degraded_mode(session_id, state)
        return "degraded"

    def _rollback_strategy(self, session_id: str, state: AgentHealthState) -> bool:
        snap = self.version_manager.rollback()
        if snap:
            self.health.heartbeat({
                "pid": state.pid,
                "last_progress_event": time.time(),
                "error_count": 0,
                "progress_metric": 0.0,
            })
            return True
        return False

    def _factory_reset_strategy(self, session_id: str) -> bool:
        versions = self.version_manager.list_versions()
        factory = next((v for v in versions if v.description.startswith("factory")), None)
        if factory:
            self.version_manager.rollback(factory.version_id)
            return True
        return False

    def _enter_degraded_mode(self, session_id: str, state: AgentHealthState) -> None:
        self._degraded_mode = True
        self.event_log.append(Event.create(
            event_type="degraded_mode_entered",
            session_id=session_id,
            source="runtime",
            payload={
                "status": state.status,
                "attempts": self._attempt_count,
                "message": "已达到最大修复尝试次数，进入降级模式，等待人类介入。",
            },
        ))

    def reset_degraded_mode(self) -> None:
        self._degraded_mode = False
        self._attempt_count = 0
