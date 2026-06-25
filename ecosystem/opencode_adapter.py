"""
ecosystem/opencode_adapter.py — OpenCode / OpenClaw 适配器

OpenCode 是一个终端优先的 coding agent，兼容 OpenClaw 技能格式。
TTMEvolve 可以读取 opencode/openclaw 技能并将其转换为 CanonicalSkill。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

OPENCLAW_CONFIG = "openclaw.json"
OPENCLAW_SKILLS_DIR = ".openclaw"
OPENCLAW_SKILL_MARKER = "# opencode-skill"


def load_opencode_skill(path: Path) -> Optional[Dict[str, Any]]:
    """从 opencode/openclaw 技能文件加载，返回 CanonicalSkill 格式。"""
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None

    name = path.stem
    lines = text.splitlines()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") and not stripped.startswith("# "):
            name = stripped.lstrip("#").strip()
            break

    return {
        "id": path.stem,
        "name": name,
        "version": "v1",
        "description": _extract_description(text),
        "parameters": {"type": "object", "properties": {}},
        "examples": [],
        "source": "opencode",
        "author": "opencode",
        "license": "unknown",
        "tags": ["opencode", "openclaw"],
        "body": text[:2000],
        "code": text[:5000],
        "_path": str(path),
    }


def _extract_description(text: str) -> str:
    """从技能文件提取第一段描述。"""
    lines = text.splitlines()
    parts: List[str] = []
    for line in lines:
        stripped = line.strip()
        if OPENCLAW_SKILL_MARKER in stripped:
            continue
        if stripped and not stripped.startswith("#"):
            parts.append(stripped)
        if len(parts) >= 3:
            break
    return " ".join(parts)[:300]


def find_opencode_skills(root: Path) -> List[Path]:
    """扫描项目中的所有 opencode/openclaw 技能文件。"""
    candidates: List[Path] = []
    patterns: List[str] = [
        str(root / OPENCLAW_SKILLS_DIR / "**" / "*.md"),
        str(root / OPENCLAW_SKILLS_DIR / "**" / "*.lua"),
        str(root / OPENCLAW_SKILLS_DIR / "**" / "*.py"),
        str(root / "skills" / "**" / "*.md"),
    ]
    for pattern in patterns:
        try:
            parent_str = pattern.rsplit("/", 1)[0]
            glob_str = pattern.rsplit("/", 1)[-1]
            for p in Path(parent_str).glob(glob_str):
                if p.is_file():
                    candidates.append(p)
        except Exception:
            pass
    return candidates


def load_opencode_config(root: Path) -> Dict[str, Any]:
    """加载 opencode/openclaw 配置文件。"""
    candidates = [
        root / OPENCLAW_CONFIG,
        root / ".openclaw" / OPENCLAW_CONFIG,
        root / "openclaw.json",
    ]
    for path in candidates:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {}


def export_to_opencode(skill: Dict[str, Any], target_dir: Path) -> bool:
    """将 CanonicalSkill 导出为 opencode/openclaw 技能文件。"""
    skill_id = skill.get("id", "unknown")
    safe_name = re.sub(r"[^\w\-]+", "_", skill_id).strip("_")
    out_dir = target_dir / OPENCLAW_SKILLS_DIR / safe_name
    out_dir.mkdir(parents=True, exist_ok=True)
    skill_file = out_dir / "skill.md"
    body = skill.get("body", "") or skill.get("description", "")
    lines = [
        OPENCLAW_SKILL_MARKER,
        "# " + skill.get("name", skill_id),
        "",
        body,
    ]
    try:
        skill_file.write_text("\n".join(lines), encoding="utf-8")
        return True
    except Exception:
        return False
