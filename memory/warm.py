"""
memory/warm.py — 温记忆

按需加载：技能、项目规则、相关文档、会话摘要。
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List


class WarmMemory:
    """温记忆：按需加载的上下文。"""

    def __init__(self, project_root: Path, skills_dir: Path):
        self.project_root = Path(project_root)
        self.skills_dir = Path(skills_dir)
        self._cache: Dict[str, Any] = {}

    def load_skill(self, skill_name: str) -> str:
        if skill_name in self._cache:
            return self._cache[skill_name]
        path = self.skills_dir / f"{skill_name}.md"
        if path.exists():
            content = path.read_text(encoding="utf-8")
        else:
            content = ""
        self._cache[skill_name] = content
        return content

    def load_doc(self, relative_path: str) -> str:
        key = f"doc:{relative_path}"
        if key in self._cache:
            return self._cache[key]
        path = self.project_root / relative_path
        if path.exists():
            content = path.read_text(encoding="utf-8")
        else:
            content = ""
        self._cache[key] = content
        return content

    def invalidate(self, key: str) -> None:
        self._cache.pop(key, None)
