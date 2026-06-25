"""
core/event_log.py — 不可变事件日志

所有跨层通信、状态变更、动作执行、修复决策都写入事件日志。
Agent 层无权修改，只能由核心运转层追加。
"""

from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
import json
import threading


@dataclass
class Event:
    """单条事件记录。"""
    event_type: str          # action_proposed / action_executed / action_rejected /
                             # state_changed / health_check / repair_started /
                             # repair_finished / rollback / knowledge_written
    timestamp: str
    session_id: str
    source: str              # agent / runtime / learning / user
    payload: Dict[str, Any]
    event_id: str

    @classmethod
    def create(
        cls,
        event_type: str,
        session_id: str,
        source: str,
        payload: Dict[str, Any],
    ) -> "Event":
        now = datetime.now(timezone.utc).isoformat()
        eid = f"{now}-{session_id}-{event_type}"
        return cls(
            event_type=event_type,
            timestamp=now,
            session_id=session_id,
            source=source,
            payload=payload,
            event_id=eid,
        )


class EventLog:
    """追加-only 事件日志。线程安全。"""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def append(self, event: Event) -> None:
        with self._lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")

    def read_since(self, since_iso: Optional[str] = None, limit: int = 1000) -> list[Event]:
        events: list[Event] = []
        if not self.path.exists():
            return events
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if since_iso and data.get("timestamp", "") <= since_iso:
                        continue
                    events.append(Event(**data))
                except Exception:
                    continue
        return events[-limit:]

    def latest_of_type(self, event_type: str) -> Optional[Event]:
        events = self.read_since(limit=10000)
        for e in reversed(events):
            if e.event_type == event_type:
                return e
        return None
