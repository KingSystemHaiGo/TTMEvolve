"""
ecosystem/claude_code_adapter.py — Claude Code 兼容适配器

Claude Code uses:
- CLAUDE.md / .claude/CLAUDE.md as project context
- .claude/skills/{skill}/SKILL.md as skills
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional

from ecosystem.skill_schema import CanonicalSkill
from ecosystem.hermes_adapter import parse_frontmatter


def load_claude_code_skill(path: Path) -> Optional[CanonicalSkill]:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)
    name = path.parent.name
    if fm:
        name = fm.get("name", name)
    return CanonicalSkill(
        id=name,
        name=name,
        version=str(fm.get("version", "1.0") if fm else "1.0"),
        description=fm.get("description", "") if fm else "",
        parameters={"type": "object", "properties": {}},
        examples=[],
        source="claude_code",
        author=fm.get("author", "") if fm else "",
        license=fm.get("license", "") if fm else "",
        tags=fm.get("tags", []) if fm else [],
        body=body,
    )


def discover_claude_code_skills(root: Optional[Path] = None) -> List[CanonicalSkill]:
    roots = []
    if root:
        roots.append(root)
    roots.extend([
        Path.home() / ".claude" / "skills",
        Path(".claude") / "skills",
    ])
    skills = []
    for r in roots:
        if not r.exists():
            continue
        for skill_dir in r.iterdir():
            if skill_dir.is_dir():
                skill_file = skill_dir / "SKILL.md"
                if skill_file.exists():
                    skill = load_claude_code_skill(skill_file)
                    if skill:
                        skills.append(skill)
    return skills


def load_claude_code_context(project_root: Path) -> str:
    """加载项目中的 CLAUDE.md / .claude/CLAUDE.md。"""
    candidates = [
        project_root / "CLAUDE.md",
        project_root / ".claude" / "CLAUDE.md",
        project_root / ".claude" / "claude.md",
    ]
    for path in candidates:
        if path.exists():
            return path.read_text(encoding="utf-8")
    return ""


def export_to_claude_code(skill: CanonicalSkill) -> str:
    """导出为 Claude Code SKILL.md 字符串。"""
    lines = ["---"]
    lines.append(f"name: {skill.id}")
    lines.append(f"version: {skill.version}")
    lines.append(f"description: {skill.description}")
    if skill.author:
        lines.append(f"author: {skill.author}")
    if skill.tags:
        lines.append(f"tags: [{', '.join(skill.tags)}]")
    lines.append("---")
    lines.append("")
    lines.append(skill.body or skill.description)
    return "\n".join(lines)
