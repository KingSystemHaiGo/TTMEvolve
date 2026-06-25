"""
ecosystem/skill_schema.py — Canonical Skill 格式

TTMEvolve 的内部统一格式，可无损导出为 Hermes / OpenClaw / Claude Code / Codex。
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CanonicalSkill:
    id: str
    name: str
    version: str
    description: str
    parameters: Dict[str, Any]
    examples: List[Dict[str, Any]] = field(default_factory=list)
    source: str = "ttmevolve"
    author: str = ""
    license: str = ""
    tags: List[str] = field(default_factory=list)
    body: str = ""  # markdown body / usage instructions
    code: str = ""  # Python implementation (optional)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "parameters": self.parameters,
            "examples": self.examples,
            "source": self.source,
            "author": self.author,
            "license": self.license,
            "tags": self.tags,
            "body": self.body,
            "code": self.code,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CanonicalSkill":
        return cls(**data)


# Minimal JSON schema for skill.json
CANONICAL_SKILL_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["id", "name", "version", "description", "parameters"],
    "properties": {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "version": {"type": "string"},
        "description": {"type": "string"},
        "parameters": {"type": "object"},
        "examples": {"type": "array"},
        "source": {"type": "string"},
        "author": {"type": "string"},
        "license": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "body": {"type": "string"},
        "code": {"type": "string"},
    },
}
