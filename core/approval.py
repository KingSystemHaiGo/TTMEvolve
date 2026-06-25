"""
core/approval.py — 审批策略引擎

支持三种策略：
- on-request：高风险动作询问人类
- never：自动通过（CI/批量模式）
- always：每个动作都询问

风险等级由工具名决定，可通过配置覆盖。
"""

from __future__ import annotations
from enum import Enum
from typing import Any, Callable, Dict, Optional


class ApprovalPolicy(str, Enum):
    ON_REQUEST = "on-request"
    NEVER = "never"
    ALWAYS = "always"


class ApprovalEngine:
    """根据策略和动作风险决定是否触发人类确认。"""

    DEFAULT_RISK_LEVELS = {
        "read_file": "low",
        "list_directory": "low",
        "search_files": "low",
        "modify_file": "high",
        "delete_file": "high",
        "execute_shell": "high",
        "git_commit": "medium",
        "install_dependency": "high",
    }

    def __init__(
        self,
        policy: ApprovalPolicy,
        human_confirm_callback: Optional[Callable[[str], bool]] = None,
        risk_levels: Optional[Dict[str, str]] = None,
    ):
        self.policy = ApprovalPolicy(policy)
        self.human_confirm_callback = human_confirm_callback
        self.risk_levels = risk_levels or dict(self.DEFAULT_RISK_LEVELS)

    def check(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """返回 {"allowed": bool, "reason": str}。"""
        if self.policy == ApprovalPolicy.NEVER:
            return {"allowed": True, "reason": "policy=never，自动通过"}

        risk = self.risk_levels.get(tool_name, "medium")

        if self.policy == ApprovalPolicy.ALWAYS:
            return self._ask(f"策略要求始终确认。执行 {tool_name}，参数：{params}。是否允许？")

        # on-request：仅高风险动作询问
        if risk == "high":
            return self._ask(f"Agent 请求执行高风险工具 {tool_name}，参数：{params}。是否允许？")

        if risk == "medium" and self.human_confirm_callback:
            # medium 风险默认自动通过，但 future 可配置
            pass

        return {"allowed": True, "reason": "低风险动作，无需确认"}

    def _ask(self, message: str) -> Dict[str, Any]:
        if not self.human_confirm_callback:
            return {"allowed": False, "reason": "需要人类确认，但未提供确认回调"}
        if self.human_confirm_callback(message):
            return {"allowed": True, "reason": "人类确认通过"}
        return {"allowed": False, "reason": "人类未确认"}
