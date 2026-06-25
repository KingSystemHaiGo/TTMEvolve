"""
agent/rescue_orchestrator.py — 救援编排器

协调本地 ReAct 循环与外部专家 LLM 的救援流程。
"""

from __future__ import annotations
import time
from typing import Any, Dict, List, Optional

from core.config import Config
from agent.rescue_trigger import RescueRequired, RescueTrigger
from core.health import HealthMonitor
from core.rescue_telemetry import RescueTelemetry
from llm.expert_protocol import RescueAction
from llm.expert_rescuer import ExpertRescuer


class RescueOrchestrator:
    """本地模型为主，外部专家 LLM 救援，成功后沉淀技能。"""

    def __init__(
        self,
        react_loop: Any,
        expert_rescuer: ExpertRescuer,
        trigger: RescueTrigger,
        distiller: Optional[Any],
        health: Optional[HealthMonitor],
        config: Optional[Config] = None,
    ):
        self.react = react_loop
        self.expert = expert_rescuer
        self.trigger = trigger
        self.distiller = distiller
        self.health = health
        self.cfg = config or Config()

        self._rescue_count = 0
        self._last_rescue_time = 0.0
        self._last_trigger_reason = "unknown"
        self._in_rescue = False
        self._max_rescue_per_session = int(
            self.cfg.get("rescue.max_rescue_per_session", 1)
        )
        self._cooldown_seconds = float(
            self.cfg.get("rescue.cooldown_seconds", 60)
        )
        self._distill_after_rescue = bool(
            self.cfg.get("rescue.distill_after_rescue", True)
        )

    def run(self, task: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """运行任务，必要时触发专家救援。"""
        result = None
        resumed = False
        while True:
            try:
                result = self.react.run(
                    task=task,
                    session_id=session_id,
                    on_step=self._check_rescue,
                    resume=resumed,
                )
                break
            except RescueRequired as exc:
                self._last_trigger_reason = getattr(exc, "reason", "unknown")
                self._emit("rescue_triggered", {"reason": self._last_trigger_reason})

                skip_reason = self._can_rescue()
                if skip_reason:
                    telemetry = RescueTelemetry.skipped(
                        reason=skip_reason,
                        trigger_reason=self._last_trigger_reason,
                        rescue_count=self._rescue_count,
                        max_rescue_per_session=self._max_rescue_per_session,
                    )
                    self._emit("rescue_skipped", telemetry.to_event_payload())
                    # 不能再救援，让本地模型继续直到自然结束
                    result = self.react.run(
                        task=task,
                        session_id=session_id,
                        on_step=None,
                        resume=resumed,
                    )
                    break

                self._emit("rescue_calling", {"reason": self._last_trigger_reason})
                started_at = time.time()
                rescue = self._call_expert(task)
                latency_ms = (time.time() - started_at) * 1000

                telemetry = RescueTelemetry(
                    trigger_reason=self._last_trigger_reason,
                    rescue_count=self._rescue_count,
                    max_rescue_per_session=self._max_rescue_per_session,
                    expert_available=True,
                    expert_latency_ms=latency_ms,
                    mode=rescue.mode,
                    thought=rescue.thought,
                    action_tool=(rescue.action or {}).get("tool") if rescue.action else None,
                    takeover_steps=rescue.takeover_steps,
                )
                self._emit("rescue_action", telemetry.to_event_payload())

                self._in_rescue = True
                try:
                    self._apply_rescue(rescue)
                finally:
                    self._in_rescue = False
                self._rescue_count += 1
                self._last_rescue_time = time.time()
                telemetry.rescue_count = self._rescue_count
                self._emit("rescue_applied", telemetry.to_event_payload())
                resumed = True

        if self._rescue_count > 0 and self._distill_after_rescue and self.distiller:
            try:
                distill_result = self.distiller.distill(
                    session_id=result.get("session_id") if result else session_id,
                    trajectory=self.react.trajectory,
                )
                telemetry = RescueTelemetry(
                    trigger_reason=self._last_trigger_reason,
                    rescue_count=self._rescue_count,
                    max_rescue_per_session=self._max_rescue_per_session,
                    distill_insights_count=distill_result.get("insights_count", 0),
                    skill_names=distill_result.get("skill_names", []),
                )
                self._emit("rescue_distilled", telemetry.to_event_payload())
            except Exception as e:
                telemetry = RescueTelemetry(
                    trigger_reason=self._last_trigger_reason,
                    rescue_count=self._rescue_count,
                    max_rescue_per_session=self._max_rescue_per_session,
                    error=str(e),
                )
                self._emit("rescue_distilled", telemetry.to_event_payload())
                print(f"[RescueOrchestrator] 蒸馏失败：{e}")

        return result or {"session_id": session_id, "task": task, "output": "", "trajectory": [], "iteration_count": 0}

    def _check_rescue(self, step: Dict[str, Any], trajectory: List[Dict[str, Any]]) -> None:
        """on_step 回调：判断是否触发救援。救援执行期间不再嵌套触发。"""
        if self._in_rescue:
            return
        health_state = self.health.get_state() if self.health else None
        try:
            self.trigger.check_and_raise(trajectory, health_state)
        except RescueRequired as exc:
            self._last_trigger_reason = getattr(exc, "reason", "unknown")
            raise

    def _can_rescue(self) -> Optional[str]:
        """检查救援次数与冷却，返回跳过原因（None 表示可以救援）。"""
        if self._rescue_count >= self._max_rescue_per_session:
            return "max_rescue_reached"
        now = time.time()
        if now - self._last_rescue_time < self._cooldown_seconds:
            return "cooldown"
        if not self.expert.is_available():
            return "expert_unavailable"
        return None

    def _emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        """通过 ReActLoop 的事件通道发送救援事件。"""
        if hasattr(self.react, "_emit") and self.react._emit:
            try:
                self.react._emit(
                    getattr(self.react, "_session_id", "unknown"),
                    event_type,
                    payload,
                )
            except Exception:
                pass

    def _call_expert(self, task: str) -> RescueAction:
        """调用专家 LLM 获取救援动作。"""
        health_state = self.health.get_state() if self.health else None
        health_dict = health_state.to_dict() if health_state else {}

        tools_description = ""
        if hasattr(self.react, "tools") and self.react.tools:
            tools_description = self.react.tools.schema_for_llm()

        warm_context = ""
        if self.distiller and hasattr(self.distiller, "knowledge_base"):
            kb = self.distiller.knowledge_base
            if kb:
                try:
                    matches = kb.search(task, top_k=3)
                    warm_context = "\n".join(
                        f"- {m.get('rule', '')}" for m in matches
                    )
                except Exception:
                    pass

        return self.expert.rescue(
            task=task,
            trajectory=self.react.trajectory,
            health_state=health_dict,
            tools_description=tools_description,
            warm_context=warm_context,
        )

    def _apply_rescue(self, rescue: RescueAction) -> None:
        """根据专家返回的 mode 执行救援。"""
        print(f"[RescueOrchestrator] 专家救援 mode={rescue.mode}")

        if rescue.mode == "thought_injection":
            if not rescue.thought:
                raise ValueError("thought_injection 模式需要提供 thought")
            self.react.inject_expert_thought(rescue.thought)

        elif rescue.mode == "direct_action":
            if not rescue.action:
                raise ValueError("direct_action 模式需要提供 action")
            observation = self.react.inject_expert_action(rescue.action)
            self.react.trajectory.append({
                "iteration": len(self.react.trajectory),
                "timestamp": time.time(),
                "source": "expert",
                "thought": rescue.thought or "",
                "action": rescue.action,
                "observation": observation,
            })

        elif rescue.mode == "loop_takeover":
            steps = max(1, min(rescue.takeover_steps or 3, 5))
            self.react.takeover(self.expert.llm, steps)

        else:
            raise ValueError(f"未知的救援 mode：{rescue.mode}")
