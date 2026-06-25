"""
core/project_context.py — 项目上下文发现

扫描项目目录，聚合来自 Codex / Claude Code / OpenClaw / Hermes 的上下文文件。
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List

from ecosystem.claude_code_adapter import load_claude_code_context, discover_claude_code_skills
from ecosystem.codex_adapter import load_codex_context, load_codex_profile
from ecosystem.openclaw_adapter import discover_openclaw_skills
from ecosystem.hermes_adapter import discover_hermes_skills


class ProjectContext:
    """发现并聚合多生态项目上下文。"""

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)

    def load(self) -> Dict[str, Any]:
        context: Dict[str, Any] = {
            "project_root": str(self.project_root),
            "conventions": [],
            "skills": [],
            "profile": {},
        }

        # 项目级上下文
        context["conventions"].append({
            "source": "codex/AGENTS.md",
            "content": load_codex_context(self.project_root),
        })
        context["conventions"].append({
            "source": "claude_code/CLAUDE.md",
            "content": load_claude_code_context(self.project_root),
        })

        # 合并 Codex profile
        context["profile"].update(load_codex_profile(self.project_root))

        # 技能
        for skill in discover_hermes_skills(self.project_root / ".hermes" / "skills"):
            context["skills"].append({"source": "hermes", "skill": skill.to_dict()})
        for skill in discover_openclaw_skills(self.project_root / ".openclaw" / "skills"):
            context["skills"].append({"source": "openclaw", "skill": skill.to_dict()})
        for skill in discover_claude_code_skills(self.project_root / ".claude" / "skills"):
            context["skills"].append({"source": "claude_code", "skill": skill.to_dict()})

        return context

    def build_repo_map(self) -> str:
        """构建简单的 repo map。"""
        if not self.project_root.exists():
            return ""
        lines = [f"项目根目录：{self.project_root}", "目录结构："]
        for p in sorted(self.project_root.iterdir()):
            if p.name.startswith("."):
                continue
            marker = "📁" if p.is_dir() else "📄"
            lines.append(f"  {marker} {p.name}")
        return "\n".join(lines)
