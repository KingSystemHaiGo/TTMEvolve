"""
ecosystem/hermes_adapter.py — Hermes Agent 兼容适配器

Hermes skill format: SKILL.md with YAML frontmatter.
"""

from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ecosystem.skill_schema import CanonicalSkill


HERMES_SKILL_DIR = Path.home() / ".hermes" / "skills"


def parse_frontmatter(text: str) -> tuple[Dict[str, Any], str]:
    """解析 YAML frontmatter，返回 (frontmatter_dict, body)。"""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm_text = parts[1].strip()
    body = parts[2].strip()

    # 简易 YAML 解析：只支持 key: value 单层
    data: Dict[str, Any] = {}
    current_key: Optional[str] = None
    for line in fm_text.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value.startswith("[") and value.endswith("]"):
                value = [v.strip().strip('"').strip("'") for v in value[1:-1].split(",") if v.strip()]
            data[key] = value
            current_key = key
        elif current_key and line.strip().startswith("-"):
            item = line.strip()[1:].strip()
            if isinstance(data.get(current_key), list):
                data[current_key].append(item)
            else:
                data[current_key] = [item]
    return data, body


def load_hermes_skill(path: Path) -> Optional[CanonicalSkill]:
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
        source="hermes",
        author=fm.get("author", ""),
        license=fm.get("license", ""),
        tags=fm.get("tags", []),
        body=body,
    )


def discover_hermes_skills(root: Optional[Path] = None) -> List[CanonicalSkill]:
    root = root or HERMES_SKILL_DIR
    skills = []
    if not root.exists():
        return skills
    for skill_file in root.rglob("SKILL.md"):
        skill = load_hermes_skill(skill_file)
        if skill:
            skills.append(skill)
    return skills


def export_to_hermes(skill: CanonicalSkill) -> str:
    """导出为 Hermes SKILL.md 字符串。"""
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


def load_hermes_mcp_servers(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """读取 Hermes config.yaml 中的 mcp_servers。"""
    path = config_path or (Path.home() / ".hermes" / "config.yaml")
    if not path.exists():
        return {}
    # 简易解析 mcp_servers 段
    text = path.read_text(encoding="utf-8")
    servers: Dict[str, Any] = {}
    in_mcp = False
    current = None
    for line in text.splitlines():
        stripped = line.rstrip()
        if stripped.startswith("mcp_servers:"):
            in_mcp = True
            continue
        if in_mcp:
            if stripped and not stripped.startswith(" ") and not stripped.startswith("\t"):
                break
            if stripped.strip().endswith(":") and not stripped.startswith("  -"):
                current = stripped.strip().rstrip(":")
                servers[current] = {}
            elif current and ":" in stripped:
                key, value = stripped.split(":", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key in ("command", "cwd"):
                    servers[current][key] = value
                elif key == "args":
                    servers[current]["args"] = []
                elif key.startswith("-") and "args" in servers[current]:
                    servers[current]["args"].append(value)
    return servers
