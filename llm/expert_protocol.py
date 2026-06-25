"""
llm/expert_protocol.py — 专家救援协议

定义专家救援的通信格式：
- RescueAction: 专家返回的救援动作
- RescueContext: 构建专家 prompt 所需的上下文
- EXPERT_RESCUE_PROMPT: 专家 prompt 模板
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RescueAction:
    """专家返回的救援动作。"""

    mode: str  # "thought_injection" | "direct_action" | "loop_takeover"
    thought: Optional[str] = None
    action: Optional[Dict[str, Any]] = None
    takeover_steps: int = 0
    skill_seed: Optional[Dict[str, str]] = None

    def __post_init__(self):
        if self.mode not in ("thought_injection", "direct_action", "loop_takeover"):
            raise ValueError(f"Unknown rescue mode: {self.mode}")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RescueAction":
        """从 LLM 返回的 JSON dict 解析 RescueAction。"""
        if not isinstance(data, dict):
            raise ValueError(f"RescueAction must be a dict, got {type(data)}")

        mode = data.get("mode", "thought_injection")
        return cls(
            mode=mode,
            thought=data.get("thought"),
            action=data.get("action"),
            takeover_steps=int(data.get("takeover_steps", 0) or 0),
            skill_seed=data.get("skill_seed"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "thought": self.thought,
            "action": self.action,
            "takeover_steps": self.takeover_steps,
            "skill_seed": self.skill_seed,
        }


@dataclass
class RescueContext:
    """构建专家 prompt 的上下文。"""

    task: str
    truncated_trajectory: str
    error_summary: str
    tools_description: str
    warm_context: str
    iteration_count: int
    consecutive_errors: int
    health_status: str

    def to_prompt_kwargs(self) -> Dict[str, str]:
        return {
            "task": self.task,
            "truncated_trajectory": self.truncated_trajectory,
            "error_summary": self.error_summary,
            "tools_description": self.tools_description,
            "warm_context": self.warm_context,
            "iteration_count": str(self.iteration_count),
            "consecutive_errors": str(self.consecutive_errors),
            "health_status": self.health_status,
        }

    @classmethod
    def build(
        cls,
        task: str,
        trajectory: List[Dict[str, Any]],
        health_state: Optional[Dict[str, Any]],
        tools_description: str,
        warm_context: str,
        max_step_text_len: int = 300,
    ) -> "RescueContext":
        """从完整轨迹构建截断的专家上下文。"""
        iteration_count = len(trajectory)
        consecutive_errors = cls._count_consecutive_errors(trajectory)
        health_status = health_state.get("status", "unknown") if health_state else "unknown"

        truncated = cls._truncate_trajectory(trajectory, max_step_text_len)
        error_summary = cls._build_error_summary(trajectory)

        return cls(
            task=task,
            truncated_trajectory=truncated,
            error_summary=error_summary,
            tools_description=tools_description,
            warm_context=warm_context,
            iteration_count=iteration_count,
            consecutive_errors=consecutive_errors,
            health_status=health_status,
        )

    @staticmethod
    def _count_consecutive_errors(trajectory: List[Dict[str, Any]]) -> int:
        count = 0
        for step in reversed(trajectory):
            observation = step.get("observation", {}) or {}
            if not observation.get("ok", True):
                count += 1
            else:
                break
        return count

    @staticmethod
    def _truncate_trajectory(trajectory: List[Dict[str, Any]], max_len: int) -> str:
        """保留前 2 步 + 后 3 步，截断长文本。"""
        if not trajectory:
            return "（无）"

        def fmt_step(step: Dict[str, Any], idx: int) -> str:
            source = step.get("source", "local")
            thought = RescueContext._truncate_text(step.get("thought", ""), max_len)
            action = step.get("action", {})
            observation = step.get("observation", {}) or {}
            ok = observation.get("ok", True)
            obs_text = RescueContext._truncate_text(str(observation.get("output") or observation.get("error") or ""), max_len)
            lines = [
                f"步骤 {idx} [来源:{source}]",
                f"  思考: {thought}",
                f"  动作: {action}",
                f"  观察: {'[OK]' if ok else '[FAIL]'} {obs_text}",
            ]
            return "\n".join(lines)

        total = len(trajectory)
        if total <= 5:
            selected = list(range(total))
        else:
            selected = [0, 1] + list(range(total - 3, total))

        parts = []
        for i, idx in enumerate(selected):
            if i > 0 and idx - selected[i - 1] > 1:
                parts.append("  ...\n")
            parts.append(fmt_step(trajectory[idx], idx + 1))

        return "\n\n".join(parts)

    @staticmethod
    def _build_error_summary(trajectory: List[Dict[str, Any]]) -> str:
        errors = []
        for idx, step in enumerate(trajectory, start=1):
            observation = step.get("observation", {}) or {}
            if not observation.get("ok", True):
                action = step.get("action", {})
                tool = action.get("tool", "unknown")
                err = observation.get("error", "未知错误")
                errors.append(f"- 步骤 {idx} [{tool}]: {err}")
        return "\n".join(errors) if errors else "无"

    @staticmethod
    def _truncate_text(text: str, max_len: int) -> str:
        text = str(text).replace("\n", " ")
        if len(text) <= max_len:
            return text
        return text[:max_len] + "...[截断]"


EXPERT_RESCUE_PROMPT = """你是一位高级专家 AI，正在协助一个本地轻量级模型完成 TapTap Maker 游戏开发任务。

本地模型已经尝试了若干步骤但未能成功，请你提供救援方案。

【任务】
{task}

【本地模型已尝试的步骤】
{truncated_trajectory}

【失败摘要】
{error_summary}

【可用工具】
{tools_description}

【本地模型已知的经验】
{warm_context}

【当前状态】
- 迭代次数：{iteration_count}
- 连续错误：{consecutive_errors}
- 健康状态：{health_status}

请输出严格的 JSON，格式如下：

{{
  "mode": "thought_injection" | "direct_action" | "loop_takeover",
  "thought": "给本地模型的下一步思考建议（mode=thought_injection 时必填）",
  "action": {{"tool": "工具名", "params": {{...}}}},
  "takeover_steps": 3,
  "skill_seed": {{
    "domain": "任务领域",
    "rule": "为什么本地模型失败、正确解决的方法论",
    "context": "适用场景"
  }}
}}

说明：
- thought_injection：只给出思考提示，本地模型仍自己 choose_action。仅在本地模型只需一点提示即可继续时使用。
- direct_action：直接给出 tool + params，orchestrator 会立即执行。适用于只需一次动作就能扭转局面的情况。
- loop_takeover：专家 LLM 直接接管 think/choose_action 若干轮（takeover_steps）。当任务需要创建/修改文件、读取多个参考文件或连续执行多步时，**优先使用 loop_takeover**，并设置 takeover_steps 为 3~5。

重要原则：
1. 不要只给建议，要实际采取行动推进任务。
2. 如果需要写文件或修改文件，请在 loop_takeover 中一次性完成关键步骤。
3. 每次返回的 action 必须是可用工具列表中存在的 tool。
4. skill_seed 可选但强烈建议填写，用于后续沉淀为技能。
"""
