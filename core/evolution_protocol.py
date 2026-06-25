"""
core/evolution_protocol.py — 自进化协议层（SEPL）

所有自我修改必须走：
观察 -> 归因 -> 提出修改 -> 沙箱验证 -> 灰度部署 -> 监控 -> 回滚
"""

from __future__ import annotations
import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.resource_registry import ResourceRegistry
from core.event_log import EventLog, Event


@dataclass
class ChangeProposal:
    """修改提案。"""

    proposal_id: str
    resource_id: str
    resource_type: str
    reason: str
    diff: str          # 统一 diff 或新内容
    content: str       # 修改后的完整内容
    author: str = "agent"
    created_at: float = field(default_factory=time.time)
    status: str = "pending"  # pending | validated | deployed | rejected | rolled_back
    validation_result: Optional[Dict[str, Any]] = None
    rollout_ratio: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "resource_id": self.resource_id,
            "resource_type": self.resource_type,
            "reason": self.reason,
            "diff": self.diff,
            "content": self.content,
            "author": self.author,
            "created_at": self.created_at,
            "status": self.status,
            "validation_result": self.validation_result,
            "rollout_ratio": self.rollout_ratio,
        }


class EvolutionProtocol:
    """自进化协议引擎。"""

    HIGH_RISK_TYPES = {"agent_code", "config_profile"}

    def __init__(
        self,
        registry: ResourceRegistry,
        event_log: EventLog,
        storage_path: Path,
        validator: Optional[Callable[[ChangeProposal], Dict[str, Any]]] = None,
        human_confirm_callback: Optional[Callable[[str], bool]] = None,
    ):
        self.registry = registry
        self.event_log = event_log
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._proposals_path = self.storage_path / "proposals.jsonl"
        self._validator = validator or self._default_validator
        self._human_confirm_callback = human_confirm_callback
        self._proposals: Dict[str, ChangeProposal] = {}
        self._load()

    def propose_change(
        self,
        resource_id: str,
        resource_type: str,
        content: str,
        reason: str,
        diff: str = "",
        author: str = "agent",
    ) -> ChangeProposal:
        proposal = ChangeProposal(
            proposal_id=str(uuid.uuid4())[:8],
            resource_id=resource_id,
            resource_type=resource_type,
            reason=reason,
            diff=diff,
            content=content,
            author=author,
        )
        self._proposals[proposal.proposal_id] = proposal
        self._save(proposal)
        self.event_log.append(Event.create(
            event_type="change_proposed",
            session_id="evolution",
            source="evolution_protocol",
            payload=proposal.to_dict(),
        ))
        return proposal

    def validate(self, proposal_id: str) -> ChangeProposal:
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            raise ValueError(f"提案不存在：{proposal_id}")

        result = self._validator(proposal)
        proposal.validation_result = result
        proposal.status = "validated" if result.get("ok") else "rejected"
        self._save(proposal)

        self.event_log.append(Event.create(
            event_type="change_validated" if result.get("ok") else "change_rejected",
            session_id="evolution",
            source="evolution_protocol",
            payload={"proposal_id": proposal_id, "result": result},
        ))
        return proposal

    def deploy(
        self,
        proposal_id: str,
        rollout_ratio: float = 1.0,
    ) -> ChangeProposal:
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            raise ValueError(f"提案不存在：{proposal_id}")

        if proposal.status != "validated":
            # 自动先验证
            self.validate(proposal_id)

        if proposal.status == "rejected":
            return proposal

        # 高风险资源需要人类确认
        if proposal.resource_type in self.HIGH_RISK_TYPES:
            if not self._confirm(f"高风险修改：{proposal.resource_type} {proposal.resource_id}\n理由：{proposal.reason}\n是否部署？"):
                proposal.status = "rejected"
                proposal.validation_result = {"ok": False, "reason": "人类未确认高风险修改"}
                self._save(proposal)
                return proposal

        self.registry.register(
            resource_id=proposal.resource_id,
            resource_type=proposal.resource_type,
            content=proposal.content,
            source=f"evolution:{proposal.proposal_id}",
            metadata={
                "proposal_id": proposal.proposal_id,
                "reason": proposal.reason,
                "rollout_ratio": rollout_ratio,
            },
        )
        proposal.status = "deployed"
        proposal.rollout_ratio = rollout_ratio
        self._save(proposal)

        self.event_log.append(Event.create(
            event_type="change_deployed",
            session_id="evolution",
            source="evolution_protocol",
            payload=proposal.to_dict(),
        ))
        return proposal

    def rollback(self, resource_id: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        resource = self.registry.rollback(resource_id, version)
        if not resource:
            return None
        self.event_log.append(Event.create(
            event_type="change_rolled_back",
            session_id="evolution",
            source="evolution_protocol",
            payload={"resource_id": resource_id, "to_version": resource.version},
        ))
        return {"resource_id": resource_id, "version": resource.version}

    def _confirm(self, message: str) -> bool:
        if not self._human_confirm_callback:
            # 没有回调时默认拒绝高风险修改
            return False
        return self._human_confirm_callback(message)

    def _default_validator(self, proposal: ChangeProposal) -> Dict[str, Any]:
        """默认验证器：检查内容非空、长度合理、不包含明显危险模式。"""
        if not proposal.content:
            return {"ok": False, "reason": "内容为空"}
        if len(proposal.content) > 1_000_000:
            return {"ok": False, "reason": "内容超过 1MB"}

        dangerous = ("__import__", "eval(", "exec(", "subprocess.call", "os.system")
        lower = proposal.content.lower()
        for d in dangerous:
            if d in lower:
                return {"ok": False, "reason": f"内容包含危险模式：{d}"}

        return {"ok": True, "reason": "基础验证通过"}

    def _save(self, proposal: ChangeProposal) -> None:
        with self._proposals_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(proposal.to_dict(), ensure_ascii=False) + "\n")

    def _load(self) -> None:
        if not self._proposals_path.exists():
            return
        for line in self._proposals_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                proposal = ChangeProposal(**data)
                self._proposals[proposal.proposal_id] = proposal
            except Exception:
                continue
