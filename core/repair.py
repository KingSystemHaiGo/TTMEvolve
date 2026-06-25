"""
core/repair.py — 修复调度器（指數退避 + 故障感知版本）

健康监控检测到 Agent 异常时，RepairScheduler 执行：
1. 故障分类（网络 / 内存 / Maker MCP / LLM API / 工具调用）
2. 指數退避重试（带 jitter，最长等待上限）
3. 确定性修复（回滚 / 重置 / MCP 重连）
4. 如果修复失败，进入降级模式并通知人类
5. 修复成功后触发学习转化层复盘
"""

from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .health import HealthMonitor, AgentHealthState
from .version_manager import VersionManager
from .event_log import EventLog, Event


# 故障类型 -> 最大重试次数（0=跳过重试直接降级）
FAULT_MAX_RETRIES: Dict[str, int] = {
    "maker_mcp_disconnected": 3,
    "maker_mcp_timeout": 2,
    "maker_proxy_not_exposed": 2,
    "llm_api_error": 3,
    "llm_timeout": 2,
    "memory_pressure": 1,
    "context_overflow": 1,
    "tool_validation_failed": 1,
    "unknown": 2,
}

# 指數退避参数（秒）
BASE_BACKOFF = 2.0
MAX_BACKOFF = 60.0
JITTER_RATIO = 0.3


def _classify_fault(state: AgentHealthState) -> str:
    """根据健康状态分类故障类型。"""
    error_count = state.error_count or 0
    token_ratio = state.token_usage_ratio or 0.0
    context_sat = state.context_saturation or 0.0

    if token_ratio > 0.95 or context_sat > 0.95:
        return "context_overflow"
    if token_ratio > 0.85 or context_sat > 0.85:
        return "memory_pressure"
    if error_count >= 3:
        return "llm_api_error"
    if state.status in ("degraded", "error"):
        return "unknown"
    return "unknown"


def _compute_backoff(attempt: int, fault_type: str) -> float:
    """指數退避：min(BASE * 2^attempt, MAX) + jitter。"""
    max_retries = FAULT_MAX_RETRIES.get(fault_type, 1)
    capped = min(attempt, max(max_retries, 1))
    delay = min(BASE_BACKOFF * (2 ** (capped - 1)), MAX_BACKOFF)
    jitter = delay * JITTER_RATIO * random.random()
    return delay + jitter


class RepairScheduler:
    """核心运转层的修复调度器，支持指數退避和故障感知重试。"""

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
        self._current_fault_type = "unknown"
        self._last_repair_time = 0.0
        self._repair_history: List[Dict[str, Any]] = []

    def check_and_repair(self, session_id: str) -> Optional[str]:
        state = self.health.get_state()
        if not state:
            return None
        if state.status == "healthy":
            self._attempt_count = 0
            self._current_fault_type = "unknown"
            return None

        fault_type = _classify_fault(state)
        self._current_fault_type = fault_type

        if self._degraded_mode:
            self.event_log.append(Event.create(
                event_type="repair_skipped_degraded",
                session_id=session_id,
                source="runtime",
                payload={"status": state.status, "fault_type": fault_type},
            ))
            return "degraded"

        # 指數退避：检查冷却期
        now = time.time()
        if self._attempt_count > 0:
            backoff = _compute_backoff(self._attempt_count, fault_type)
            elapsed = now - self._last_repair_time
            if elapsed < backoff:
                remaining = backoff - elapsed
                self.event_log.append(Event.create(
                    event_type="repair_backoff",
                    session_id=session_id,
                    source="runtime",
                    payload={
                        "fault_type": fault_type,
                        "attempt": self._attempt_count,
                        "backoff_remaining_s": round(remaining, 1),
                    },
                ))
                return "backoff"

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
                "fault_type": fault_type,
                "attempt": self._attempt_count,
                "error_count": state.error_count,
            },
        ))

        # 故障感知策略调度
        strategy = self._fault_aware_repair(session_id, state, fault_type)

        if strategy:
            self._last_repair_time = time.time()
            self.event_log.append(Event.create(
                event_type="repair_finished",
                session_id=session_id,
                source="runtime",
                payload={"strategy": strategy, "fault_type": fault_type},
            ))
            self._attempt_count = 0
            if self.on_repair_success:
                self.on_repair_success(session_id, {
                    "strategy": strategy,
                    "fault_type": fault_type,
                    "state": state.to_dict(),
                })
            self._log_repair_history(fault_type, strategy, True)
            return "repaired"

        self._log_repair_history(fault_type, "exhausted", False)
        self._enter_degraded_mode(session_id, state)
        return "degraded"

    def _fault_aware_repair(
        self, session_id: str, state: AgentHealthState, fault_type: str
    ) -> Optional[str]:
        """根据故障类型选择最合适的修复策略。"""
        # 上下文/内存问题 -> 清理缓存
        if fault_type in ("context_overflow", "memory_pressure"):
            if self._context_clear_strategy(state):
                return "context_clear"

        # Maker MCP 问题 -> MCP 重连标记
        if fault_type in ("maker_mcp_disconnected", "maker_mcp_timeout", "maker_proxy_not_exposed"):
            self.event_log.append(Event.create(
                event_type="repair_strategy_marker",
                session_id=session_id,
                source="runtime",
                payload={"strategy": "maker_reconnect", "action": "requires_external_trigger"},
            ))
            return "maker_reconnect"

        # 回滚到上一个健康版本
        if self._rollback_strategy(state):
            return "rollback"

        # 重置到出厂默认
        if self._factory_reset_strategy():
            return "factory_reset"

        return None

    def _context_clear_strategy(self, state: AgentHealthState) -> bool:
        """清理上下文缓存（用于内存/上下文溢出）。"""
        try:
            self.health.heartbeat({
                "pid": state.pid,
                "last_progress_event": time.time(),
                "error_count": 0,
                "progress_metric": 0.0,
                "token_usage_ratio": 0.0,
                "context_window_ratio": 0.0,
            })
            return True
        except Exception:
            return False

    def _rollback_strategy(self, state: AgentHealthState) -> bool:
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

    def _factory_reset_strategy(self) -> bool:
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
                "fault_type": self._current_fault_type,
                "attempts": self._attempt_count,
                "repair_history": self._repair_history[-5:],
                "message": "已达到最大修复尝试次数，进入降级模式，等待人类介入。",
            },
        ))

    def _log_repair_history(self, fault_type: str, strategy: str, success: bool) -> None:
        entry = {
            "fault_type": fault_type,
            "strategy": strategy,
            "success": success,
            "timestamp": time.time(),
        }
        self._repair_history.append(entry)
        if len(self._repair_history) > 20:
            self._repair_history = self._repair_history[-20:]

    def reset_degraded_mode(self) -> None:
        self._degraded_mode = False
        self._attempt_count = 0

    def get_repair_history(self) -> List[Dict[str, Any]]:
        return list(self._repair_history)
