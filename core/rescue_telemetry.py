"""
core/rescue_telemetry.py — 救援遥测数据结构

提供结构化、可序列化的救援事件负载，便于 SSE、事件日志和 benchmark 消费。
"""

from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RescueTelemetry:
    """单次救援过程的关键指标。"""

    trigger_reason: str = "unknown"
    rescue_count: int = 0
    max_rescue_per_session: int = 1
    expert_available: bool = True
    skipped_reason: Optional[str] = None
    expert_latency_ms: Optional[float] = None
    mode: Optional[str] = None
    thought: Optional[str] = None
    action_tool: Optional[str] = None
    takeover_steps: Optional[int] = None
    distill_insights_count: Optional[int] = None
    skill_names: List[str] = field(default_factory=list)
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def to_event_payload(self) -> Dict[str, Any]:
        """转换为 SSE / 事件日志可用的轻量 JSON。"""
        return {
            "trigger_reason": self.trigger_reason,
            "rescue_count": self.rescue_count,
            "max_rescue_per_session": self.max_rescue_per_session,
            "expert_available": self.expert_available,
            "skipped_reason": self.skipped_reason,
            "expert_latency_ms": self.expert_latency_ms,
            "mode": self.mode,
            "thought": self.thought,
            "action_tool": self.action_tool,
            "takeover_steps": self.takeover_steps,
            "distill_insights_count": self.distill_insights_count,
            "skill_names": self.skill_names,
            "error": self.error,
            "timestamp": self.timestamp,
        }

    @classmethod
    def skipped(
        cls,
        reason: str,
        trigger_reason: str = "unknown",
        rescue_count: int = 0,
        max_rescue_per_session: int = 1,
    ) -> "RescueTelemetry":
        return cls(
            trigger_reason=trigger_reason,
            rescue_count=rescue_count,
            max_rescue_per_session=max_rescue_per_session,
            expert_available=False,
            skipped_reason=reason,
        )
