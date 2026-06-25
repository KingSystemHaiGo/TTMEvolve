"""
ecosystem/codex_adapter.py — Codex 兼容适配器

Codex uses:
- AGENTS.md for project conventions
- .codex/config.toml / .codex/instructions.md for instructions
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List


CODEX_INSTRUCTION_FILES = [
    "AGENTS.md",
    ".codex/instructions.md",
    ".codex/AGENTS.md",
]


def load_codex_context(project_root: Path) -> str:
    """加载 Codex 风格的项目上下文。"""
    parts = []
    for filename in CODEX_INSTRUCTION_FILES:
        path = project_root / filename
        if path.exists():
            parts.append(f"# {path.name}\n\n{path.read_text(encoding='utf-8')}")
    return "\n\n".join(parts)


def load_codex_profile(project_root: Path) -> Dict[str, Any]:
    """简易解析 .codex/config.toml 中的 profile。"""
    config_path = project_root / ".codex" / "config.toml"
    if not config_path.exists():
        return {}
    text = config_path.read_text(encoding="utf-8")
    profile: Dict[str, Any] = {}
    for line in text.splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key in ("model", "approval_policy", "sandbox_mode"):
                profile[key] = value
    return profile


def export_to_codex_agents(conventions: List[str]) -> str:
    """把 conventions 导出为 AGENTS.md 片段。"""
    lines = ["# Agent Conventions", ""]
    for c in conventions:
        lines.append(f"- {c}")
    return "\n".join(lines)
