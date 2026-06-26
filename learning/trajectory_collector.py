"""
learning/trajectory_collector.py — 轨迹收集器

把 Agent 层的每次 ReAct 循环记录为结构化 JSON Lines。
这是学习转化层的原材料。
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List
import json


class TrajectoryCollector:
    """收集并持久化 Agent 执行轨迹。"""

    def __init__(self, storage_path: Path):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def append(self, session_id: str, trajectory: List[Dict[str, Any]]) -> None:
        self.storage_path.mkdir(parents=True, exist_ok=True)
        file_path = self.storage_path / f"{session_id}.jsonl"
        with file_path.open("a", encoding="utf-8") as f:
            for step in trajectory:
                f.write(json.dumps(step, ensure_ascii=False) + "\n")

    def read(self, session_id: str) -> List[Dict[str, Any]]:
        file_path = self.storage_path / f"{session_id}.jsonl"
        if not file_path.exists():
            return []
        steps = []
        with file_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    steps.append(json.loads(line))
                except Exception:
                    continue
        return steps

    def list_sessions(self) -> List[str]:
        return [p.stem for p in self.storage_path.glob("*.jsonl")]
