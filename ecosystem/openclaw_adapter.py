"""
ecosystem/openclaw_adapter.py — OpenClaw 兼容适配器

OpenClaw config: openclaw.json with mcp.servers.
OpenClaw skill: SKILL.md with YAML frontmatter (similar to Hermes).
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ecosystem.skill_schema import CanonicalSkill
from ecosystem.hermes_adapter import parse_frontmatter


OPENCLAW_CONFIG_PATHS = [
    Path.home() / ".openclaw" / "openclaw.json",
    Path("openclaw.json"),
]


def find_openclaw_config() -> Optional[Path]:
    for p in OPENCLAW_CONFIG_PATHS:
        if p.exists():
            return p
    return None


def load_openclaw_skill(path: Path) -> Optional[CanonicalSkill]:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)
    if not fm:
        return None
    name = fm.get("name", path.parent.name)
    return CanonicalSkill(
        id=name,
        name=name,
        version=str(fm.get("version", "1.0")),
        description=fm.get("description", ""),
        parameters={"type": "object", "properties": {}},
        examples=[],
        source="openclaw",
        author=fm.get("author", ""),
        license=fm.get("license", ""),
        tags=fm.get("tags", []),
        body=body,
    )


def discover_openclaw_skills(root: Optional[Path] = None) -> List[CanonicalSkill]:
    roots = []
    if root:
        roots.append(root)
    roots.extend([
        Path.home() / ".openclaw" / "skills",
        Path(".openclaw") / "skills",
    ])
    skills = []
    for r in roots:
        if not r.exists():
            continue
        for skill_file in r.rglob("SKILL.md"):
            skill = load_openclaw_skill(skill_file)
            if skill:
                skills.append(skill)
    return skills


def load_openclaw_mcp_servers(config_path: Optional[Path] = None) -> Dict[str, Any]:
    path = config_path or find_openclaw_config()
    if not path or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("mcp", {}).get("servers", {})
    except Exception:
        return {}


def export_to_openclaw(skill: CanonicalSkill) -> str:
    """导出为 OpenClaw SKILL.md 字符串。"""
    lines = ["---"]
    lines.append(f"name: {skill.id}")
    lines.append(f"version: {skill.version}")
    lines.append(f"description: {skill.description}")
    if skill.author:
        lines.append(f"author: {skill.author}")
    if skill.license:
        lines.append(f"license: {skill.license}")
    if skill.tags:
        lines.append(f"tags: [{', '.join(skill.tags)}]")
    lines.append("---")
    lines.append("")
    lines.append(skill.body or skill.description)
    return "\n".join(lines)
