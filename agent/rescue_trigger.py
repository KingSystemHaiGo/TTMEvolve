"""
agent/rescue_trigger.py — 救援触发器

多因素判断当前 ReAct 会话是否需要请求外部专家 LLM 救援。
"""

from __future__ import annotations
import json
import time
from typing import Any, Dict, List, Optional

from core.config import Config
from core.health import AgentHealthState
from core import error_hooks


class RescueRequired(Exception):
    """表示需要触发专家救援。"""

    def __init__(self, reason: str = "unknown"):
        super().__init__(reason)
        self.reason = reason


class RescueTrigger:
    """根据轨迹和健康状态判断是否触发救援。"""

    def __init__(self, config: Optional[Config] = None):
        self.cfg = config or Config()
        self.max_consecutive_errors = int(
            self.cfg.get("rescue.max_consecutive_errors", 3)
        )
        self.max_iterations_ratio = float(
            self.cfg.get("rescue.max_iterations_ratio", 0.75)
        )
        self.detect_repeated_actions = bool(
            self.cfg.get("rescue.detect_repeated_actions", True)
        )
        self.health_degraded = bool(
            self.cfg.get("rescue.health_degraded", True)
        )
        self.max_iterations = int(
            self.cfg.get("react_loop.max_iterations", 20)
        )

    def evaluate(
        self,
        trajectory: List[Dict[str, Any]],
        health_state: Optional[AgentHealthState] = None,
    ) -> bool:
        """返回 True 表示应该触发救援。"""
        if self._consecutive_errors(trajectory):
            return True
        if self._iteration_exhaustion(trajectory):
            return True
        if self._repeated_actions(trajectory):
            return True
        if self._health_degraded(health_state):
            return True
        return False

    def check_and_raise(
        self,
        trajectory: List[Dict[str, Any]],
        health_state: Optional[AgentHealthState] = None,
    ) -> None:
        """如果满足触发条件，抛出 RescueRequired（带具体原因）。"""
        reason = self._first_trigger_reason(trajectory, health_state)
        if reason:
            # Phase L: surface a rescue trigger through the error
            # hook. The agent is "stuck" at this point; the
            # operator should see why and how often it recurs.
            error_hooks.fire(
                "vsm",
                message=f"rescue trigger fired: {reason}",
                severity="critical",
                extra={
                    "trigger_reason": reason,
                    "trajectory_len": len(trajectory),
                },
            )
            raise RescueRequired(reason=reason)

    def _first_trigger_reason(
        self,
        trajectory: List[Dict[str, Any]],
        health_state: Optional[AgentHealthState] = None,
    ) -> Optional[str]:
        if self._consecutive_errors(trajectory):
            return "consecutive_errors"
        if self._iteration_exhaustion(trajectory):
            return "iteration_exhaustion"
        if self._repeated_actions(trajectory):
            return "repeated_actions"
        if self._health_degraded(health_state):
            return "health_degraded"
        return None

    def _consecutive_errors(self, trajectory: List[Dict[str, Any]]) -> bool:
        if self.max_consecutive_errors <= 0:
            return False
        count = 0
        for step in reversed(trajectory):
            observation = step.get("observation", {}) or {}
            if not observation.get("ok", True):
                count += 1
                if count >= self.max_consecutive_errors:
                    return True
            else:
                break
        return False

    def _iteration_exhaustion(self, trajectory: List[Dict[str, Any]]) -> bool:
        if not trajectory:
            return False
        iteration = trajectory[-1].get("iteration", len(trajectory))
        threshold = self.max_iterations * self.max_iterations_ratio
        if iteration >= threshold:
            # 只有在还没有成功输出时才触发
            last_step = trajectory[-1]
            if not last_step.get("output"):
                return True
        return False

    def _repeated_actions(self, trajectory: List[Dict[str, Any]]) -> bool:
        if not self.detect_repeated_actions:
            return False
        if len(trajectory) < 3:
            return False
        last_three = trajectory[-3:]
        actions = []
        for step in last_three:
            action = step.get("action", {}) or {}
            if not action.get("tool"):
                return False
            actions.append(json.dumps(action, sort_keys=True, ensure_ascii=False))
        return len(set(actions)) == 1

    def _health_degraded(self, health_state: Optional[AgentHealthState]) -> bool:
        if not self.health_degraded or health_state is None:
            return False
        return health_state.status in ("degraded", "stalled")
