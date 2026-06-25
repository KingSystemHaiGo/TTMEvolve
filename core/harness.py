"""
core/harness.py — 向后兼容 re-export

Harness 已移动到 `cli.harness`，请优先从那里导入。
"""

from __future__ import annotations
from cli.harness import AgentSession, Harness  # noqa: F401

__all__ = ["AgentSession", "Harness"]
