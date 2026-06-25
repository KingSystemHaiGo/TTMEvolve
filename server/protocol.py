"""
server/protocol.py — App Server 协议定义

CLI / TUI / GUI 统一通过这组数据结构交互。
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SessionRequest:
    task: str
    profile: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    session_id: Optional[str] = None


@dataclass
class ToolCall:
    name: str
    arguments: Dict[str, Any]
    id: str = ""


@dataclass
class ApprovalRequest:
    action_id: str
    tool_name: str
    params: Dict[str, Any]
    reason: str = ""


@dataclass
class ApprovalResponse:
    """GUI / CLI 对审批请求的答复，POST /sessions/{id}/approve 请求体。"""

    action_id: str
    allowed: bool
    reason: str = ""


@dataclass
class TurnEvent:
    """Agent 循环中的单个事件，SSE 流输出。"""

    # thought | action | tool_call | observation | output | error |
    # approval_request | approval_response | status
    type: str
    session_id: str
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "session_id": self.session_id,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TurnEvent":
        return cls(
            type=data.get("type", "unknown"),
            session_id=data.get("session_id", ""),
            payload=data.get("payload", {}),
        )
